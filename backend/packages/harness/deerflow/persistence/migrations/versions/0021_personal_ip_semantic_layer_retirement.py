"""Retire the legacy Personal-IP semantic layer.

Revision ID: 0021_personal_ip_semantic_layer_retirement
Revises: 0020_personal_ip_differentiation
Create Date: 2026-08-01

This migration is intentionally fail-closed. Semantic rows must be exported in
an Owner backup before any schema is removed. Downgrade recreates empty legacy
schemas only; it cannot restore deleted rows.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_personal_ip_semantic_layer_retirement"
down_revision: str | Sequence[str] | None = "0020_personal_ip_differentiation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RETIRED_TABLES = (
    "personal_ip_strategy_versions",
    "personal_ip_differentiation_versions",
    "personal_ip_asset_observations",
    "personal_ip_preflights",
    "personal_ip_retrospectives",
    "personal_ip_evidence_promotions",
    "personal_ip_brand_identity_versions",
    "personal_ip_reputation_snapshots",
)

_DROP_ORDER = (
    "personal_ip_evidence_promotions",
    "personal_ip_retrospectives",
    "personal_ip_asset_observations",
    "personal_ip_differentiation_versions",
    "personal_ip_strategy_versions",
    "personal_ip_reputation_snapshots",
    "personal_ip_brand_identity_versions",
    "personal_ip_preflights",
)


def _require_empty_retired_tables() -> set[str]:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    nonempty: list[tuple[str, int]] = []
    for table_name in _RETIRED_TABLES:
        if table_name not in tables:
            continue
        count = int(bind.execute(sa.text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one())
        if count:
            nonempty.append((table_name, count))
    if nonempty:
        details = ", ".join(f"{name}={count}" for name, count in nonempty)
        raise RuntimeError(
            "Personal-IP semantic retirement stopped because legacy data exists "
            f"({details}). Create and verify an Owner backup before upgrading."
        )
    return tables


def _drop_publish_preflight_column(tables: set[str]) -> None:
    if "personal_ip_publish_receipts" not in tables:
        return
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("personal_ip_publish_receipts")}
    if "preflight_id" not in columns:
        return
    indexes = [
        index["name"]
        for index in inspector.get_indexes("personal_ip_publish_receipts")
        if index.get("name") and index.get("column_names") == ["preflight_id"]
    ]
    with op.batch_alter_table("personal_ip_publish_receipts", schema=None) as batch_op:
        for index_name in indexes:
            batch_op.drop_index(index_name)
        batch_op.drop_column("preflight_id")


def upgrade() -> None:
    tables = _require_empty_retired_tables()
    _drop_publish_preflight_column(tables)
    for table_name in _DROP_ORDER:
        if table_name in tables:
            op.drop_table(table_name)


def downgrade() -> None:
    # Reuse the authoritative historical schema builders. They create no rows.
    modules = (
        "deerflow.persistence.migrations.versions.0008_personal_ip_preflights",
        "deerflow.persistence.migrations.versions.0017_personal_ip_brand_method",
        "deerflow.persistence.migrations.versions.0019_personal_ip_strategy_versions",
        "deerflow.persistence.migrations.versions.0020_personal_ip_differentiation",
        "deerflow.persistence.migrations.versions.0011_personal_ip_retrospectives",
        "deerflow.persistence.migrations.versions.0012_personal_ip_evidence_promotions",
    )
    for module_name in modules:
        importlib.import_module(module_name).upgrade()

    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "personal_ip_publish_receipts" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("personal_ip_publish_receipts")}
    if "preflight_id" not in columns:
        with op.batch_alter_table("personal_ip_publish_receipts", schema=None) as batch_op:
            batch_op.add_column(sa.Column("preflight_id", sa.String(length=64), nullable=True))
            batch_op.create_index("ix_personal_ip_publish_preflight_id", ["preflight_id"], unique=False)
