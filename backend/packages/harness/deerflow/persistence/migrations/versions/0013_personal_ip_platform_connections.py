"""Personal-IP account-level platform authorization connections

Revision ID: 0013_personal_ip_platform_connections
Revises: 0012_personal_ip_evidence_promotions
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_personal_ip_platform_connections"
down_revision: str | Sequence[str] | None = "0012_personal_ip_evidence_promotions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_platform_connections" not in existing:
        op.create_table(
            "personal_ip_platform_connections",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("external_user_id", sa.String(length=256), nullable=False),
            sa.Column("oauth_open_id", sa.String(length=256), nullable=True),
            sa.Column("scopes_json", sa.JSON(), nullable=False),
            sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("token_version", sa.Integer(), nullable=False),
            sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_code", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["personal_ip_accounts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "account_id",
                "platform",
                name="uq_personal_ip_platform_connection_owner_account_platform",
            ),
        )
        with op.batch_alter_table("personal_ip_platform_connections", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_platform_connections_account_id",
                ["account_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_platform_connections_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_platform_connections_platform",
                ["platform"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_platform_connections_owner_status_updated",
                ["owner_user_id", "status", "updated_at"],
                unique=False,
            )
        op.create_index(
            "uq_personal_ip_platform_connection_active_external",
            "personal_ip_platform_connections",
            ["platform", "external_user_id"],
            unique=True,
            sqlite_where=sa.text("status != 'revoked'"),
            postgresql_where=sa.text("status != 'revoked'"),
        )

    if "personal_ip_platform_credentials" not in existing:
        op.create_table(
            "personal_ip_platform_credentials",
            sa.Column("connection_id", sa.String(length=64), nullable=False),
            sa.Column("encrypted_access_token", sa.Text(), nullable=False),
            sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["connection_id"],
                ["personal_ip_platform_connections.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("connection_id"),
        )

    if "personal_ip_platform_oauth_states" not in existing:
        op.create_table(
            "personal_ip_platform_oauth_states",
            sa.Column("state_hash", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("requested_scopes_json", sa.JSON(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["account_id"], ["personal_ip_accounts.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("state_hash"),
        )
        with op.batch_alter_table("personal_ip_platform_oauth_states", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_platform_oauth_states_account_id",
                ["account_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_platform_oauth_states_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_platform_oauth_states_platform",
                ["platform"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_platform_oauth_states_owner_expiry",
                ["owner_user_id", "expires_at"],
                unique=False,
            )


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_platform_oauth_states" in existing:
        op.drop_table("personal_ip_platform_oauth_states")
    if "personal_ip_platform_credentials" in existing:
        op.drop_table("personal_ip_platform_credentials")
    if "personal_ip_platform_connections" in existing:
        op.drop_table("personal_ip_platform_connections")
