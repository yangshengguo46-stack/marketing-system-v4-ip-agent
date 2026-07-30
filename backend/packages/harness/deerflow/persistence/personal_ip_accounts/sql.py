"""SQL repository for personal-IP accounts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.utils.time import coerce_iso

_ACCOUNT_FIELDS = frozenset(
    {
        "platform",
        "subject_id",
        "display_name",
        "handle",
        "avatar_url",
        "status",
    }
)


class PersonalIPAccountRepository:
    """Owner-scoped CRUD for creator and brand accounts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPAccountRow) -> dict[str, Any]:
        data = row.to_dict()
        # Kept as physical compatibility columns until a later destructive
        # migration, but removed from the account contract. Identity truth is
        # versioned at the subject level.
        for legacy_field in (
            "promise_to_audience",
            "primary_audience",
            "content_pillars_json",
            "voice_and_boundaries_json",
            "business_goal",
        ):
            data.pop(legacy_field, None)
        data["metadata"] = data.pop("metadata_json") or {}
        for key in ("created_at", "updated_at"):
            value = data.get(key)
            if isinstance(value, datetime):
                data[key] = coerce_iso(value)
        return data

    async def create(
        self,
        *,
        owner_user_id: str,
        platform: str,
        display_name: str,
        subject_id: str | None = None,
        handle: str | None = None,
        avatar_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        async with self._sf() as session:
            if subject_id is not None and not await self._subject_belongs_to_owner(
                session,
                subject_id=subject_id,
                owner_user_id=owner_user_id,
            ):
                raise ValueError("Personal-IP subject not found")
            row = PersonalIPAccountRow(
                id=f"acct-{uuid.uuid4().hex}",
                owner_user_id=owner_user_id,
                subject_id=subject_id,
                platform=platform,
                display_name=display_name,
                handle=handle,
                avatar_url=avatar_url,
                status="active",
                metadata_json=dict(metadata or {}),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def list(
        self,
        owner_user_id: str,
        *,
        include_archived: bool = False,
        subject_id: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(PersonalIPAccountRow).where(PersonalIPAccountRow.owner_user_id == owner_user_id)
        if not include_archived:
            stmt = stmt.where(PersonalIPAccountRow.status == "active")
        if subject_id is not None:
            stmt = stmt.where(PersonalIPAccountRow.subject_id == subject_id)
        stmt = stmt.order_by(
            PersonalIPAccountRow.updated_at.desc(),
            PersonalIPAccountRow.id.desc(),
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            return [self._to_dict(row) for row in result.scalars()]

    async def get(
        self,
        account_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPAccountRow, account_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    @staticmethod
    async def _subject_belongs_to_owner(
        session: AsyncSession,
        *,
        subject_id: str,
        owner_user_id: str,
    ) -> bool:
        subject = await session.get(PersonalIPSubjectRow, subject_id)
        return subject is not None and subject.owner_user_id == owner_user_id and subject.status == "active"

    async def update(
        self,
        account_id: str,
        *,
        owner_user_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPAccountRow, account_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None

            if "subject_id" in updates:
                subject_id = updates["subject_id"]
                if subject_id is not None and not await self._subject_belongs_to_owner(
                    session,
                    subject_id=subject_id,
                    owner_user_id=owner_user_id,
                ):
                    raise ValueError("Personal-IP subject not found")

            for key in _ACCOUNT_FIELDS:
                if key in updates:
                    setattr(row, key, updates[key])
            if "metadata" in updates:
                row.metadata_json = dict(updates["metadata"] or {})
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def delete(self, account_id: str, *, owner_user_id: str) -> bool:
        async with self._sf() as session:
            row = await session.get(PersonalIPAccountRow, account_id)
            if row is None or row.owner_user_id != owner_user_id:
                return False
            await session.delete(row)
            await session.commit()
            return True
