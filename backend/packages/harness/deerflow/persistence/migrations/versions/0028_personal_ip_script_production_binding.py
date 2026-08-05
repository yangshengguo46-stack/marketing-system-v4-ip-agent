"""Bind video production receipts to immutable ScriptVersions.

Revision ID: 0028_personal_ip_script_production_binding
Revises: 0027_personal_ip_content_lineage
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_personal_ip_script_production_binding"
down_revision: str | Sequence[str] | None = "0027_personal_ip_content_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "personal_ip_video_productions"
_CONTENT_CHECK = "ck_personal_ip_video_productions_content_source"
_WORK_FK = "fk_personal_ip_video_productions_content_work"
_SCRIPT_FK = "fk_personal_ip_video_productions_script_version"


def _columns() -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}


def _indexes() -> set[str]:
    return {str(index["name"]) for index in sa.inspect(op.get_bind()).get_indexes(_TABLE) if index.get("name")}


def _foreign_keys() -> set[str]:
    return {str(foreign_key["name"]) for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(_TABLE) if foreign_key.get("name")}


def _checks() -> set[str]:
    return {str(check["name"]) for check in sa.inspect(op.get_bind()).get_check_constraints(_TABLE) if check.get("name")}


def upgrade() -> None:
    if _TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    columns = _columns()
    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        if "content_work_id" not in columns:
            batch_op.add_column(sa.Column("content_work_id", sa.String(length=64), nullable=True))
        if "script_version_id" not in columns:
            batch_op.add_column(sa.Column("script_version_id", sa.String(length=64), nullable=True))

    columns = _columns()
    if {"content_work_id", "script_version_id"}.issubset(columns):
        indexes = _indexes()
        foreign_keys = _foreign_keys()
        checks = _checks()
        with op.batch_alter_table(_TABLE, schema=None) as batch_op:
            if _WORK_FK not in foreign_keys:
                batch_op.create_foreign_key(
                    _WORK_FK,
                    "personal_ip_content_works",
                    ["content_work_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
            if _SCRIPT_FK not in foreign_keys:
                batch_op.create_foreign_key(
                    _SCRIPT_FK,
                    "personal_ip_script_versions",
                    ["script_version_id"],
                    ["id"],
                    ondelete="RESTRICT",
                )
            if _CONTENT_CHECK not in checks:
                batch_op.create_check_constraint(
                    _CONTENT_CHECK,
                    "(content_work_id IS NULL AND script_version_id IS NULL) OR (content_work_id IS NOT NULL AND script_version_id IS NOT NULL AND source_kind = 'script')",
                )
            for name, fields in (
                (
                    "ix_personal_ip_video_productions_content_work_id",
                    ["content_work_id"],
                ),
                (
                    "ix_personal_ip_video_productions_script_version_id",
                    ["script_version_id"],
                ),
                (
                    "ix_personal_ip_video_productions_owner_content_work",
                    ["owner_user_id", "content_work_id"],
                ),
                (
                    "ix_personal_ip_video_productions_owner_script_version",
                    ["owner_user_id", "script_version_id"],
                ),
            ):
                if name not in indexes:
                    batch_op.create_index(name, fields, unique=False)


def downgrade() -> None:
    if _TABLE not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    columns = _columns()
    if {"content_work_id", "script_version_id"}.issubset(columns):
        linked = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_video_productions WHERE content_work_id IS NOT NULL OR script_version_id IS NOT NULL")).scalar_one()
        if int(linked) > 0:
            raise RuntimeError("cannot downgrade ScriptVersion production binding while linked Owner data exists; export and verify an Owner backup, then delete the linked productions first")
        with op.batch_alter_table(_TABLE, schema=None) as batch_op:
            batch_op.drop_index("ix_personal_ip_video_productions_owner_script_version")
            batch_op.drop_index("ix_personal_ip_video_productions_owner_content_work")
            batch_op.drop_index("ix_personal_ip_video_productions_script_version_id")
            batch_op.drop_index("ix_personal_ip_video_productions_content_work_id")
            batch_op.drop_constraint(_CONTENT_CHECK, type_="check")
            batch_op.drop_constraint(_SCRIPT_FK, type_="foreignkey")
            batch_op.drop_constraint(_WORK_FK, type_="foreignkey")
            batch_op.drop_column("script_version_id")
            batch_op.drop_column("content_work_id")
