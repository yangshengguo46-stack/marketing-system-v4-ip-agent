"""immutable Personal-IP audience preflight snapshots

Revision ID: 0008_personal_ip_preflights
Revises: 0007_personal_ip_subjects
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_personal_ip_preflights"
down_revision: str | Sequence[str] | None = "0007_personal_ip_subjects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "personal_ip_preflights" in inspector.get_table_names():
        return
    op.create_table(
        "personal_ip_preflights",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("operation_key", sa.String(length=256), nullable=False),
        sa.Column("subject_ids_json", sa.JSON(), nullable=False),
        sa.Column("target_account_ids_json", sa.JSON(), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=160), nullable=False),
        sa.Column("algorithm_version", sa.String(length=160), nullable=False),
        sa.Column("model_request_json", sa.JSON(), nullable=False),
        sa.Column("provider_receipt_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('sealed','published','settled','invalidated')",
            name="ck_personal_ip_preflights_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_preflights_owner_operation",
        ),
    )
    with op.batch_alter_table("personal_ip_preflights", schema=None) as batch_op:
        batch_op.create_index(
            "ix_personal_ip_preflights_owner_user_id",
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_preflights_owner_created",
            ["owner_user_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_preflights_owner_digest",
            ["owner_user_id", "request_digest"],
            unique=False,
        )


def downgrade() -> None:
    if "personal_ip_preflights" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("personal_ip_preflights")
