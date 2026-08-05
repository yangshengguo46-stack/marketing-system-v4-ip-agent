"""Add reusable EditorialProgramVersion decisions to the content lineage.

Revision ID: 0030_personal_ip_editorial_program_versions
Revises: 0029_personal_ip_final_artifacts
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_personal_ip_editorial_program_versions"
down_revision: str | Sequence[str] | None = "0029_personal_ip_final_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROGRAM_TABLE = "personal_ip_editorial_program_versions"
_WORK_TABLE = "personal_ip_content_works"
_SUBJECT_TABLE = "personal_ip_subjects"
_WORK_COLUMN = "editorial_program_version_id"
_WORK_FK = "fk_personal_ip_content_works_editorial_program_version"
_WORK_INDEX = "ix_personal_ip_content_works_editorial_program_version_id"


def _columns(table: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {str(index["name"]) for index in sa.inspect(op.get_bind()).get_indexes(table) if index.get("name")}


def _foreign_keys(table: str) -> set[str]:
    return {str(foreign_key["name"]) for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table) if foreign_key.get("name")}


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    # Historical partial-schema test profiles may not contain the retained
    # content domain at all. Match the preceding content migrations and leave
    # those profiles untouched rather than creating an unusable half graph.
    if _WORK_TABLE not in tables or _SUBJECT_TABLE not in tables:
        return

    if _PROGRAM_TABLE not in tables:
        op.create_table(
            _PROGRAM_TABLE,
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("program_id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("subject_id", sa.String(length=64), nullable=True),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("operation_key", sa.String(length=256), nullable=False),
            sa.Column("operation_digest", sa.String(length=64), nullable=False),
            sa.Column(
                "parent_program_version_id",
                sa.String(length=64),
                nullable=True,
            ),
            sa.Column("title", sa.String(length=1000), nullable=False),
            sa.Column("decision_json", sa.JSON(), nullable=False),
            sa.Column("created_by_run_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["subject_id"],
                ["personal_ip_subjects.id"],
                name="fk_personal_ip_editorial_program_versions_subject",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "program_id",
                "version_number",
                name=("uq_personal_ip_editorial_program_versions_program_version"),
            ),
            sa.UniqueConstraint(
                "owner_user_id",
                "operation_key",
                name=("uq_personal_ip_editorial_program_versions_owner_operation"),
            ),
        )
        with op.batch_alter_table(_PROGRAM_TABLE, schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_editorial_program_versions_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_editorial_program_versions_subject_id",
                ["subject_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_editorial_program_versions_owner_program_version",
                ["owner_user_id", "program_id", "version_number"],
                unique=False,
            )

    if _WORK_COLUMN not in _columns(_WORK_TABLE):
        with op.batch_alter_table(_WORK_TABLE, schema=None) as batch_op:
            batch_op.add_column(sa.Column(_WORK_COLUMN, sa.String(length=64), nullable=True))

    indexes = _indexes(_WORK_TABLE)
    foreign_keys = _foreign_keys(_WORK_TABLE)
    with op.batch_alter_table(_WORK_TABLE, schema=None) as batch_op:
        if _WORK_FK not in foreign_keys:
            batch_op.create_foreign_key(
                _WORK_FK,
                _PROGRAM_TABLE,
                [_WORK_COLUMN],
                ["id"],
                ondelete="RESTRICT",
            )
        if _WORK_INDEX not in indexes:
            batch_op.create_index(_WORK_INDEX, [_WORK_COLUMN], unique=False)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if _WORK_TABLE in tables and _WORK_COLUMN in _columns(_WORK_TABLE):
        linked = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_content_works WHERE editorial_program_version_id IS NOT NULL")).scalar_one()
        if int(linked) > 0:
            raise RuntimeError("cannot downgrade EditorialProgramVersion binding while Owner content works remain linked; export and verify an Owner backup, then delete the linked content first")
    if _PROGRAM_TABLE in tables:
        count = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_editorial_program_versions")).scalar_one()
        if int(count) > 0:
            raise RuntimeError("cannot downgrade EditorialProgramVersion persistence while Owner decisions exist; export and verify an Owner backup, then delete the data first")

    if _WORK_TABLE in tables and _WORK_COLUMN in _columns(_WORK_TABLE):
        indexes = _indexes(_WORK_TABLE)
        foreign_keys = _foreign_keys(_WORK_TABLE)
        with op.batch_alter_table(_WORK_TABLE, schema=None) as batch_op:
            if _WORK_INDEX in indexes:
                batch_op.drop_index(_WORK_INDEX)
            if _WORK_FK in foreign_keys:
                batch_op.drop_constraint(_WORK_FK, type_="foreignkey")
            batch_op.drop_column(_WORK_COLUMN)
    if _PROGRAM_TABLE in tables:
        op.drop_table(_PROGRAM_TABLE)
