"""Credential-safe backup, verified restore and destructive deletion for Personal-IP.

The service deliberately uses the existing owner-scoped tables as its source of
truth.  It does not create a second mutable state store.  Platform credentials
and one-use OAuth state are deletion-only data: exports contain a revoked
connection shell so a restore always requires a fresh platform authorization.
One-shot paid-call scopes/events are also deletion-only, but unlike connection
shells they are omitted entirely so restore can never revive an approval,
reservation, or consumed admission.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.base import Base
from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_metrics.model import PersonalIPMetricObservationRow
from deerflow.persistence.personal_ip_paid_calls.model import (
    PersonalIPPaidCallEventRow,
    PersonalIPPaidCallScopeRow,
)
from deerflow.persistence.personal_ip_platform_connections.model import (
    PersonalIPPlatformConnectionRow,
    PersonalIPPlatformCredentialRow,
    PersonalIPPlatformOAuthStateRow,
)
from deerflow.persistence.personal_ip_platform_observations.model import PersonalIPPlatformObservationRow
from deerflow.persistence.personal_ip_publish_receipts.model import PersonalIPPublishReceiptRow
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.persistence.personal_ip_video_productions.model import (
    PersonalIPVideoProductionEventRow,
    PersonalIPVideoProductionRow,
)

BACKUP_SCHEMA_VERSION = "personal-ip-owner-backup-v1"
RESTORE_RECEIPT_VERSION = "personal-ip-owner-restore-receipt-v1"
DELETE_PREVIEW_VERSION = "personal-ip-destructive-delete-preview-v1"
DELETE_CONFIRMATION_VERSION = "personal-ip-destructive-delete-confirmation-v1"
DELETE_RECEIPT_VERSION = "personal-ip-destructive-delete-receipt-v1"
DELETE_CONFIRMATION_PHRASE = "永久删除我的全部个人IP数据"

_FORBIDDEN_EXPORT_KEYS = {
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "cookies",
    "password",
    "secret",
    "state_hash",
    "encrypted_access_token",
    "encrypted_refresh_token",
}


@dataclass(frozen=True)
class _Dataset:
    name: str
    model: type[Base]


# Restore order is dependency order; deletion uses the reverse.
_DATASETS: tuple[_Dataset, ...] = (
    _Dataset("subjects", PersonalIPSubjectRow),
    _Dataset("accounts", PersonalIPAccountRow),
    _Dataset("publish_receipts", PersonalIPPublishReceiptRow),
    _Dataset("metric_observations", PersonalIPMetricObservationRow),
    _Dataset("platform_observations", PersonalIPPlatformObservationRow),
    _Dataset("platform_connections", PersonalIPPlatformConnectionRow),
    _Dataset("video_productions", PersonalIPVideoProductionRow),
    _Dataset("video_production_events", PersonalIPVideoProductionEventRow),
)
EXPORT_DATASET_NAMES: tuple[str, ...] = tuple(item.name for item in _DATASETS)
PERSONAL_IP_EXPORT_TABLES: frozenset[str] = frozenset(item.model.__tablename__ for item in _DATASETS)
PERSONAL_IP_SECRET_TABLES: frozenset[str] = frozenset(
    {
        PersonalIPPlatformCredentialRow.__tablename__,
        PersonalIPPlatformOAuthStateRow.__tablename__,
    }
)
_DELETION_ONLY_DATASETS: tuple[_Dataset, ...] = (
    _Dataset("paid_call_scopes", PersonalIPPaidCallScopeRow),
    _Dataset("paid_call_events", PersonalIPPaidCallEventRow),
)
PERSONAL_IP_DELETION_ONLY_TABLES: frozenset[str] = frozenset(
    item.model.__tablename__ for item in _DELETION_ONLY_DATASETS
)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _assert_credential_free(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_EXPORT_KEYS:
                raise ValueError(f"credential-bearing field is not exportable: {path}.{key}")
            _assert_credential_free(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_credential_free(item, path=f"{path}[{index}]")


def _primary_key(model: type[Base], record: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(record[column.name]) for column in model.__table__.primary_key.columns)


def _safe_connection_record(record: dict[str, Any]) -> dict[str, Any]:
    """Turn authorization metadata into a credential-free reconnect shell."""

    record.update(
        {
            "status": "revoked",
            "oauth_open_id": None,
            "scopes_json": [],
            "access_expires_at": None,
            "refresh_expires_at": None,
            "last_refreshed_at": None,
            "last_error_code": "restore_reauthorization_required",
            "credential_state": "omitted_reauthorization_required",
        }
    )
    return record


def _dataset_digest(name: str, records: Sequence[Mapping[str, Any]]) -> str:
    return _digest({"name": name, "records": records})


class PersonalIPDataLifecycleService:
    """Owner-scoped lifecycle service over every Personal-IP persistence table."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        minecontext: Any | None,
    ) -> None:
        self._sf = session_factory
        self._minecontext = minecontext

    @staticmethod
    async def _lock_owner(session: AsyncSession, owner_user_id: str) -> None:
        bind = session.get_bind()
        dialect = bind.dialect.name
        if dialect == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        else:
            await session.begin()
            if dialect == "postgresql":
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"personal-ip-data-lifecycle:{owner_user_id}"},
                )

    @staticmethod
    async def _export_datasets(
        session: AsyncSession,
        owner_user_id: str,
    ) -> list[dict[str, Any]]:
        exported: list[dict[str, Any]] = []
        for dataset in _DATASETS:
            rows = (await session.execute(select(dataset.model).where(dataset.model.owner_user_id == owner_user_id))).scalars().all()
            records = [_json_value(row.to_dict()) for row in rows]
            if dataset.name == "platform_connections":
                records = [_safe_connection_record(record) for record in records]
            records.sort(key=lambda record, model=dataset.model: _primary_key(model, record))
            _assert_credential_free(records, path=f"$.datasets.{dataset.name}")
            exported.append(
                {
                    "name": dataset.name,
                    "count": len(records),
                    "digest": _dataset_digest(dataset.name, records),
                    "records": records,
                }
            )
        return exported

    @staticmethod
    async def _secret_counts(
        session: AsyncSession,
        owner_user_id: str,
    ) -> dict[str, int]:
        connection_ids = select(PersonalIPPlatformConnectionRow.id).where(PersonalIPPlatformConnectionRow.owner_user_id == owner_user_id)
        credentials = (await session.execute(select(func.count()).select_from(PersonalIPPlatformCredentialRow).where(PersonalIPPlatformCredentialRow.connection_id.in_(connection_ids)))).scalar_one()
        oauth_states = (await session.execute(select(func.count()).select_from(PersonalIPPlatformOAuthStateRow).where(PersonalIPPlatformOAuthStateRow.owner_user_id == owner_user_id))).scalar_one()
        return {
            "platform_credentials": int(credentials),
            "platform_oauth_states": int(oauth_states),
        }

    @staticmethod
    async def _deletion_only_counts(
        session: AsyncSession,
        owner_user_id: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for dataset in _DELETION_ONLY_DATASETS:
            count = (
                await session.execute(
                    select(func.count())
                    .select_from(dataset.model)
                    .where(dataset.model.owner_user_id == owner_user_id)
                )
            ).scalar_one()
            counts[dataset.name] = int(count)
        return counts

    @staticmethod
    def _data_digest(datasets: Sequence[Mapping[str, Any]]) -> str:
        return _digest([{"name": dataset["name"], "records": dataset["records"]} for dataset in datasets])

    @staticmethod
    def _manifest_digest(
        *,
        owner_user_id: str,
        exported_at: str,
        datasets: Sequence[Mapping[str, Any]],
        data_digest: str,
    ) -> str:
        return _digest(
            {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "owner_user_id": owner_user_id,
                "exported_at": exported_at,
                "dataset_digests": [{"name": item["name"], "count": item["count"], "digest": item["digest"]} for item in datasets],
                "data_digest": data_digest,
            }
        )

    async def export_backup(
        self,
        owner_user_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not owner_user_id:
            raise ValueError("owner_user_id is required")
        exported_at = _iso(now or datetime.now(UTC))
        async with self._sf() as session:
            datasets = await self._export_datasets(session, owner_user_id)
        data_digest = self._data_digest(datasets)
        manifest_digest = self._manifest_digest(
            owner_user_id=owner_user_id,
            exported_at=exported_at,
            datasets=datasets,
            data_digest=data_digest,
        )
        backup = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "owner_user_id": owner_user_id,
            "exported_at": exported_at,
            "credential_policy": {
                "credentials_included": False,
                "oauth_states_included": False,
                "paid_call_admissions_included": False,
                "platform_reauthorization_required_after_restore": True,
                "paid_call_reapproval_required_after_restore": True,
            },
            "datasets": datasets,
            "verification": {
                "algorithm": "sha256-canonical-json-v1",
                "data_digest": data_digest,
                "manifest_digest": manifest_digest,
            },
        }
        _assert_credential_free(backup)
        return backup

    @staticmethod
    def _verify_backup(owner_user_id: str, backup: Mapping[str, Any]) -> list[dict[str, Any]]:
        if backup.get("schema_version") != BACKUP_SCHEMA_VERSION:
            raise ValueError("unsupported Personal-IP backup schema version")
        if backup.get("owner_user_id") != owner_user_id:
            raise ValueError("backup owner does not match the authenticated owner")
        datasets = backup.get("datasets")
        if not isinstance(datasets, list):
            raise ValueError("backup datasets are required")
        if [item.get("name") for item in datasets if isinstance(item, Mapping)] != list(EXPORT_DATASET_NAMES):
            raise ValueError("backup dataset inventory is incomplete or out of order")
        normalized: list[dict[str, Any]] = []
        for specification, raw_dataset in zip(_DATASETS, datasets, strict=True):
            if not isinstance(raw_dataset, Mapping):
                raise ValueError("backup dataset must be an object")
            records = raw_dataset.get("records")
            if not isinstance(records, list):
                raise ValueError(f"backup dataset {specification.name} records are required")
            if raw_dataset.get("count") != len(records):
                raise ValueError(f"backup dataset {specification.name} count mismatch")
            if raw_dataset.get("digest") != _dataset_digest(specification.name, records):
                raise ValueError(f"backup dataset {specification.name} digest mismatch")
            expected_columns = {column.name for column in specification.model.__table__.columns}
            allowed_columns = set(expected_columns)
            if specification.name == "platform_connections":
                allowed_columns.add("credential_state")
            for record in records:
                if not isinstance(record, Mapping) or set(record) != allowed_columns:
                    raise ValueError(f"backup dataset {specification.name} record shape mismatch")
                if record.get("owner_user_id") != owner_user_id:
                    raise ValueError("backup contains a record for a different owner")
                if specification.name == "platform_connections" and (record.get("status") != "revoked" or record.get("credential_state") != "omitted_reauthorization_required"):
                    raise ValueError("restored platform connections must require reauthorization")
            normalized.append(dict(raw_dataset))
        _assert_credential_free(normalized)
        verification = backup.get("verification")
        if not isinstance(verification, Mapping):
            raise ValueError("backup verification receipt is required")
        data_digest = PersonalIPDataLifecycleService._data_digest(normalized)
        if verification.get("data_digest") != data_digest:
            raise ValueError("backup data digest mismatch")
        exported_at = backup.get("exported_at")
        if not isinstance(exported_at, str):
            raise ValueError("backup exported_at is required")
        manifest_digest = PersonalIPDataLifecycleService._manifest_digest(
            owner_user_id=owner_user_id,
            exported_at=exported_at,
            datasets=normalized,
            data_digest=data_digest,
        )
        if verification.get("manifest_digest") != manifest_digest:
            raise ValueError("backup manifest digest mismatch")
        return normalized

    @staticmethod
    def _restore_values(dataset: _Dataset, record: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(record)
        values.pop("credential_state", None)
        for column in dataset.model.__table__.columns:
            value = values.get(column.name)
            if value is not None and isinstance(column.type, DateTime):
                if not isinstance(value, str):
                    raise ValueError(f"backup datetime {dataset.name}.{column.name} must be an ISO string")
                values[column.name] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return values

    async def restore_backup(
        self,
        owner_user_id: str,
        backup: Mapping[str, Any],
    ) -> dict[str, Any]:
        datasets = self._verify_backup(owner_user_id, backup)
        async with self._sf() as session:
            try:
                await self._lock_owner(session, owner_user_id)
                existing = await self._export_datasets(session, owner_user_id)
                secret_counts = await self._secret_counts(session, owner_user_id)
                deletion_only_counts = await self._deletion_only_counts(session, owner_user_id)
                if (
                    any(item["count"] for item in existing)
                    or any(secret_counts.values())
                    or any(deletion_only_counts.values())
                ):
                    raise ValueError("Personal-IP restore requires an empty owner scope; delete existing data first")
                for specification, dataset in zip(_DATASETS, datasets, strict=True):
                    for record in dataset["records"]:
                        session.add(specification.model(**self._restore_values(specification, record)))
                    # These mappings intentionally do not declare ORM
                    # relationships. Flush each dependency tier explicitly so
                    # SQLAlchemy cannot reorder a child before its parent.
                    await session.flush()
                restored = await self._export_datasets(session, owner_user_id)
                restored_digest = self._data_digest(restored)
                expected_digest = str(backup["verification"]["data_digest"])
                if restored_digest != expected_digest:
                    raise ValueError("restored data digest does not match the backup")
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return {
            "schema_version": RESTORE_RECEIPT_VERSION,
            "owner_user_id": owner_user_id,
            "verified": True,
            "restored_data_digest": restored_digest,
            "restored_records": sum(item["count"] for item in datasets),
            "credentials_restored": False,
            "paid_call_admissions_restored": False,
            "platform_reauthorization_required": True,
            "paid_call_reapproval_required": True,
            "restored_at": _iso(datetime.now(UTC)),
        }

    async def preview_delete(
        self,
        owner_user_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        async with self._sf() as session:
            datasets = await self._export_datasets(session, owner_user_id)
            secret_counts = await self._secret_counts(session, owner_user_id)
            deletion_only_counts = await self._deletion_only_counts(session, owner_user_id)
        counts = {item["name"]: int(item["count"]) for item in datasets}
        counts.update(secret_counts)
        counts.update(deletion_only_counts)
        data_digest = self._data_digest(datasets)
        state_digest = _digest(
            {
                "owner_user_id": owner_user_id,
                "data_digest": data_digest,
                "record_counts": counts,
            }
        )
        return {
            "schema_version": DELETE_PREVIEW_VERSION,
            "owner_user_id": owner_user_id,
            "prepared_at": _iso(now or datetime.now(UTC)),
            "record_counts": counts,
            "total_records": sum(counts.values()),
            "state_digest": state_digest,
            "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
            "requires_backup_acknowledgement": True,
            "includes_local_context": True,
            "irreversible": True,
        }

    @staticmethod
    def _validate_delete_confirmation(
        owner_user_id: str,
        confirmation: Mapping[str, Any],
    ) -> None:
        if confirmation.get("schema_version") != DELETE_CONFIRMATION_VERSION:
            raise ValueError("invalid destructive-delete confirmation schema")
        if confirmation.get("owner_user_id") != owner_user_id:
            raise ValueError("destructive-delete confirmation owner mismatch")
        if confirmation.get("confirmation_phrase") != DELETE_CONFIRMATION_PHRASE:
            raise ValueError("exact destructive-delete confirmation phrase is required")
        if confirmation.get("backup_acknowledged") is not True:
            raise ValueError("backup acknowledgement is required")
        if confirmation.get("delete_local_context") is not True:
            raise ValueError("whole Personal-IP deletion must include local context")

    async def delete_all(
        self,
        owner_user_id: str,
        confirmation: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._validate_delete_confirmation(owner_user_id, confirmation)
        async with self._sf() as session:
            try:
                await self._lock_owner(session, owner_user_id)
                datasets = await self._export_datasets(session, owner_user_id)
                secret_counts = await self._secret_counts(session, owner_user_id)
                deletion_only_counts = await self._deletion_only_counts(session, owner_user_id)
                counts = {item["name"]: int(item["count"]) for item in datasets}
                counts.update(secret_counts)
                counts.update(deletion_only_counts)
                current_state_digest = _digest(
                    {
                        "owner_user_id": owner_user_id,
                        "data_digest": self._data_digest(datasets),
                        "record_counts": counts,
                    }
                )
                if confirmation.get("state_digest") != current_state_digest:
                    raise ValueError("Personal-IP state changed after the delete preview; prepare a fresh confirmation")
                if self._minecontext is None:
                    raise RuntimeError("MineContext lifecycle service is unavailable")
                local_receipt = await asyncio.to_thread(
                    self._minecontext.clear,
                    owner_user_id,
                    scope="all",
                )
                if not local_receipt.get("local_data_deleted"):
                    raise RuntimeError("MineContext local data deletion was not verified")

                connection_ids = select(PersonalIPPlatformConnectionRow.id).where(PersonalIPPlatformConnectionRow.owner_user_id == owner_user_id)
                await session.execute(delete(PersonalIPPlatformCredentialRow).where(PersonalIPPlatformCredentialRow.connection_id.in_(connection_ids)))
                await session.execute(delete(PersonalIPPlatformOAuthStateRow).where(PersonalIPPlatformOAuthStateRow.owner_user_id == owner_user_id))
                for dataset in reversed(_DELETION_ONLY_DATASETS):
                    await session.execute(delete(dataset.model).where(dataset.model.owner_user_id == owner_user_id))
                for dataset in reversed(_DATASETS):
                    await session.execute(delete(dataset.model).where(dataset.model.owner_user_id == owner_user_id))
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return {
            "schema_version": DELETE_RECEIPT_VERSION,
            "owner_user_id": owner_user_id,
            "deleted_records": sum(counts.values()),
            "record_counts": counts,
            "state_digest": current_state_digest,
            "local_context_deleted": True,
            "credentials_deleted": True,
            "oauth_states_deleted": True,
            "paid_call_admissions_deleted": True,
            "deleted_at": _iso(now or datetime.now(UTC)),
        }


__all__ = [
    "BACKUP_SCHEMA_VERSION",
    "DELETE_CONFIRMATION_PHRASE",
    "EXPORT_DATASET_NAMES",
    "PERSONAL_IP_DELETION_ONLY_TABLES",
    "PERSONAL_IP_EXPORT_TABLES",
    "PERSONAL_IP_SECRET_TABLES",
    "PersonalIPDataLifecycleService",
]
