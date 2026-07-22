"""ORM models for auditable Personal-IP video production orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPVideoProductionRow(Base):
    """Immutable production request plus its current append-only projection."""

    __tablename__ = "personal_ip_video_productions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("personal_ip_subjects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_account_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    delivery_spec_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provider_policy_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    budget_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    current_stage: Mapped[str] = mapped_column(String(24), nullable=False, default="intake")
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_video_productions_owner_operation",
        ),
        CheckConstraint("source_kind IN ('idea','script')", name="ck_personal_ip_video_productions_source_kind"),
        CheckConstraint(
            "status IN ('draft','running','awaiting_review','blocked','completed','cancelled')",
            name="ck_personal_ip_video_productions_status",
        ),
        CheckConstraint(
            "current_stage IN ('intake','blueprint','assets','storyboard','generation','consistency','selection','finishing','delivery')",
            name="ck_personal_ip_video_productions_stage",
        ),
        Index("ix_personal_ip_video_productions_owner_updated", "owner_user_id", "updated_at"),
    )


class PersonalIPVideoProductionEventRow(Base):
    """One immutable provider/task/decision receipt in a video production."""

    __tablename__ = "personal_ip_video_production_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    production_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_video_productions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_key: Mapped[str] = mapped_column(String(256), nullable=False)
    event_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider_task_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    output_refs_json: Mapped[list] = mapped_column(JSON, nullable=False)
    cost_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "production_id",
            "event_key",
            name="uq_personal_ip_video_production_events_key",
        ),
        UniqueConstraint(
            "production_id",
            "sequence",
            name="uq_personal_ip_video_production_events_sequence",
        ),
        CheckConstraint(
            "status IN ('planned','running','succeeded','failed','awaiting_review','approved','rejected')",
            name="ck_personal_ip_video_production_events_status",
        ),
        Index(
            "ix_personal_ip_video_production_events_production_sequence",
            "production_id",
            "sequence",
        ),
    )
