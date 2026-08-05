"""Add immutable final artifacts derived from video delivery receipts.

Revision ID: 0029_personal_ip_final_artifacts
Revises: 0028_personal_ip_script_production_binding
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_personal_ip_final_artifacts"
down_revision: str | Sequence[str] | None = "0028_personal_ip_script_production_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "personal_ip_artifacts"
_PRODUCTION_TABLE = "personal_ip_video_productions"
_EVENT_TABLE = "personal_ip_video_production_events"


def upgrade() -> None:
    table_names = set(sa.inspect(op.get_bind()).get_table_names())
    # Historical test-profile databases can legitimately omit the entire
    # video-production subsystem.  Match the owning migrations' partial-schema
    # behavior instead of querying or creating foreign keys against tables that
    # do not exist.
    if _PRODUCTION_TABLE not in table_names or _EVENT_TABLE not in table_names:
        return
    table_exists = _TABLE in table_names
    completed_linked_sql = (
        """
        SELECT COUNT(*)
        FROM personal_ip_video_productions AS production
        WHERE production.contract_version = 'personal-ip-video-production-v2'
          AND production.status = 'completed'
          AND production.content_work_id IS NOT NULL
          AND production.script_version_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM personal_ip_artifacts AS artifact
              WHERE artifact.production_id = production.id
                AND artifact.role = 'final_video'
          )
        """
        if table_exists
        else """
        SELECT COUNT(*)
        FROM personal_ip_video_productions AS production
        WHERE production.contract_version = 'personal-ip-video-production-v2'
          AND production.status = 'completed'
          AND production.content_work_id IS NOT NULL
          AND production.script_version_id IS NOT NULL
        """
    )
    completed_linked = op.get_bind().execute(sa.text(completed_linked_sql)).scalar_one()
    if int(completed_linked) > 0:
        raise RuntimeError("cannot add formal final Artifact persistence while completed linked Owner productions lack an Artifact; export and verify an Owner backup, then resolve those terminal productions before upgrading")
    if table_exists:
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("production_id", sa.String(length=64), nullable=False),
        sa.Column("qa_event_id", sa.String(length=64), nullable=False),
        sa.Column("delivery_event_id", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("content_available", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("artifact_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "contract_version = 'personal-ip-final-artifact-v1'",
            name="ck_personal_ip_artifacts_contract_version",
        ),
        sa.CheckConstraint(
            "role = 'final_video'",
            name="ck_personal_ip_artifacts_role",
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_personal_ip_artifacts_size",
        ),
        sa.ForeignKeyConstraint(
            ["production_id"],
            ["personal_ip_video_productions.id"],
            name="fk_personal_ip_artifacts_production",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["qa_event_id"],
            ["personal_ip_video_production_events.id"],
            name="fk_personal_ip_artifacts_qa_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_event_id"],
            ["personal_ip_video_production_events.id"],
            name="fk_personal_ip_artifacts_delivery_event",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "production_id",
            "role",
            name="uq_personal_ip_artifacts_production_role",
        ),
        sa.UniqueConstraint(
            "delivery_event_id",
            "role",
            name="uq_personal_ip_artifacts_delivery_event_role",
        ),
    )
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        batch_op.create_index(
            "ix_personal_ip_artifacts_owner_user_id",
            ["owner_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_artifacts_production_id",
            ["production_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_artifacts_qa_event_id",
            ["qa_event_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_artifacts_delivery_event_id",
            ["delivery_event_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_artifacts_owner_created",
            ["owner_user_id", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_personal_ip_artifacts_owner_production",
            ["owner_user_id", "production_id"],
            unique=False,
        )


def downgrade() -> None:
    if _TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    count = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar_one()
    if int(count) > 0:
        raise RuntimeError("cannot downgrade final Artifact persistence while Owner artifacts exist; export and verify an Owner backup, then delete the artifacts first")
    op.drop_table(_TABLE)
