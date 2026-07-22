"""ORM model for detailed, owner-scoped platform business-data evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPPlatformObservationRow(Base):
    """One immutable creator-backend snapshot with collection provenance."""

    __tablename__ = "personal_ip_platform_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dataset: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    records_json: Mapped[list] = mapped_column(JSON, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    coverage_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "observation_key",
            name="uq_personal_ip_platform_observations_owner_key",
        ),
        CheckConstraint(
            "source IN ('platform_api','ui_tars','browser','manual')",
            name="ck_personal_ip_platform_observations_source",
        ),
        CheckConstraint(
            "status IN ('observed','partial','unavailable')",
            name="ck_personal_ip_platform_observations_status",
        ),
        Index(
            "ix_personal_ip_platform_observations_owner_observed",
            "owner_user_id",
            "observed_at",
        ),
        Index(
            "ix_personal_ip_platform_observations_owner_account_dataset",
            "owner_user_id",
            "account_id",
            "dataset",
        ),
    )
