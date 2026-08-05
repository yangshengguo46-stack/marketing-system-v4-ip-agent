"""Add the minimal Personal-IP content lineage.

Revision ID: 0027_personal_ip_content_lineage
Revises: 0026_personal_ip_paid_call_submission_recovery
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_personal_ip_content_lineage"
down_revision: str | Sequence[str] | None = "0026_personal_ip_paid_call_submission_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_content_works" not in tables:
        op.create_table(
            "personal_ip_content_works",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("objective_id", sa.String(length=64), nullable=False),
            sa.Column("thread_id", sa.String(length=128), nullable=True),
            sa.Column("subject_id", sa.String(length=64), nullable=True),
            sa.Column("operation_key", sa.String(length=256), nullable=False),
            sa.Column("operation_digest", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=1000), nullable=False),
            sa.Column("entry_route", sa.String(length=32), nullable=False),
            sa.Column("objective_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_by_run_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "entry_route IN ('zero_start','benchmark')",
                name="ck_personal_ip_content_works_entry_route",
            ),
            sa.CheckConstraint(
                "status IN ('active','archived')",
                name="ck_personal_ip_content_works_status",
            ),
            sa.ForeignKeyConstraint(["subject_id"], ["personal_ip_subjects.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "operation_key",
                name="uq_personal_ip_content_works_owner_operation",
            ),
            sa.UniqueConstraint(
                "objective_id",
                name="uq_personal_ip_content_works_objective",
            ),
        )
        with op.batch_alter_table("personal_ip_content_works", schema=None) as batch_op:
            batch_op.create_index("ix_personal_ip_content_works_owner_user_id", ["owner_user_id"], unique=False)
            batch_op.create_index("ix_personal_ip_content_works_subject_id", ["subject_id"], unique=False)
            batch_op.create_index(
                "ix_personal_ip_content_works_owner_status_updated",
                ["owner_user_id", "status", "updated_at"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_content_works_owner_subject",
                ["owner_user_id", "subject_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_content_works_owner_thread",
                ["owner_user_id", "thread_id"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_breakdown_versions" not in tables:
        op.create_table(
            "personal_ip_breakdown_versions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("content_work_id", sa.String(length=64), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("commit_key", sa.String(length=256), nullable=False),
            sa.Column("commit_digest", sa.String(length=64), nullable=False),
            sa.Column("source_kind", sa.String(length=32), nullable=False),
            sa.Column("source_identity_json", sa.JSON(), nullable=False),
            sa.Column("source_digest", sa.String(length=64), nullable=True),
            sa.Column("evidence_request_id", sa.String(length=80), nullable=True),
            sa.Column("evidence_item_index", sa.Integer(), nullable=True),
            sa.Column("evidence_contract_version", sa.String(length=80), nullable=True),
            sa.Column("evidence_payload_digest", sa.String(length=64), nullable=True),
            sa.Column(
                "evidence_snapshot_json",
                sa.JSON(none_as_null=True),
                nullable=True,
            ),
            sa.Column("observations_json", sa.JSON(), nullable=False),
            sa.Column("interpretations_json", sa.JSON(), nullable=False),
            sa.Column("limitations_json", sa.JSON(), nullable=False),
            sa.Column("created_by_run_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "source_kind IN ('platform_content','uploaded_file','owner_material')",
                name="ck_personal_ip_breakdown_versions_source_kind",
            ),
            sa.CheckConstraint(
                "(source_kind = 'owner_material' AND evidence_request_id IS NULL AND evidence_item_index IS NULL "
                "AND evidence_contract_version IS NULL AND evidence_payload_digest IS NULL "
                "AND evidence_snapshot_json IS NULL) OR "
                "(source_kind IN ('platform_content','uploaded_file') AND source_digest IS NOT NULL "
                "AND evidence_request_id IS NOT NULL AND evidence_item_index IS NOT NULL "
                "AND evidence_contract_version IS NOT NULL AND evidence_payload_digest IS NOT NULL "
                "AND evidence_snapshot_json IS NOT NULL)",
                name="ck_personal_ip_breakdown_versions_evidence_binding",
            ),
            sa.ForeignKeyConstraint(["content_work_id"], ["personal_ip_content_works.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "content_work_id",
                "version_number",
                name="uq_personal_ip_breakdown_versions_work_version",
            ),
            sa.UniqueConstraint(
                "content_work_id",
                "commit_key",
                name="uq_personal_ip_breakdown_versions_work_commit",
            ),
        )
        with op.batch_alter_table("personal_ip_breakdown_versions", schema=None) as batch_op:
            batch_op.create_index("ix_personal_ip_breakdown_versions_owner_user_id", ["owner_user_id"], unique=False)
            batch_op.create_index("ix_personal_ip_breakdown_versions_content_work_id", ["content_work_id"], unique=False)
            batch_op.create_index(
                "ix_personal_ip_breakdown_versions_owner_work_version",
                ["owner_user_id", "content_work_id", "version_number"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_direction_versions" not in tables:
        op.create_table(
            "personal_ip_direction_versions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("content_work_id", sa.String(length=64), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("commit_key", sa.String(length=256), nullable=False),
            sa.Column("commit_digest", sa.String(length=64), nullable=False),
            sa.Column("parent_direction_version_id", sa.String(length=64), nullable=True),
            sa.Column("breakdown_version_ids_json", sa.JSON(), nullable=False),
            sa.Column("objective_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("direction_json", sa.JSON(), nullable=False),
            sa.Column("created_by_run_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["content_work_id"], ["personal_ip_content_works.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "content_work_id",
                "version_number",
                name="uq_personal_ip_direction_versions_work_version",
            ),
            sa.UniqueConstraint(
                "content_work_id",
                "commit_key",
                name="uq_personal_ip_direction_versions_work_commit",
            ),
        )
        with op.batch_alter_table("personal_ip_direction_versions", schema=None) as batch_op:
            batch_op.create_index("ix_personal_ip_direction_versions_owner_user_id", ["owner_user_id"], unique=False)
            batch_op.create_index("ix_personal_ip_direction_versions_content_work_id", ["content_work_id"], unique=False)
            batch_op.create_index(
                "ix_personal_ip_direction_versions_owner_work_version",
                ["owner_user_id", "content_work_id", "version_number"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_script_versions" not in tables:
        op.create_table(
            "personal_ip_script_versions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("content_work_id", sa.String(length=64), nullable=False),
            sa.Column("direction_version_id", sa.String(length=64), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("commit_key", sa.String(length=256), nullable=False),
            sa.Column("commit_digest", sa.String(length=64), nullable=False),
            sa.Column("parent_script_version_id", sa.String(length=64), nullable=True),
            sa.Column("title", sa.String(length=1000), nullable=False),
            sa.Column("story_mode", sa.String(length=16), nullable=False),
            sa.Column("script_text", sa.Text(), nullable=False),
            sa.Column("claim_basis_json", sa.JSON(), nullable=False),
            sa.Column("creative_elements_json", sa.JSON(), nullable=False),
            sa.Column("story_engine_seed_json", sa.JSON(), nullable=True),
            sa.Column("locked_story", sa.Text(), nullable=True),
            sa.Column("locked_story_digest", sa.String(length=64), nullable=True),
            sa.Column("production_notes_json", sa.JSON(), nullable=False),
            sa.Column("created_by_run_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "story_mode IN ('factual','fictional','hybrid')",
                name="ck_personal_ip_script_versions_story_mode",
            ),
            sa.ForeignKeyConstraint(["content_work_id"], ["personal_ip_content_works.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["direction_version_id"], ["personal_ip_direction_versions.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "content_work_id",
                "version_number",
                name="uq_personal_ip_script_versions_work_version",
            ),
            sa.UniqueConstraint(
                "content_work_id",
                "commit_key",
                name="uq_personal_ip_script_versions_work_commit",
            ),
        )
        with op.batch_alter_table("personal_ip_script_versions", schema=None) as batch_op:
            batch_op.create_index("ix_personal_ip_script_versions_owner_user_id", ["owner_user_id"], unique=False)
            batch_op.create_index("ix_personal_ip_script_versions_content_work_id", ["content_work_id"], unique=False)
            batch_op.create_index("ix_personal_ip_script_versions_direction_version_id", ["direction_version_id"], unique=False)
            batch_op.create_index(
                "ix_personal_ip_script_versions_owner_work_version",
                ["owner_user_id", "content_work_id", "version_number"],
                unique=False,
            )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in (
        "personal_ip_script_versions",
        "personal_ip_direction_versions",
        "personal_ip_breakdown_versions",
        "personal_ip_content_works",
    ):
        if table_name in tables:
            count = op.get_bind().execute(sa.text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one()
            if int(count) > 0:
                raise RuntimeError("cannot downgrade Personal-IP content lineage while Owner data exists; export and verify an Owner backup, then delete the data first")
    for table_name in (
        "personal_ip_script_versions",
        "personal_ip_direction_versions",
        "personal_ip_breakdown_versions",
        "personal_ip_content_works",
    ):
        if table_name in tables:
            op.drop_table(table_name)
