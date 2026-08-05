from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy.ext.asyncio import create_async_engine

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.base import Base
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade

REVISION = "0029_personal_ip_final_artifacts"
PREVIOUS_REVISION = "0028_personal_ip_script_production_binding"
TABLE = "personal_ip_artifacts"


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


async def _seed_artifact(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_video_productions (
                    id, owner_user_id, thread_id, operation_key, contract_version,
                    title, content_work_id, script_version_id, subject_id,
                    target_account_ids_json, source_kind, source_json,
                    delivery_spec_json, provider_policy_json, budget_json,
                    request_digest, status, current_stage, event_count,
                    created_at, updated_at
                ) VALUES (
                    'video-production-artifact', 'owner-1', NULL,
                    'artifact-migration', 'personal-ip-video-production-v1',
                    'Artifact migration', NULL, NULL, NULL, '[]', 'script',
                    '{}', '{}', '{}', '{}', :request_digest, 'completed',
                    'delivery', 2, '2026-08-05 00:00:00',
                    '2026-08-05 00:00:02'
                )
                """
            ),
            {"request_digest": "a" * 64},
        )
        for values in (
            {
                "id": "video-event-qa",
                "event_key": "qa",
                "event_digest": "b" * 64,
                "sequence": 1,
                "event_type": "delivery_qa_completed",
                "entity_type": "delivery",
                "entity_id": "delivery-1",
                "payload": '{"contract_version":"personal-ip-delivery-qa-v1","passed":true}',
                "output_refs": '["file:///private/final.mp4"]',
                "occurred_at": "2026-08-05 00:00:01",
            },
            {
                "id": "video-event-delivery",
                "event_key": "delivery",
                "event_digest": "c" * 64,
                "sequence": 2,
                "event_type": "delivery_completed",
                "entity_type": "artifact",
                "entity_id": "artifact-1",
                "payload": '{"contract_version":"personal-ip-final-artifact-v1","accepted":true}',
                "output_refs": '["artifact://artifact-1"]',
                "occurred_at": "2026-08-05 00:00:02",
            },
        ):
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO personal_ip_video_production_events (
                        id, owner_user_id, production_id, event_key,
                        event_digest, sequence, event_type, stage, status,
                        entity_type, entity_id, provider, model,
                        provider_task_id, payload_json, input_refs_json,
                        output_refs_json, cost_json, occurred_at, created_at
                    ) VALUES (
                        :id, 'owner-1', 'video-production-artifact', :event_key,
                        :event_digest, :sequence, :event_type, 'delivery',
                        'succeeded', :entity_type, :entity_id, 'local', NULL,
                        NULL, :payload, '[]', :output_refs, '{}',
                        :occurred_at, :occurred_at
                    )
                    """
                ),
                values,
            )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_artifacts (
                    id, owner_user_id, production_id, qa_event_id,
                    delivery_event_id, contract_version, role, storage_key,
                    sha256, size_bytes, mime_type, content_available, metadata_json,
                    artifact_digest, created_at
                ) VALUES (
                    'artifact-1', 'owner-1', 'video-production-artifact',
                    'video-event-qa', 'video-event-delivery',
                    'personal-ip-final-artifact-v1', 'final_video',
                    'video-deliveries/final.mp4', :sha256, 42, 'video/mp4', 1,
                    '{}', :artifact_digest, '2026-08-05 00:00:02'
                )
                """
            ),
            {"sha256": "d" * 64, "artifact_digest": "e" * 64},
        )


async def _seed_completed_linked_production_without_artifact(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_content_works (
                    id, owner_user_id, objective_id, thread_id, subject_id,
                    operation_key, operation_digest, title, entry_route,
                    objective_json, status, created_by_run_id, created_at,
                    updated_at
                ) VALUES (
                    'content-work-unsealed', 'owner-legacy', 'objective-1',
                    'thread-1', NULL, 'content-unsealed', :digest, '稿件',
                    'zero_start', '{"desired_change":"test"}', 'active',
                    NULL, '2026-08-05 00:00:00', '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "a" * 64},
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_direction_versions (
                    id, owner_user_id, content_work_id, version_number,
                    commit_key, commit_digest, parent_direction_version_id,
                    breakdown_version_ids_json, objective_snapshot_json,
                    direction_json, created_by_run_id, created_at
                ) VALUES (
                    'direction-unsealed', 'owner-legacy',
                    'content-work-unsealed', 1, 'direction-unsealed', :digest,
                    NULL, '[]', '{"desired_change":"test"}',
                    '{"truth_mode":"factual"}', NULL,
                    '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "b" * 64},
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
                    'script-unsealed', 'owner-legacy',
                    'content-work-unsealed', 'direction-unsealed', 1,
                    'script-unsealed', :digest, NULL, '稿件', 'factual',
                    '正文', '[]', '[]', NULL, NULL, NULL, '{}', NULL,
                    '2026-08-05 00:00:00'
                )
                """
            ),
            {"digest": "c" * 64},
        )
        await connection.execute(
            sa.text(
                """
                INSERT INTO personal_ip_video_productions (
                    id, owner_user_id, thread_id, operation_key, contract_version,
                    title, content_work_id, script_version_id, subject_id,
                    target_account_ids_json, source_kind, source_json,
                    delivery_spec_json, provider_policy_json, budget_json,
                    request_digest, status, current_stage, event_count,
                    created_at, updated_at
                ) VALUES (
                    'video-production-unsealed-v2', 'owner-legacy', NULL,
                    'unsealed-v2', 'personal-ip-video-production-v2',
                    'Unsealed linked terminal', 'content-work-unsealed',
                    'script-unsealed', NULL, '[]', 'script', '{}', '{}',
                    '{}', '{}', :request_digest,
                    'completed', 'delivery', 0, '2026-08-05 00:00:00',
                    '2026-08-05 00:00:00'
                )
                """
            ),
            {"request_digest": "f" * 64},
        )


