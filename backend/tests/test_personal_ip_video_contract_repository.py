from __future__ import annotations

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_video_productions import PersonalIPVideoProductionRepository
from deerflow.personal_ip.video_contracts import (
    compile_final_edit_lock,
    compile_generated_shot_qa,
    compile_timeline_revision,
    compile_video_plan,
)


@pytest.mark.asyncio
async def test_legacy_mode_less_production_accepts_a_sealed_timeline_revision(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    productions = PersonalIPVideoProductionRepository(sf)
    created = await productions.begin(
        owner_user_id="user-1",
        operation_key="video:legacy:1",
        title="旧视频制作",
        subject_id=None,
        target_account_ids=[],
        source_kind="script",
        source={"script": "创建时还没有 production_mode"},
        delivery_spec={"aspect_ratio": "9:16"},
        provider_policy={},
        budget={},
    )
    assert created["production_mode"] is None
    revision = compile_timeline_revision(
        production_id=created["id"],
        production_mode="faceless_material",
        revision_id="legacy-r1",
        base_revision_id=None,
        author_kind="human",
        intent="旧制作继续裁切",
        fps=24,
        tracks=[
            {
                "id": "video",
                "type": "video",
                "clips": [
                    {
                        "id": "clip-1",
                        "start_sec": 0,
                        "duration_sec": 1.5,
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
                "duration_sec": 1.5,
            }
        ],
        strategy_confirmed=True,
    )
    updated = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="timeline:legacy-r1",
        event_type="timeline_revision_compiled",
        status="succeeded",
        entity_type="timeline",
        entity_id="legacy-r1",
        payload=revision,
        input_refs=[f"video-production://{created['id']}/assembly"],
        output_refs=[f"contract://timeline/{revision['sha256']}"],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )

    assert updated is not None
    assert updated["events"][-1]["payload"]["production_mode"] == "faceless_material"
    await close_engine()


@pytest.mark.asyncio
async def test_video_production_mode_and_compiled_contract_share_existing_ledger(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    productions = PersonalIPVideoProductionRepository(sf)

    created = await productions.begin(
        owner_user_id="user-1",
        operation_key="video:faceless:1",
        title="素材视频",
        subject_id=None,
        target_account_ids=[],
        source_kind="script",
        source={"script": "智能体统筹八个平台。"},
        delivery_spec={"aspect_ratio": "9:16"},
        provider_policy={},
        budget={},
        production_mode="faceless_material",
    )

    assert created["production_mode"] == "faceless_material"
    assert created["source"]["production_mode"] == "faceless_material"

    contract = compile_video_plan(
        production_id=created["id"],
        production_mode="faceless_material",
        plan={
            "title": "素材视频",
            "objective": "解释本地智能体",
            "target_audience": "个人 IP 创作者",
            "platforms": ["douyin"],
            "argument": "智能体应该统筹全部账号",
            "narration_language": "zh-CN",
            "evidence_refs": ["evidence://1"],
            "measurement_plan": {"primary_metric": "views"},
        },
    )
    updated = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="plan:v1",
        event_type="video_plan_compiled",
        status="succeeded",
        entity_type="production",
        entity_id=created["id"],
        payload=contract,
        input_refs=[f"video-production://{created['id']}/request"],
        output_refs=[f"contract://video-plan/{contract['sha256']}"],
        provider="deerflow_contract_compiler",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "currency": "CNY", "amount": 0},
    )

    assert updated is not None
    assert updated["events"][0]["payload"]["sha256"] == contract["sha256"]
    assert updated["current_stage"] == "blueprint"

    forged = {**contract, "sha256": "0" * 64}
    with pytest.raises(ValueError, match="digest"):
        await productions.append_event(
            created["id"],
            owner_user_id="user-1",
            event_key="plan:forged",
            event_type="video_plan_compiled",
            status="succeeded",
            entity_type="production",
            entity_id=created["id"],
            payload=forged,
            input_refs=[],
            output_refs=["contract://forged"],
            provider="manual",
            model=None,
            provider_task_id=None,
            cost={},
        )

    failed_qa = compile_generated_shot_qa(
        production_id=created["id"],
        production_mode="faceless_material",
        shot_id="shot-1",
        candidate_id="shot-1:candidate-1",
        artifact={"ref": "artifact://candidate.mp4", "sha256": "c" * 64},
        anchor={"ref": "artifact://anchor.png", "sha256": "d" * 64},
        policy={
            "expected_width": 1080,
            "expected_height": 1920,
            "expected_fps": 24,
            "expected_duration_seconds": 5,
        },
        evidence={
            "width": 1080,
            "height": 1920,
            "fps": 24,
            "duration_seconds": 5,
            "audio_stream_count": 0,
            "decode_error_count": 0,
            "first_frame_ssim": 0.1,
            "internal_cut_transitions": [],
            "review_artifacts": [{"ref": "artifact://contact.jpg", "sha256": "e" * 64}],
        },
    )
    qa_result = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="qa:shot-1",
        event_type="generated_shot_qa_compiled",
        status="failed",
        entity_type="candidate",
        entity_id="shot-1:candidate-1",
        payload=failed_qa,
        input_refs=["artifact://candidate.mp4"],
        output_refs=[f"contract://qa/{failed_qa['sha256']}"],
        provider="deerflow_contract_compiler",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    assert qa_result is not None and qa_result["status"] == "blocked"

    with pytest.raises(ValueError, match="gate must match event status"):
        await productions.append_event(
            created["id"],
            owner_user_id="user-1",
            event_key="qa:shot-1:forged-status",
            event_type="generated_shot_qa_compiled",
            status="succeeded",
            entity_type="candidate",
            entity_id="shot-1:candidate-1",
            payload=failed_qa,
            input_refs=[],
            output_refs=["contract://qa/forged"],
            provider="manual",
            model=None,
            provider_task_id=None,
            cost={},
        )

    with pytest.raises(ValueError, match="source.production_mode is reserved"):
        await productions.begin(
            owner_user_id="user-1",
            operation_key="video:bad-source-mode",
            title="冲突模式",
            subject_id=None,
            target_account_ids=[],
            source_kind="idea",
            source={"idea": "冲突", "production_mode": "generative_cinematic"},
            delivery_spec={},
            provider_policy={},
            budget={},
            production_mode="faceless_material",
        )

    timeline_revision = compile_timeline_revision(
        production_id=created["id"],
        production_mode="faceless_material",
        revision_id="timeline-r1",
        base_revision_id=None,
        author_kind="human",
        intent="用户把素材镜头缩短半秒",
        fps=25,
        tracks=[
            {
                "id": "video",
                "type": "video",
                "clips": [
                    {
                        "id": "clip-1",
                        "shot_id": "shot-1",
                        "start_sec": 0,
                        "duration_sec": 4.5,
                        "source_in_sec": 0.5,
                    }
                ],
            }
        ],
        operations=[
            {
                "id": "edit-1",
                "type": "trim",
                "clip_id": "clip-1",
                "source_in_sec": 0.5,
                "duration_sec": 4.5,
            }
        ],
        strategy_confirmed=True,
    )
    revised = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="timeline:r1",
        event_type="timeline_revision_compiled",
        status="succeeded",
        entity_type="timeline",
        entity_id="timeline-r1",
        payload=timeline_revision,
        input_refs=[f"video-production://{created['id']}/assembly"],
        output_refs=[f"contract://timeline/{timeline_revision['sha256']}"],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    assert revised is not None
    assert revised["current_stage"] == "finishing"
    assert revised["events"][-1]["payload"]["revision_id"] == "timeline-r1"

    delivery_qa = {
        "contract_version": "personal-ip-delivery-qa-v1",
        "passed": True,
        "checks": {"decode": {"passed": True}},
    }
    with pytest.raises(ValueError, match="final_edit_locked"):
        await productions.append_event(
            created["id"],
            owner_user_id="user-1",
            event_key="delivery-qa:before-lock",
            event_type="delivery_qa_completed",
            status="succeeded",
            entity_type="delivery",
            entity_id="delivery-1",
            payload=delivery_qa,
            input_refs=["timeline-revision://timeline-r1"],
            output_refs=["artifact://final.mp4"],
            provider="ffmpeg_ffprobe",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0, "currency": "CNY"},
        )

    final_lock = compile_final_edit_lock(
        production_id=created["id"],
        production_mode="faceless_material",
        lock_id="final-lock-1",
        timeline_revision=timeline_revision,
        locked_by="human",
        note="用户确认进入最终渲染和交付 QA",
    )
    locked = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
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
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    assert locked is not None
    accepted_qa = await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="delivery-qa:after-lock",
        event_type="delivery_qa_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="delivery-1",
        payload=delivery_qa,
        input_refs=["final-edit-lock://final-lock-1"],
        output_refs=["artifact://final.mp4"],
        provider="ffmpeg_ffprobe",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    assert accepted_qa is not None
    assert accepted_qa["current_stage"] == "delivery"
    timeline_revision_2 = compile_timeline_revision(
        production_id=created["id"],
        production_mode="faceless_material",
        revision_id="timeline-r2",
        base_revision_id="timeline-r1",
        author_kind="human",
        intent="QA 后又调整了一次时间线",
        fps=25,
        tracks=timeline_revision["tracks"],
        operations=[
            {
                "id": "edit-2",
                "type": "restore_revision",
                "revision_id": "timeline-r1",
                "clip_id": None,
            }
        ],
        strategy_confirmed=True,
    )
    await productions.append_event(
        created["id"],
        owner_user_id="user-1",
        event_key="timeline:r2",
        event_type="timeline_revision_compiled",
        status="succeeded",
        entity_type="timeline",
        entity_id="timeline-r2",
        payload=timeline_revision_2,
        input_refs=["timeline-revision://timeline-r1"],
        output_refs=[f"contract://timeline/{timeline_revision_2['sha256']}"],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    with pytest.raises(ValueError, match="latest timeline revision"):
        await productions.append_event(
            created["id"],
            owner_user_id="user-1",
            event_key="delivery:stale-qa",
            event_type="delivery_completed",
            status="succeeded",
            entity_type="delivery",
            entity_id="delivery-1",
            payload={"contract_version": "personal-ip-delivery-v1"},
            input_refs=["delivery-qa://after-lock"],
            output_refs=["artifact://final.mp4"],
            provider="deerflow",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0, "currency": "CNY"},
        )
    await close_engine()
