"""Personal-IP cross-platform metric observations

Revision ID: 0010_personal_ip_metrics
Revises: 0009_personal_ip_publish_receipts
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_personal_ip_metrics"
down_revision: str | Sequence[str] | None = "0009_personal_ip_publish_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "personal_ip_metric_observations" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "personal_ip_metric_observations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("observation_key", sa.String(length=256), nullable=False),
        sa.Column("series_key", sa.String(length=256), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("receipt_id", sa.String(length=64), nullable=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("metric_mode", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("coverage_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope IN ('account','post')", name="ck_personal_ip_metrics_scope"),
        sa.CheckConstraint("metric_mode IN ('window_total','delta','snapshot')", name="ck_personal_ip_metrics_mode"),
        sa.CheckConstraint("source IN ('platform_api','ui_tars','browser','manual')", name="ck_personal_ip_metrics_source"),
        sa.CheckConstraint("status IN ('observed','partial','unavailable')", name="ck_personal_ip_metrics_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "observation_key", name="uq_personal_ip_metrics_owner_observation"),
    )
    with op.batch_alter_table("personal_ip_metric_observations", schema=None) as batch_op:
        batch_op.create_index("ix_personal_ip_metric_observations_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_index("ix_personal_ip_metric_observations_account_id", ["account_id"], unique=False)
        batch_op.create_index("ix_personal_ip_metric_observations_subject_id", ["subject_id"], unique=False)
        batch_op.create_index("ix_personal_ip_metric_observations_platform", ["platform"], unique=False)
        batch_op.create_index("ix_personal_ip_metric_observations_receipt_id", ["receipt_id"], unique=False)
        batch_op.create_index("ix_personal_ip_metrics_owner_observed", ["owner_user_id", "observed_at"], unique=False)
        batch_op.create_index(
            "ix_personal_ip_metrics_owner_account_window",
            ["owner_user_id", "account_id", "window_started_at", "window_ended_at"],
            unique=False,
        )


def downgrade() -> None:
    if "personal_ip_metric_observations" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("personal_ip_metric_observations")
