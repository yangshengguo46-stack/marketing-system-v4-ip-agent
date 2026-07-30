"""Add differentiation theses and observed IP-asset effects.

Revision ID: 0020_personal_ip_differentiation
Revises: 0019_personal_ip_strategy_versions
Create Date: 2026-07-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_personal_ip_differentiation"
down_revision: str | Sequence[str] | None = "0019_personal_ip_strategy_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_differentiation_versions" not in tables:
        op.create_table(
            "personal_ip_differentiation_versions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("operation_key", sa.String(length=256), nullable=False),
            sa.Column("subject_id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("thesis_key", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("method_version", sa.String(length=80), nullable=False),
            sa.Column("primary_entity_json", sa.JSON(), nullable=False),
            sa.Column("supporting_entities_json", sa.JSON(), nullable=False),
            sa.Column("decision_context_json", sa.JSON(), nullable=False),
            sa.Column("contrast_field_json", sa.JSON(), nullable=False),
            sa.Column("proprietary_truth_json", sa.JSON(), nullable=False),
            sa.Column("strategic_difference_json", sa.JSON(), nullable=False),
            sa.Column("dramatic_engine_json", sa.JSON(), nullable=False),
            sa.Column("distinctive_encoding_json", sa.JSON(), nullable=False),
            sa.Column("operating_fit_json", sa.JSON(), nullable=False),
            sa.Column("validation_json", sa.JSON(), nullable=False),
            sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
            sa.Column("validation_summary_json", sa.JSON(), nullable=False),
            sa.Column("content_digest", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('candidate','pilot','provisionally_adopted','validated','retired')",
                name="ck_personal_ip_differentiation_status",
            ),
            sa.ForeignKeyConstraint(["subject_id"], ["personal_ip_subjects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "operation_key",
                name="uq_personal_ip_differentiation_owner_operation",
            ),
            sa.UniqueConstraint(
                "owner_user_id",
                "subject_id",
                "version",
                name="uq_personal_ip_differentiation_owner_subject_version",
            ),
        )
        with op.batch_alter_table("personal_ip_differentiation_versions", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_differentiation_versions_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_differentiation_versions_subject_id",
                ["subject_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_differentiation_owner_subject_created",
                ["owner_user_id", "subject_id", "created_at"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_differentiation_owner_subject_thesis",
                ["owner_user_id", "subject_id", "thesis_key"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_asset_observations" not in tables:
        op.create_table(
            "personal_ip_asset_observations",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("operation_key", sa.String(length=256), nullable=False),
            sa.Column("subject_id", sa.String(length=64), nullable=False),
            sa.Column("differentiation_version_id", sa.String(length=64), nullable=False),
            sa.Column("thesis_key", sa.String(length=128), nullable=False),
            sa.Column("observation_type", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("coverage_status", sa.String(length=16), nullable=False),
            sa.Column("measures_json", sa.JSON(), nullable=False),
            sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
            sa.Column("evidence_digest", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "observation_type IN ('recognition','trust','intent','adoption','conversion','economic','extension')",
                name="ck_personal_ip_asset_observation_type",
            ),
            sa.CheckConstraint(
                "source IN ('platform_metrics','platform_observation','retrospective','audience_feedback','user_research','commercial_record','product_telemetry')",
                name="ck_personal_ip_asset_observation_source",
            ),
            sa.CheckConstraint(
                "coverage_status IN ('complete','partial','unavailable')",
                name="ck_personal_ip_asset_observation_coverage",
            ),
            sa.ForeignKeyConstraint(["subject_id"], ["personal_ip_subjects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["differentiation_version_id"],
                ["personal_ip_differentiation_versions.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "operation_key",
                name="uq_personal_ip_asset_observation_owner_operation",
            ),
        )
        with op.batch_alter_table("personal_ip_asset_observations", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_asset_observations_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_asset_observations_subject_id",
                ["subject_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_asset_observations_differentiation_version_id",
                ["differentiation_version_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_asset_observation_owner_subject_observed",
                ["owner_user_id", "subject_id", "observed_at"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_asset_observation_owner_thesis_type",
                ["owner_user_id", "subject_id", "thesis_key", "observation_type"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_strategy_versions" in tables:
        columns = {
            column["name"]
            for column in sa.inspect(op.get_bind()).get_columns("personal_ip_strategy_versions")
        }
        if "differentiation_version_id" not in columns:
            with op.batch_alter_table("personal_ip_strategy_versions", schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column("differentiation_version_id", sa.String(length=64), nullable=True)
                )
                batch_op.create_index(
                    "ix_personal_ip_strategy_versions_differentiation_version_id",
                    ["differentiation_version_id"],
                    unique=False,
                )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_strategy_versions" in tables:
        columns = {
            column["name"]
            for column in sa.inspect(op.get_bind()).get_columns("personal_ip_strategy_versions")
        }
        if "differentiation_version_id" in columns:
            with op.batch_alter_table("personal_ip_strategy_versions", schema=None) as batch_op:
                batch_op.drop_index(
                    "ix_personal_ip_strategy_versions_differentiation_version_id"
                )
                batch_op.drop_column("differentiation_version_id")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_asset_observations" in tables:
        op.drop_table("personal_ip_asset_observations")
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_differentiation_versions" in tables:
        op.drop_table("personal_ip_differentiation_versions")
