"""Regression coverage for automatic promotion of legacy evidence proposals."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.base import Base
from deerflow.persistence.engine import close_engine, init_engine


def _seed_legacy_proposal(db_path: Path) -> None:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    now = datetime(2026, 7, 21, 8, 0, tzinfo=UTC).isoformat()
    with sqlite3.connect(db_path) as raw:
        raw.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(64) NOT NULL)")
        raw.execute("DELETE FROM alembic_version")
        raw.execute("INSERT INTO alembic_version (version_num) VALUES ('0015_personal_ip_video_productions')")
        raw.execute(
            """
            INSERT INTO personal_ip_evidence_promotions (
                id, owner_user_id, proposal_key, evidence_type, claim,
                retrospective_ids_json, evidence_summary_json, evidence_digest,
                minimum_support, status, decisions_json, decided_at, created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "promotion-legacy",
                "user-1",
                "pattern:legacy",
                "content_pattern",
                "开头直给结果提高完播。",
                json.dumps(["retro-1", "retro-2", "retro-3"]),
                json.dumps({"independent_measured_support": 3}),
                "a" * 64,
                3,
                "proposed",
                json.dumps([]),
                None,
                now,
                now,
            ),
        )
        raw.commit()


@pytest.mark.asyncio
async def test_upgrade_converts_legacy_proposal_to_policy_approval(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-evidence.db"
    _seed_legacy_proposal(db_path)

    await init_engine(
        backend="sqlite",
        url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        sqlite_dir=str(tmp_path),
    )
    try:
        with sqlite3.connect(db_path) as raw:
            row = raw.execute(
                "SELECT status, decisions_json, decided_at FROM personal_ip_evidence_promotions WHERE id = ?",
                ("promotion-legacy",),
            ).fetchone()
            version = raw.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert row is not None
        assert row[0] == "approved"
        decisions = json.loads(row[1])
        assert decisions[0]["decision"] == "approved"
        assert decisions[0]["reviewer_source"] == "cross_sample_evidence_policy"
        assert row[2] is not None
        assert version == "0020_personal_ip_differentiation"
    finally:
        await close_engine()
