"""Regression coverage for Personal-IP semantic-layer retirement."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from alembic import command as alembic_command

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.bootstrap import _get_alembic_config
from deerflow.persistence.engine import close_engine, get_engine, init_engine

_RETIRED_TABLES = {
    "personal_ip_strategy_versions",
    "personal_ip_differentiation_versions",
    "personal_ip_asset_observations",
    "personal_ip_preflights",
    "personal_ip_retrospectives",
    "personal_ip_evidence_promotions",
    "personal_ip_brand_identity_versions",
    "personal_ip_reputation_snapshots",
}


def _seed_0020_database(db_path: Path, *, nonempty_table: str | None = None) -> None:
    with sqlite3.connect(db_path) as raw:
        raw.execute("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)")
        raw.execute("INSERT INTO alembic_version (version_num) VALUES ('0020_personal_ip_differentiation')")
        for table_name in sorted(_RETIRED_TABLES):
            raw.execute(f'CREATE TABLE "{table_name}" (id VARCHAR(64) PRIMARY KEY)')
        raw.execute("CREATE TABLE personal_ip_publish_receipts (id VARCHAR(64) PRIMARY KEY, preflight_id VARCHAR(64))")
        raw.execute("CREATE INDEX ix_personal_ip_publish_preflight_id ON personal_ip_publish_receipts (preflight_id)")
        if nonempty_table:
            raw.execute(f'INSERT INTO "{nonempty_table}" (id) VALUES ("legacy-row")')
        raw.commit()


def _tables_and_publish_columns(db_path: Path) -> tuple[set[str], set[str], str]:
    with sqlite3.connect(db_path) as raw:
        tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        columns = {row[1] for row in raw.execute("PRAGMA table_info(personal_ip_publish_receipts)")}
        version = raw.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    return tables, columns, version


@pytest.mark.asyncio
async def test_upgrade_refuses_to_drop_nonempty_semantic_data(tmp_path: Path) -> None:
    db_path = tmp_path / "nonempty.db"
    _seed_0020_database(db_path, nonempty_table="personal_ip_preflights")

    with pytest.raises(RuntimeError, match="Owner backup"):
        await init_engine(
            backend="sqlite",
            url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
            sqlite_dir=str(tmp_path),
        )
    await close_engine()

    tables, columns, version = _tables_and_publish_columns(db_path)
    assert _RETIRED_TABLES <= tables
    assert "preflight_id" in columns
    assert version == "0020_personal_ip_differentiation"


@pytest.mark.asyncio
async def test_upgrade_drops_empty_semantic_schema_and_publish_dependency(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    _seed_0020_database(db_path)

    await init_engine(
        backend="sqlite",
        url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        sqlite_dir=str(tmp_path),
    )
    try:
        tables, columns, version = _tables_and_publish_columns(db_path)
        assert not (_RETIRED_TABLES & tables)
        assert "preflight_id" not in columns
        assert version == "0029_personal_ip_final_artifacts"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_fresh_database_never_creates_retired_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"

    await init_engine(
        backend="sqlite",
        url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        sqlite_dir=str(tmp_path),
    )
    try:
        tables, columns, version = _tables_and_publish_columns(db_path)
        assert not (_RETIRED_TABLES & tables)
        assert "preflight_id" not in columns
        assert version == "0029_personal_ip_final_artifacts"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_downgrade_recreates_only_empty_legacy_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "downgrade.db"
    _seed_0020_database(db_path)

    await init_engine(
        backend="sqlite",
        url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        sqlite_dir=str(tmp_path),
    )
    try:
        engine = get_engine()
        assert engine is not None
        config = _get_alembic_config(engine)
        await asyncio.to_thread(
            alembic_command.downgrade,
            config,
            "0020_personal_ip_differentiation",
        )
    finally:
        await close_engine()

    tables, columns, version = _tables_and_publish_columns(db_path)
    assert _RETIRED_TABLES <= tables
    assert "preflight_id" in columns
    with sqlite3.connect(db_path) as raw:
        assert all(raw.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] == 0 for name in _RETIRED_TABLES)
    assert version == "0020_personal_ip_differentiation"
