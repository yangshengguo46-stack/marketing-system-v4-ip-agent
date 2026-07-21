"""ORM model for user-owned personal-IP accounts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPAccountRow(Base):
    """One operated creator/brand account owned by one DeerFlow user."""

    __tablename__ = "personal_ip_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    handle: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    promise_to_audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    primary_audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_pillars_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    voice_and_boundaries_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    business_goal: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        Index(
            "ix_personal_ip_accounts_owner_status_updated",
            "owner_user_id",
            "status",
            "updated_at",
        ),
    )
