"""ORM models for differentiation theses and their observed IP-asset effects."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPDifferentiationVersionRow(Base):
    """One immutable differentiation-thesis version for an operated subject."""

    __tablename__ = "personal_ip_differentiation_versions"

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
    thesis_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    primary_entity_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    supporting_entities_json: Mapped[list] = mapped_column(JSON, nullable=False)
    decision_context_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    contrast_field_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    proprietary_truth_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    strategic_difference_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    dramatic_engine_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    distinctive_encoding_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    operating_fit_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    validation_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_differentiation_owner_operation",
        ),
        UniqueConstraint(
            "owner_user_id",
            "subject_id",
            "version",
            name="uq_personal_ip_differentiation_owner_subject_version",
        ),
        CheckConstraint(
            "status IN ('candidate','pilot','provisionally_adopted','validated','retired')",
            name="ck_personal_ip_differentiation_status",
        ),
        Index(
            "ix_personal_ip_differentiation_owner_subject_created",
            "owner_user_id",
            "subject_id",
            "created_at",
        ),
        Index(
            "ix_personal_ip_differentiation_owner_subject_thesis",
            "owner_user_id",
            "subject_id",
            "thesis_key",
        ),
    )


class PersonalIPAssetObservationRow(Base):
    """One immutable observation of recognition, trust, adoption or economic effect."""

    __tablename__ = "personal_ip_asset_observations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    subject_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    differentiation_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_differentiation_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    thesis_key: Mapped[str] = mapped_column(String(128), nullable=False)
    observation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    coverage_status: Mapped[str] = mapped_column(String(16), nullable=False)
    measures_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    evidence_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_asset_observation_owner_operation",
        ),
        CheckConstraint(
            "observation_type IN ('recognition','trust','intent','adoption','conversion','economic','extension')",
            name="ck_personal_ip_asset_observation_type",
        ),
        CheckConstraint(
            "source IN ('platform_metrics','platform_observation','retrospective','audience_feedback','user_research','commercial_record','product_telemetry')",
            name="ck_personal_ip_asset_observation_source",
        ),
        CheckConstraint(
            "coverage_status IN ('complete','partial','unavailable')",
            name="ck_personal_ip_asset_observation_coverage",
        ),
        Index(
            "ix_personal_ip_asset_observation_owner_subject_observed",
            "owner_user_id",
            "subject_id",
            "observed_at",
        ),
        Index(
            "ix_personal_ip_asset_observation_owner_thesis_type",
            "owner_user_id",
            "subject_id",
            "thesis_key",
            "observation_type",
        ),
    )
