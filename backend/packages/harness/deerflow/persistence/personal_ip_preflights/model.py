"""ORM model for immutable Personal-IP audience preflight snapshots."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPPreflightRow(Base):
    """A sealed model input and receipt, scoped to its authenticated owner."""

    __tablename__ = "personal_ip_preflights"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    subject_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    target_account_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(160), nullable=False)
    model_request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    provider_receipt_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="sealed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_preflights_owner_operation",
        ),
        CheckConstraint(
            "status IN ('sealed','published','settled','invalidated')",
            name="ck_personal_ip_preflights_status",
        ),
        Index(
            "ix_personal_ip_preflights_owner_created",
            "owner_user_id",
            "created_at",
        ),
        Index(
            "ix_personal_ip_preflights_owner_digest",
            "owner_user_id",
            "request_digest",
        ),
    )