@pytest.mark.asyncio
async def test_0029_adds_registered_artifact_table_and_nonempty_downgrade_fails_closed(
    tmp_path,
) -> None:
    assert TABLE in Base.metadata.tables
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'final-artifact.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, PREVIOUS_REVISION)
        assert await _version(engine) == PREVIOUS_REVISION
        assert TABLE not in await _tables(engine)

        await asyncio.to_thread(_upgrade, config, "head")
        assert await _version(engine) == REVISION
        assert {
            "id",
            "owner_user_id",
            "production_id",
            "qa_event_id",
            "delivery_event_id",
            "contract_version",
            "role",
            "storage_key",
            "sha256",
            "size_bytes",
            "mime_type",
            "content_available",
            "metadata_json",
            "artifact_digest",
            "created_at",
        } == await _columns(engine, TABLE)

        await _seed_artifact(engine)
        with pytest.raises(RuntimeError, match="Owner backup"):
            await asyncio.to_thread(
                alembic_command.downgrade,
                config,
                PREVIOUS_REVISION,
            )
        assert await _version(engine) == REVISION
        async with engine.connect() as connection:
            row = (await connection.execute(sa.text("SELECT owner_user_id, storage_key, sha256, content_available FROM personal_ip_artifacts WHERE id = 'artifact-1'"))).one()
        assert tuple(row) == (
            "owner-1",
            "video-deliveries/final.mp4",
            "d" * 64,
            True,
        )

        async with engine.begin() as connection:
            await connection.execute(sa.text("DELETE FROM personal_ip_artifacts WHERE id = 'artifact-1'"))
        await asyncio.to_thread(
            alembic_command.downgrade,
            config,
            PREVIOUS_REVISION,
        )
        assert await _version(engine) == PREVIOUS_REVISION
        assert TABLE not in await _tables(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0029_upgrade_fails_closed_for_completed_linked_production_without_artifact(
    tmp_path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'unsealed-linked.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, PREVIOUS_REVISION)
        await _seed_completed_linked_production_without_artifact(engine)

        with pytest.raises(RuntimeError, match="completed linked Owner productions"):
            await asyncio.to_thread(_upgrade, config, "head")
        assert await _version(engine) == PREVIOUS_REVISION
        assert TABLE not in await _tables(engine)
    finally:
        await engine.dispose()
