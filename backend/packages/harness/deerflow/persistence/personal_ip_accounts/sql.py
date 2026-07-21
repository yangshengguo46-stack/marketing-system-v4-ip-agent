"""SQL repository for personal-IP accounts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.utils.time import coerce_iso

_ACCOUNT_FIELDS = frozenset(
    {
        "platform",
        "display_name",
        "handle",
        "avatar_url",
        "promise_to_audience",
        "primary_audience",
        "business_goal",
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
        data["content_pillars"] = data.pop("content_pillars_json") or []
        data["voice_and_boundaries"] = data.pop("voice_and_boundaries_json") or []
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
        handle: str | None = None,
        avatar_url: str | None = None,
        promise_to_audience: str = "",
        primary_audience: str = "",
        content_pillars: list[str] | None = None,
        voice_and_boundaries: list[str] | None = None,
        business_goal: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        row = PersonalIPAccountRow(
            id=f"acct-{uuid.uuid4().hex}",
            owner_user_id=owner_user_id,
            platform=platform,
            display_name=display_name,
            handle=handle,
            avatar_url=avatar_url,
            promise_to_audience=promise_to_audience,
            primary_audience=primary_audience,
            content_pillars_json=list(content_pillars or []),
            voice_and_boundaries_json=list(voice_and_boundaries or []),
            business_goal=business_goal,
            status="active",
            metadata_json=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        async with self._sf() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def list(
        self,
        owner_user_id: str,
        *,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        stmt = select(PersonalIPAccountRow).where(PersonalIPAccountRow.owner_user_id == owner_user_id)
        if not include_archived:
            stmt = stmt.where(PersonalIPAccountRow.status == "active")
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

            for key in _ACCOUNT_FIELDS:
                if key in updates:
                    setattr(row, key, updates[key])
            if "content_pillars" in updates:
                row.content_pillars_json = list(updates["content_pillars"] or [])
            if "voice_and_boundaries" in updates:
                row.voice_and_boundaries_json = list(updates["voice_and_boundaries"] or [])
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
