from __future__ import annotations

from deerflow.personal_ip.video_workbench import build_video_workbench_read_model


def _event(
    sequence: int,
    event_type: str,
    *,
    status: str = "succeeded",
    entity_type: str = "production",
    entity_id: str = "video-production-1",
    payload: dict | None = None,
    output_refs: list[str] | None = None,
    provider: str = "deerflow",
    model: str | None = None,
    provider_task_id: str | None = None,
    cost: dict | None = None,
) -> dict:
    return {
        "id": f"event-{sequence}",
        "event_key": f"event-key-{sequence}",
        "sequence": sequence,
        "event_type": event_type,
        "stage": {
            "blueprint_sealed": "blueprint",
            "asset_generation_completed": "assets",
            "storyboard_sealed": "storyboard",
            "shot_generation_failed": "generation",
            "shot_generation_completed": "generation",
            "consistency_checked": "consistency",
            "review_requested": "selection",
            "review_recorded": "selection",
            "voice_generated": "finishing",
            "media_processing_completed": "finishing",
            "delivery_qa_completed": "delivery",
        }[event_type],
        "status": status,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload or {},
        "input_refs": [],
        "output_refs": output_refs or [],
        "provider": provider,
        "model": model,
        "provider_task_id": provider_task_id,
        "cost": cost or {"status": "known", "amount": 0, "currency": "CNY"},
        "occurred_at": f"2026-07-22T05:{sequence:02d}:00+00:00",
        "created_at": f"2026-07-22T05:{sequence:02d}:00+00:00",
    }


def test_video_workbench_is_derived_from_the_immutable_event_ledger() -> None:
    final_ref = "file:///tmp/video-e2e/final.mp4"
    production = {
        "id": "video-production-1",
        "contract_version": "personal-ip-video-production-v1",
        "title": "本地回执验收",
        "status": "awaiting_review",
        "current_stage": "selection",
        "source_kind": "script",
        "source": {"script": "让每一步执行都有回执。"},
        "delivery_spec": {"aspect_ratio": "9:16", "duration_seconds": 2},
        "provider_policy": {"video": ["seedance"]},
        "budget": {"paid_calls_require_explicit_approval": True},
        "event_count": 10,
        "created_at": "2026-07-22T05:00:00+00:00",
        "updated_at": "2026-07-22T05:10:00+00:00",
        "events": [
            _event(
                1,
                "blueprint_sealed",
                payload={"artifact": {"ref": "file:///tmp/video-e2e/blueprint.json", "sha256": "a" * 64}},
            ),
            _event(
                2,
                "asset_generation_completed",
                entity_type="scene",
                entity_id="asset-01",
                payload={
                    "outputs": [
                        {
                            "ref": "file:///tmp/video-e2e/asset.png",
                            "sha256": "b" * 64,
                            "size_bytes": 128,
                            "mime_type": "image/png",
                        }
                    ]
                },
                output_refs=["file:///tmp/video-e2e/asset.png"],
                provider="volcengine-simulated",
            ),
            _event(3, "storyboard_sealed", payload={"shot_count": 1}),
            _event(
                4,
                "shot_generation_failed",
                status="failed",
                entity_type="shot",
                entity_id="shot-01",
                payload={
                    "parameters": {"attempt": 1, "retry_of": None},
                    "failure": {"category": "provider_timeout", "message": "timed out", "retryable": True},
                },
                provider="volcengine-simulated",
                model="seedance-2.0",
                provider_task_id="task-attempt-1",
                cost={"status": "unknown", "reason": "billing unavailable"},
            ),
            _event(
                5,
                "shot_generation_completed",
                entity_type="candidate",
                entity_id="shot-01:candidate-2",
                payload={
                    "parameters": {"attempt": 2, "retry_of": "shot-01:attempt-1"},
                    "outputs": [
                        {
                            "ref": "file:///tmp/video-e2e/shot-01-attempt-2.mp4",
                            "sha256": "c" * 64,
                            "size_bytes": 256,
                            "mime_type": "video/mp4",
                        }
                    ],
                },
                output_refs=["file:///tmp/video-e2e/shot-01-attempt-2.mp4"],
                provider="volcengine-simulated",
                model="seedance-2.0",
                provider_task_id="task-attempt-2",
            ),
            _event(
                6,
                "consistency_checked",
                entity_type="candidate",
                entity_id="shot-01:candidate-2",
                payload={"checks": {"aspect_ratio": True, "reference_asset_present": True}},
            ),
            _event(
                7,
                "review_requested",
                status="awaiting_review",
                entity_type="candidate",
                entity_id="shot-01:candidate-2",
                payload={"review_kind": "candidate_selection", "reason": "候选通过一致性检查"},
            ),
            _event(8, "voice_generated", entity_type="audio", entity_id="voice-01"),
            _event(9, "media_processing_completed", entity_type="timeline", entity_id="timeline-final-v1"),
            _event(
                10,
                "delivery_qa_completed",
                entity_type="delivery",
                entity_id="delivery-v1",
                payload={
                    "contract_version": "personal-ip-delivery-qa-v1",
                    "passed": True,
                    "artifact": {"ref": final_ref, "sha256": "d" * 64, "size_bytes": 512},
                    "checks": {"duration": {"passed": True}, "audio": {"passed": True}},
                },
                output_refs=[final_ref],
                provider="ffmpeg_ffprobe",
            ),
        ],
    }

    workbench = build_video_workbench_read_model(production)

    assert workbench["contract_version"] == "personal-ip-video-workbench-v1"
    assert "events" not in workbench["production"]
    assert workbench["stage_summary"][4]["event_count"] == 2
    assert workbench["blueprint"]["artifacts"][0]["sha256"] == "a" * 64
    assert workbench["assets"][0]["entity_type"] == "scene"
    assert workbench["storyboard"]["shot_count"] == 1
    failed_task = next(task for task in workbench["tasks"] if task["event_type"] == "shot_generation_failed")
    retried_task = next(task for task in workbench["tasks"] if task["event_type"] == "shot_generation_completed")
    assert failed_task["failure"]["category"] == "provider_timeout"
    assert retried_task["attempt"] == 2
    assert retried_task["retry_of"] == "shot-01:attempt-1"
    assert workbench["shots"][0]["id"] == "shot-01"
    assert workbench["candidates"][0]["consistency"]["checks"]["aspect_ratio"] is True
    assert workbench["candidates"][0]["artifacts"][0]["sha256"] == "c" * 64
    assert workbench["confirmations"][0]["kind"] == "candidate_selection"
    assert workbench["delivery"]["qa_passed"] is True
    assert workbench["delivery"]["artifacts"][0]["sha256"] == "d" * 64


