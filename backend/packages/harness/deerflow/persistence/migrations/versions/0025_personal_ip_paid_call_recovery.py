"""Add encrypted MediaKit task recovery to existing paid-call scopes.

Revision ID: 0025_personal_ip_paid_call_recovery
Revises: 0024_personal_ip_paid_call_operator_cap
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_personal_ip_paid_call_recovery"
down_revision: str | Sequence[str] | None = "0024_personal_ip_paid_call_operator_cap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPES = "personal_ip_paid_call_scopes"
_EVENTS = "personal_ip_paid_call_events"
_EVENT_CHECK = "ck_personal_ip_paid_call_events_type"
_OLD_EVENT_TYPES = "event_type IN ('requested','approved','rejected','reserved','budget_rejected','admitted','released','settled','reconciliation_required')"
_NEW_EVENT_TYPES = _OLD_EVENT_TYPES[:-1] + ",'provider_task')"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table)}


def _checks(table: str) -> set[str]:
    return {str(check["name"]) for check in sa.inspect(op.get_bind()).get_check_constraints(table) if check.get("name")}


def _replace_event_check(expression: str) -> None:
    checks = _checks(_EVENTS)
    with op.batch_alter_table(_EVENTS, schema=None) as batch_op:
        if _EVENT_CHECK in checks:
            batch_op.drop_constraint(_EVENT_CHECK, type_="check")
        batch_op.create_check_constraint(_EVENT_CHECK, expression)


def upgrade() -> None:
    tables = _tables()
    if _SCOPES in tables:
        columns = _columns(_SCOPES)
        inspector = sa.inspect(op.get_bind())
        checks = _checks(_SCOPES)
        indexes = {str(index["name"]) for index in inspector.get_indexes(_SCOPES) if index.get("name")}
        uniques = {str(constraint["name"]) for constraint in inspector.get_unique_constraints(_SCOPES) if constraint.get("name")}
        with op.batch_alter_table(_SCOPES, schema=None) as batch_op:
            additions = (
                sa.Column("provider_task_status", sa.String(length=16), nullable=True),
                sa.Column("encrypted_provider_client_token", sa.Text(), nullable=True),
                sa.Column("provider_client_token_sha256", sa.String(length=64), nullable=True),
                sa.Column("encrypted_provider_task_id", sa.Text(), nullable=True),
                sa.Column("provider_task_id_sha256", sa.String(length=64), nullable=True),
                sa.Column("provider_terminal_status", sa.String(length=16), nullable=True),
                sa.Column("encrypted_provider_terminal_json", sa.Text(), nullable=True),
                sa.Column("provider_terminal_sha256", sa.String(length=64), nullable=True),
            )
            for column in additions:
                if column.name not in columns:
                    batch_op.add_column(column)
            if "uq_personal_ip_paid_call_scopes_provider_client_token" not in uniques:
                batch_op.create_unique_constraint(
                    "uq_personal_ip_paid_call_scopes_provider_client_token",
                    ["provider_client_token_sha256"],
                )
            if "ck_personal_ip_paid_call_scopes_provider_task_status" not in checks:
                batch_op.create_check_constraint(
                    "ck_personal_ip_paid_call_scopes_provider_task_status",
                    "provider_task_status IS NULL OR provider_task_status IN ('submitting','submitted','running','terminal')",
                )
            if "ck_personal_ip_paid_call_scopes_provider_terminal_status" not in checks:
                batch_op.create_check_constraint(
                    "ck_personal_ip_paid_call_scopes_provider_terminal_status",
                    "provider_terminal_status IS NULL OR provider_terminal_status IN ('completed','failed','canceled')",
                )
            if "ck_personal_ip_paid_call_scopes_provider_task_state" not in checks:
                batch_op.create_check_constraint(
                    "ck_personal_ip_paid_call_scopes_provider_task_state",
                    "(provider_task_status IS NULL AND encrypted_provider_client_token IS NULL "
                    "AND provider_client_token_sha256 IS NULL AND encrypted_provider_task_id IS NULL "
                    "AND provider_task_id_sha256 IS NULL AND provider_terminal_status IS NULL "
                    "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
                    "(provider_task_status = 'submitting' AND encrypted_provider_client_token IS NOT NULL "
                    "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_task_id IS NULL "
                    "AND provider_task_id_sha256 IS NULL AND provider_terminal_status IS NULL "
                    "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
                    "(provider_task_status IN ('submitted','running') AND encrypted_provider_client_token IS NOT NULL "
                    "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_task_id IS NOT NULL "
                    "AND provider_task_id_sha256 IS NOT NULL AND provider_terminal_status IS NULL "
                    "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
                    "(provider_task_status = 'terminal' AND encrypted_provider_client_token IS NOT NULL "
                    "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_task_id IS NOT NULL "
                    "AND provider_task_id_sha256 IS NOT NULL AND provider_terminal_status IS NOT NULL "
                    "AND encrypted_provider_terminal_json IS NOT NULL AND provider_terminal_sha256 IS NOT NULL)",
                )
            if "updated_at" in columns and "ix_personal_ip_paid_call_scopes_provider_task_recovery" not in indexes:
                batch_op.create_index(
                    "ix_personal_ip_paid_call_scopes_provider_task_recovery",
                    ["provider_task_status", "updated_at"],
                    unique=False,
                )
    if _EVENTS in tables:
        _replace_event_check(_NEW_EVENT_TYPES)


def downgrade() -> None:
    tables = _tables()
    if _SCOPES in tables:
        active = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_paid_call_scopes WHERE provider_task_status IS NOT NULL")).scalar_one()
        if int(active) > 0:
            raise RuntimeError("cannot downgrade paid-call recovery while provider tasks exist")
    if _EVENTS in tables:
        provider_events = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_paid_call_events WHERE event_type = 'provider_task'")).scalar_one()
        if int(provider_events) > 0:
            raise RuntimeError("cannot downgrade paid-call recovery while provider task events exist")
        _replace_event_check(_OLD_EVENT_TYPES)
    if _SCOPES in tables:
        indexes = {str(index["name"]) for index in sa.inspect(op.get_bind()).get_indexes(_SCOPES) if index.get("name")}
        with op.batch_alter_table(_SCOPES, schema=None) as batch_op:
            if "ix_personal_ip_paid_call_scopes_provider_task_recovery" in indexes:
                batch_op.drop_index("ix_personal_ip_paid_call_scopes_provider_task_recovery")
            batch_op.drop_constraint(
                "ck_personal_ip_paid_call_scopes_provider_task_state",
                type_="check",
            )
            batch_op.drop_constraint(
                "ck_personal_ip_paid_call_scopes_provider_terminal_status",
                type_="check",
            )
            batch_op.drop_constraint(
                "ck_personal_ip_paid_call_scopes_provider_task_status",
                type_="check",
            )
            batch_op.drop_constraint(
                "uq_personal_ip_paid_call_scopes_provider_client_token",
                type_="unique",
            )
            for column in (
                "provider_terminal_sha256",
                "encrypted_provider_terminal_json",
                "provider_terminal_status",
                "provider_task_id_sha256",
                "encrypted_provider_task_id",
                "provider_client_token_sha256",
                "encrypted_provider_client_token",
                "provider_task_status",
            ):
                batch_op.drop_column(column)
