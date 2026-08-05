"""Persist the exact encrypted provider submission needed for safe recovery.

Revision ID: 0026_personal_ip_paid_call_submission_recovery
Revises: 0025_personal_ip_paid_call_recovery
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_personal_ip_paid_call_submission_recovery"
down_revision: str | Sequence[str] | None = "0025_personal_ip_paid_call_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPES = "personal_ip_paid_call_scopes"
_STATE_CHECK = "ck_personal_ip_paid_call_scopes_provider_task_state"

_OLD_STATE_EXPRESSION = (
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
    "AND encrypted_provider_terminal_json IS NOT NULL AND provider_terminal_sha256 IS NOT NULL)"
)

_NEW_STATE_EXPRESSION = (
    "(provider_task_status IS NULL AND encrypted_provider_client_token IS NULL "
    "AND provider_client_token_sha256 IS NULL AND encrypted_provider_submission_json IS NULL "
    "AND provider_submission_sha256 IS NULL AND encrypted_provider_task_id IS NULL "
    "AND provider_task_id_sha256 IS NULL AND provider_terminal_status IS NULL "
    "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
    "(provider_task_status = 'submitting' AND encrypted_provider_client_token IS NOT NULL "
    "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_submission_json IS NOT NULL "
    "AND provider_submission_sha256 IS NOT NULL AND encrypted_provider_task_id IS NULL "
    "AND provider_task_id_sha256 IS NULL AND provider_terminal_status IS NULL "
    "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
    "(provider_task_status IN ('submitted','running') AND encrypted_provider_client_token IS NOT NULL "
    "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_submission_json IS NOT NULL "
    "AND provider_submission_sha256 IS NOT NULL AND encrypted_provider_task_id IS NOT NULL "
    "AND provider_task_id_sha256 IS NOT NULL AND provider_terminal_status IS NULL "
    "AND encrypted_provider_terminal_json IS NULL AND provider_terminal_sha256 IS NULL) OR "
    "(provider_task_status = 'terminal' AND encrypted_provider_client_token IS NOT NULL "
    "AND provider_client_token_sha256 IS NOT NULL AND encrypted_provider_submission_json IS NOT NULL "
    "AND provider_submission_sha256 IS NOT NULL AND encrypted_provider_task_id IS NOT NULL "
    "AND provider_task_id_sha256 IS NOT NULL AND provider_terminal_status IS NOT NULL "
    "AND encrypted_provider_terminal_json IS NOT NULL AND provider_terminal_sha256 IS NOT NULL)"
)


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table)}


def _checks(table: str) -> set[str]:
    return {str(check["name"]) for check in sa.inspect(op.get_bind()).get_check_constraints(table) if check.get("name")}


def _replace_state_check(expression: str) -> None:
    checks = _checks(_SCOPES)
    with op.batch_alter_table(_SCOPES, schema=None) as batch_op:
        if _STATE_CHECK in checks:
            batch_op.drop_constraint(_STATE_CHECK, type_="check")
        batch_op.create_check_constraint(_STATE_CHECK, expression)


def upgrade() -> None:
    if _SCOPES not in _tables():
        return
    active = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_paid_call_scopes WHERE provider_task_status IS NOT NULL")).scalar_one()
    if int(active) > 0:
        raise RuntimeError("cannot add exact provider submission recovery while legacy provider tasks exist; export and retire those task records with the audited migration runbook before upgrading")
    columns = _columns(_SCOPES)
    with op.batch_alter_table(_SCOPES, schema=None) as batch_op:
        if "encrypted_provider_submission_json" not in columns:
            batch_op.add_column(
                sa.Column(
                    "encrypted_provider_submission_json",
                    sa.Text(),
                    nullable=True,
                )
            )
        if "provider_submission_sha256" not in columns:
            batch_op.add_column(
                sa.Column(
                    "provider_submission_sha256",
                    sa.String(length=64),
                    nullable=True,
                )
            )
    _replace_state_check(_NEW_STATE_EXPRESSION)


def downgrade() -> None:
    if _SCOPES not in _tables():
        return
    columns = _columns(_SCOPES)
    if "provider_submission_sha256" in columns:
        active = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_paid_call_scopes WHERE provider_submission_sha256 IS NOT NULL")).scalar_one()
        if int(active) > 0:
            raise RuntimeError("cannot downgrade exact provider submission recovery while provider submissions exist")
    _replace_state_check(_OLD_STATE_EXPRESSION)
    columns = _columns(_SCOPES)
    with op.batch_alter_table(_SCOPES, schema=None) as batch_op:
        if "provider_submission_sha256" in columns:
            batch_op.drop_column("provider_submission_sha256")
        if "encrypted_provider_submission_json" in columns:
            batch_op.drop_column("encrypted_provider_submission_json")
