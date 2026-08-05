"""ORM models for the Owner-scoped Personal-IP content lineage."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPContentWorkRow(Base):
    """Stable identity for one original piece of content."""

    __tablename__ = "personal_ip_content_works"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    objective_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("personal_ip_subjects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    operation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(1_000), nullable=False)
    entry_route: Mapped[str] = mapped_column(String(32), nullable=False)
    objective_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_content_works_owner_operation",
        ),
        UniqueConstraint(
            "objective_id",
            name="uq_personal_ip_content_works_objective",
        ),
        CheckConstraint(
            "entry_route IN ('zero_start','benchmark')",
            name="ck_personal_ip_content_works_entry_route",
        ),
        CheckConstraint(
            "status IN ('active','archived')",
            name="ck_personal_ip_content_works_status",
        ),
        Index(
            "ix_personal_ip_content_works_owner_status_updated",
            "owner_user_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_personal_ip_content_works_owner_subject",
            "owner_user_id",
            "subject_id",
        ),
        Index(
            "ix_personal_ip_content_works_owner_thread",
            "owner_user_id",
            "thread_id",
        ),
    )


class PersonalIPBreakdownVersionRow(Base):
    """One immutable external or Owner-material breakdown."""

    __tablename__ = "personal_ip_breakdown_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_work_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_content_works.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    commit_key: Mapped[str] = mapped_column(String(256), nullable=False)
    commit_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_identity_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_item_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_contract_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_payload_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_snapshot_json: Mapped[dict | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )
    observations_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    interpretations_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    limitations_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "content_work_id",
            "version_number",
            name="uq_personal_ip_breakdown_versions_work_version",
        ),
        UniqueConstraint(
            "content_work_id",
            "commit_key",
            name="uq_personal_ip_breakdown_versions_work_commit",
        ),
        CheckConstraint(
            "source_kind IN ('platform_content','uploaded_file','owner_material')",
            name="ck_personal_ip_breakdown_versions_source_kind",
        ),
        CheckConstraint(
            "(source_kind = 'owner_material' AND evidence_request_id IS NULL AND evidence_item_index IS NULL "
            "AND evidence_contract_version IS NULL AND evidence_payload_digest IS NULL "
            "AND evidence_snapshot_json IS NULL) OR "
            "(source_kind IN ('platform_content','uploaded_file') AND source_digest IS NOT NULL "
            "AND evidence_request_id IS NOT NULL AND evidence_item_index IS NOT NULL "
            "AND evidence_contract_version IS NOT NULL AND evidence_payload_digest IS NOT NULL "
            "AND evidence_snapshot_json IS NOT NULL)",
            name="ck_personal_ip_breakdown_versions_evidence_binding",
        ),
        Index(
            "ix_personal_ip_breakdown_versions_owner_work_version",
            "owner_user_id",
            "content_work_id",
            "version_number",
        ),
    )


class PersonalIPDirectionVersionRow(Base):
    """One immutable decision-brain direction."""

    __tablename__ = "personal_ip_direction_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_work_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_content_works.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    commit_key: Mapped[str] = mapped_column(String(256), nullable=False)
    commit_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_direction_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    breakdown_version_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    objective_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    direction_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "content_work_id",
            "version_number",
            name="uq_personal_ip_direction_versions_work_version",
        ),
        UniqueConstraint(
            "content_work_id",
            "commit_key",
            name="uq_personal_ip_direction_versions_work_commit",
        ),
        Index(
            "ix_personal_ip_direction_versions_owner_work_version",
            "owner_user_id",
            "content_work_id",
            "version_number",
        ),
    )


class PersonalIPScriptVersionRow(Base):
    """One immutable script with truth boundary and separate production notes."""

    __tablename__ = "personal_ip_script_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_work_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_content_works.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction_version_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_direction_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    commit_key: Mapped[str] = mapped_column(String(256), nullable=False)
    commit_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_script_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(1_000), nullable=False)
    story_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    script_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_basis_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    creative_elements_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    story_engine_seed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    locked_story: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_story_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    production_notes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "content_work_id",
            "version_number",
            name="uq_personal_ip_script_versions_work_version",
        ),
        UniqueConstraint(
            "content_work_id",
            "commit_key",
            name="uq_personal_ip_script_versions_work_commit",
        ),
        CheckConstraint(
            "story_mode IN ('factual','fictional','hybrid')",
            name="ck_personal_ip_script_versions_story_mode",
        ),
        Index(
            "ix_personal_ip_script_versions_owner_work_version",
            "owner_user_id",
            "content_work_id",
            "version_number",
        ),
    )


__all__ = [
    "PersonalIPBreakdownVersionRow",
    "PersonalIPContentWorkRow",
    "PersonalIPDirectionVersionRow",
    "PersonalIPScriptVersionRow",
]
