"""ORM model for owner-scoped Personal-IP metric observations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPMetricObservationRow(Base):
    """One immutable platform observation, suitable for replay and audit."""

    __tablename__ = "personal_ip_metric_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    observation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    series_key: Mapped[str] = mapped_column(String(256), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    metric_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    coverage_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "observation_key",
            name="uq_personal_ip_metrics_owner_observation",
        ),
        CheckConstraint(
            "scope IN ('account','post')",
            name="ck_personal_ip_metrics_scope",
        ),
        CheckConstraint(
            "metric_mode IN ('window_total','delta','snapshot')",
            name="ck_personal_ip_metrics_mode",
        ),
        CheckConstraint(
            "source IN ('platform_api','ui_tars','browser','manual')",
            name="ck_personal_ip_metrics_source",
        ),
        CheckConstraint(
            "status IN ('observed','partial','unavailable')",
            name="ck_personal_ip_metrics_status",
        ),
        Index(
            "ix_personal_ip_metrics_owner_observed",
            "owner_user_id",
            "observed_at",
        ),
        Index(
            "ix_personal_ip_metrics_owner_account_window",
            "owner_user_id",
            "account_id",
            "window_started_at",
            "window_ended_at",
        ),
    )
