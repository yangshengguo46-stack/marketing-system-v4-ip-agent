"""Immutable detailed platform observations with a hard credential boundary."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_platform_observations.model import PersonalIPPlatformObservationRow
from deerflow.utils.time import coerce_iso

PLATFORM_OBSERVATION_CONTRACT_VERSION = "personal-ip-platform-observation-v1"

_DATASETS = {
    "account_profile",
    "audience_analytics",
    "comments",
    "content_inventory",
    "content_metrics",
    "conversions",
    "dashboard",
    "platform_receipts",
    "traffic_sources",
}
_SOURCES = {"platform_api", "ui_tars", "browser", "manual"}
_STATUSES = {"observed", "partial", "unavailable"}
_FORBIDDEN_FIELD_NAMES = {
    "api_key",
    "app_secret",
    "authorization",
    "client_secret",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "csrf_token",
    "id_token",
    "passcode",
    "passwd",
    "password",
    "proxy_authorization",
    "refresh_token",
    "session_id",
    "session_token",
    "set_cookie",
    "token",
    "xsrf_token",
    "access_token",
}
_FORBIDDEN_FIELD_SUFFIXES = ("_api_key", "_cookie", "_password", "_secret", "_token")
_BEARER_VALUE = re.compile(r"^\s*bearer\s+\S+", re.IGNORECASE)
_TOKEN_QUERY_VALUE = re.compile(r"(?:access|refresh|id|session)_token\s*=", re.IGNORECASE)
_JWT_VALUE = re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$")


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _utc_datetime(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _credential_safe(value: Any, *, field: str) -> None:
    if isinstance(value, dict):
        for raw_key, child in value.items():
            key = re.sub(r"[^a-z0-9]+", "_", str(raw_key).strip().lower()).strip("_")
            if key in _FORBIDDEN_FIELD_NAMES or key.endswith(_FORBIDDEN_FIELD_SUFFIXES):
                raise ValueError(f"{field} contains forbidden credential field: {raw_key}")
            _credential_safe(child, field=f"{field}.{raw_key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _credential_safe(child, field=f"{field}[{index}]")
        return
    if isinstance(value, str):
        if _BEARER_VALUE.search(value) or _TOKEN_QUERY_VALUE.search(value) or _JWT_VALUE.fullmatch(value.strip()):
            raise ValueError(f"{field} contains a forbidden credential value")


def validate_credential_free_payload(value: Any, *, field: str = "payload") -> None:
    """Reject raw authentication material before it reaches persistence or tools."""
    _credential_safe(value, field=field)


def _json_snapshot(value: Any, *, field: str, expected: type, byte_limit: int) -> Any:
    if not isinstance(value, expected):
        kind = "object" if expected is dict else "array"
        raise ValueError(f"{field} must be an {kind}")
    _credential_safe(value, field=field)
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(serialized.encode("utf-8")) > byte_limit:
        raise ValueError(f"{field} exceeds the snapshot limit")
    return json.loads(serialized)


def _records_snapshot(value: Any) -> list[dict[str, Any]]:
    records = _json_snapshot(value, field="records", expected=list, byte_limit=2_000_000)
    if len(records) > 2_000:
        raise ValueError("records may contain at most 2000 items")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("every records item must be an object")
    return records


def _safe_source_url(value: Any) -> str:
    raw = _clean_required(value, field="source_url", limit=4_096)
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source_url must be an HTTP(S) URL")
    host = parsed.hostname.lower()
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", "", ""))


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PersonalIPPlatformObservationRepository:
    """Store detailed business data while refusing authentication material."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPPlatformObservationRow) -> dict[str, Any]:
        data = row.to_dict()
        data["records"] = data.pop("records_json") or []
        data["summary"] = data.pop("summary_json") or {}
        data["coverage"] = data.pop("coverage_json") or {}
        data["evidence"] = data.pop("evidence_json") or {}
        for field in ("observed_at", "created_at"):
            if isinstance(data.get(field), datetime):
                data[field] = coerce_iso(data[field])
        return data

    async def record(
        self,
        *,
        owner_user_id: str,
        observation_key: str,
        account_id: str,
        dataset: str,
        source: str,
        status: str,
        source_url: str,
        observed_at: datetime,
        records: list[dict[str, Any]],
        summary: dict[str, Any],
        coverage: dict[str, Any],
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        observation = _clean_required(observation_key, field="observation_key", limit=256)
        account_key = _clean_required(account_id, field="account_id", limit=64)
        dataset_key = str(dataset or "").strip()
        source_key = str(source or "").strip()
        status_key = str(status or "").strip()
        if dataset_key not in _DATASETS:
            raise ValueError("unsupported platform observation dataset")
        if source_key not in _SOURCES:
            raise ValueError("unsupported platform observation source")
        if status_key not in _STATUSES:
            raise ValueError("unsupported platform observation status")

        observed = _utc_datetime(observed_at, field="observed_at")
        safe_url = _safe_source_url(source_url)
        records_snapshot = _records_snapshot(records)
        summary_snapshot = _json_snapshot(summary, field="summary", expected=dict, byte_limit=256_000)
        coverage_snapshot = _json_snapshot(coverage, field="coverage", expected=dict, byte_limit=256_000)
        evidence_snapshot = _json_snapshot(evidence, field="evidence", expected=dict, byte_limit=256_000)
        if status_key in {"observed", "partial"} and not records_snapshot and not summary_snapshot:
            raise ValueError(f"{status_key} platform observations require records or summary")
        if status_key == "unavailable" and records_snapshot:
            raise ValueError("unavailable platform observations cannot contain records")
        if status_key in {"partial", "unavailable"} and not coverage_snapshot:
            raise ValueError(f"{status_key} platform observations require coverage detail")

        async with self._sf() as session:
            account = await session.get(PersonalIPAccountRow, account_key)
            if account is None or account.owner_user_id != owner or account.status != "active":
                raise ValueError("Personal-IP platform observation account not found")
            payload = {
                "account_id": account.id,
                "contract_version": PLATFORM_OBSERVATION_CONTRACT_VERSION,
                "coverage": coverage_snapshot,
                "dataset": dataset_key,
                "evidence": evidence_snapshot,
                "observed_at": coerce_iso(observed),
                "platform": account.platform,
                "records": records_snapshot,
                "source": source_key,
                "source_url": safe_url,
                "status": status_key,
                "summary": summary_snapshot,
            }
            evidence_digest = _digest(payload)

            statement = select(PersonalIPPlatformObservationRow).where(
                PersonalIPPlatformObservationRow.owner_user_id == owner,
                PersonalIPPlatformObservationRow.observation_key == observation,
            )
            existing = (await session.execute(statement)).scalars().first()
            if existing is not None:
                if existing.evidence_digest == evidence_digest:
                    return self._to_dict(existing)
                raise ValueError("observation_key already records a different observation")

            row = PersonalIPPlatformObservationRow(
                id=f"platform-observation-{uuid.uuid4().hex}",
                owner_user_id=owner,
                observation_key=observation,
                contract_version=PLATFORM_OBSERVATION_CONTRACT_VERSION,
                account_id=account.id,
                subject_id=account.subject_id,
                platform=account.platform,
                dataset=dataset_key,
                source=source_key,
                status=status_key,
                source_url=safe_url,
                observed_at=observed,
                records_json=records_snapshot,
                summary_json=summary_snapshot,
                coverage_json=coverage_snapshot,
                evidence_json=evidence_snapshot,
                evidence_digest=evidence_digest,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def get(self, observation_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPPlatformObservationRow, observation_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    async def get_by_key(self, observation_key: str, *, owner_user_id: str) -> dict[str, Any] | None:
        statement = select(PersonalIPPlatformObservationRow).where(
            PersonalIPPlatformObservationRow.owner_user_id == owner_user_id,
            PersonalIPPlatformObservationRow.observation_key == observation_key,
        )
        async with self._sf() as session:
            row = (await session.execute(statement)).scalars().first()
            return self._to_dict(row) if row is not None else None

    async def list(
        self,
        owner_user_id: str,
        *,
        account_id: str | None = None,
        dataset: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPPlatformObservationRow).where(PersonalIPPlatformObservationRow.owner_user_id == owner_user_id)
        if account_id is not None:
            statement = statement.where(PersonalIPPlatformObservationRow.account_id == account_id)
        if dataset is not None:
            statement = statement.where(PersonalIPPlatformObservationRow.dataset == dataset)
        statement = statement.order_by(
            PersonalIPPlatformObservationRow.observed_at.desc(),
            PersonalIPPlatformObservationRow.id.desc(),
        ).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._to_dict(row) for row in rows]
