from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.config.paths import Paths
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins import personal_ip_tools as tools_module


@pytest.mark.asyncio
async def test_locked_delivery_seals_linked_artifact_through_trusted_path(monkeypatch, tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    toolchain.mkdir(parents=True)
    (toolchain / "ffmpeg").write_bytes(b"binary")
    (toolchain / "ffprobe").write_bytes(b"binary")

    payload = b"final-video-payload"
    output = paths.user_dir("owner-1") / "video-deliveries" / "job" / "final.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    revision_sha = "a" * 64
    production = {
        "id": "video-production-1",
        "contract_version": "personal-ip-video-production-v2",
        "status": "running",
        "current_stage": "finishing",
        "event_count": 2,
        "events": [
            {
                "event_type": "timeline_revision_compiled",
                "payload": {"revision_id": "revision-1", "sha256": revision_sha},
            },
            {
                "event_type": "final_edit_locked",
                "payload": {
                    "lock_id": "lock-1",
                    "source_revision_id": "revision-1",
                    "source_timeline_sha256": revision_sha,
                },
            },
        ],
    }
    final_artifact = {
        "id": "artifact-1",
        "contract_version": "personal-ip-final-artifact-v1",
        "role": "final_video",
        "production_id": "video-production-1",
        "content_sha256": digest,
        "size_bytes": len(payload),
        "mime_type": "video/mp4",
        "metadata": {"lock_id": "lock-1"},
    }
    repository = SimpleNamespace(
        get=AsyncMock(return_value=production),
        append_event=AsyncMock(
            side_effect=[
                {**production, "event_count": 3},
                {**production, "event_count": 4},
            ]
        ),
        complete_delivery_and_seal_artifact=AsyncMock(
            return_value={
                **production,
                "status": "completed",
                "current_stage": "delivery",
                "event_count": 5,
                "final_artifact": final_artifact,
            }
        ),
    )
    render_result = {
        "output_path": str(output),
        "receipt": {"unused": True},
        "qa": {
            "contract_version": "personal-ip-delivery-qa-v1",
            "passed": True,
            "artifact": {
                "ref": output.as_uri(),
                "sha256": digest,
                "size_bytes": len(payload),
                "mime_type": "video/mp4",
            },
            "delivery_spec": {},
            "checks": [{"name": "decode", "passed": True}],
            "probe": {"video_codec": "h264"},
            "executors": {"ffmpeg": "ffmpeg"},
        },
    }
    normalized_receipt = {
        "event_type": "media_processing_completed",
        "event_status": "succeeded",
        "payload": {
            "contract_version": "personal-ip-media-execution-v1",
            "capability": "media_processing",
            "status": "succeeded",
            "outputs": [render_result["qa"]["artifact"]],
        },
        "input_refs": ["timeline://revision-1"],
        "output_refs": [output.as_uri()],
        "provider": "local",
        "model": None,
        "provider_task_id": None,
        "cost": {"status": "known", "amount": 0, "currency": "CNY"},
        "occurred_at": None,
    }
    monkeypatch.setattr(tools_module, "get_paths", lambda: paths)
    monkeypatch.setattr(
        tools_module,
        "render_locked_timeline_delivery",
        lambda *_args, **_kwargs: render_result,
    )
    monkeypatch.setattr(
        tools_module,
        "normalize_media_execution_receipt",
        lambda *_args, **_kwargs: normalized_receipt,
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=repository,
        )
    )
    try:
        result_text = await tools_module._personal_ip_render_locked_video_delivery(
            SimpleNamespace(context={"user_id": "owner-1"}),
            "video-production-1",
        )
    finally:
        configure_personal_ip_runtime(None)

    result = json.loads(result_text)
    assert result["operation_status"] == "ok"
    assert result["artifact"] == final_artifact
    assert result["qa"]["artifact"] == final_artifact
    assert "file://" not in result_text
    assert "storage_key" not in result_text
    assert repository.append_event.await_count == 2
    qa_kwargs = repository.append_event.await_args_list[1].kwargs
    assert qa_kwargs["event_type"] == "delivery_qa_completed"
    assert qa_kwargs["trusted_delivery_qa"] is True
    seal_kwargs = repository.complete_delivery_and_seal_artifact.await_args.kwargs
    assert seal_kwargs["storage_key"] == "video-deliveries/job/final.mp4"
    expected_suffix = hashlib.sha256(f"video-production-1\0revision-1\0{revision_sha}".encode()).hexdigest()[:20]
    assert seal_kwargs["source_execution_event_keys"] == [f"locked-timeline-render:{expected_suffix}"]
    assert seal_kwargs["source_ref"] == output.as_uri()
    assert seal_kwargs["sha256"] == digest
    assert seal_kwargs["size_bytes"] == len(payload)
    assert seal_kwargs["mime_type"] == "video/mp4"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure_stage",
    [
        "render_event_none",
        "qa_event_none",
        "qa_failed",
        "seal_none",
        "render_event_error",
        "qa_event_error",
    ],
)
async def test_linked_delivery_applies_commit_aware_unsealed_render_cleanup(
    monkeypatch,
    tmp_path,
    failure_stage: str,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    toolchain.mkdir(parents=True)
    (toolchain / "ffmpeg").write_bytes(b"binary")
    (toolchain / "ffprobe").write_bytes(b"binary")
    payload = b"unsealed-final-video"
    output = paths.user_dir("owner-1") / "video-deliveries" / "job" / "final.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    revision_sha = "a" * 64
    production = {
        "id": "video-production-1",
        "contract_version": "personal-ip-video-production-v2",
        "status": "running",
        "current_stage": "finishing",
        "event_count": 2,
        "events": [
            {
                "event_type": "timeline_revision_compiled",
                "payload": {
                    "revision_id": "revision-1",
                    "sha256": revision_sha,
                },
            },
            {
                "event_type": "final_edit_locked",
                "payload": {
                    "lock_id": "lock-1",
                    "source_revision_id": "revision-1",
                    "source_timeline_sha256": revision_sha,
                },
            },
        ],
    }
    artifact = {
        "ref": output.as_uri(),
        "sha256": digest,
        "size_bytes": len(payload),
        "mime_type": "video/mp4",
    }
    render_result = {
        "output_path": str(output),
        "receipt": {"unused": True},
        "qa": {
            "contract_version": "personal-ip-delivery-qa-v1",
            "passed": failure_stage != "qa_failed",
            "artifact": artifact,
            "delivery_spec": {},
            "checks": [],
            "probe": {},
            "executors": {},
        },
    }
    normalized_receipt = {
        "event_type": "media_processing_completed",
        "event_status": "succeeded",
        "payload": {"outputs": [artifact]},
        "input_refs": ["timeline://revision-1"],
        "output_refs": [output.as_uri()],
        "provider": "local",
        "model": None,
        "provider_task_id": None,
        "cost": {"status": "known", "amount": 0, "currency": "CNY"},
        "occurred_at": None,
    }
    if failure_stage == "render_event_none":
        append_results = [None]
    elif failure_stage == "qa_event_none":
        append_results = [{**production, "event_count": 3}, None]
    elif failure_stage == "render_event_error":
        append_results = [RuntimeError("render receipt commit unknown")]
    elif failure_stage == "qa_event_error":
        append_results = [
            {**production, "event_count": 3},
            RuntimeError("QA receipt commit unknown"),
        ]
    else:
        append_results = [
            {**production, "event_count": 3},
            {**production, "event_count": 4},
        ]
    repository = SimpleNamespace(
        get=AsyncMock(return_value=production),
        append_event=AsyncMock(side_effect=append_results),
        complete_delivery_and_seal_artifact=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(tools_module, "get_paths", lambda: paths)
    monkeypatch.setattr(
        tools_module,
        "render_locked_timeline_delivery",
        lambda *_args, **_kwargs: render_result,
    )
    monkeypatch.setattr(
        tools_module,
        "normalize_media_execution_receipt",
        lambda *_args, **_kwargs: normalized_receipt,
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            video_productions=repository,
        )
    )
    try:
        result_text = await tools_module._personal_ip_render_locked_video_delivery(
            SimpleNamespace(context={"user_id": "owner-1"}),
            "video-production-1",
        )
    finally:
        configure_personal_ip_runtime(None)

    result = json.loads(result_text)
    if failure_stage in {"render_event_error", "qa_event_error"}:
        assert output.read_bytes() == payload
    else:
        assert not output.exists()
    if failure_stage == "qa_failed":
        assert result["operation_status"] == "blocked"
    else:
        assert result["status"] == "error"
