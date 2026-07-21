"""personal IP accounts

Revision ID: 0006_personal_ip_accounts
Revises: 0005_run_stop_reason
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_personal_ip_accounts"
down_revision: str | Sequence[str] | None = "0005_run_stop_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("personal_ip_accounts"):
        return
    op.create_table(
        "personal_ip_accounts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("handle", sa.String(length=128), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("promise_to_audience", sa.Text(), nullable=False),
        sa.Column("primary_audience", sa.Text(), nullable=False),
        sa.Column("content_pillars_json", sa.JSON(), nullable=False),
        sa.Column("voice_and_boundaries_json", sa.JSON(), nullable=False),
        sa.Column("business_goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("personal_ip_accounts", schema=None) as batch_op:
        batch_op.create_index(
            "ix_personal_ip_accounts_owner_user_id",
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_accounts_platform",
            ["platform"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_accounts_owner_status_updated",
            ["owner_user_id", "status", "updated_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("personal_ip_accounts")
