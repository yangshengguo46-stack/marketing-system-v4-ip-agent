from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy.ext.asyncio import create_async_engine

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.base import Base
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade

REVISION = "0030_personal_ip_editorial_program_versions"
PREVIOUS_REVISION = "0029_personal_ip_final_artifacts"
PROGRAM_TABLE = "personal_ip_editorial_program_versions"
WORK_TABLE = "personal_ip_content_works"
WORK_COLUMN = "editorial_program_version_id"


async def _version(engine) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(sa.text("SELECT version_num FROM alembic_version"))
        return str(result.scalar_one())


async def _tables(engine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))


async def _columns(engine, table: str) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: {str(column["name"]) for column in sa.inspect(sync).get_columns(table)})


async def _indexes(engine, table: str) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: {str(index["name"]) for index in sa.inspect(sync).get_indexes(table) if index.get("name")})


async def _foreign_keys(engine, table: str) -> dict[str, dict]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: {str(foreign_key["name"]): foreign_key for foreign_key in sa.inspect(sync).get_foreign_keys(table) if foreign_key.get("name")})


async def _unique_constraints(engine, table: str) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: {str(constraint["name"]) for constraint in sa.inspect(sync).get_unique_constraints(table) if constraint.get("name")})


async def _seed_linked_program(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_subjects (
                    id, owner_user_id, display_name, subject_type,
                    relationship, description, status, metadata_json,
                    created_at, updated_at
                ) VALUES (
                    'subject-editorial', 'owner-editorial', '营销主体', 'brand',
                    'self', '', 'active', '{}',
                    '2026-08-05 00:00:00', '2026-08-05 00:00:00'
                )
                """
            )
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_editorial_program_versions (
                    id, program_id, owner_user_id, subject_id, version_number,
                    operation_key, operation_digest,
                    parent_program_version_id, title, decision_json,
                    created_by_run_id, created_at
                ) VALUES (
                    'editorial-version-1', 'editorial-program-1',
                    'owner-editorial', 'subject-editorial', 1,
                    'editorial-migration', :operation_digest,
                    NULL, '黄金礼品人情故事', :decision_json,
                    'run-editorial', '2026-08-05 00:00:00'
                )
                """
            ),
            {
                "operation_digest": "a" * 64,
                "decision_json": '{"contract_version":"personal-ip-editorial-program-v1"}',
            },
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_content_works (
                    id, owner_user_id, objective_id, thread_id, subject_id,
                    editorial_program_version_id, operation_key,
                    operation_digest, title, entry_route, objective_json,
                    status, created_by_run_id, created_at, updated_at
                ) VALUES (
                    'work-editorial', 'owner-editorial', 'objective-editorial',
                    'thread-editorial', 'subject-editorial',
                    'editorial-version-1', 'work-editorial', :operation_digest,
                    '人情故事第一集', 'zero_start', :objective_json,
                    'active', 'run-editorial',
                    '2026-08-05 00:00:00', '2026-08-05 00:00:00'
                )
                """
            ),
            {
                "operation_digest": "b" * 64,
                "objective_json": '{"desired_change":"让观众理解送礼分寸"}',
            },
        )


@pytest.mark.asyncio
async def test_0029_to_0030_upgrade_registers_program_binding_and_downgrade_fails_closed(
    tmp_path,
) -> None:
    assert PROGRAM_TABLE in Base.metadata.tables
    assert WORK_COLUMN in Base.metadata.tables[WORK_TABLE].columns

    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'editorial-program.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, PREVIOUS_REVISION)
        assert await _version(engine) == PREVIOUS_REVISION
        assert PROGRAM_TABLE not in await _tables(engine)
        assert WORK_COLUMN not in await _columns(engine, WORK_TABLE)

        await asyncio.to_thread(_upgrade, config, "head")
        assert await _version(engine) == REVISION
        assert {
            "id",
            "program_id",
            "owner_user_id",
            "subject_id",
            "version_number",
            "operation_key",
            "operation_digest",
            "parent_program_version_id",
            "title",
            "decision_json",
            "created_by_run_id",
            "created_at",
        } == await _columns(engine, PROGRAM_TABLE)
        assert WORK_COLUMN in await _columns(engine, WORK_TABLE)
        assert {
            "ix_personal_ip_editorial_program_versions_owner_user_id",
            "ix_personal_ip_editorial_program_versions_subject_id",
            "ix_personal_ip_editorial_program_versions_owner_program_version",
        } <= await _indexes(engine, PROGRAM_TABLE)
        assert "ix_personal_ip_content_works_editorial_program_version_id" in await _indexes(engine, WORK_TABLE)
        assert {
            "uq_personal_ip_editorial_program_versions_program_version",
            "uq_personal_ip_editorial_program_versions_owner_operation",
        } == await _unique_constraints(engine, PROGRAM_TABLE)

        program_foreign_keys = await _foreign_keys(engine, PROGRAM_TABLE)
        subject_foreign_key = program_foreign_keys["fk_personal_ip_editorial_program_versions_subject"]
        assert subject_foreign_key["referred_table"] == "personal_ip_subjects"
        assert subject_foreign_key["options"].get("ondelete") == "SET NULL"
        work_foreign_keys = await _foreign_keys(engine, WORK_TABLE)
        work_program_foreign_key = work_foreign_keys["fk_personal_ip_content_works_editorial_program_version"]
        assert work_program_foreign_key["referred_table"] == PROGRAM_TABLE
        assert work_program_foreign_key["constrained_columns"] == [WORK_COLUMN]
        assert work_program_foreign_key["options"].get("ondelete") == "RESTRICT"

        await _seed_linked_program(engine)
        with pytest.raises(RuntimeError, match="Owner backup"):
            await asyncio.to_thread(
                alembic_command.downgrade,
                config,
                PREVIOUS_REVISION,
            )
        assert await _version(engine) == REVISION

        async with engine.begin() as connection:
            await connection.execute(sa.text("DELETE FROM personal_ip_content_works WHERE id = 'work-editorial'"))
        with pytest.raises(RuntimeError, match="Owner backup"):
            await asyncio.to_thread(
                alembic_command.downgrade,
                config,
                PREVIOUS_REVISION,
            )
        assert await _version(engine) == REVISION

        async with engine.begin() as connection:
            await connection.execute(sa.text("DELETE FROM personal_ip_editorial_program_versions WHERE id = 'editorial-version-1'"))
        await asyncio.to_thread(
            alembic_command.downgrade,
            config,
            PREVIOUS_REVISION,
        )
        assert await _version(engine) == PREVIOUS_REVISION
        assert PROGRAM_TABLE not in await _tables(engine)
        assert WORK_COLUMN not in await _columns(engine, WORK_TABLE)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0030_fresh_database_bootstraps_to_head(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'editorial-program-fresh.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "head")
        assert await _version(engine) == REVISION
        assert PROGRAM_TABLE in await _tables(engine)
        assert WORK_COLUMN in await _columns(engine, WORK_TABLE)
    finally:
        await engine.dispose()
