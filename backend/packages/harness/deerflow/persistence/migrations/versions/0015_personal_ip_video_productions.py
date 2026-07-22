"""Auditable Personal-IP video production orchestration

Revision ID: 0015_personal_ip_video_productions
Revises: 0014_personal_ip_platform_observations
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_personal_ip_video_productions"
down_revision: str | Sequence[str] | None = "0014_personal_ip_platform_observations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_video_productions" not in tables:
        op.create_table(
            "personal_ip_video_productions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("operation_key", sa.String(length=256), nullable=False),
            sa.Column("contract_version", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=256), nullable=False),
            sa.Column("subject_id", sa.String(length=64), nullable=True),
            sa.Column("target_account_ids_json", sa.JSON(), nullable=False),
            sa.Column("source_kind", sa.String(length=16), nullable=False),
            sa.Column("source_json", sa.JSON(), nullable=False),
            sa.Column("delivery_spec_json", sa.JSON(), nullable=False),
            sa.Column("provider_policy_json", sa.JSON(), nullable=False),
            sa.Column("budget_json", sa.JSON(), nullable=False),
            sa.Column("request_digest", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("current_stage", sa.String(length=24), nullable=False),
            sa.Column("event_count", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("source_kind IN ('idea','script')", name="ck_personal_ip_video_productions_source_kind"),
            sa.CheckConstraint(
                "status IN ('draft','running','awaiting_review','blocked','completed','cancelled')",
                name="ck_personal_ip_video_productions_status",
            ),
            sa.CheckConstraint(
                "current_stage IN ('intake','blueprint','assets','storyboard','generation','consistency','selection','finishing','delivery')",
                name="ck_personal_ip_video_productions_stage",
            ),
            sa.ForeignKeyConstraint(["subject_id"], ["personal_ip_subjects.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "operation_key",
                name="uq_personal_ip_video_productions_owner_operation",
            ),
        )
        with op.batch_alter_table("personal_ip_video_productions", schema=None) as batch_op:
            batch_op.create_index("ix_personal_ip_video_productions_owner_user_id", ["owner_user_id"], unique=False)
            batch_op.create_index("ix_personal_ip_video_productions_subject_id", ["subject_id"], unique=False)
            batch_op.create_index(
                "ix_personal_ip_video_productions_owner_updated",
                ["owner_user_id", "updated_at"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_video_production_events" not in tables:
        op.create_table(
            "personal_ip_video_production_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("production_id", sa.String(length=64), nullable=False),
            sa.Column("event_key", sa.String(length=256), nullable=False),
            sa.Column("event_digest", sa.String(length=64), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("stage", sa.String(length=24), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("entity_type", sa.String(length=24), nullable=False),
            sa.Column("entity_id", sa.String(length=128), nullable=False),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("model", sa.String(length=160), nullable=True),
            sa.Column("provider_task_id", sa.String(length=256), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("input_refs_json", sa.JSON(), nullable=False),
            sa.Column("output_refs_json", sa.JSON(), nullable=False),
            sa.Column("cost_json", sa.JSON(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('planned','running','succeeded','failed','awaiting_review','approved','rejected')",
                name="ck_personal_ip_video_production_events_status",
            ),
            sa.ForeignKeyConstraint(["production_id"], ["personal_ip_video_productions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "production_id",
                "event_key",
                name="uq_personal_ip_video_production_events_key",
            ),
            sa.UniqueConstraint(
                "production_id",
                "sequence",
                name="uq_personal_ip_video_production_events_sequence",
            ),
        )
        with op.batch_alter_table("personal_ip_video_production_events", schema=None) as batch_op:
            batch_op.create_index("ix_personal_ip_video_production_events_owner_user_id", ["owner_user_id"], unique=False)
            batch_op.create_index("ix_personal_ip_video_production_events_production_id", ["production_id"], unique=False)
            batch_op.create_index(
                "ix_personal_ip_video_production_events_production_sequence",
                ["production_id", "sequence"],
                unique=False,
            )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_video_production_events" in tables:
        op.drop_table("personal_ip_video_production_events")
    if "personal_ip_video_productions" in tables:
        op.drop_table("personal_ip_video_productions")
