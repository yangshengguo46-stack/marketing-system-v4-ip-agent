"""auditable Personal-IP publish operation receipts

Revision ID: 0009_personal_ip_publish_receipts
Revises: 0008_personal_ip_preflights
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_personal_ip_publish_receipts"
down_revision: str | Sequence[str] | None = "0008_personal_ip_preflights"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "personal_ip_publish_receipts" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "personal_ip_publish_receipts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("operation_key", sa.String(length=256), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("preflight_id", sa.String(length=64), nullable=True),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("executor", sa.String(length=32), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("attempts_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("external_post_id", sa.String(length=256), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('planned','pending','published','failed','unknown','deleted')",
            name="ck_personal_ip_publish_status",
        ),
        sa.CheckConstraint(
            "executor IN ('platform_api','ui_tars','browser','manual')",
            name="ck_personal_ip_publish_executor",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_publish_owner_operation",
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "idempotency_key",
            name="uq_personal_ip_publish_owner_idempotency",
        ),
    )
    with op.batch_alter_table("personal_ip_publish_receipts", schema=None) as batch_op:
        batch_op.create_index("ix_personal_ip_publish_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_index("ix_personal_ip_publish_preflight_id", ["preflight_id"], unique=False)
        batch_op.create_index("ix_personal_ip_publish_subject_id", ["subject_id"], unique=False)
        batch_op.create_index("ix_personal_ip_publish_account_id", ["account_id"], unique=False)
        batch_op.create_index(
            "ix_personal_ip_publish_owner_account_updated",
            ["owner_user_id", "account_id", "updated_at"],
            unique=False,
        )


def downgrade() -> None:
    if "personal_ip_publish_receipts" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("personal_ip_publish_receipts")
