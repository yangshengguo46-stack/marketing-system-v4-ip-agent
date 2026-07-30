from __future__ import annotations

import pytest

from deerflow.personal_ip.video_contracts import (
    VIDEO_DOMAIN_CONTRACT_VERSION,
    compile_asset_manifest,
    compile_final_edit_lock,
    compile_storyboard,
    compile_timeline_revision,
    compile_video_plan,
)


def test_faceless_material_contracts_compile_to_deterministic_receipts() -> None:
    plan = compile_video_plan(
        production_id="video-production-1",
        production_mode="faceless_material",
        plan={
            "title": "智能体不是应用程序",
            "objective": "解释本地智能体的价值",
            "target_audience": "个人 IP 创作者",
            "platforms": ["douyin", "xiaohongshu"],
            "argument": "智能体应该统筹账号并执行工作",
            "narration_language": "zh-CN",
            "evidence_refs": ["evidence://preflight/1"],
            "measurement_plan": {"primary_metric": "views"},
        },
    )
    replayed = compile_video_plan(
        production_id="video-production-1",
        production_mode="faceless_material",
        plan=plan["plan"],
    )

    assert plan["contract_version"] == "personal-ip-video-plan-v1"
    assert plan["domain_contract_version"] == VIDEO_DOMAIN_CONTRACT_VERSION
    assert plan["production_mode"] == "faceless_material"
    assert plan["sha256"] == replayed["sha256"]
    assert plan["validation"]["passed"] is True

    assets = compile_asset_manifest(
        production_id="video-production-1",
        production_mode="faceless_material",
        assets=[
            {
                "id": "asset-1",
                "type": "stock_video",
                "name": "创作者工作场景",
                "source_ref": "https://example.com/clip/1",
                "license": "CC-BY-4.0",
                "allowed_for_use": True,
                "sha256": "a" * 64,
            }
        ],
    )
    assert assets["assets"][0]["license"] == "CC-BY-4.0"

    storyboard = compile_storyboard(
        production_id="video-production-1",
        production_mode="faceless_material",
        shots=[
            {
                "id": "shot-1",
                "order": 1,
                "duration_seconds": 6,
                "narration_text": "真正的智能体会统筹你的全部账号。",
                "visual_subject": "创作者查看多平台数据",
                "visual_query": "creator analytics dashboard",
                "composition_strategy": "full_bleed",
                "claim_evidence_refs": ["evidence://preflight/1"],
                "claim_evidence_quotes": {"evidence://preflight/1": "全平台经营数据"},
                "negative_conditions": ["不要出现水印"],
                "pass_criteria": ["旁白与画面语义一致"],
            }
        ],
    )
    assert storyboard["duration_seconds"] == 6
    assert storyboard["shots"][0]["composition_strategy"] == "full_bleed"


def test_faceless_material_contract_rejects_unlicensed_assets_and_unquoted_claims() -> None:
    with pytest.raises(ValueError, match="allowed_for_use"):
        compile_asset_manifest(
            production_id="video-production-1",
            production_mode="faceless_material",
            assets=[
                {
                    "id": "asset-1",
                    "type": "stock_video",
                    "name": "未知素材",
                    "source_ref": "https://example.com/clip/1",
                    "license": "unknown",
                    "allowed_for_use": False,
                }
            ],
        )

    with pytest.raises(ValueError, match="claim_evidence_quotes"):
        compile_storyboard(
            production_id="video-production-1",
            production_mode="faceless_material",
            shots=[
                {
                    "id": "shot-1",
                    "order": 1,
                    "duration_seconds": 6,
                    "narration_text": "一个需要证据的结论。",
                    "visual_subject": "结论画面",
                    "visual_query": "evidence",
                    "composition_strategy": "inset_card",
                    "claim_evidence_refs": ["evidence://1"],
                    "claim_evidence_quotes": {},
                    "negative_conditions": [],
                    "pass_criteria": ["证据准确"],
                }
            ],
        )


