from __future__ import annotations

import pytest

from deerflow.personal_ip.video_contracts import (
    compile_approved_assembly,
    compile_asset_manifest,
    compile_continuity_ledger,
    compile_generated_shot_qa,
    compile_material_selection,
    compile_narration_contract,
    compile_narration_timing,
    compile_storyboard,
)


def _material_storyboard() -> dict:
    return compile_storyboard(
        production_id="video-production-1",
        production_mode="faceless_material",
        shots=[
            {
                "id": "shot-1",
                "order": 1,
                "duration_seconds": 5,
                "narration_text": "智能体统筹全部账号。",
                "visual_subject": "全平台数据看板",
                "visual_query": "creator dashboard",
                "composition_strategy": "full_bleed",
                "claim_evidence_refs": [],
                "claim_evidence_quotes": {},
                "negative_conditions": [],
                "pass_criteria": ["语义一致"],
            }
        ],
    )


def _cinematic_storyboard() -> dict:
    return compile_storyboard(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        shots=[
            {
                "id": "shot-1",
                "scene_id": "scene-1",
                "order": 1,
                "duration_seconds": 4,
                "first_frame": "角色穿黑衣站在门外",
                "last_frame": "角色进入房间",
                "motion": "角色推门",
                "camera": "中景跟拍",
                "action": "进入房间",
                "preserve_elements": ["黑衣", "右手戒指"],
                "change_elements": ["位置"],
            },
            {
                "id": "shot-2",
                "scene_id": "scene-1",
                "order": 2,
                "duration_seconds": 4,
                "first_frame": "角色已在房间内",
                "last_frame": "角色坐下",
                "motion": "角色坐下",
                "camera": "近景固定",
                "action": "坐到桌前",
                "preserve_elements": ["黑衣", "右手戒指"],
                "change_elements": ["姿态"],
            },
        ],
    )


def test_narration_contract_is_one_to_one_with_spoken_storyboard_copy() -> None:
    contract = compile_narration_contract(
        production_id="video-production-1",
        storyboard=_material_storyboard(),
        language="zh-CN",
        segments=[
            {
                "id": "shot-1",
                "text": "智能体统筹全部账号。",
                "pronunciation_hints": ["AI：读作 A I"],
            }
        ],
    )

    assert contract["contract_version"] == "personal-ip-video-narration-v1"
    assert contract["spoken_text"] == "智能体统筹全部账号。"

    marked_storyboard = compile_storyboard(
        production_id="video-production-1",
        production_mode="faceless_material",
        shots=[
            {
                **_material_storyboard()["shots"][0],
                "narration_text": "镜头 1：智能体统筹全部账号。",
            }
        ],
    )
    with pytest.raises(ValueError, match="timeline or shot-label"):
        compile_narration_contract(
            production_id="video-production-1",
            storyboard=marked_storyboard,
            language="zh-CN",
            segments=[{"id": "shot-1", "text": "镜头 1：智能体统筹全部账号。", "pronunciation_hints": []}],
        )


def test_narration_timing_reconciles_exact_text_audio_task_cost_and_duration() -> None:
    narration = compile_narration_contract(
        production_id="video-production-1",
        storyboard=_material_storyboard(),
        language="zh-CN",
        segments=[{"id": "shot-1", "text": "智能体统筹全部账号。", "pronunciation_hints": []}],
    )
    timing = compile_narration_timing(
        production_id="video-production-1",
        narration=narration,
        segments=[
            {
                "id": "shot-1",
                "source_text_sha256": narration["segments"][0]["text_sha256"],
                "audio_ref": "artifact://voice/shot-1.mp3",
                "audio_sha256": "a" * 64,
                "duration_seconds": 4.85,
                "provider": "volcengine-speech",
                "provider_task_id": "tts-request-1",
                "characters": len("智能体统筹全部账号。"),
                "cost": {"status": "known", "currency": "CNY", "amount": 0.02},
            }
        ],
    )

    assert timing["actual_duration_seconds"] == 4.85
    assert timing["segments"][0]["provider_task_id"] == "tts-request-1"

    with pytest.raises(ValueError, match="source text hash"):
        compile_narration_timing(
            production_id="video-production-1",
            narration=narration,
            segments=[{**timing["segments"][0], "source_text_sha256": "f" * 64}],
        )


