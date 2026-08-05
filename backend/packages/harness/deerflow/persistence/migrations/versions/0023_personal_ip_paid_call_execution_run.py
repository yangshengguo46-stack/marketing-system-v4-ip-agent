"""Separate paid-call proposal origin from its consuming execution run.

Revision ID: 0023_personal_ip_paid_call_execution_run
Revises: 0022_personal_ip_paid_call_admission
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_personal_ip_paid_call_execution_run"
down_revision: str | Sequence[str] | None = "0022_personal_ip_paid_call_admission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_names(table_name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {str(index["name"]) for index in sa.inspect(op.get_bind()).get_indexes(table_name) if index.get("name")}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_paid_call_scopes" in tables:
        columns = _column_names("personal_ip_paid_call_scopes")
        indexes = _index_names("personal_ip_paid_call_scopes")
        with op.batch_alter_table("personal_ip_paid_call_scopes", schema=None) as batch_op:
            if "run_id" in columns and "origin_run_id" not in columns:
                batch_op.alter_column(
                    "run_id",
                    new_column_name="origin_run_id",
                    existing_type=sa.String(length=64),
                    existing_nullable=False,
                )
            if "execution_run_id" not in columns:
                batch_op.add_column(sa.Column("execution_run_id", sa.String(length=64), nullable=True))
            for old_index in (
                "ix_personal_ip_paid_call_scopes_run_id",
                "ix_personal_ip_paid_call_scopes_owner_run",
            ):
                if old_index in indexes:
                    batch_op.drop_index(old_index)

        indexes = _index_names("personal_ip_paid_call_scopes")
        with op.batch_alter_table("personal_ip_paid_call_scopes", schema=None) as batch_op:
            if "ix_personal_ip_paid_call_scopes_origin_run_id" not in indexes:
                batch_op.create_index(
                    "ix_personal_ip_paid_call_scopes_origin_run_id",
                    ["origin_run_id"],
                    unique=False,
                )
            if "ix_personal_ip_paid_call_scopes_execution_run_id" not in indexes:
                batch_op.create_index(
                    "ix_personal_ip_paid_call_scopes_execution_run_id",
                    ["execution_run_id"],
                    unique=False,
                )
            if "ix_personal_ip_paid_call_scopes_owner_origin_run" not in indexes:
                batch_op.create_index(
                    "ix_personal_ip_paid_call_scopes_owner_origin_run",
                    ["owner_user_id", "origin_run_id"],
                    unique=False,
                )
            if "ix_personal_ip_paid_call_scopes_owner_execution_run" not in indexes:
                batch_op.create_index(
                    "ix_personal_ip_paid_call_scopes_owner_execution_run",
                    ["owner_user_id", "execution_run_id"],
                    unique=False,
                )

    if "personal_ip_paid_call_events" in tables:
        columns = _column_names("personal_ip_paid_call_events")
        if "execution_run_id" not in columns:
            with op.batch_alter_table("personal_ip_paid_call_events", schema=None) as batch_op:
                batch_op.add_column(sa.Column("execution_run_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_paid_call_events" in tables:
        columns = _column_names("personal_ip_paid_call_events")
        if "execution_run_id" in columns:
            with op.batch_alter_table("personal_ip_paid_call_events", schema=None) as batch_op:
                batch_op.drop_column("execution_run_id")

    if "personal_ip_paid_call_scopes" in tables:
        columns = _column_names("personal_ip_paid_call_scopes")
        indexes = _index_names("personal_ip_paid_call_scopes")
        with op.batch_alter_table("personal_ip_paid_call_scopes", schema=None) as batch_op:
            for new_index in (
                "ix_personal_ip_paid_call_scopes_execution_run_id",
                "ix_personal_ip_paid_call_scopes_origin_run_id",
                "ix_personal_ip_paid_call_scopes_owner_execution_run",
                "ix_personal_ip_paid_call_scopes_owner_origin_run",
            ):
                if new_index in indexes:
                    batch_op.drop_index(new_index)
            if "execution_run_id" in columns:
                batch_op.drop_column("execution_run_id")
            if "origin_run_id" in columns and "run_id" not in columns:
                batch_op.alter_column(
                    "origin_run_id",
                    new_column_name="run_id",
                    existing_type=sa.String(length=64),
                    existing_nullable=False,
                )

        indexes = _index_names("personal_ip_paid_call_scopes")
        with op.batch_alter_table("personal_ip_paid_call_scopes", schema=None) as batch_op:
            if "ix_personal_ip_paid_call_scopes_run_id" not in indexes:
                batch_op.create_index(
                    "ix_personal_ip_paid_call_scopes_run_id",
                    ["run_id"],
                    unique=False,
                )
            if "ix_personal_ip_paid_call_scopes_owner_run" not in indexes:
                batch_op.create_index(
                    "ix_personal_ip_paid_call_scopes_owner_run",
                    ["owner_user_id", "run_id"],
                    unique=False,
                )