def test_generative_cinematic_contracts_preserve_story_and_continuity_intent() -> None:
    plan = compile_video_plan(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        plan={
            "title": "觉醒",
            "objective": "制作一支一分钟微电影",
            "target_audience": "AI 创作者",
            "platforms": ["douyin"],
            "logline": "一个智能体第一次理解创作者。",
            "genre": "科幻剧情",
            "characters": [{"id": "char-1", "name": "老杨", "description": "疲惫的创业者"}],
            "locations": [{"id": "scene-1", "name": "工作室", "description": "凌晨的工作室"}],
            "narrative_beats": [{"id": "beat-1", "order": 1, "purpose": "建立困境"}],
        },
    )
    assert plan["plan"]["characters"][0]["id"] == "char-1"

    storyboard = compile_storyboard(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        shots=[
            {
                "id": "shot-1",
                "scene_id": "scene-1",
                "order": 1,
                "duration_seconds": 5,
                "first_frame": "老杨伏在桌前，屏幕冷光照亮左脸",
                "last_frame": "屏幕出现智能体的第一句话",
                "motion": "老杨缓慢抬头",
                "camera": "中景缓慢推进",
                "action": "角色发现屏幕正在主动回应",
                "preserve_elements": ["黑色卫衣", "左侧冷光"],
                "change_elements": ["屏幕由黑变亮"],
            }
        ],
    )
    assert storyboard["shots"][0]["preserve_elements"] == ["黑色卫衣", "左侧冷光"]

    with pytest.raises(ValueError, match="shot id"):
        compile_storyboard(
            production_id="video-production-film",
            production_mode="generative_cinematic",
            shots=[storyboard["shots"][0], storyboard["shots"][0]],
        )


def test_video_contract_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="production_mode"):
        compile_video_plan(
            production_id="video-production-1",
            production_mode="second_runtime",
            plan={},
        )


def test_human_and_agent_edits_compile_to_one_timeline_revision_contract() -> None:
    tracks = [
        {
            "id": "video",
            "type": "video",
            "clips": [
                {
                    "id": "clip-1",
                    "shot_id": "shot-1",
                    "start_sec": 0,
                    "duration_sec": 4,
                    "source_in_sec": 0.1,
                    "source_ref": "artifact://shot-1-v2.mp4",
                    "source_sha256": "a" * 64,
                    "selected_candidate_id": "shot-1:candidate-2",
                }
            ],
        },
        {
            "id": "subtitle",
            "type": "subtitle",
            "clips": [
                {
                    "id": "caption-1",
                    "shot_id": "shot-1",
                    "start_sec": 0.2,
                    "duration_sec": 3.6,
                    "source_in_sec": 0,
                    "text": "智能体和用户共同剪辑。",
                }
            ],
        },
    ]
    contract = compile_timeline_revision(
        production_id="video-production-1",
        production_mode="generative_cinematic",
        revision_id="timeline-r2",
        base_revision_id="timeline-r1",
        author_kind="human",
        intent="把镜头一缩短并替换成第二个候选。",
        fps=24,
        tracks=tracks,
        operations=[
            {
                "id": "edit-1",
                "type": "replace_candidate",
                "clip_id": "clip-1",
                "candidate_id": "shot-1:candidate-2",
            },
            {
                "id": "edit-2",
                "type": "trim",
                "clip_id": "clip-1",
                "source_in_sec": 0.1,
                "duration_sec": 4,
            },
        ],
        strategy_confirmed=True,
    )

    assert contract["contract_version"] == "personal-ip-video-timeline-revision-v1"
    assert contract["rough_cut"] is True
    assert contract["editing_policy"]["subtitles_applied_last"] is True
    assert contract["editing_policy"]["audio_boundary_fade_ms"] == 30
    assert contract["tracks"][0]["clips"][0]["selected_candidate_id"] == "shot-1:candidate-2"

    final_lock = compile_final_edit_lock(
        production_id="video-production-1",
        production_mode="generative_cinematic",
        lock_id="final-lock-1",
        timeline_revision=contract,
        locked_by="human",
        note="用户确认当前剪辑可进入最终渲染和 QA。",
    )
    assert final_lock["source_timeline_sha256"] == contract["sha256"]
    assert final_lock["rough_cut"] is False
    assert final_lock["ready_for_delivery_qa"] is True

    with pytest.raises(ValueError, match="strategy_confirmed"):
        compile_timeline_revision(
            production_id="video-production-1",
            production_mode="generative_cinematic",
            revision_id="timeline-r3",
            base_revision_id="timeline-r2",
            author_kind="agent",
            intent="未经确认直接剪辑",
            fps=24,
            tracks=tracks,
            operations=[{"id": "edit-3", "type": "delete", "clip_id": "clip-1"}],
            strategy_confirmed=False,
        )
