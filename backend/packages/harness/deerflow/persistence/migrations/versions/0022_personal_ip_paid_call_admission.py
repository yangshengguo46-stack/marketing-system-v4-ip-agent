"""Add one-shot paid-call admission scopes and events.

Revision ID: 0022_personal_ip_paid_call_admission
Revises: 0021_personal_ip_semantic_layer_retirement
Create Date: 2026-08-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_personal_ip_paid_call_admission"
down_revision: str | Sequence[str] | None = "0021_personal_ip_semantic_layer_retirement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_paid_call_scopes" not in tables:
        op.create_table(
            "personal_ip_paid_call_scopes",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("request_key", sa.String(length=256), nullable=False),
            sa.Column("scope_kind", sa.String(length=16), nullable=False),
            sa.Column("thread_id", sa.String(length=64), nullable=False),
            sa.Column("run_id", sa.String(length=64), nullable=False),
            sa.Column("server_name", sa.String(length=128), nullable=False),
            sa.Column("tool_name", sa.String(length=128), nullable=False),
            sa.Column("tool_args_sha256", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("capability", sa.String(length=80), nullable=False),
            sa.Column("model", sa.String(length=160), nullable=False),
            sa.Column("sku", sa.String(length=160), nullable=False),
            sa.Column("provider_label", sa.String(length=120), nullable=False),
            sa.Column("capability_label", sa.String(length=120), nullable=False),
            sa.Column("object_ref_label", sa.String(length=96), nullable=False),
            sa.Column("source_duration_millis", sa.BigInteger(), nullable=False),
            sa.Column("source_sha256", sa.String(length=64), nullable=False),
            sa.Column("stage_digest", sa.String(length=64), nullable=False),
            sa.Column("provider_request_sha256", sa.String(length=64), nullable=False),
            sa.Column("maximum_amount_micros", sa.BigInteger(), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False),
            sa.Column("billing_basis", sa.String(length=160), nullable=False),
            sa.Column("price_status", sa.String(length=16), nullable=False),
            sa.Column("policy_version", sa.String(length=80), nullable=False),
            sa.Column("price_version", sa.String(length=80), nullable=False),
            sa.Column("provider_input_attested", sa.Boolean(), nullable=False),
            sa.Column("evidence_coverage", sa.String(length=16), nullable=False),
            sa.Column("warning_code", sa.String(length=80), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("request_digest", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("event_count", sa.Integer(), nullable=False),
            sa.Column("reserved_amount_micros", sa.BigInteger(), nullable=False),
            sa.Column("settled_amount_micros", sa.BigInteger(), nullable=True),
            sa.Column("admission_jti_hash", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint("scope_kind = 'run'", name="ck_personal_ip_paid_call_scopes_kind"),
            sa.CheckConstraint(
                "status IN ('requested','approved','rejected','reserved','budget_rejected','admitted','released','settled','reconciliation_required')",
                name="ck_personal_ip_paid_call_scopes_status",
            ),
            sa.CheckConstraint(
                "(price_status = 'unknown' AND maximum_amount_micros IS NULL) OR (price_status = 'quoted' AND maximum_amount_micros > 0)",
                name="ck_personal_ip_paid_call_scopes_price_state",
            ),
            sa.CheckConstraint(
                "source_duration_millis > 0",
                name="ck_personal_ip_paid_call_scopes_duration_positive",
            ),
            sa.CheckConstraint(
                "evidence_coverage IN ('partial','complete')",
                name="ck_personal_ip_paid_call_scopes_coverage",
            ),
            sa.CheckConstraint(
                "reserved_amount_micros >= 0",
                name="ck_personal_ip_paid_call_scopes_reserved_nonnegative",
            ),
            sa.CheckConstraint(
                "settled_amount_micros IS NULL OR settled_amount_micros >= 0",
                name="ck_personal_ip_paid_call_scopes_settled_nonnegative",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "owner_user_id",
                "request_key",
                name="uq_personal_ip_paid_call_scopes_owner_request",
            ),
            sa.UniqueConstraint(
                "admission_jti_hash",
                name="uq_personal_ip_paid_call_scopes_admission_jti",
            ),
        )
        with op.batch_alter_table("personal_ip_paid_call_scopes", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_paid_call_scopes_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_paid_call_scopes_thread_id",
                ["thread_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_paid_call_scopes_run_id",
                ["run_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_paid_call_scopes_owner_run",
                ["owner_user_id", "run_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_paid_call_scopes_owner_updated",
                ["owner_user_id", "updated_at"],
                unique=False,
            )

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_paid_call_events" not in tables:
        op.create_table(
            "personal_ip_paid_call_events",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("scope_id", sa.String(length=64), nullable=False),
            sa.Column("event_key", sa.String(length=256), nullable=False),
            sa.Column("event_digest", sa.String(length=64), nullable=False),
            sa.Column("request_digest", sa.String(length=64), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("amount_micros", sa.BigInteger(), nullable=True),
            sa.Column("proof_digest", sa.String(length=64), nullable=True),
            sa.Column("admission_jti_hash", sa.String(length=64), nullable=True),
            sa.Column("reason_code", sa.String(length=80), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "event_type IN ('requested','approved','rejected','reserved','budget_rejected','admitted','released','settled','reconciliation_required')",
                name="ck_personal_ip_paid_call_events_type",
            ),
            sa.CheckConstraint(
                "amount_micros IS NULL OR amount_micros >= 0",
                name="ck_personal_ip_paid_call_events_amount_nonnegative",
            ),
            sa.ForeignKeyConstraint(
                ["scope_id"],
                ["personal_ip_paid_call_scopes.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "scope_id",
                "event_key",
                name="uq_personal_ip_paid_call_events_key",
            ),
            sa.UniqueConstraint(
                "scope_id",
                "sequence",
                name="uq_personal_ip_paid_call_events_sequence",
            ),
        )
        with op.batch_alter_table("personal_ip_paid_call_events", schema=None) as batch_op:
            batch_op.create_index(
                "ix_personal_ip_paid_call_events_owner_user_id",
                ["owner_user_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_paid_call_events_scope_id",
                ["scope_id"],
                unique=False,
            )
            batch_op.create_index(
                "ix_personal_ip_paid_call_events_scope_sequence",
                ["scope_id", "sequence"],
                unique=False,
            )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "personal_ip_paid_call_events" in tables:
        op.drop_table("personal_ip_paid_call_events")
    if "personal_ip_paid_call_scopes" in tables:
        op.drop_table("personal_ip_paid_call_scopes")
