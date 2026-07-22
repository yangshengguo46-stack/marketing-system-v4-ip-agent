from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.personal_ip.media_execution import normalize_media_execution_receipt


def _receipt(**overrides):
    value = {
        "contract_version": "personal-ip-media-execution-v1",
        "capability": "video_generation",
        "provider": "volcengine",
        "executor": "video-generation-skill",
        "model": "doubao-seedance-2-0-260128",
        "status": "succeeded",
        "task_id": "seedance-task-1",
        "request_id": "request-1",
        "started_at": "2026-07-22T01:00:00Z",
        "completed_at": "2026-07-22T01:02:00Z",
        "parameters": {"ratio": "9:16", "duration": 5},
        "inputs": [{"ref": "artifact://shots/shot-1.json", "sha256": "a" * 64, "size_bytes": 12}],
        "outputs": [{"ref": "artifact://shots/shot-1.mp4", "sha256": "b" * 64, "size_bytes": 2048}],
        "cost": {"status": "unknown", "reason": "billing API is not connected"},
    }
    value.update(overrides)
    return value


def test_normalize_media_execution_preserves_provider_proof_and_derives_event() -> None:
    result = normalize_media_execution_receipt(_receipt(), entity_type="candidate")

    assert result["event_type"] == "shot_generation_completed"
    assert result["event_status"] == "succeeded"
    assert result["provider_task_id"] == "seedance-task-1"
    assert result["output_refs"] == ["artifact://shots/shot-1.mp4"]
    assert result["cost"]["status"] == "unknown"
    assert result["occurred_at"] == datetime(2026, 7, 22, 1, 2, tzinfo=UTC)
    assert result["payload"]["outputs"][0]["sha256"] == "b" * 64


def test_normalize_media_execution_preserves_download_and_retry_evidence() -> None:
    result = normalize_media_execution_receipt(
        _receipt(
            parameters={
                "attempt": 2,
                "retry_of": "shot-1:attempt-1",
            },
            outputs=[
                {
                    "ref": "file:///outputs/shot-1.mp4",
                    "source_ref": "https://example.com/results/shot-1.mp4?signature=secret",
                    "downloaded_at": "2026-07-22T01:01:50Z",
                    "sha256": "b" * 64,
                    "size_bytes": 2048,
                }
            ],
            cost={"status": "known", "amount": 3.25, "currency": "cny", "basis": "provider usage receipt"},
        ),
        entity_type="candidate",
    )

    output = result["payload"]["outputs"][0]
    assert output["source_ref"] == "https://example.com/results/shot-1.mp4"
    assert output["downloaded_at"] == "2026-07-22T01:01:50+00:00"
    assert result["payload"]["parameters"]["retry_of"] == "shot-1:attempt-1"
    assert result["cost"] == {
        "status": "known",
        "amount": 3.25,
        "currency": "CNY",
        "basis": "provider usage receipt",
    }


@pytest.mark.parametrize(
    ("capability", "status", "entity_type", "event_type"),
    [
        ("image_generation", "running", "character", "asset_generation_requested"),
        ("image_generation", "failed", "scene", "asset_generation_failed"),
        ("speech_generation", "succeeded", "audio", "voice_generated"),
        ("media_processing", "succeeded", "timeline", "media_processing_completed"),
    ],
)
def test_normalize_media_execution_maps_capability_status(
    capability: str,
    status: str,
    entity_type: str,
    event_type: str,
) -> None:
    overrides = {"capability": capability, "status": status}
    if status == "running":
        overrides.pop("completed_at", None)
        overrides["completed_at"] = None
        overrides["outputs"] = []
    if status == "failed":
        overrides["outputs"] = []
        overrides["failure"] = {"category": "provider_timeout", "message": "timed out", "retryable": True}
    result = normalize_media_execution_receipt(_receipt(**overrides), entity_type=entity_type)
    assert result["event_type"] == event_type


def test_normalize_media_execution_rejects_unverified_success_output() -> None:
    with pytest.raises(ValueError, match="sha256 and size_bytes"):
        normalize_media_execution_receipt(
            _receipt(outputs=[{"ref": "artifact://shots/shot-1.mp4"}]),
            entity_type="candidate",
        )


def test_normalize_media_execution_rejects_credentials_anywhere() -> None:
    with pytest.raises(ValueError, match="credential"):
        normalize_media_execution_receipt(
            _receipt(parameters={"authorization": "Bearer secret"}),
            entity_type="candidate",
        )


def test_normalize_media_execution_rejects_wrong_entity_type() -> None:
    with pytest.raises(ValueError, match="entity_type"):
        normalize_media_execution_receipt(_receipt(), entity_type="audio")


def test_normalize_media_execution_requires_boolean_retryable() -> None:
    with pytest.raises(ValueError, match="must be a boolean"):
        normalize_media_execution_receipt(
            _receipt(
                status="failed",
                outputs=[],
                failure={"category": "provider_error", "message": "failed", "retryable": "false"},
            ),
            entity_type="candidate",
        )
