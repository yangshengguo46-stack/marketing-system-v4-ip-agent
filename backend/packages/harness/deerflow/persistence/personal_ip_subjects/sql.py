"""SQL repository for personal-IP operating subjects."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.utils.time import coerce_iso

_SUBJECT_FIELDS = frozenset(
    {
        "display_name",
        "subject_type",
        "relationship",
        "description",
        "status",
    }
)


class PersonalIPSubjectRepository:
    """Owner-scoped CRUD for operated people, brands and organizations."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPSubjectRow) -> dict[str, Any]:
        data = row.to_dict()
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
        display_name: str,
        subject_type: str = "creator",
        relationship: str = "self",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        row = PersonalIPSubjectRow(
            id=f"subject-{uuid.uuid4().hex}",
            owner_user_id=owner_user_id,
            display_name=display_name,
            subject_type=subject_type,
            relationship=relationship,
            description=description,
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
        stmt = select(PersonalIPSubjectRow).where(PersonalIPSubjectRow.owner_user_id == owner_user_id)
        if not include_archived:
            stmt = stmt.where(PersonalIPSubjectRow.status == "active")
        stmt = stmt.order_by(
            PersonalIPSubjectRow.updated_at.desc(),
            PersonalIPSubjectRow.id.desc(),
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            return [self._to_dict(row) for row in result.scalars()]

    async def get(
        self,
        subject_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPSubjectRow, subject_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    async def update(
        self,
        subject_id: str,
        *,
        owner_user_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPSubjectRow, subject_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            for key in _SUBJECT_FIELDS:
                if key in updates:
                    setattr(row, key, updates[key])
            if "metadata" in updates:
                row.metadata_json = dict(updates["metadata"] or {})
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def delete(self, subject_id: str, *, owner_user_id: str) -> bool:
        async with self._sf() as session:
            row = await session.get(PersonalIPSubjectRow, subject_id)
            if row is None or row.owner_user_id != owner_user_id:
                return False
            await session.delete(row)
            await session.commit()
            return True
