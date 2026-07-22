"""Detailed Personal-IP platform business-data observations

Revision ID: 0014_personal_ip_platform_observations
Revises: 0013_personal_ip_platform_connections
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_personal_ip_platform_observations"
down_revision: str | Sequence[str] | None = "0013_personal_ip_platform_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "personal_ip_platform_observations" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "personal_ip_platform_observations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("observation_key", sa.String(length=256), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("dataset", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("records_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("coverage_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('platform_api','ui_tars','browser','manual')",
            name="ck_personal_ip_platform_observations_source",
        ),
        sa.CheckConstraint(
            "status IN ('observed','partial','unavailable')",
            name="ck_personal_ip_platform_observations_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["personal_ip_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "observation_key",
            name="uq_personal_ip_platform_observations_owner_key",
        ),
    )
    with op.batch_alter_table("personal_ip_platform_observations", schema=None) as batch_op:
        batch_op.create_index(
            "ix_personal_ip_platform_observations_owner_user_id",
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_platform_observations_account_id",
            ["account_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_platform_observations_subject_id",
            ["subject_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_platform_observations_platform",
            ["platform"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_platform_observations_dataset",
            ["dataset"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_platform_observations_owner_observed",
            ["owner_user_id", "observed_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_platform_observations_owner_account_dataset",
            ["owner_user_id", "account_id", "dataset"],
            unique=False,
        )


def downgrade() -> None:
    if "personal_ip_platform_observations" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("personal_ip_platform_observations")