def test_material_selection_locks_exact_source_ranges_rights_evidence_and_diversity() -> None:
    storyboard = _material_storyboard()
    assets = compile_asset_manifest(
        production_id="video-production-1",
        production_mode="faceless_material",
        assets=[
            {
                "id": "asset-1",
                "type": "stock_video",
                "name": "数据看板",
                "source_ref": "https://example.com/video/1",
                "license": "CC-BY-4.0",
                "allowed_for_use": True,
                "sha256": "b" * 64,
            }
        ],
    )
    selection = compile_material_selection(
        production_id="video-production-1",
        asset_manifest=assets,
        storyboard=storyboard,
        selections=[
            {
                "shot_id": "shot-1",
                "asset_id": "asset-1",
                "source_in_seconds": 3,
                "source_out_seconds": 9,
                "semantic_relevance": 0.91,
                "semantic_evidence": "抽帧显示创作者正在查看跨平台数据看板。",
                "inspection_refs": ["inspection://asset-1/v1"],
                "frame_evidence_refs": ["artifact://asset-1/frame-0003.jpg"],
            }
        ],
    )

    assert selection["selections"][0]["source_duration_seconds"] == 6
    assert selection["independent_asset_count"] == 1

    with pytest.raises(ValueError, match="semantic relevance"):
        compile_material_selection(
            production_id="video-production-1",
            asset_manifest=assets,
            storyboard=storyboard,
            selections=[{**selection["selections"][0], "semantic_relevance": 0.2}],
        )


def test_continuity_compiler_hash_chains_structured_state_and_rejects_drift() -> None:
    storyboard = _cinematic_storyboard()
    continuity = compile_continuity_ledger(
        production_id="video-production-film",
        storyboard=storyboard,
        initial_facts=[
            {"domain": "character", "subject_id": "char-1", "attribute": "wardrobe", "value": "black"},
            {"domain": "character", "subject_id": "char-1", "attribute": "location", "value": "outside"},
        ],
        shot_states=[
            {
                "shot_id": "shot-1",
                "order": 1,
                "preserve": [{"domain": "character", "subject_id": "char-1", "attribute": "wardrobe", "value": "black"}],
                "changes": [
                    {
                        "domain": "character",
                        "subject_id": "char-1",
                        "attribute": "location",
                        "before": "outside",
                        "after": "inside",
                    }
                ],
            },
            {
                "shot_id": "shot-2",
                "order": 2,
                "preserve": [
                    {"domain": "character", "subject_id": "char-1", "attribute": "wardrobe", "value": "black"},
                    {"domain": "character", "subject_id": "char-1", "attribute": "location", "value": "inside"},
                ],
                "changes": [],
            },
        ],
    )

    assert continuity["entries"][0]["after_state_sha256"] == continuity["entries"][1]["before_state_sha256"]
    assert continuity["entries"][0]["before_state_sha256"] != continuity["entries"][0]["after_state_sha256"]

    with pytest.raises(ValueError, match="continuity mismatch"):
        compile_continuity_ledger(
            production_id="video-production-film",
            storyboard=storyboard,
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
                            "before": "inside",
                            "after": "outside",
                        }
                    ],
                },
                {"shot_id": "shot-2", "order": 2, "preserve": [], "changes": []},
            ],
        )


def test_generated_shot_qa_computes_gate_instead_of_accepting_a_pass_claim() -> None:
    qa = compile_generated_shot_qa(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        shot_id="shot-1",
        candidate_id="shot-1:candidate-1",
        artifact={"ref": "artifact://shot-1.mp4", "sha256": "a" * 64},
        anchor={"ref": "artifact://shot-1-anchor.png", "sha256": "b" * 64},
        policy={
            "expected_width": 1920,
            "expected_height": 1080,
            "expected_fps": 24,
            "expected_duration_seconds": 4,
            "duration_tolerance_seconds": 0.2,
            "minimum_first_frame_ssim": 0.85,
            "maximum_internal_cut_count": 0,
            "expected_audio_stream_count": 0,
            "expected_decode_error_count": 0,
        },
        evidence={
            "width": 1920,
            "height": 1080,
            "fps": 24,
            "duration_seconds": 4.1,
            "audio_stream_count": 0,
            "decode_error_count": 0,
            "first_frame_ssim": 0.91,
            "internal_cut_transitions": [],
            "review_artifacts": [{"ref": "artifact://shot-1-contact-sheet.jpg", "sha256": "c" * 64}],
        },
    )
    assert qa["automated_gate_passed"] is True
    assert qa["candidate_eligible"] is True

    failed = compile_generated_shot_qa(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        shot_id="shot-1",
        candidate_id="shot-1:candidate-2",
        artifact={"ref": "artifact://shot-1-bad.mp4", "sha256": "d" * 64},
        anchor={"ref": "artifact://shot-1-anchor.png", "sha256": "b" * 64},
        policy=qa["policy"],
        evidence={**qa["evidence"], "first_frame_ssim": 0.3},
    )
    assert failed["automated_gate_passed"] is False
    assert failed["gates"]["first_frame_anchor"] is False


