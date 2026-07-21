"""ORM model for owner-scoped personal-IP operating subjects."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPSubjectRow(Base):
    """A person, brand or organization operated by one DeerFlow user."""

    __tablename__ = "personal_ip_subjects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(24), nullable=False, default="creator")
    relationship: Mapped[str] = mapped_column(String(24), nullable=False, default="self")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        Index(
            "ix_personal_ip_subjects_owner_status_updated",
            "owner_user_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_personal_ip_subjects_owner_relationship",
            "owner_user_id",
            "relationship",
        ),
    )
