"""ORM model for auditable Personal-IP publishing operations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPPublishReceiptRow(Base):
    """One idempotent publish operation with append-only attempt evidence."""

    __tablename__ = "personal_ip_publish_receipts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation_key: Mapped[str] = mapped_column(String(256), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    preflight_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False, default="publish")
    executor: Mapped[str] = mapped_column(String(32), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    attempts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="planned")
    external_post_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_publish_owner_operation",
        ),
        UniqueConstraint(
            "owner_user_id",
            "idempotency_key",
            name="uq_personal_ip_publish_owner_idempotency",
        ),
        CheckConstraint(
            "status IN ('planned','pending','published','failed','unknown','deleted')",
            name="ck_personal_ip_publish_status",
        ),
        CheckConstraint(
            "executor IN ('platform_api','ui_tars','browser','manual')",
            name="ck_personal_ip_publish_executor",
        ),
        Index(
            "ix_personal_ip_publish_owner_account_updated",
            "owner_user_id",
            "account_id",
            "updated_at",
        ),
    )
