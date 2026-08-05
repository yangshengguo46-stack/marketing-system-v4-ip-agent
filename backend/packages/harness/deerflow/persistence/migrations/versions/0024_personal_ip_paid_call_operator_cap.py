"""Allow an explicit local admission cap while provider price is unknown.

Revision ID: 0024_personal_ip_paid_call_operator_cap
Revises: 0023_personal_ip_paid_call_execution_run
Create Date: 2026-08-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_personal_ip_paid_call_operator_cap"
down_revision: str | Sequence[str] | None = "0023_personal_ip_paid_call_execution_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "personal_ip_paid_call_scopes"
_CONSTRAINT = "ck_personal_ip_paid_call_scopes_price_state"
_LEGACY_CONSTRAINT = "ck_personal_ip_paid_call_scopes_maximum_positive"
_OLD_EXPRESSION = "(price_status = 'unknown' AND maximum_amount_micros IS NULL) OR (price_status = 'quoted' AND maximum_amount_micros > 0)"
_NEW_EXPRESSION = "(price_status = 'unknown' AND maximum_amount_micros IS NULL) OR (price_status IN ('quoted','operator_capped') AND maximum_amount_micros > 0)"
_FINAL_COLUMNS: tuple[sa.Column[object], ...] = (
    sa.Column("server_name", sa.String(length=128), nullable=False),
    sa.Column("tool_name", sa.String(length=128), nullable=False),
    sa.Column("tool_args_sha256", sa.String(length=64), nullable=False),
    sa.Column("provider_request_sha256", sa.String(length=64), nullable=False),
    sa.Column("price_status", sa.String(length=16), nullable=False),
)


def _has_table() -> bool:
    return _TABLE in set(sa.inspect(op.get_bind()).get_table_names())


def _column_state() -> dict[str, dict[str, object]]:
    return {str(column["name"]): column for column in sa.inspect(op.get_bind()).get_columns(_TABLE)}


def _constraint_names() -> set[str]:
    return {str(check["name"]) for check in sa.inspect(op.get_bind()).get_check_constraints(_TABLE) if check.get("name")}


def _replace_constraint(
    expression: str,
    *,
    add_missing_columns: bool = False,
) -> None:
    columns = _column_state()
    constraints = _constraint_names()
    missing = [column for column in _FINAL_COLUMNS if column.name not in columns]
    if missing:
        row_count = op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {_TABLE}")).scalar_one()
        if int(row_count) > 0:
            raise RuntimeError("cannot upgrade legacy paid-call schema with rows; create an Owner backup before migration")
        if not add_missing_columns:
            raise RuntimeError("paid-call schema is missing required columns")

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        for name in (_CONSTRAINT, _LEGACY_CONSTRAINT):
            if name in constraints:
                batch_op.drop_constraint(name, type_="check")
        if columns.get("maximum_amount_micros", {}).get("nullable") is False:
            batch_op.alter_column(
                "maximum_amount_micros",
                existing_type=sa.BigInteger(),
                nullable=True,
            )
        for column in missing:
            batch_op.add_column(column)
        batch_op.create_check_constraint(_CONSTRAINT, expression)


def upgrade() -> None:
    if _has_table():
        _replace_constraint(_NEW_EXPRESSION, add_missing_columns=True)


def downgrade() -> None:
    if not _has_table():
        return
    operator_capped = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM personal_ip_paid_call_scopes WHERE price_status = 'operator_capped'")).scalar_one()
    if int(operator_capped) > 0:
        raise RuntimeError("cannot downgrade paid-call operator-cap schema while operator-capped rows exist")
    _replace_constraint(_OLD_EXPRESSION)
