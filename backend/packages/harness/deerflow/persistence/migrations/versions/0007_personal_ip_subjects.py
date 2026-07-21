"""personal IP operating subjects

Revision ID: 0007_personal_ip_subjects
Revises: 0006_personal_ip_accounts
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_personal_ip_subjects"
down_revision: str | Sequence[str] | None = "0006_personal_ip_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "personal_ip_subjects" not in _table_names():
        op.create_table(
            "personal_ip_subjects",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=False),
            sa.Column("subject_type", sa.String(length=24), nullable=False),
            sa.Column("relationship", sa.String(length=24), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    subject_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("personal_ip_subjects")}
    with op.batch_alter_table("personal_ip_subjects", schema=None) as batch_op:
        if "ix_personal_ip_subjects_owner_user_id" not in subject_indexes:
            batch_op.create_index(
                "ix_personal_ip_subjects_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
        if "ix_personal_ip_subjects_owner_status_updated" not in subject_indexes:
            batch_op.create_index(
                "ix_personal_ip_subjects_owner_status_updated",
                ["owner_user_id", "status", "updated_at"],
                unique=False,
            )
        if "ix_personal_ip_subjects_owner_relationship" not in subject_indexes:
            batch_op.create_index(
                "ix_personal_ip_subjects_owner_relationship",
                ["owner_user_id", "relationship"],
                unique=False,
            )

    from deerflow.persistence.migrations._helpers import safe_add_column

    safe_add_column(
        "personal_ip_accounts",
        sa.Column("subject_id", sa.String(length=64), nullable=True),
    )
    account_inspector = sa.inspect(op.get_bind())
    account_indexes = {index["name"] for index in account_inspector.get_indexes("personal_ip_accounts")}
    account_foreign_keys = {foreign_key.get("name") for foreign_key in account_inspector.get_foreign_keys("personal_ip_accounts")}
    with op.batch_alter_table("personal_ip_accounts", schema=None) as batch_op:
        if "ix_personal_ip_accounts_subject_id" not in account_indexes:
            batch_op.create_index(
                "ix_personal_ip_accounts_subject_id",
                ["subject_id"],
                unique=False,
            )
        if "ix_personal_ip_accounts_owner_subject" not in account_indexes:
            batch_op.create_index(
                "ix_personal_ip_accounts_owner_subject",
                ["owner_user_id", "subject_id"],
                unique=False,
            )
        if "fk_personal_ip_accounts_subject_id" not in account_foreign_keys:
            batch_op.create_foreign_key(
                "fk_personal_ip_accounts_subject_id",
                "personal_ip_subjects",
                ["subject_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    if "personal_ip_accounts" in _table_names():
        with op.batch_alter_table("personal_ip_accounts", schema=None) as batch_op:
            batch_op.drop_constraint("fk_personal_ip_accounts_subject_id", type_="foreignkey")
            batch_op.drop_index("ix_personal_ip_accounts_owner_subject")
            batch_op.drop_index("ix_personal_ip_accounts_subject_id")
            batch_op.drop_column("subject_id")
    if "personal_ip_subjects" in _table_names():
        op.drop_table("personal_ip_subjects")
