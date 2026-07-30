"""Regression coverage for the differentiation-thesis migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.base import Base
from deerflow.persistence.engine import close_engine, init_engine


def _seed_strategy_head(db_path: Path) -> None:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE personal_ip_asset_observations")
            connection.exec_driver_sql("DROP TABLE personal_ip_differentiation_versions")
            connection.exec_driver_sql(
                "DROP INDEX ix_personal_ip_strategy_versions_differentiation_version_id"
            )
            connection.exec_driver_sql(
                "ALTER TABLE personal_ip_strategy_versions DROP COLUMN differentiation_version_id"
            )
    finally:
        engine.dispose()
    with sqlite3.connect(db_path) as raw:
        raw.execute(
            "CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64) NOT NULL)"
        )
        raw.execute("DELETE FROM alembic_version")
        raw.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('0019_personal_ip_strategy_versions')"
        )
        raw.commit()


@pytest.mark.asyncio
async def test_upgrade_from_strategy_head_adds_differentiation_schema(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "strategy-head.db"
    _seed_strategy_head(db_path)

    await init_engine(
        backend="sqlite",
        url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        sqlite_dir=str(tmp_path),
    )
    try:
        with sqlite3.connect(db_path) as raw:
            tables = {
                row[0]
                for row in raw.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            strategy_columns = {
                row[1]
                for row in raw.execute(
                    "PRAGMA table_info(personal_ip_strategy_versions)"
                )
            }
            version = raw.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
        assert "personal_ip_differentiation_versions" in tables
        assert "personal_ip_asset_observations" in tables
        assert "differentiation_version_id" in strategy_columns
        assert version == "0020_personal_ip_differentiation"
    finally:
        await close_engine()
