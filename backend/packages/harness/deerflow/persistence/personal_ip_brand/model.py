"""ORM model for immutable Personal-IP operating strategies."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPStrategyVersionRow(Base):
    """One immutable snapshot of a subject's operating strategy."""

    __tablename__ = "personal_ip_strategy_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    subject_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    person_model_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    business_model_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    benchmark_research_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    positioning_candidates_json: Mapped[list] = mapped_column(JSON, nullable=False)
    launch_package_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_strategy_owner_operation",
        ),
        UniqueConstraint(
            "owner_user_id",
            "subject_id",
            "version",
            name="uq_personal_ip_strategy_owner_subject_version",
        ),
        CheckConstraint(
            "mode IN ('monetization_first','influence_first')",
            name="ck_personal_ip_strategy_mode",
        ),
        CheckConstraint(
            "stage IN ('evidence_collecting','person_model_draft','business_model_draft','benchmark_researching','positioning_candidates','launch_package_ready','pilot_running','commercial_signal_observed','scaling')",
            name="ck_personal_ip_strategy_stage",
        ),
        Index(
            "ix_personal_ip_strategy_owner_subject_created",
            "owner_user_id",
            "subject_id",
            "created_at",
        ),
    )


class _ArchivedPersonalIPIdentityVersionRow(Base):
    """Schema-only mapping retained so old databases upgrade without data loss."""

    __tablename__ = "personal_ip_brand_identity_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    subject_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    identity_prism_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    expression_star_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    reputation_intent_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_basis_json: Mapped[list] = mapped_column(JSON, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_brand_identity_owner_operation",
        ),
        UniqueConstraint(
            "owner_user_id",
            "subject_id",
            "version",
            name="uq_personal_ip_brand_identity_owner_subject_version",
        ),
        CheckConstraint(
            "status IN ('draft','active','superseded')",
            name="ck_personal_ip_brand_identity_status",
        ),
        Index(
            "ix_personal_ip_brand_identity_owner_subject_status",
            "owner_user_id",
            "subject_id",
            "status",
        ),
    )


class _ArchivedPersonalIPReputationSnapshotRow(Base):
    """Schema-only mapping retained so old databases upgrade without data loss."""

    __tablename__ = "personal_ip_reputation_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    subject_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identity_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_brand_identity_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    perceived_identity_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    reputation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    alignment_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_reputation_owner_operation",
        ),
        CheckConstraint(
            "status IN ('measured','partial')",
            name="ck_personal_ip_reputation_status",
        ),
        Index(
            "ix_personal_ip_reputation_owner_subject_created",
            "owner_user_id",
            "subject_id",
            "created_at",
        ),
    )
