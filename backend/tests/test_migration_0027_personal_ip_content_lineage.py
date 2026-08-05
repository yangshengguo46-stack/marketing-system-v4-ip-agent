from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy.ext.asyncio import create_async_engine

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade

_CONTENT_TABLES = {
    "personal_ip_content_works",
    "personal_ip_breakdown_versions",
    "personal_ip_direction_versions",
    "personal_ip_script_versions",
}


async def _tables(engine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))


async def _columns(engine, table: str) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: {str(column["name"]) for column in sa.inspect(sync).get_columns(table)})


async def _version(engine) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(sa.text("SELECT version_num FROM alembic_version"))
        return str(result.scalar_one())


@pytest.mark.asyncio
async def test_0026_to_0027_upgrade_and_nonempty_downgrade_fail_closed(
    tmp_path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'content-lineage.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(
            _upgrade,
            config,
            "0026_personal_ip_paid_call_submission_recovery",
        )
        assert await _version(engine) == ("0026_personal_ip_paid_call_submission_recovery")
        assert _CONTENT_TABLES.isdisjoint(await _tables(engine))

        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO personal_ip_subjects (
                        id, owner_user_id, display_name, subject_type,
                        relationship, description, status, metadata_json,
                        created_at, updated_at
                    ) VALUES (
                        'subject-existing', 'owner-existing', '已有主体', 'creator',
                        'self', '', 'active', '{}',
                        '2026-08-05 00:00:00', '2026-08-05 00:00:00'
                    )
                    """
                )
            )

        await asyncio.to_thread(
            _upgrade,
            config,
            "0027_personal_ip_content_lineage",
        )
        assert await _version(engine) == "0027_personal_ip_content_lineage"
        assert _CONTENT_TABLES <= await _tables(engine)
        assert {
            "objective_id",
            "thread_id",
            "operation_digest",
            "objective_json",
        } <= await _columns(engine, "personal_ip_content_works")
        assert {
            "evidence_request_id",
            "evidence_item_index",
            "evidence_contract_version",
            "evidence_payload_digest",
            "evidence_snapshot_json",
        } <= await _columns(engine, "personal_ip_breakdown_versions")

        async with engine.connect() as connection:
            retained_subject = (await connection.execute(sa.text("SELECT owner_user_id FROM personal_ip_subjects WHERE id = 'subject-existing'"))).scalar_one()
        assert retained_subject == "owner-existing"

        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO personal_ip_content_works (
                        id, owner_user_id, objective_id, thread_id, subject_id,
                        operation_key, operation_digest, title, entry_route,
                        objective_json, status, created_by_run_id,
                        created_at, updated_at
                    ) VALUES (
                        'work-existing', 'owner-existing', 'objective-existing',
                        'thread-existing', 'subject-existing', 'operation-existing',
                        :operation_digest, '已有内容', 'zero_start',
                        :objective_json, 'active', NULL,
                        '2026-08-05 00:00:00', '2026-08-05 00:00:00'
                    )
                    """
                ),
                {
                    "operation_digest": "a" * 64,
                    "objective_json": ('{"desired_change":"验证非空降级必须拒绝","success_criteria":[],"constraints":[]}'),
                },
            )

        with pytest.raises(RuntimeError, match="Owner backup"):
            await asyncio.to_thread(
                alembic_command.downgrade,
                config,
                "0026_personal_ip_paid_call_submission_recovery",
            )
        assert await _version(engine) == "0027_personal_ip_content_lineage"
        assert _CONTENT_TABLES <= await _tables(engine)
        async with engine.connect() as connection:
            retained_work = (await connection.execute(sa.text("SELECT owner_user_id FROM personal_ip_content_works WHERE id = 'work-existing'"))).scalar_one()
        assert retained_work == "owner-existing"

        async with engine.begin() as connection:
            await connection.execute(sa.text("DELETE FROM personal_ip_content_works WHERE id = 'work-existing'"))
        await asyncio.to_thread(
            alembic_command.downgrade,
            config,
            "0026_personal_ip_paid_call_submission_recovery",
        )
        assert await _version(engine) == ("0026_personal_ip_paid_call_submission_recovery")
        assert _CONTENT_TABLES.isdisjoint(await _tables(engine))
        async with engine.connect() as connection:
            retained_subject = (await connection.execute(sa.text("SELECT owner_user_id FROM personal_ip_subjects WHERE id = 'subject-existing'"))).scalar_one()
        assert retained_subject == "owner-existing"
    finally:
        await engine.dispose()