def test_generated_shot_qa_can_enforce_motion_cadence_and_recommend_interpolation() -> None:
    qa = compile_generated_shot_qa(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        shot_id="shot-1",
        candidate_id="shot-1:candidate-motion",
        artifact={"ref": "artifact://shot-1.mp4", "sha256": "a" * 64},
        anchor={"ref": "artifact://shot-1-anchor.png", "sha256": "b" * 64},
        policy={
            "expected_width": 1920,
            "expected_height": 1080,
            "expected_fps": 24,
            "expected_duration_seconds": 4,
            "motion_expectation": "continuous",
            "target_playback_fps": 48,
            "enforce_motion_cadence": True,
            "maximum_near_duplicate_ratio": 0.05,
        },
        evidence={
            "width": 1920,
            "height": 1080,
            "fps": 24,
            "duration_seconds": 4,
            "audio_stream_count": 0,
            "decode_error_count": 0,
            "first_frame_ssim": 0.91,
            "internal_cut_transitions": [],
            "motion_cadence": {
                "available": True,
                "source_fps": 24,
                "classification": "active_motion",
                "near_duplicate_transition_ratio": 0.02,
                "longest_near_duplicate_run_seconds": 0.04,
                "motion_delta_cv": 0.3,
                "interpolation_recommended": True,
            },
            "review_artifacts": [{"ref": "artifact://shot-1-contact-sheet.jpg", "sha256": "c" * 64}],
        },
    )

    assert qa["gates"]["motion_cadence"] is True
    assert qa["motion_cadence_enforced"] is True
    assert qa["interpolation_recommended"] is True
    assert qa["automated_gate_passed"] is True

    frozen = compile_generated_shot_qa(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        shot_id="shot-1",
        candidate_id="shot-1:candidate-frozen",
        artifact={"ref": "artifact://shot-1-frozen.mp4", "sha256": "d" * 64},
        anchor={"ref": "artifact://shot-1-anchor.png", "sha256": "b" * 64},
        policy=qa["policy"],
        evidence={
            **qa["evidence"],
            "motion_cadence": {
                **qa["evidence"]["motion_cadence"],
                "classification": "static",
                "near_duplicate_transition_ratio": 0.9,
                "interpolation_recommended": False,
            },
        },
    )
    assert frozen["gates"]["motion_cadence"] is False
    assert frozen["automated_gate_passed"] is False


def test_assembly_admission_requires_selected_and_qa_hashes_for_exact_same_clip() -> None:
    contract = compile_approved_assembly(
        production_id="video-production-film",
        production_mode="generative_cinematic",
        resolution="1920x1080",
        fps=24,
        clips=[
            {
                "order": 1,
                "shot_id": "shot-1",
                "candidate_id": "shot-1:candidate-1",
                "duration_seconds": 4,
                "source_ref": "artifact://shot-1.mp4",
                "source_sha256": "a" * 64,
                "selection_receipt_ref": "event://selection-1",
                "selection_source_sha256": "a" * 64,
                "qa_receipt_ref": "event://qa-1",
                "qa_source_sha256": "a" * 64,
                "qa_passed": True,
            },
            {
                "order": 2,
                "shot_id": "shot-2",
                "candidate_id": "shot-2:candidate-1",
                "duration_seconds": 4,
                "source_ref": "artifact://shot-2.mp4",
                "source_sha256": "b" * 64,
                "selection_receipt_ref": "event://selection-2",
                "selection_source_sha256": "b" * 64,
                "qa_receipt_ref": "event://qa-2",
                "qa_source_sha256": "b" * 64,
                "qa_passed": True,
            },
        ],
    )

    assert contract["timeline"][1]["timeline_start_seconds"] == 4
    assert contract["duration_seconds"] == 8

    with pytest.raises(ValueError, match="selected source hash"):
        compile_approved_assembly(
            production_id="video-production-film",
            production_mode="generative_cinematic",
            resolution="1920x1080",
            fps=24,
            clips=[{**contract["clips"][0], "selection_source_sha256": "f" * 64}],
        )
