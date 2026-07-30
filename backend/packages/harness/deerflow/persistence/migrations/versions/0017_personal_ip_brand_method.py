"""Version Personal-IP identity and evidence-bound reputation

Revision ID: 0017_personal_ip_brand_method
Revises: 0016_personal_ip_auto_evidence
Create Date: 2026-07-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_personal_ip_brand_method"
down_revision: str | Sequence[str] | None = "0016_personal_ip_auto_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_brand_identity_versions" not in tables:
        op.create_table(
            "personal_ip_brand_identity_versions",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("operation_key", sa.String(length=256), nullable=False),
            sa.Column("subject_id", sa.String(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("method_version", sa.String(length=80), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("identity_prism_json", sa.JSON(), nullable=False),
            sa.Column("expression_star_json", sa.JSON(), nullable=False),
            sa.Column("reputation_intent_json", sa.JSON(), nullable=False),
            sa.Column("evidence_basis_json", sa.JSON(), nullable=False),
            sa.Column("content_digest", sa.String(length=64), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('draft','active','superseded')",
                name="ck_personal_ip_brand_identity_status",
            ),
            sa.ForeignKeyConstraint(
                ["subject_id"],
                ["personal_ip_subjects.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "operation_key",
                name="uq_personal_ip_brand_identity_owner_operation",
            ),
            sa.UniqueConstraint(
                "owner_user_id",
                "subject_id",
                "version",
                name="uq_personal_ip_brand_identity_owner_subject_version",
            ),
        )
        with op.batch_alter_table("personal_ip_brand_identity_versions", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_brand_identity_versions_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_brand_identity_versions_subject_id",
                ["subject_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_brand_identity_owner_subject_status",
                ["owner_user_id", "subject_id", "status"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_reputation_snapshots" not in tables:
        op.create_table(
            "personal_ip_reputation_snapshots",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("operation_key", sa.String(length=256), nullable=False),
            sa.Column("subject_id", sa.String(length=64), nullable=False),
            sa.Column("identity_version_id", sa.String(length=64), nullable=False),
            sa.Column("horizon", sa.String(length=32), nullable=False),
            sa.Column("method_version", sa.String(length=80), nullable=False),
            sa.Column("perceived_identity_json", sa.JSON(), nullable=False),
            sa.Column("reputation_json", sa.JSON(), nullable=False),
            sa.Column("alignment_json", sa.JSON(), nullable=False),
            sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
            sa.Column("model_version", sa.String(length=160), nullable=False),
            sa.Column("algorithm_version", sa.String(length=160), nullable=False),
            sa.Column("evidence_digest", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('measured','partial')",
                name="ck_personal_ip_reputation_status",
            ),
            sa.ForeignKeyConstraint(
                ["identity_version_id"],
                ["personal_ip_brand_identity_versions.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["subject_id"],
                ["personal_ip_subjects.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "operation_key",
                name="uq_personal_ip_reputation_owner_operation",
            ),
        )
        with op.batch_alter_table("personal_ip_reputation_snapshots", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_reputation_snapshots_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_reputation_snapshots_subject_id",
                ["subject_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_reputation_snapshots_identity_version_id",
                ["identity_version_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_reputation_owner_subject_created",
                ["owner_user_id", "subject_id", "created_at"],
                unique=False,
            )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_reputation_snapshots" in tables:
        op.drop_table("personal_ip_reputation_snapshots")
    if "personal_ip_brand_identity_versions" in tables:
        op.drop_table("personal_ip_brand_identity_versions")
