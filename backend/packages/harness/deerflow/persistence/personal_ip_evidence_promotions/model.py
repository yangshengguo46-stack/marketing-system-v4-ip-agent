"""ORM model for cross-sample, human-reviewed evidence promotions."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPEvidencePromotionRow(Base):
    """One proposed pattern and its terminal authenticated-user decision."""

    __tablename__ = "personal_ip_evidence_promotions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    proposal_key: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    retrospective_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    minimum_support: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    decisions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "proposal_key",
            name="uq_personal_ip_evidence_promotions_owner_proposal",
        ),
        CheckConstraint(
            "evidence_type IN ('audience_pattern','content_pattern','platform_pattern','training_cohort')",
            name="ck_personal_ip_evidence_promotions_type",
        ),
        CheckConstraint(
            "status IN ('proposed','approved','rejected')",
            name="ck_personal_ip_evidence_promotions_status",
        ),
        CheckConstraint(
            "minimum_support >= 3 AND minimum_support <= 100",
            name="ck_personal_ip_evidence_promotions_support",
        ),
        Index(
            "ix_personal_ip_evidence_promotions_owner_status_created",
            "owner_user_id",
            "status",
            "created_at",
        ),
    )
