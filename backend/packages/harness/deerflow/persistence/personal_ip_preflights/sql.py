"""SQL repository for immutable Personal-IP audience preflight snapshots."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_preflights.model import PersonalIPPreflightRow
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.personal_ip.audience_provider import AudiencePreflightRequest, AudiencePreflightResult
from deerflow.utils.time import coerce_iso


def _normalized_ids(values: Sequence[str], *, field: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            raise ValueError(f"{field} contains an empty id")
        if len(value) > 64:
            raise ValueError(f"{field} contains an oversized id")
        if value not in seen:
            seen.add(value)
            result.append(value)
    if len(result) > 200:
        raise ValueError(f"{field} contains too many ids")
    return result


class PersonalIPPreflightRepository:
    """Seal and read preflights without allowing prediction rewrites."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPPreflightRow) -> dict[str, Any]:
        data = row.to_dict()
        data["subject_ids"] = data.pop("subject_ids_json") or []
        data["target_account_ids"] = data.pop("target_account_ids_json") or []
        data["model_request"] = data.pop("model_request_json") or {}
        data["provider_receipt"] = data.pop("provider_receipt_json") or {}
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = coerce_iso(data["created_at"])
        return data

    @staticmethod
    async def _validate_targets(
        session: AsyncSession,
        *,
        owner_user_id: str,
        subject_ids: list[str],
        target_account_ids: list[str],
    ) -> None:
        if subject_ids:
            statement = select(PersonalIPSubjectRow.id).where(
                PersonalIPSubjectRow.id.in_(subject_ids),
                PersonalIPSubjectRow.owner_user_id == owner_user_id,
                PersonalIPSubjectRow.status == "active",
            )
            found = set((await session.execute(statement)).scalars())
            if found != set(subject_ids):
                raise ValueError("Personal-IP preflight subject not found")
        if target_account_ids:
            statement = select(PersonalIPAccountRow.id).where(
                PersonalIPAccountRow.id.in_(target_account_ids),
                PersonalIPAccountRow.owner_user_id == owner_user_id,
                PersonalIPAccountRow.status == "active",
            )
            found = set((await session.execute(statement)).scalars())
            if found != set(target_account_ids):
                raise ValueError("Personal-IP preflight target account not found")

    @staticmethod
    def _same_snapshot(
        row: PersonalIPPreflightRow,
        *,
        subject_ids: list[str],
        target_account_ids: list[str],
        request_payload: dict[str, Any],
        result_payload: dict[str, Any],
    ) -> bool:
        return row.subject_ids_json == subject_ids and row.target_account_ids_json == target_account_ids and row.model_request_json == request_payload and row.provider_receipt_json == result_payload

    async def seal(
        self,
        *,
        owner_user_id: str,
        operation_key: str,
        subject_ids: Sequence[str],
        target_account_ids: Sequence[str],
        request: AudiencePreflightRequest,
        result: AudiencePreflightResult,
    ) -> dict[str, Any]:
        owner = str(owner_user_id or "").strip()
        operation = str(operation_key or "").strip()
        if not owner:
            raise ValueError("owner_user_id is required")
        if not operation or len(operation) > 256:
            raise ValueError("operation_key must contain 1 to 256 characters")
        normalized_subjects = _normalized_ids(subject_ids, field="subject_ids")
        normalized_accounts = _normalized_ids(target_account_ids, field="target_account_ids")
        if result.request_digest != request.request_digest:
            raise ValueError("audience provider receipt does not match its request")
        if result.audience_basis != request.audience_basis:
            raise ValueError("audience provider receipt uses a different audience basis")
        request_payload = request.to_payload()
        result_payload = result.model_dump(mode="json")

        async with self._sf() as session:
            existing_statement = select(PersonalIPPreflightRow).where(
                PersonalIPPreflightRow.owner_user_id == owner,
                PersonalIPPreflightRow.operation_key == operation,
            )
            existing = (await session.execute(existing_statement)).scalar_one_or_none()
            if existing is not None:
                if self._same_snapshot(
                    existing,
                    subject_ids=normalized_subjects,
                    target_account_ids=normalized_accounts,
                    request_payload=request_payload,
                    result_payload=result_payload,
                ):
                    return self._to_dict(existing)
                raise ValueError("operation_key already seals a different preflight")

            await self._validate_targets(
                session,
                owner_user_id=owner,
                subject_ids=normalized_subjects,
                target_account_ids=normalized_accounts,
            )
            row = PersonalIPPreflightRow(
                id=f"preflight-{uuid.uuid4().hex}",
                owner_user_id=owner,
                operation_key=operation,
                subject_ids_json=normalized_subjects,
                target_account_ids_json=normalized_accounts,
                request_digest=request.request_digest,
                provider=result.provider,
                model_version=result.model_version,
                algorithm_version=result.algorithm_version,
                model_request_json=request_payload,
                provider_receipt_json=result_payload,
                status="sealed",
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def get(self, preflight_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPPreflightRow, preflight_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    async def list(self, owner_user_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 500))
        statement = select(PersonalIPPreflightRow).where(PersonalIPPreflightRow.owner_user_id == owner_user_id).order_by(PersonalIPPreflightRow.created_at.desc(), PersonalIPPreflightRow.id.desc()).limit(bounded_limit)
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._to_dict(row) for row in rows]
