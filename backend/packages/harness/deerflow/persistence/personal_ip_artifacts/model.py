"""ORM model for immutable, owner-scoped Personal-IP final artifacts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPArtifactRow(Base):
    """Immutable final identity plus a monotonic byte-availability flag."""

    __tablename__ = "personal_ip_artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    production_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "personal_ip_video_productions.id",
            ondelete="RESTRICT",
            name="fk_personal_ip_artifacts_production",
        ),
        nullable=False,
        index=True,
    )
    qa_event_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "personal_ip_video_production_events.id",
            ondelete="RESTRICT",
            name="fk_personal_ip_artifacts_qa_event",
        ),
        nullable=False,
        index=True,
    )
    delivery_event_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "personal_ip_video_production_events.id",
            ondelete="RESTRICT",
            name="fk_personal_ip_artifacts_delivery_event",
        ),
        nullable=False,
        index=True,
    )
    contract_version: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1_024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    content_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    artifact_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "production_id",
            "role",
            name="uq_personal_ip_artifacts_production_role",
        ),
        UniqueConstraint(
            "delivery_event_id",
            "role",
            name="uq_personal_ip_artifacts_delivery_event_role",
        ),
        CheckConstraint(
            "contract_version = 'personal-ip-final-artifact-v1'",
            name="ck_personal_ip_artifacts_contract_version",
        ),
        CheckConstraint(
            "role = 'final_video'",
            name="ck_personal_ip_artifacts_role",
        ),
        CheckConstraint("size_bytes > 0", name="ck_personal_ip_artifacts_size"),
        Index(
            "ix_personal_ip_artifacts_owner_created",
            "owner_user_id",
            "created_at",
        ),
        Index(
            "ix_personal_ip_artifacts_owner_production",
            "owner_user_id",
            "production_id",
        ),
    )
