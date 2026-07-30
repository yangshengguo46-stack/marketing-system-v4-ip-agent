from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.persistence.personal_ip_video_productions import PersonalIPVideoProductionRepository


@pytest.mark.asyncio
async def test_video_production_is_one_task_thread_and_legacy_projects_can_bind_once(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    productions = PersonalIPVideoProductionRepository(sf)

    task = await productions.begin(
        owner_user_id="user-1",
        thread_id="thread-video-1",
        operation_key="video:task:1",
        title="第一条视频",
        subject_id=None,
        target_account_ids=[],
        source_kind="idea",
        source={"idea": "任务式视频创作"},
        delivery_spec={},
        provider_policy={},
        budget={},
    )
    assert task["thread_id"] == "thread-video-1"
    assert [item["id"] for item in await productions.list("user-1", thread_id="thread-video-1")] == [task["id"]]

    legacy = await productions.begin(
        owner_user_id="user-1",
        operation_key="video:legacy:1",
        title="旧视频项目",
        subject_id=None,
        target_account_ids=[],
        source_kind="idea",
        source={"idea": "迁入历史任务"},
        delivery_spec={},
        provider_policy={},
        budget={},
    )
    bound = await productions.bind_thread(
        legacy["id"],
        owner_user_id="user-1",
        thread_id="thread-video-legacy",
    )
    assert bound is not None
    assert bound["thread_id"] == "thread-video-legacy"

    with pytest.raises(ValueError, match="already bound"):
        await productions.bind_thread(
            legacy["id"],
            owner_user_id="user-1",
            thread_id="thread-video-other",
        )

    await close_engine()


@pytest.mark.asyncio
async def test_video_production_keeps_immutable_request_and_append_only_stage_receipts(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    productions = PersonalIPVideoProductionRepository(sf)
    subject = await subjects.create(owner_user_id="user-1", display_name="老杨")
    account = await accounts.create(
        owner_user_id="user-1",
        subject_id=subject["id"],
        platform="douyin",
        display_name="老杨说 AI",
    )

    created = await productions.begin(
        owner_user_id="user-1",
        operation_key="video:agent-film:001",
        title="智能体不是应用程序",
        subject_id=subject["id"],
        target_account_ids=[account["id"]],
        source_kind="script",
        source={"script": "第一幕：智能体接管电脑。"},
        delivery_spec={"aspect_ratio": "9:16", "duration_seconds": 90},
        provider_policy={"video": ["seedance"], "image": ["seedream"]},
        budget={"currency": "CNY", "hard_limit": 200},
    )
    replayed = await productions.begin(
        owner_user_id="user-1",
        operation_key="video:agent-film:001",
        title="智能体不是应用程序",
        subject_id=subject["id"],
        target_account_ids=[account["id"]],
        source_kind="script",
        source={"script": "第一幕：智能体接管电脑。"},
        delivery_spec={"aspect_ratio": "9:16", "duration_seconds": 90},
        provider_policy={"video": ["seedance"], "image": ["seedream"]},
        budget={"currency": "CNY", "hard_limit": 200},
    )

    assert replayed == created
    assert created["contract_version"] == "personal-ip-video-production-v1"
    assert created["status"] == "draft"
    assert created["current_stage"] == "intake"
    assert created["events"] == []

    blueprint = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="blueprint:v1",
        event_type="blueprint_sealed",
        status="succeeded",
        entity_type="production",
        entity_id=created["id"],
        payload={"beats": ["冲突", "升级", "结果"], "characters": ["创作者", "智能体"]},
        input_refs=["source:script"],
        output_refs=["artifact://video/blueprint-v1.json"],
        provider="doubao",
        model="doubao-seed-1-8",
        provider_task_id=None,
        cost={"currency": "CNY", "amount": 0.12},
        occurred_at=datetime(2026, 7, 22, 5, 0, tzinfo=UTC),
    )
    failed = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="shot-01:attempt-1",
        event_type="shot_generation_failed",
        status="failed",
        entity_type="shot",
        entity_id="shot-01",
        payload={"error_category": "provider_timeout", "retryable": True},
        input_refs=["asset://character/creator", "shot://shot-01"],
        output_refs=[],
        provider="seedance",
        model="seedance-2.0",
        provider_task_id="task-1",
        cost={"currency": "CNY", "amount": 0},
        occurred_at=datetime(2026, 7, 22, 5, 1, tzinfo=UTC),
    )
    retried = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="shot-01:attempt-2",
        event_type="shot_generation_completed",
        status="succeeded",
        entity_type="candidate",
        entity_id="shot-01:candidate-2",
        payload={"shot_id": "shot-01", "duration_seconds": 6},
        input_refs=["shot://shot-01"],
        output_refs=["artifact://video/shot-01-candidate-2.mp4"],
        provider="seedance",
        model="seedance-2.0",
        provider_task_id="task-2",
        cost={"currency": "CNY", "amount": 3.2},
        occurred_at=datetime(2026, 7, 22, 5, 2, tzinfo=UTC),
    )
    qa = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="delivery:qa:v1",
        event_type="delivery_qa_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={"contract_version": "personal-ip-delivery-qa-v1", "passed": True},
        input_refs=["timeline://final-v1"],
        output_refs=["artifact://delivery/final-v1.mp4"],
        provider="ffmpeg_ffprobe",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "currency": "CNY", "amount": 0},
        occurred_at=datetime(2026, 7, 22, 5, 2, 30, tzinfo=UTC),
    )
    completed = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="delivery:v1",
        event_type="delivery_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={"duration_seconds": 90, "aspect_ratio": "9:16"},
        input_refs=["timeline://final-v1"],
        output_refs=["artifact://delivery/final-v1.mp4"],
        provider="mediakit_ffmpeg",
        model=None,
        provider_task_id=None,
        cost={"currency": "CNY", "amount": 0},
        occurred_at=datetime(2026, 7, 22, 5, 3, tzinfo=UTC),
    )

    assert blueprint is not None and blueprint["current_stage"] == "blueprint"
    assert failed is not None and failed["status"] == "blocked"
    assert retried is not None and retried["status"] == "running"
    assert completed is not None and completed["status"] == "completed"
    assert completed["current_stage"] == "delivery"
    assert qa is not None and qa["current_stage"] == "delivery"
    assert completed["event_count"] == 5
    assert [event["sequence"] for event in completed["events"]] == [1, 2, 3, 4, 5]
    assert completed["events"][1]["payload"]["retryable"] is True
    assert await productions.get(created["id"], owner_user_id="user-2") is None

    duplicate = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="delivery:v1",
        event_type="delivery_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={"duration_seconds": 90, "aspect_ratio": "9:16"},
        input_refs=["timeline://final-v1"],
        output_refs=["artifact://delivery/final-v1.mp4"],
        provider="mediakit_ffmpeg",
        model=None,
        provider_task_id=None,
        cost={"currency": "CNY", "amount": 0},
        occurred_at=datetime(2026, 7, 22, 5, 3, tzinfo=UTC),
    )
    assert duplicate == completed

    with pytest.raises(ValueError, match="terminal"):
        await productions.append_event(
            created["id"],
            owner_user_id="user-1",
            event_key="late-edit",
            event_type="edit_completed",
            status="succeeded",
            entity_type="timeline",
            entity_id="timeline-v2",
            payload={},
            input_refs=[],
            output_refs=[],
            provider="ffmpeg",
            model=None,
            provider_task_id=None,
            cost={},
        )
    await close_engine()


