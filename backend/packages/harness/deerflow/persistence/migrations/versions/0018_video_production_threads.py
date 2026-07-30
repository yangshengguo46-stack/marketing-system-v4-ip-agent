"""Bind each video production to one customer-visible task thread

Revision ID: 0018_video_production_threads
Revises: 0017_personal_ip_brand_method
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_video_production_threads"
down_revision: str | Sequence[str] | None = "0017_personal_ip_brand_method"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "personal_ip_video_productions" not in tables:
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("personal_ip_video_productions")}
    if "thread_id" not in columns:
        with op.batch_alter_table("personal_ip_video_productions", schema=None) as batch_op:
            batch_op.add_column(sa.Column("thread_id", sa.String(length=64), nullable=True))
            batch_op.create_index(
                "ix_personal_ip_video_productions_thread_id",
                ["thread_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_video_productions_owner_thread",
                ["owner_user_id", "thread_id"],
                unique=False,
            )
            batch_op.create_unique_constraint(
                "uq_personal_ip_video_productions_owner_thread",
                ["owner_user_id", "thread_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "personal_ip_video_productions" not in tables:
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("personal_ip_video_productions")}
    if "thread_id" in columns:
        with op.batch_alter_table("personal_ip_video_productions", schema=None) as batch_op:
            batch_op.drop_constraint(
                "uq_personal_ip_video_productions_owner_thread",
                type_="unique",
            )
            batch_op.drop_index("ix_personal_ip_video_productions_owner_thread")
            batch_op.drop_index("ix_personal_ip_video_productions_thread_id")
            batch_op.drop_column("thread_id")
