"""Personal-IP immutable retrospective evidence

Revision ID: 0011_personal_ip_retrospectives
Revises: 0010_personal_ip_metrics
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_personal_ip_retrospectives"
down_revision: str | Sequence[str] | None = "0010_personal_ip_metrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "personal_ip_retrospectives" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "personal_ip_retrospectives",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("review_key", sa.String(length=256), nullable=False),
        sa.Column("preflight_id", sa.String(length=64), nullable=False),
        sa.Column("publish_receipt_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("horizon", sa.String(length=32), nullable=False),
        sa.Column("selected_variant_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=160), nullable=False),
        sa.Column("algorithm_version", sa.String(length=160), nullable=False),
        sa.Column("metric_observation_ids_json", sa.JSON(), nullable=False),
        sa.Column("prediction_json", sa.JSON(), nullable=False),
        sa.Column("outcome_json", sa.JSON(), nullable=False),
        sa.Column("training_eligibility_json", sa.JSON(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("comparison_state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('measured','partial')", name="ck_personal_ip_retrospectives_status"),
        sa.CheckConstraint("comparison_state IN ('scored','unscored')", name="ck_personal_ip_retrospectives_comparison"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "review_key", name="uq_personal_ip_retrospectives_owner_review"),
        sa.UniqueConstraint(
            "owner_user_id",
            "publish_receipt_id",
            "horizon",
            name="uq_personal_ip_retrospectives_owner_publish_horizon",
        ),
    )
    with op.batch_alter_table("personal_ip_retrospectives", schema=None) as batch_op:
        batch_op.create_index("ix_personal_ip_retrospectives_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_index("ix_personal_ip_retrospectives_preflight_id", ["preflight_id"], unique=False)
        batch_op.create_index("ix_personal_ip_retrospectives_publish_receipt_id", ["publish_receipt_id"], unique=False)
        batch_op.create_index("ix_personal_ip_retrospectives_account_id", ["account_id"], unique=False)
        batch_op.create_index("ix_personal_ip_retrospectives_subject_id", ["subject_id"], unique=False)
        batch_op.create_index("ix_personal_ip_retrospectives_platform", ["platform"], unique=False)
        batch_op.create_index("ix_personal_ip_retrospectives_owner_created", ["owner_user_id", "created_at"], unique=False)


def downgrade() -> None:
    if "personal_ip_retrospectives" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("personal_ip_retrospectives")
