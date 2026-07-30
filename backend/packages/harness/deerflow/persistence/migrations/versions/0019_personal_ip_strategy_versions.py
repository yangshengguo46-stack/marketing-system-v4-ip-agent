"""Add immutable Personal-IP operating strategy versions

Revision ID: 0019_personal_ip_strategy_versions
Revises: 0018_video_production_threads
Create Date: 2026-07-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_personal_ip_strategy_versions"
down_revision: str | Sequence[str] | None = "0018_video_production_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_strategy_versions" in tables:
        return
    op.create_table(
        "personal_ip_strategy_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("operation_key", sa.String(length=256), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("method_version", sa.String(length=80), nullable=False),
        sa.Column("person_model_json", sa.JSON(), nullable=False),
        sa.Column("business_model_json", sa.JSON(), nullable=False),
        sa.Column("benchmark_research_json", sa.JSON(), nullable=False),
        sa.Column("positioning_candidates_json", sa.JSON(), nullable=False),
        sa.Column("launch_package_json", sa.JSON(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('monetization_first','influence_first')",
            name="ck_personal_ip_strategy_mode",
        ),
        sa.CheckConstraint(
            "stage IN ('evidence_collecting','person_model_draft','business_model_draft','benchmark_researching','positioning_candidates','launch_package_ready','pilot_running','commercial_signal_observed','scaling')",
            name="ck_personal_ip_strategy_stage",
        ),
        sa.ForeignKeyConstraint(["subject_id"], ["personal_ip_subjects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_user_id",
            "operation_key",
            name="uq_personal_ip_strategy_owner_operation",
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "subject_id",
            "version",
            name="uq_personal_ip_strategy_owner_subject_version",
        ),
    )
    with op.batch_alter_table("personal_ip_strategy_versions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_personal_ip_strategy_versions_owner_user_id",
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_strategy_versions_subject_id",
            ["subject_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_strategy_owner_subject_created",
            ["owner_user_id", "subject_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_strategy_versions" in tables:
        op.drop_table("personal_ip_strategy_versions")