def test_video_workbench_exposes_only_meaningful_unanswered_confirmations() -> None:
    production = {
        "id": "video-production-1",
        "status": "running",
        "current_stage": "selection",
        "source_kind": "idea",
        "source": {"idea": "test"},
        "delivery_spec": {},
        "provider_policy": {},
        "budget": {},
        "events": [
            _event(1, "review_requested", status="awaiting_review", entity_type="production", payload={"review_kind": "evidence_promotion"}),
            _event(2, "review_requested", status="awaiting_review", entity_type="production", payload={"review_kind": "paid_provider_call"}),
        ],
    }

    workbench = build_video_workbench_read_model(production)

    assert [item["kind"] for item in workbench["confirmations"]] == ["paid_provider_call"]


def test_approved_selection_review_marks_the_candidate_selected() -> None:
    production = {
        "id": "video-production-1",
        "status": "running",
        "current_stage": "selection",
        "source_kind": "idea",
        "source": {"idea": "test"},
        "delivery_spec": {},
        "provider_policy": {},
        "budget": {},
        "events": [
            _event(
                1,
                "review_requested",
                status="awaiting_review",
                entity_type="candidate",
                entity_id="shot-01:candidate-2",
                payload={"review_kind": "candidate_selection"},
            ),
            _event(
                2,
                "review_recorded",
                status="approved",
                entity_type="candidate",
                entity_id="shot-01:candidate-2",
                payload={"review_kind": "candidate_selection", "decision": "approved"},
            ),
        ],
    }

    workbench = build_video_workbench_read_model(production)

    assert workbench["candidates"][0]["selected"] is True
    assert workbench["confirmations"] == []


def test_video_workbench_never_exposes_credential_bearing_urls() -> None:
    signed_ref = "https://user:secret@example.com/video.mp4?X-Amz-Credential=secret#download"
    production = {
        "id": "video-production-1",
        "status": "running",
        "current_stage": "generation",
        "source_kind": "idea",
        "source": {"idea": "test", "reference_url": signed_ref},
        "delivery_spec": {},
        "provider_policy": {},
        "budget": {},
        "events": [
            _event(
                1,
                "shot_generation_completed",
                entity_type="candidate",
                entity_id="shot-01:candidate-1",
                payload={"outputs": [{"ref": signed_ref, "source_ref": signed_ref}]},
                output_refs=[signed_ref],
            )
        ],
    }

    workbench = build_video_workbench_read_model(production)

    safe_ref = "https://example.com/video.mp4"
    assert workbench["source"]["content"]["reference_url"] == safe_ref
    assert workbench["tasks"][0]["output_refs"] == [safe_ref]
    assert workbench["tasks"][0]["artifacts"][0]["ref"] == safe_ref
    assert workbench["tasks"][0]["artifacts"][0]["source_ref"] == safe_ref
    assert workbench["events"][0]["payload"]["outputs"][0]["ref"] == safe_ref
