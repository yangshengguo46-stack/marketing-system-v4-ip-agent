"""ORM model for sealed prediction-to-outcome Personal-IP evidence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPRetrospectiveRow(Base):
    """One immutable join of a preflight, publication and observed outcome."""

    __tablename__ = "personal_ip_retrospectives"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    review_key: Mapped[str] = mapped_column(String(256), nullable=False)
    preflight_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    publish_receipt_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_variant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(160), nullable=False)
    metric_observation_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    prediction_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    outcome_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    training_eligibility_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    comparison_state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "review_key",
            name="uq_personal_ip_retrospectives_owner_review",
        ),
        UniqueConstraint(
            "owner_user_id",
            "publish_receipt_id",
            "horizon",
            name="uq_personal_ip_retrospectives_owner_publish_horizon",
        ),
        CheckConstraint(
            "status IN ('measured','partial')",
            name="ck_personal_ip_retrospectives_status",
        ),
        CheckConstraint(
            "comparison_state IN ('scored','unscored')",
            name="ck_personal_ip_retrospectives_comparison",
        ),
        Index(
            "ix_personal_ip_retrospectives_owner_created",
            "owner_user_id",
            "created_at",
        ),
    )
