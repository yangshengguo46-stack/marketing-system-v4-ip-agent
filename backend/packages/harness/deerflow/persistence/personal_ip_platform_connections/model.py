"""ORM models for account-level platform authorization connections."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PersonalIPPlatformConnectionRow(Base):
    """A platform authorization attached to an operated account, never a thread."""

    __tablename__ = "personal_ip_platform_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="connected")
    external_user_id: Mapped[str] = mapped_column(String(256), nullable=False)
    oauth_open_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    scopes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    access_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "account_id",
            "platform",
            name="uq_personal_ip_platform_connection_owner_account_platform",
        ),
        Index(
            "uq_personal_ip_platform_connection_active_external",
            "platform",
            "external_user_id",
            unique=True,
            sqlite_where=text("status != 'revoked'"),
            postgresql_where=text("status != 'revoked'"),
        ),
        Index(
            "ix_personal_ip_platform_connections_owner_status_updated",
            "owner_user_id",
            "status",
            "updated_at",
        ),
    )


class PersonalIPPlatformCredentialRow(Base):
    """Encrypted credential material; never serialized by the public repository API."""

    __tablename__ = "personal_ip_platform_credentials"

    connection_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_platform_connections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class PersonalIPPlatformOAuthStateRow(Base):
    """One-use, owner-bound authorization ceremony state; only its digest is stored."""

    __tablename__ = "personal_ip_platform_oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("personal_ip_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_scopes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        Index(
            "ix_personal_ip_platform_oauth_states_owner_expiry",
            "owner_user_id",
            "expires_at",
        ),
    )
