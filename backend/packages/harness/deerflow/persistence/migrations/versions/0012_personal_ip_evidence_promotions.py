"""Personal-IP cross-sample evidence promotions

Revision ID: 0012_personal_ip_evidence_promotions
Revises: 0011_personal_ip_retrospectives
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_personal_ip_evidence_promotions"
down_revision: str | Sequence[str] | None = "0011_personal_ip_retrospectives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if "personal_ip_evidence_promotions" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "personal_ip_evidence_promotions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("proposal_key", sa.String(length=256), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("retrospective_ids_json", sa.JSON(), nullable=False),
        sa.Column("evidence_summary_json", sa.JSON(), nullable=False),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.Column("minimum_support", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("decisions_json", sa.JSON(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "evidence_type IN ('audience_pattern','content_pattern','platform_pattern','training_cohort')",
            name="ck_personal_ip_evidence_promotions_type",
        ),
        sa.CheckConstraint("status IN ('proposed','approved','rejected')", name="ck_personal_ip_evidence_promotions_status"),
        sa.CheckConstraint("minimum_support >= 3 AND minimum_support <= 100", name="ck_personal_ip_evidence_promotions_support"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "proposal_key", name="uq_personal_ip_evidence_promotions_owner_proposal"),
    )
    with op.batch_alter_table("personal_ip_evidence_promotions", schema=None) as batch_op:
        batch_op.create_index("ix_personal_ip_evidence_promotions_owner_user_id", ["owner_user_id"], unique=False)
        batch_op.create_index(
            "ix_personal_ip_evidence_promotions_owner_status_created",
            ["owner_user_id", "status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    if "personal_ip_evidence_promotions" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("personal_ip_evidence_promotions")
