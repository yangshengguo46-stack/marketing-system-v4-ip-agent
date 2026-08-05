from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy.ext.asyncio import create_async_engine

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade


async def _version(engine) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(sa.text("SELECT version_num FROM alembic_version"))
        return str(result.scalar_one())


async def _columns(engine, table: str) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: {str(column["name"]) for column in sa.inspect(sync).get_columns(table)})


async def _insert_legacy_production(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_video_productions (
                    id, owner_user_id, thread_id, operation_key, contract_version,
                    title, subject_id, target_account_ids_json, source_kind,
                    source_json, delivery_spec_json, provider_policy_json,
                    budget_json, request_digest, status, current_stage,
                    event_count, created_at, updated_at
                ) VALUES (
                    'video-production-legacy', 'owner-1', NULL, 'legacy-operation',
                    'personal-ip-video-production-v1', '旧制作', NULL, '[]',
                    'idea', '{"idea":"legacy"}', '{}', '{}', '{}', :digest,
                    'draft', 'intake', 0, '2026-08-05 00:00:00',
                    '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "a" * 64},
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_video_production_events (
                    id, owner_user_id, production_id, event_key, event_digest,
                    sequence, event_type, stage, status, entity_type, entity_id,
                    provider, model, provider_task_id, payload_json,
                    input_refs_json, output_refs_json, cost_json,
                    occurred_at, created_at
                ) VALUES (
                    'video-event-legacy', 'owner-1', 'video-production-legacy',
                    'legacy-event', :digest, 1, 'blueprint_sealed', 'blueprint',
                    'succeeded', 'production', 'video-production-legacy',
                    'local', NULL, NULL, '{}', '[]', '[]', '{}',
                    '2026-08-05 00:00:00', '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "e" * 64},
        )


async def _link_legacy_production(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_content_works (
                    id, owner_user_id, objective_id, thread_id, subject_id,
                    operation_key, operation_digest, title, entry_route,
                    objective_json, status, created_by_run_id, created_at, updated_at
                ) VALUES (
                    'content-work-1', 'owner-1', 'objective-1', 'thread-1', NULL,
                    'content-operation', :digest, '稿件', 'zero_start',
                    '{"desired_change":"test","audience_situation":"unknown","business_context":"","constraints":[]}',
                    'active', NULL, '2026-08-05 00:00:00', '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "b" * 64},
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_direction_versions (
                    id, owner_user_id, content_work_id, version_number, commit_key,
                    commit_digest, parent_direction_version_id,
                    breakdown_version_ids_json, objective_snapshot_json,
                    direction_json, created_by_run_id, created_at
                ) VALUES (
                    'direction-1', 'owner-1', 'content-work-1', 1, 'direction-op',
                    :digest, NULL, '[]', '{"desired_change":"test"}',
                    '{"truth_mode":"factual"}', NULL, '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "c" * 64},
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_script_versions (
                    id, owner_user_id, content_work_id, direction_version_id,
                    version_number, commit_key, commit_digest,
                    parent_script_version_id, title, story_mode, script_text,
                    claim_basis_json, creative_elements_json,
                    story_engine_seed_json, locked_story, locked_story_digest,
                    production_notes_json, created_by_run_id, created_at
                ) VALUES (
                    'script-1', 'owner-1', 'content-work-1', 'direction-1', 1,
                    'script-op', :digest, NULL, '稿件', 'factual', '正文',
                    '[]', '[]', NULL, NULL, NULL, '{}', NULL,
                    '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "d" * 64},
        )
        await connection.execute(
            sa.text(
                """
                UPDATE personal_ip_video_productions
                SET content_work_id = 'content-work-1',
                    script_version_id = 'script-1',
                    source_kind = 'script',
                    contract_version = 'personal-ip-video-production-v2'
                WHERE id = 'video-production-legacy'
                """
            )
        )


@pytest.mark.asyncio
async def test_0028_preserves_legacy_rows_and_downgrade_fails_closed_for_links(
    tmp_path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'script-production-binding.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0027_personal_ip_content_lineage")
        await _insert_legacy_production(engine)

        await asyncio.to_thread(
            _upgrade,
            config,
            "0029_personal_ip_final_artifacts",
        )
        assert await _version(engine) == "0029_personal_ip_final_artifacts"
        assert {"content_work_id", "script_version_id"} <= await _columns(
            engine,
            "personal_ip_video_productions",
        )
        async with engine.connect() as connection:
            legacy = (await connection.execute(sa.text("SELECT content_work_id, script_version_id, source_kind FROM personal_ip_video_productions WHERE id = 'video-production-legacy'"))).one()
        assert tuple(legacy) == (None, None, "idea")
        async with engine.connect() as connection:
            event_count = (await connection.execute(sa.text("SELECT COUNT(*) FROM personal_ip_video_production_events WHERE production_id = 'video-production-legacy'"))).scalar_one()
        assert int(event_count) == 1

        await asyncio.to_thread(
            alembic_command.downgrade,
            config,
            "0027_personal_ip_content_lineage",
        )
        assert {"content_work_id", "script_version_id"}.isdisjoint(await _columns(engine, "personal_ip_video_productions"))

        await asyncio.to_thread(
            _upgrade,
            config,
            "0029_personal_ip_final_artifacts",
        )
        await _link_legacy_production(engine)
        with pytest.raises(RuntimeError, match="linked Owner data exists"):
            await asyncio.to_thread(
                alembic_command.downgrade,
                config,
                "0027_personal_ip_content_lineage",
            )
        assert await _version(engine) == "0028_personal_ip_script_production_binding"
    finally:
        await engine.dispose()