@pytest.mark.asyncio
async def test_video_production_rejects_contradictory_event_status(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    productions = PersonalIPVideoProductionRepository(sf)
    created = await productions.begin(
        owner_user_id="user-1",
        operation_key="video:status-contract",
        title="状态契约",
        subject_id=None,
        target_account_ids=[],
        source_kind="idea",
        source={"idea": "检验生产事件"},
        delivery_spec={},
        provider_policy={},
        budget={},
    )

    with pytest.raises(ValueError, match="shot_generation_failed status"):
        await productions.append_event(
            created["id"],
            owner_user_id="user-1",
            event_key="shot-1:bad-status",
            event_type="shot_generation_failed",
            status="succeeded",
            entity_type="shot",
            entity_id="shot-1",
            payload={},
            input_refs=[],
            output_refs=[],
            provider="seedance",
            model="seedance-2.0",
            provider_task_id="task-1",
            cost={},
        )
    with pytest.raises(ValueError, match="credential"):
        await productions.append_event(
            created["id"],
            owner_user_id="user-1",
            event_key="shot-1:credential-leak",
            event_type="shot_generation_requested",
            status="running",
            entity_type="shot",
            entity_id="shot-1",
            payload={"authorization": "Bearer secret-token"},
            input_refs=[],
            output_refs=[],
            provider="seedance",
            model="seedance-2.0",
            provider_task_id="task-1",
            cost={},
        )
    await close_engine()


@pytest.mark.asyncio
async def test_video_delivery_requires_successful_qa_for_the_exact_outputs(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    productions = PersonalIPVideoProductionRepository(sf)
    created = await productions.begin(
        owner_user_id="user-1",
        operation_key="video:delivery-qa-gate",
        title="交付 QA 门禁",
        subject_id=None,
        target_account_ids=[],
        source_kind="script",
        source={"script": "测试"},
        delivery_spec={"aspect_ratio": "9:16"},
        provider_policy={},
        budget={},
    )

    delivery_kwargs = {
        "owner_user_id": "user-1",
        "event_key": "delivery:v1",
        "event_type": "delivery_completed",
        "status": "succeeded",
        "entity_type": "delivery",
        "entity_id": "delivery-v1",
        "payload": {"accepted": True},
        "input_refs": ["timeline://v1"],
        "output_refs": ["file:///outputs/final.mp4"],
        "provider": "local",
        "model": None,
        "provider_task_id": None,
        "cost": {"status": "known", "currency": "CNY", "amount": 0},
    }
    with pytest.raises(ValueError, match="successful delivery QA"):
        await productions.append_event(created["id"], **delivery_kwargs)

    await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="delivery:qa:failed",
        event_type="delivery_qa_completed",
        status="failed",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={"contract_version": "personal-ip-delivery-qa-v1", "passed": False},
        input_refs=["timeline://v1"],
        output_refs=["file:///outputs/final.mp4"],
        provider="ffmpeg_ffprobe",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "currency": "CNY", "amount": 0},
    )
    with pytest.raises(ValueError, match="successful delivery QA"):
        await productions.append_event(created["id"], **delivery_kwargs)

    await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="delivery:qa:passed",
        event_type="delivery_qa_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={"contract_version": "personal-ip-delivery-qa-v1", "passed": True},
        input_refs=["timeline://v1"],
        output_refs=["file:///outputs/another.mp4"],
        provider="ffmpeg_ffprobe",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "currency": "CNY", "amount": 0},
    )
    with pytest.raises(ValueError, match="exact delivery outputs"):
        await productions.append_event(created["id"], **delivery_kwargs)

    await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="delivery:qa:passed-v2",
        event_type="delivery_qa_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-v1",
        payload={"contract_version": "personal-ip-delivery-qa-v1", "passed": True},
        input_refs=["timeline://v1"],
        output_refs=["file:///outputs/final.mp4"],
        provider="ffmpeg_ffprobe",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "currency": "CNY", "amount": 0},
    )
    completed = await productions.append_event(created["id"], **delivery_kwargs)
    assert completed is not None and completed["status"] == "completed"
    await close_engine()
