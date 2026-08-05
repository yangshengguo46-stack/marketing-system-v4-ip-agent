from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import update
from sqlalchemy.dialects import postgresql

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_artifacts import PersonalIPArtifactRow
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_video_productions import PersonalIPVideoProductionRepository
from deerflow.personal_ip.content_contracts import (
    ContentWorkCreate,
    ScriptDraft,
    script_decision_digest,
)
from deerflow.personal_ip.video_contracts import compile_final_edit_lock, compile_timeline_revision

OWNER = "owner-1"
SOURCE_REF = "file:///private/owner-1/video-deliveries/final.mp4"
STORAGE_KEY = "video-deliveries/production-1/final.mp4"
CONTENT_SHA256 = "a" * 64
CONTENT_SIZE = 2_048
MIME_TYPE = "video/mp4"
ZERO_COST = {"status": "known", "amount": 0, "currency": "CNY"}


def _content_request() -> ContentWorkCreate:
    return ContentWorkCreate.model_validate(
        {
            "idempotency_key": "content-final-artifact-1",
            "title": "第一次公开演示",
            "entry_route": "zero_start",
            "objective": {"desired_change": "把已发生的一步讲清楚"},
            "direction": {
                "premise": "从已经完成的动作开始",
                "audience_situation": "还不知道项目进展的人",
                "core_tension": "展示进展但不夸大结果",
                "content_promise": "只说已经发生的事",
                "creative_route": "第一人称事实口述",
                "rationale": "事实足以成立。",
                "truth_mode": "factual",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
            "script": {
                "title": "第一次公开演示",
                "story_mode": "factual",
                "script_text": "我今天完成了第一次公开演示。",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
                "production_notes": {"form": "spoken", "setting": "工作台"},
            },
        }
    )


def _verified_script(script: ScriptDraft | None) -> frozenset[str]:
    assert script is not None
    return frozenset({script_decision_digest(script)})


async def _linked_production(
    content: PersonalIPContentRepository,
    productions: PersonalIPVideoProductionRepository,
) -> dict:
    request = _content_request()
    lineage = await content.create(
        owner_user_id=OWNER,
        request=request,
        thread_id="thread-final-artifact",
        verified_script_digests=_verified_script(request.script),
    )
    work = lineage["content_work"]
    script = lineage["script_versions"][0]
    return await productions.begin(
        owner_user_id=OWNER,
        operation_key="production-final-artifact-1",
        title="制作：第一次公开演示",
        subject_id=None,
        target_account_ids=[],
        source_kind="script",
        source={},
        delivery_spec={"aspect_ratio": "9:16", "require_audio": True},
        provider_policy={},
        budget={},
        production_mode="faceless_material",
        thread_id="thread-production-final-artifact",
        content_work_id=work["id"],
        script_version_id=script["id"],
    )


async def _lock_latest_timeline(
    productions: PersonalIPVideoProductionRepository,
    production: dict,
) -> None:
    revision = compile_timeline_revision(
        production_id=production["id"],
        production_mode="faceless_material",
        revision_id="timeline-r1",
        base_revision_id=None,
        author_kind="human",
        intent="确认最终剪辑",
        fps=25,
        tracks=[
            {
                "id": "video",
                "type": "video",
                "clips": [
                    {
                        "id": "clip-1",
                        "start_sec": 0,
                        "duration_sec": 2,
                        "source_in_sec": 0,
                    }
                ],
            }
        ],
        operations=[
            {
                "id": "edit-1",
                "type": "trim",
                "clip_id": "clip-1",
                "source_in_sec": 0,
                "duration_sec": 2,
            }
        ],
        strategy_confirmed=True,
    )
    await productions.append_event(
        production["id"],
        owner_user_id=OWNER,
        event_key="timeline:r1",
        event_type="timeline_revision_compiled",
        status="succeeded",
        entity_type="timeline",
        entity_id="timeline-r1",
        payload=revision,
        input_refs=[f"video-production://{production['id']}/assembly"],
        output_refs=[f"contract://timeline/{revision['sha256']}"],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost=ZERO_COST,
    )
    final_lock = compile_final_edit_lock(
        production_id=production["id"],
        production_mode="faceless_material",
        lock_id="final-lock-1",
        timeline_revision=revision,
        locked_by="human",
        note="确认进入最终渲染和 QA",
    )
    await productions.append_event(
        production["id"],
        owner_user_id=OWNER,
        event_key="final-lock:1",
        event_type="final_edit_locked",
        status="succeeded",
        entity_type="timeline",
        entity_id="final-lock-1",
        payload=final_lock,
        input_refs=["timeline-revision://timeline-r1"],
        output_refs=[f"contract://final-lock/{final_lock['sha256']}"],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost=ZERO_COST,
    )


async def _append_source_execution(
    productions: PersonalIPVideoProductionRepository,
    production_id: str,
    *,
    event_key: str = "render:final",
    sha256: str = CONTENT_SHA256,
    mime_type: str = MIME_TYPE,
) -> None:
    await productions.append_event(
        production_id,
        owner_user_id=OWNER,
        event_key=event_key,
        event_type="media_processing_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="final-lock-1",
        payload={
            "contract_version": "personal-ip-media-execution-v1",
            "capability": "media_processing",
            "provider": "project-ffmpeg",
            "executor": "locked-timeline-renderer",
            "model": None,
            "status": "succeeded",
            "task_id": None,
            "request_id": "render-final-1",
            "started_at": "2026-08-05T01:00:00+00:00",
            "completed_at": "2026-08-05T01:00:02+00:00",
            "parameters": {"job_kind": "locked_timeline_delivery"},
            "inputs": [],
            "outputs": [
                {
                    "ref": SOURCE_REF,
                    "sha256": sha256,
                    "size_bytes": CONTENT_SIZE,
                    "mime_type": mime_type,
                }
            ],
            "cost": ZERO_COST,
            "failure": None,
        },
        input_refs=["contract://final-lock/1"],
        output_refs=[SOURCE_REF],
        provider="project-ffmpeg",
        model=None,
        provider_task_id=None,
        cost=ZERO_COST,
    )


def _qa_payload(
    *,
    sha256: str = CONTENT_SHA256,
    mime_type: str = MIME_TYPE,
) -> dict:
    return {
        "contract_version": "personal-ip-delivery-qa-v1",
        "passed": True,
        "artifact": {
            "ref": SOURCE_REF,
            "sha256": sha256,
            "size_bytes": CONTENT_SIZE,
            "mime_type": mime_type,
        },
        "delivery_spec": {"aspect_ratio": "9:16", "require_audio": True},
        "checks": [{"name": "decode", "passed": True}],
        "probe": {"video_codec": "h264", "width": 1080, "height": 1920},
        "executors": {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"},
    }


async def _append_qa(
    productions: PersonalIPVideoProductionRepository,
    production_id: str,
    *,
    event_key: str,
    sha256: str = CONTENT_SHA256,
    mime_type: str = MIME_TYPE,
    trusted: bool = True,
) -> dict | None:
    return await productions.append_event(
        production_id,
        owner_user_id=OWNER,
        event_key=event_key,
        event_type="delivery_qa_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="final-lock-1",
        payload=_qa_payload(sha256=sha256, mime_type=mime_type),
        input_refs=[SOURCE_REF],
        output_refs=[SOURCE_REF],
        provider="project-ffmpeg-ffprobe",
        model=None,
        provider_task_id=None,
        cost=ZERO_COST,
        trusted_delivery_qa=trusted,
    )


def _complete_args(
    *,
    qa_event_key: str = "qa:correct",
    source_execution_event_keys: list[str] | None = None,
) -> dict:
    return {
        "owner_user_id": OWNER,
        "event_key": "delivery:final",
        "qa_event_key": qa_event_key,
        "source_execution_event_keys": source_execution_event_keys or ["render:final"],
        "source_ref": SOURCE_REF,
        "storage_key": STORAGE_KEY,
        "sha256": CONTENT_SHA256,
        "size_bytes": CONTENT_SIZE,
        "mime_type": MIME_TYPE,
        "metadata": {"source_revision_id": "timeline-r1", "lock_id": "final-lock-1"},
        "provider": "project-ffmpeg",
        "model": None,
        "provider_task_id": None,
        "cost": ZERO_COST,
        "occurred_at": datetime(2026, 8, 5, 1, 1, tzinfo=UTC),
    }


@pytest.mark.asyncio
async def test_linked_delivery_atomically_seals_one_customer_safe_final_artifact(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    productions = PersonalIPVideoProductionRepository(sf)
    try:
        production = await _linked_production(content, productions)
        await _lock_latest_timeline(productions, production)
        await _append_source_execution(productions, production["id"])

        with pytest.raises(ValueError, match="trusted executor"):
            await _append_qa(
                productions,
                production["id"],
                event_key="qa:untrusted",
                trusted=False,
            )

        await _append_qa(
            productions,
            production["id"],
            event_key="qa:wrong",
            sha256="b" * 64,
        )
        before = await productions.get(production["id"], owner_user_id=OWNER)
        assert before is not None
        assert before["status"] == "running"
        assert before["final_artifact"] is None
        with pytest.raises(ValueError, match="exact passed delivery QA"):
            await productions.complete_delivery_and_seal_artifact(
                production["id"],
                **_complete_args(qa_event_key="qa:wrong"),
            )
        after_failed_seal = await productions.get(production["id"], owner_user_id=OWNER)
        assert after_failed_seal is not None
        assert after_failed_seal["event_count"] == before["event_count"]
        assert after_failed_seal["final_artifact"] is None

        await _append_qa(productions, production["id"], event_key="qa:correct")
        with pytest.raises(ValueError, match="latest delivery QA"):
            await productions.complete_delivery_and_seal_artifact(
                production["id"],
                **_complete_args(qa_event_key="qa:wrong"),
            )
        with pytest.raises(ValueError, match="must use complete_delivery_and_seal_artifact"):
            await productions.append_event(
                production["id"],
                owner_user_id=OWNER,
                event_key="delivery:generic",
                event_type="delivery_completed",
                status="succeeded",
                entity_type="delivery",
                entity_id="final-lock-1",
                payload={"accepted": True},
                input_refs=[SOURCE_REF],
                output_refs=[SOURCE_REF],
                provider="project-ffmpeg",
                model=None,
                provider_task_id=None,
                cost=ZERO_COST,
            )

        completed = await productions.complete_delivery_and_seal_artifact(
            production["id"],
            **_complete_args(),
        )
        assert completed is not None
        assert completed["status"] == "completed"
        assert completed["current_stage"] == "delivery"
        artifact = completed["final_artifact"]
        assert artifact["contract_version"] == "personal-ip-final-artifact-v1"
        assert artifact["role"] == "final_video"
        assert artifact["content_sha256"] == CONTENT_SHA256
        assert artifact["size_bytes"] == CONTENT_SIZE
        assert artifact["mime_type"] == MIME_TYPE
        assert artifact["content_available"] is True
        assert "owner_user_id" not in artifact
        assert "storage_key" not in artifact
        assert "sha256" not in artifact
        delivery_event = completed["events"][-1]
        assert delivery_event["event_type"] == "delivery_completed"
        assert delivery_event["entity_type"] == "artifact"
        assert delivery_event["entity_id"] == artifact["id"]
        assert delivery_event["output_refs"] == [f"artifact://{artifact['id']}"]
        assert "content_available" not in delivery_event["payload"]["artifact"]
        serialized_delivery = json.dumps(delivery_event, sort_keys=True)
        assert SOURCE_REF not in serialized_delivery
        assert STORAGE_KEY not in serialized_delivery

        fetched = await productions.get_artifact(artifact["id"], owner_user_id=OWNER)
        assert fetched == artifact
        private = await productions.get_artifact(
            artifact["id"],
            owner_user_id=OWNER,
            include_storage_key=True,
        )
        assert private == {**artifact, "storage_key": STORAGE_KEY}
        assert await productions.get_artifact(artifact["id"], owner_user_id="owner-2") is None
        listed = await productions.list(OWNER, content_work_id=completed["content_work_id"])
        assert listed[0]["final_artifact"] == artifact

        replayed = await productions.complete_delivery_and_seal_artifact(
            production["id"],
            **_complete_args(),
        )
        assert replayed == completed
        with pytest.raises(ValueError, match="different final Artifact"):
            await productions.complete_delivery_and_seal_artifact(
                production["id"],
                **{
                    **_complete_args(),
                    "storage_key": "video-deliveries/production-1/other.mp4",
                },
            )
        unchanged = await productions.get(production["id"], owner_user_id=OWNER)
        assert unchanged == completed

        async with sf() as session:
            await session.execute(update(PersonalIPArtifactRow).where(PersonalIPArtifactRow.id == artifact["id"]).values(content_available=False))
            await session.commit()
        unavailable = await productions.get_artifact(
            artifact["id"],
            owner_user_id=OWNER,
        )
        assert unavailable is not None
        assert unavailable["content_available"] is False
        assert (
            await productions.mark_artifact_content_available(
                artifact["id"],
                owner_user_id="owner-2",
                expected_sha256=CONTENT_SHA256,
                expected_size_bytes=CONTENT_SIZE,
                expected_mime_type=MIME_TYPE,
            )
            is None
        )
        with pytest.raises(ValueError, match="canonical lowercase"):
            await productions.mark_artifact_content_available(
                artifact["id"],
                owner_user_id=OWNER,
                expected_sha256="A" * 64,
                expected_size_bytes=CONTENT_SIZE,
                expected_mime_type=MIME_TYPE,
            )
        for identity_override in (
            {"expected_sha256": "b" * 64},
            {"expected_size_bytes": CONTENT_SIZE + 1},
            {"expected_mime_type": "video/webm"},
        ):
            with pytest.raises(ValueError, match="immutable Artifact identity"):
                await productions.mark_artifact_content_available(
                    artifact["id"],
                    owner_user_id=OWNER,
                    expected_sha256=identity_override.get(
                        "expected_sha256",
                        CONTENT_SHA256,
                    ),
                    expected_size_bytes=identity_override.get(
                        "expected_size_bytes",
                        CONTENT_SIZE,
                    ),
                    expected_mime_type=identity_override.get(
                        "expected_mime_type",
                        MIME_TYPE,
                    ),
                )
        available = await productions.mark_artifact_content_available(
            artifact["id"],
            owner_user_id=OWNER,
            expected_sha256=CONTENT_SHA256,
            expected_size_bytes=CONTENT_SIZE,
            expected_mime_type=MIME_TYPE,
        )
        assert available == artifact
        replayed_availability = await productions.mark_artifact_content_available(
            artifact["id"],
            owner_user_id=OWNER,
            expected_sha256=CONTENT_SHA256,
            expected_size_bytes=CONTENT_SIZE,
            expected_mime_type=MIME_TYPE,
        )
        assert replayed_availability == artifact
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_final_artifact_receipts_must_already_use_canonical_hash_and_mime(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    productions = PersonalIPVideoProductionRepository(sf)
    try:
        production = await _linked_production(content, productions)
        await _lock_latest_timeline(productions, production)
        await _append_source_execution(
            productions,
            production["id"],
            event_key="render:uppercase",
            sha256="A" * 64,
            mime_type="VIDEO/MP4",
        )
        await _append_qa(
            productions,
            production["id"],
            event_key="qa:canonical-before-source",
        )
        with pytest.raises(ValueError, match="successful source execution"):
            await productions.complete_delivery_and_seal_artifact(
                production["id"],
                **_complete_args(
                    qa_event_key="qa:canonical-before-source",
                    source_execution_event_keys=["render:uppercase"],
                ),
            )

        await _append_source_execution(
            productions,
            production["id"],
            event_key="render:canonical",
        )
        await _append_qa(
            productions,
            production["id"],
            event_key="qa:uppercase",
            sha256="A" * 64,
            mime_type="VIDEO/MP4",
        )
        with pytest.raises(ValueError, match="exact passed delivery QA"):
            await productions.complete_delivery_and_seal_artifact(
                production["id"],
                **_complete_args(
                    qa_event_key="qa:uppercase",
                    source_execution_event_keys=["render:canonical"],
                ),
            )
        rejected = await productions.get(production["id"], owner_user_id=OWNER)
        assert rejected is not None
        assert rejected["final_artifact"] is None
        assert rejected["status"] == "running"

        await _append_qa(
            productions,
            production["id"],
            event_key="qa:canonical",
        )
        completed = await productions.complete_delivery_and_seal_artifact(
            production["id"],
            **_complete_args(
                qa_event_key="qa:canonical",
                source_execution_event_keys=["render:canonical"],
            ),
        )
        assert completed is not None
        assert completed["final_artifact"]["content_sha256"] == CONTENT_SHA256
        assert completed["final_artifact"]["mime_type"] == MIME_TYPE
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_final_artifact_rejects_qa_for_a_stale_delivery_execution(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    productions = PersonalIPVideoProductionRepository(sf)
    try:
        production = await _linked_production(content, productions)
        await _lock_latest_timeline(productions, production)
        await _append_source_execution(
            productions,
            production["id"],
            event_key="render:old",
        )
        await _append_qa(
            productions,
            production["id"],
            event_key="qa:old",
        )
        await _append_source_execution(
            productions,
            production["id"],
            event_key="render:new",
        )

        with pytest.raises(ValueError, match="source execution is stale"):
            await productions.complete_delivery_and_seal_artifact(
                production["id"],
                **_complete_args(
                    qa_event_key="qa:old",
                    source_execution_event_keys=["render:old"],
                ),
            )

        rejected = await productions.get(production["id"], owner_user_id=OWNER)
        assert rejected is not None
        assert rejected["status"] == "running"
        assert rejected["final_artifact"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_formal_final_artifact_rejects_unlinked_production_and_unsafe_storage_key(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    productions = PersonalIPVideoProductionRepository(sf)
    try:
        legacy = await productions.begin(
            owner_user_id=OWNER,
            operation_key="legacy-final-artifact",
            title="旧制作",
            subject_id=None,
            target_account_ids=[],
            source_kind="script",
            source={"script": "旧制作没有 ScriptVersion 绑定"},
            delivery_spec={},
            provider_policy={},
            budget={},
        )
        for unsafe_storage_key in (
            "/private/owner-1/final.mp4",
            "../owner-2/final.mp4",
            "video-deliveries/../owner-2/final.mp4",
            "file:///private/owner-1/final.mp4",
            "C:\\private\\final.mp4",
        ):
            with pytest.raises(ValueError, match="Owner-relative POSIX path"):
                await productions.complete_delivery_and_seal_artifact(
                    legacy["id"],
                    **{
                        **_complete_args(),
                        "storage_key": unsafe_storage_key,
                    },
                )
        with pytest.raises(ValueError, match="video-deliveries namespace"):
            await productions.complete_delivery_and_seal_artifact(
                legacy["id"],
                **{
                    **_complete_args(),
                    "storage_key": "other-owner-area/final.mp4",
                },
            )
        with pytest.raises(ValueError, match="private artifact locator"):
            await productions.complete_delivery_and_seal_artifact(
                legacy["id"],
                **{
                    **_complete_args(),
                    "metadata": {"source_ref": SOURCE_REF},
                },
            )
        with pytest.raises(ValueError, match="absolute filesystem locator"):
            await productions.complete_delivery_and_seal_artifact(
                legacy["id"],
                **{
                    **_complete_args(),
                    "metadata": {"diagnostic": "/private/owner-1/final.mp4"},
                },
            )
        with pytest.raises(ValueError, match="linked ScriptVersion production"):
            await productions.complete_delivery_and_seal_artifact(
                legacy["id"],
                **_complete_args(),
            )
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_postgres_seal_takes_owner_lifecycle_lock_before_production_read() -> None:
    operations: list[tuple] = []

    class EmptyResult:
        def scalar_one_or_none(self):
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.bind = type("Bind", (), {"dialect": postgresql.dialect()})()

        def get_bind(self):
            return self.bind

        async def begin(self) -> None:
            operations.append(("begin",))

        async def execute(self, statement, params=None):
            operations.append(("execute", statement, params))
            return EmptyResult()

    session = FakeSession()

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return False

    class SessionFactory:
        def __call__(self):
            return SessionContext()

    productions = PersonalIPVideoProductionRepository(SessionFactory())  # type: ignore[arg-type]
    result = await productions.complete_delivery_and_seal_artifact(
        "video-production-missing",
        **_complete_args(),
    )

    assert result is None
    assert operations[0] == ("begin",)
    assert operations[1][2] == {"lock_key": f"personal-ip-data-lifecycle:{OWNER}"}
    assert "pg_advisory_xact_lock(hashtext" in str(operations[1][1])
    production_read = str(operations[2][1].compile(dialect=postgresql.dialect()))
    assert "personal_ip_video_productions" in production_read
    assert "FOR UPDATE" in production_read
