from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins.personal_ip_tools import (
    _personal_ip_compile_approved_video_assembly,
    _personal_ip_compile_generated_shot_qa,
    _personal_ip_compile_video_asset_manifest,
    _personal_ip_compile_video_continuity,
    _personal_ip_compile_video_material_selection,
    _personal_ip_compile_video_narration,
    _personal_ip_compile_video_narration_timing,
    _personal_ip_compile_video_plan,
    _personal_ip_compile_video_storyboard,
    _personal_ip_compile_video_timeline_revision,
    _personal_ip_lock_video_final_edit,
)


@pytest.mark.asyncio
async def test_typed_video_tools_compile_server_side_and_append_to_existing_ledger() -> None:
    production = {
        "id": "video-production-1",
        "production_mode": "faceless_material",
        "source": {"production_mode": "faceless_material"},
    }
    repository = SimpleNamespace(
        get=AsyncMock(return_value=production),
        append_event=AsyncMock(return_value={"id": "video-production-1", "status": "running", "events": []}),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=repository,
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    plan_result = json.loads(
        await _personal_ip_compile_video_plan(
            runtime,
            production_id="video-production-1",
            event_key="plan:v1",
            plan={
                "title": "素材视频",
                "objective": "解释智能体",
                "target_audience": "创作者",
                "platforms": ["douyin"],
                "argument": "智能体统筹所有账号",
                "narration_language": "zh-CN",
                "evidence_refs": ["evidence://1"],
                "measurement_plan": {"primary_metric": "views"},
            },
        )
    )
    plan_kwargs = repository.append_event.await_args.kwargs
    assert plan_result["operation_status"] == "ok"
    assert plan_kwargs["event_type"] == "video_plan_compiled"
    assert plan_kwargs["payload"]["production_mode"] == "faceless_material"
    assert plan_kwargs["provider"] == "deerflow_contract_compiler"

    await _personal_ip_compile_video_asset_manifest(
        runtime,
        production_id="video-production-1",
        event_key="assets:v1",
        assets=[
            {
                "id": "asset-1",
                "type": "owned_video",
                "name": "本人拍摄素材",
                "source_ref": "artifact://owned/1.mp4",
                "license": "owner-provided",
                "allowed_for_use": True,
            }
        ],
    )
    assert repository.append_event.await_args.kwargs["event_type"] == "asset_manifest_compiled"

    await _personal_ip_compile_video_storyboard(
        runtime,
        production_id="video-production-1",
        event_key="storyboard:v1",
        shots=[
            {
                "id": "shot-1",
                "order": 1,
                "duration_seconds": 5,
                "narration_text": "智能体统筹全部账号。",
                "visual_subject": "创作者的数据看板",
                "visual_query": "creator dashboard",
                "composition_strategy": "full_bleed",
                "claim_evidence_refs": [],
                "claim_evidence_quotes": {},
                "negative_conditions": [],
                "pass_criteria": ["语义一致"],
            }
        ],
    )
    assert repository.append_event.await_args.kwargs["event_type"] == "storyboard_compiled"
    assert repository.append_event.await_count == 3


@pytest.mark.asyncio
async def test_advanced_video_tools_reuse_storyboard_and_verify_assembly_receipts() -> None:
    from deerflow.personal_ip.video_contracts import compile_storyboard

    storyboard = compile_storyboard(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        shots=[
            {
                "id": "shot-1",
                "scene_id": "scene-1",
                "order": 1,
                "duration_seconds": 4,
                "first_frame": "角色站在门外",
                "last_frame": "角色进入房间",
                "motion": "推门",
                "camera": "中景跟拍",
                "action": "进入房间",
                "preserve_elements": ["黑衣"],
                "change_elements": ["位置"],
            }
        ],
    )
    source_sha = "a" * 64
    production = {
        "id": "video-production-film",
        "production_mode": "generative_cinematic",
        "source": {"production_mode": "generative_cinematic"},
        "events": [
            {
                "id": "storyboard-event",
                "event_key": "storyboard:v1",
                "event_type": "storyboard_compiled",
                "entity_type": "production",
                "entity_id": "video-production-film",
                "status": "succeeded",
                "payload": storyboard,
            },
            {
                "id": "selection-1",
                "event_key": "selection:shot-1",
                "event_type": "candidate_selected",
                "entity_type": "candidate",
                "entity_id": "shot-1:candidate-1",
                "status": "succeeded",
                "payload": {"source_sha256": source_sha},
            },
            {
                "id": "qa-1",
                "event_key": "qa:shot-1",
                "event_type": "generated_shot_qa_compiled",
                "entity_type": "candidate",
                "entity_id": "shot-1:candidate-1",
                "status": "succeeded",
                "payload": {
                    "artifact": {"ref": "artifact://shot-1.mp4", "sha256": source_sha},
                    "automated_gate_passed": True,
                },
            },
        ],
    }
    repository = SimpleNamespace(
        get=AsyncMock(return_value=production),
        append_event=AsyncMock(return_value={"id": "video-production-film", "status": "running", "events": []}),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=repository,
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    continuity = json.loads(
        await _personal_ip_compile_video_continuity(
            runtime,
            production_id="video-production-film",
            event_key="continuity:v1",
            initial_facts=[{"domain": "character", "subject_id": "char-1", "attribute": "location", "value": "outside"}],
            shot_states=[
                {
                    "shot_id": "shot-1",
                    "order": 1,
                    "preserve": [],
                    "changes": [
                        {
                            "domain": "character",
                            "subject_id": "char-1",
                            "attribute": "location",
                            "before": "outside",
                            "after": "inside",
                        }
                    ],
                }
            ],
        )
    )
    assert continuity["operation_status"] == "ok"
    assert repository.append_event.await_args.kwargs["event_type"] == "continuity_compiled"

    qa = json.loads(
        await _personal_ip_compile_generated_shot_qa(
            runtime,
            production_id="video-production-film",
            event_key="qa:new",
            shot_id="shot-1",
            candidate_id="shot-1:candidate-new",
            artifact={"ref": "artifact://new.mp4", "sha256": "d" * 64},
            anchor={"ref": "artifact://anchor.png", "sha256": "e" * 64},
            policy={
                "expected_width": 1920,
                "expected_height": 1080,
                "expected_fps": 24,
                "expected_duration_seconds": 4,
            },
            evidence={
                "width": 1920,
                "height": 1080,
                "fps": 24,
                "duration_seconds": 4,
                "audio_stream_count": 0,
                "decode_error_count": 0,
                "first_frame_ssim": 0.9,
                "internal_cut_transitions": [],
                "review_artifacts": [{"ref": "artifact://contact.jpg", "sha256": "f" * 64}],
            },
        )
    )
    assert qa["compiled_contract"]["automated_gate_passed"] is True
    assert repository.append_event.await_args.kwargs["event_type"] == "generated_shot_qa_compiled"

    assembly = json.loads(
        await _personal_ip_compile_approved_video_assembly(
            runtime,
            production_id="video-production-film",
            event_key="assembly:v1",
            timeline_id="timeline-v1",
            resolution="1920x1080",
            fps=24,
            clips=[
                {
                    "order": 1,
                    "shot_id": "shot-1",
                    "candidate_id": "shot-1:candidate-1",
                    "duration_seconds": 4,
                    "source_ref": "artifact://shot-1.mp4",
                    "source_sha256": source_sha,
                    "selection_receipt_ref": "event://selection-1",
                    "selection_source_sha256": source_sha,
                    "qa_receipt_ref": "event://qa-1",
                    "qa_source_sha256": source_sha,
                    "qa_passed": True,
                }
            ],
        )
    )
    assert assembly["operation_status"] == "ok"
    assert repository.append_event.await_args.kwargs["event_type"] == "assembly_admitted"
    assert repository.append_event.await_args.kwargs["entity_type"] == "timeline"

    revision = json.loads(
        await _personal_ip_compile_video_timeline_revision(
            runtime,
            production_id="video-production-film",
            event_key="timeline:r2",
            revision_id="timeline-r2",
            base_revision_id="timeline-v1",
            author_kind="agent",
            intent="把镜头一缩短半秒",
            fps=24,
            tracks=[
                {
                    "id": "video",
                    "type": "video",
                    "clips": [
                        {
                            "id": "clip-1",
                            "shot_id": "shot-1",
                            "start_sec": 0,
                            "duration_sec": 3.5,
                            "source_in_sec": 0.5,
                            "source_ref": "artifact://shot-1.mp4",
                            "source_sha256": source_sha,
                            "selected_candidate_id": "shot-1:candidate-1",
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
                    "duration_sec": 3.5,
                }
            ],
            strategy_confirmed=True,
        )
    )
    assert revision["operation_status"] == "ok"
    assert repository.append_event.await_args.kwargs["event_type"] == "timeline_revision_compiled"
    assert repository.append_event.await_args.kwargs["payload"]["author_kind"] == "agent"
    production["events"].append(
        {
            "event_type": "timeline_revision_compiled",
            "payload": revision["compiled_contract"],
        }
    )
    locked = json.loads(
        await _personal_ip_lock_video_final_edit(
            runtime,
            production_id="video-production-film",
            event_key="final-lock:1",
            lock_id="final-lock-1",
            locked_by="agent",
            note="已完成剪辑策略并锁定最新修订用于 QA",
        )
    )
    assert locked["operation_status"] == "ok"
    assert repository.append_event.await_args.kwargs["event_type"] == "final_edit_locked"
    assert repository.append_event.await_args.kwargs["payload"]["source_timeline_sha256"] == revision["compiled_contract"]["sha256"]


@pytest.mark.asyncio
async def test_material_narration_tool_uses_latest_typed_storyboard() -> None:
    from deerflow.personal_ip.video_contracts import compile_asset_manifest, compile_storyboard

    storyboard = compile_storyboard(
        production_id="video-production-1",
        production_mode="faceless_material",
        shots=[
            {
                "id": "shot-1",
                "order": 1,
                "duration_seconds": 5,
                "narration_text": "智能体统筹全部账号。",
                "visual_subject": "全平台看板",
                "visual_query": "dashboard",
                "composition_strategy": "full_bleed",
                "claim_evidence_refs": [],
                "claim_evidence_quotes": {},
                "negative_conditions": [],
                "pass_criteria": ["语义一致"],
            }
        ],
    )
    assets = compile_asset_manifest(
        production_id="video-production-1",
        production_mode="faceless_material",
        assets=[
            {
                "id": "asset-1",
                "type": "stock_video",
                "name": "全平台看板",
                "source_ref": "https://example.com/video/1",
                "license": "CC-BY-4.0",
                "allowed_for_use": True,
                "sha256": "a" * 64,
            }
        ],
    )
    production = {
        "id": "video-production-1",
        "production_mode": "faceless_material",
        "source": {"production_mode": "faceless_material"},
        "events": [
            {"event_type": "asset_manifest_compiled", "payload": assets},
            {"event_type": "storyboard_compiled", "payload": storyboard},
        ],
    }
    repository = SimpleNamespace(
        get=AsyncMock(return_value=production),
        append_event=AsyncMock(return_value={"id": "video-production-1", "events": []}),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=repository,
        )
    )

    payload = json.loads(
        await _personal_ip_compile_video_narration(
            SimpleNamespace(context={"user_id": "user-1"}),
            production_id="video-production-1",
            event_key="narration:v1",
            language="zh-CN",
            segments=[{"id": "shot-1", "text": "智能体统筹全部账号。", "pronunciation_hints": []}],
        )
    )
    assert payload["compiled_contract"]["spoken_text"] == "智能体统筹全部账号。"
    assert repository.append_event.await_args.kwargs["event_type"] == "narration_contract_compiled"

    material = json.loads(
        await _personal_ip_compile_video_material_selection(
            SimpleNamespace(context={"user_id": "user-1"}),
            production_id="video-production-1",
            event_key="materials:v1",
            selections=[
                {
                    "shot_id": "shot-1",
                    "asset_id": "asset-1",
                    "source_in_seconds": 2,
                    "source_out_seconds": 8,
                    "semantic_relevance": 0.9,
                    "semantic_evidence": "抽帧显示全平台数据看板。",
                    "inspection_refs": ["inspection://1"],
                    "frame_evidence_refs": ["artifact://frame-1.jpg"],
                }
            ],
        )
    )
    assert material["compiled_contract"]["selections"][0]["source_in_seconds"] == 2
    assert repository.append_event.await_args.kwargs["event_type"] == "material_selection_compiled"

    production["events"].append({"event_type": "narration_contract_compiled", "payload": payload["compiled_contract"]})
    timing = json.loads(
        await _personal_ip_compile_video_narration_timing(
            SimpleNamespace(context={"user_id": "user-1"}),
            production_id="video-production-1",
            event_key="narration-timing:v1",
            segments=[
                {
                    "id": "shot-1",
                    "source_text_sha256": payload["compiled_contract"]["segments"][0]["text_sha256"],
                    "audio_ref": "artifact://voice/shot-1.mp3",
                    "audio_sha256": "b" * 64,
                    "duration_seconds": 4.8,
                    "provider": "volcengine-speech",
                    "provider_task_id": "tts-1",
                    "characters": len("智能体统筹全部账号。"),
                    "cost": {"status": "known", "currency": "CNY", "amount": 0.02},
                }
            ],
        )
    )
    assert timing["compiled_contract"]["actual_duration_seconds"] == 4.8
    assert repository.append_event.await_args.kwargs["event_type"] == "narration_timing_compiled"
