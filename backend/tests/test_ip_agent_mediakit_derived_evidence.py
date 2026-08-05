from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from deerflow.ip_agent import reference_evidence as reference_evidence_module
from deerflow.ip_agent.evidence_contracts import (
    MediaMetadata,
    ProviderEvidence,
    ReferenceVideoEvidence,
    ReferenceVideoItem,
    RemuxArtifactCandidate,
    VideoSource,
    VideoUnderstandingProviderInference,
)
from deerflow.ip_agent.evidence_mcp import _reference_video_model_summary
from deerflow.ip_agent.mediakit_remux_ingress import MediaKitRemuxIngressReceipt
from deerflow.ip_agent.mediakit_video_understanding import VideoUnderstandingObservation
from deerflow.ip_agent.reference_evidence import (
    EvidenceDerivedPaidStageBinding,
    EvidenceDerivedStageUnavailable,
    RemuxArtifactStageExecution,
    assemble_remux_artifact_candidate,
    assemble_video_understanding_inference,
    remux_artifact_paid_stage_binding,
    run_remux_artifact_stage,
    run_video_understanding_inference_stage,
    video_understanding_paid_stage_binding,
)
from deerflow.mcp.paid_admission import PaidCallAdmissionClaim

WORK_ID = "7658501922794432731"
RUNTIME_URL = "https://output.volcvideo.com/candidate.mp4?signature=runtime-secret"


@pytest.fixture(autouse=True)
def _thread_evidence_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        reference_evidence_module,
        "_mcp_user_data_root",
        lambda: tmp_path,
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _authorization(
    binding: EvidenceDerivedPaidStageBinding,
    **updates: object,
) -> PaidCallAdmissionClaim:
    payload = {
        "owner_user_id": "owner-derived-evidence",
        "thread_id": "thread-derived-evidence",
        "run_id": "run-derived-evidence",
        "server_name": "ip-agent-evidence-internal",
        "tool_name": binding.capability,
        "tool_args_sha256": "0" * 64,
        "provider": binding.provider,
        "capability": binding.capability,
        "call_id": f"call-{binding.capability}",
        "jti": f"jti-{binding.capability}-1234567890",
        "approval_ref": "approval-derived-evidence",
        "reservation_ref": "reservation-derived-evidence",
        "provider_request_sha256": binding.provider_request_sha256,
        "source_sha256": binding.source_sha256,
        "stage_spec_sha256": binding.stage_spec_sha256,
        "maximum_amount_micros": 100_000,
        "currency": "CNY",
        "expires_at": datetime.now(UTC) + timedelta(minutes=10),
        "admission_state": "admitted",
    }
    payload.update(updates)
    return PaidCallAdmissionClaim.model_validate(payload)


def _source_fact(source_sha256: str) -> VideoSource:
    return VideoSource.model_validate(
        {
            "ref": f"https://www.douyin.com/video/{WORK_ID}",
            "content_sha256": source_sha256,
            "requested_work_id": WORK_ID,
            "resolved_work_id": WORK_ID,
            "observed_work_id": WORK_ID,
            "author_sec_uid": "MS4wLjABAAAAexact-author",
            "identity_verification": "api_work_id_match",
            "observed_at": "2026-08-03T00:00:00+00:00",
            "trust": "untrusted_source_data",
        }
    )


def _metadata(size_bytes: int) -> MediaMetadata:
    return MediaMetadata.model_validate(
        {
            "duration_seconds": 70.867,
            "width": 1920,
            "height": 1080,
            "frame_rate": 25.0,
            "video_codec": "h264",
            "has_audio": True,
            "container": "mov,mp4,m4a,3gp,3g2,mj2",
            "size_bytes": size_bytes,
        }
    )


def _remux_receipt(source_sha256: str, source_size: int) -> MediaKitRemuxIngressReceipt:
    completed_at = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)
    return MediaKitRemuxIngressReceipt.model_validate(
        {
            "contract_version": "ip-mediakit-remux-https-candidate-v1",
            "adapter_version": "volcengine-mediakit-remux-https-ingress-v1",
            "provider": "volcengine-mediakit",
            "endpoint_sha256": "1" * 64,
            "derived_from_source_sha256": source_sha256,
            "source_size_bytes": source_size,
            "source_hash_checks": 2,
            "source_hash_unchanged": True,
            "container_format": "MP4",
            "candidate_kind": "provider_remux_derivative",
            "candidate_byte_identity": "not_attested_equal_to_source",
            "provider_content_attestation": "unavailable",
            "upload_file_id_sha256": "2" * 64,
            "client_token_sha256": "3" * 64,
            "task_id_sha256": "4" * 64,
            "provider_request_id_sha256s": ["5" * 64],
            "runtime_url_sha256": hashlib.sha256(RUNTIME_URL.encode()).hexdigest(),
            "request_sha256": "6" * 64,
            "provider_response_sha256s": ["7" * 64, "8" * 64, "9" * 64, "a" * 64],
            "provider_response_sizes_bytes": [10, 20, 30, 40],
            "status": "completed",
            "completed_at": completed_at,
            "expires_at": completed_at + timedelta(hours=24),
            "observed_ttl_seconds": 86_400,
            "expiry_basis": "provider_reported",
            "poll_attempts": 1,
            "max_poll_attempts": 80,
            "poll_interval_seconds": 3.0,
            "response_size_limit_bytes": 1_048_576,
            "request_timeout_seconds": 120,
            "total_timeout_seconds": 600,
            "retries": 0,
            "billing_status": "provider_amount_unavailable",
        }
    )


def _observation(
    *,
    candidate_sha256: str,
    provider_input_ref_sha256: str,
    summary: str = "雨巷中可见两个人共撑一把伞。",
) -> VideoUnderstandingObservation:
    content = {
        "visual_summary": summary,
        "observations": [
            {
                "category": "action",
                "description": "两个人沿小巷移动。",
                "start_seconds": 0.0,
                "end_seconds": 3.0,
                "certainty": "observed",
            }
        ],
        "visible_text_presence": "present_unread",
        "uncertainties": ["未处理音频，人物身份未知。"],
    }
    return VideoUnderstandingObservation.model_validate(
        {
            "contract_version": "ip-video-visual-observation-v1",
            "trust": "untrusted_source_data",
            "observation_kind": "provider_inference",
            "provider": "volcengine-mediakit-video-understanding-chat",
            "source_sha256": candidate_sha256,
            "content": content,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "reasoning_tokens": 5,
                "total_tokens": 120,
            },
            "receipt": {
                "adapter_version": "volcengine-mediakit-video-understanding-chat-v2",
                "profile_version": "ip-visible-events-120-frames-v3",
                "endpoint_sha256": "b" * 64,
                "model": "doubao-seed-2-0-pro-260215",
                "source_sha256": candidate_sha256,
                "provider_input_ref_sha256": provider_input_ref_sha256,
                "request_sha256": "c" * 64,
                "output_schema_sha256": "d" * 64,
                "raw_response_sha256": "e" * 64,
                "result_sha256": _canonical_sha256(content),
                "fps": 1.0,
                "max_frames": 120,
                "max_pixels": 518_400,
                "response_format": "json_object",
                "input_binding": "public_url_unverified",
                "provider_input_attestation": "not_provided",
                "audio_processed": False,
                "retries": 0,
                "service_tier": "default",
                "max_completion_tokens": 3_000,
                "read_timeout_seconds": 300,
                "latency_millis": 100,
                "billing_status": "ark_tokens_reported_amount_unavailable",
            },
            "coverage": {
                "collection_status": "partial",
                "observation_scope": "provider_sampled_visual_frames_unknown",
                "reason_codes": [
                    "PROVIDER_CONTENT_HASH_NOT_ATTESTED",
                    "PROVIDER_FRAME_COVERAGE_UNATTESTED",
                    "AUDIO_NOT_PROCESSED",
                    "TIMESTAMPS_APPROXIMATE",
                ],
            },
        }
    )


def _artifact(
    *,
    source_bytes: bytes,
    candidate_bytes: bytes,
) -> RemuxArtifactCandidate:
    source_sha256 = _sha256_bytes(source_bytes)
    return assemble_remux_artifact_candidate(
        source_fact=_source_fact(source_sha256),
        artifact_sha256=_sha256_bytes(candidate_bytes),
        artifact_size_bytes=len(candidate_bytes),
        media_metadata=_metadata(len(candidate_bytes)),
        transform_receipt=_remux_receipt(source_sha256, len(source_bytes)),
    )


def _reference_item_with_visual_inference(
    *,
    status: str,
    source: VideoSource,
    artifact: RemuxArtifactCandidate,
    inference: VideoUnderstandingProviderInference,
) -> dict[str, object]:
    def complete(
        scope: str,
        *,
        requested_count: int | None = None,
        observed_count: int | None = None,
    ) -> dict[str, object]:
        return {
            "collection_status": "completed",
            "observation_scope": scope,
            "truncated": False,
            "requested_count": requested_count,
            "observed_count": observed_count,
            "reason_codes": [],
        }

    def not_requested(scope: str) -> dict[str, object]:
        return {
            "collection_status": "not_requested",
            "observation_scope": scope,
            "truncated": False,
            "reason_codes": ["ANALYSIS_DEPTH_NOT_REQUESTED"],
        }

    return {
        "status": status,
        "purpose": "benchmark",
        "source": source.model_dump(mode="json"),
        "media_metadata": _metadata(1_024).model_copy(update={"size_bytes": 1_024}).model_dump(mode="json"),
        "visual_samples": [
            {
                "at_seconds": float(index),
                "artifact_ref": f"outputs/reference/frame-{index}.jpg",
                "artifact_sha256": f"{index:064x}",
            }
            for index in range(1, 5)
        ],
        "contact_sheet_ref": "outputs/reference/contact-sheet.jpg",
        "contact_sheet_sha256": "b" * 64,
        "scene_boundaries_seconds": [],
        "provider_evidence": {},
        "derived_artifacts": {"remux": artifact.model_dump(mode="json")},
        "provider_inferences": {"video_understanding": inference.model_dump(mode="json")},
        "coverage": {
            "source_identity": complete("exact_public_work_and_content_hash"),
            "media_metadata": complete("full_container_and_stream_probe"),
            "sampled_frames": complete(
                "uniform_point_samples",
                requested_count=4,
                observed_count=4,
            ),
            "contact_sheet": complete(
                "all_observed_uniform_samples",
                requested_count=1,
                observed_count=1,
            ),
            "local_scene_detection": complete(
                "full_timeline_scene_threshold_scan",
                observed_count=0,
            ),
            "asr": not_requested("full_audio_track_asr"),
            "ocr": not_requested("provider_subtitle_ocr"),
            "provider_scene_segmentation": not_requested("provider_full_video_scene_analysis"),
            "storyline": not_requested("provider_full_video_storyline_analysis"),
        },
        "analysis_receipt": {
            "pipeline_version": "test-derived-evidence-v1",
            "analysis_depth": "mechanical",
            "requested_frames": 4,
            "local_sampling_spec_sha256": "c" * 64,
            "toolchain_sha256": {"ffmpeg": "d" * 64, "ffprobe": "e" * 64},
            "local_cache_hit": False,
            "artifact_manifest_sha256": "f" * 64,
            "provider_stage_spec_sha256": {},
        },
    }


def test_r1_and_r2_contracts_preserve_source_and_hide_provider_locator() -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    inference = assemble_video_understanding_inference(
        source_fact=_source_fact(_sha256_bytes(source_bytes)),
        remux_artifact=artifact,
        observation=_observation(
            candidate_sha256=_sha256_bytes(candidate_bytes),
            provider_input_ref_sha256=hashlib.sha256(RUNTIME_URL.encode()).hexdigest(),
        ),
    )

    assert artifact.derived_from_source_sha256 == _sha256_bytes(source_bytes)
    assert artifact.artifact_sha256 == _sha256_bytes(candidate_bytes)
    assert artifact.semantic_equivalence == "not_established"
    assert inference.original_source_sha256 == _sha256_bytes(source_bytes)
    assert inference.candidate_artifact_sha256 == artifact.artifact_sha256
    assert inference.remux_transform_receipt_sha256 == artifact.transform_receipt_sha256
    assert inference.collection_status == "partial"
    serialized = artifact.model_dump_json() + inference.model_dump_json()
    assert RUNTIME_URL not in serialized
    assert "runtime-secret" not in serialized
    assert RUNTIME_URL not in repr(artifact)
    assert RUNTIME_URL not in repr(inference)


def test_visual_inference_forces_partial_item_and_aggregate_status() -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    source = _source_fact(_sha256_bytes(source_bytes))
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    inference = assemble_video_understanding_inference(
        source_fact=source,
        remux_artifact=artifact,
        observation=_observation(
            candidate_sha256=artifact.artifact_sha256,
            provider_input_ref_sha256=artifact.runtime_url_sha256,
        ),
    )
    with pytest.raises(ValidationError, match="requires partial item status"):
        ReferenceVideoItem.model_validate(
            _reference_item_with_visual_inference(
                status="ok",
                source=source,
                artifact=artifact,
                inference=inference,
            )
        )

    item = ReferenceVideoItem.model_validate(
        _reference_item_with_visual_inference(
            status="partial",
            source=source,
            artifact=artifact,
            inference=inference,
        )
    )
    aggregate = {
        "contract_version": "ip-reference-video-evidence-v2",
        "operation_status": "partial_or_failed",
        "trust_boundary": "untrusted source data",
        "requested_count": 1,
        "completed_count": 0,
        "items": [item.model_dump(mode="json")],
        "limitations": ["provider visual inference remains partial"],
        "metadata": {
            "request_id": "video-derived-123456",
            "manifest_version": "f" * 64,
            "adapter_version": "test-derived-v1",
            "duration_ms": 1.0,
            "truncated": False,
        },
    }
    validated = ReferenceVideoEvidence.model_validate(aggregate)
    assert validated.operation_status == "partial_or_failed"
    assert validated.completed_count == 0
    with pytest.raises(ValidationError, match="operation_status"):
        ReferenceVideoEvidence.model_validate({**aggregate, "operation_status": "ok"})


@pytest.mark.asyncio
async def test_r1_and_r2_require_two_separate_injected_executors(tmp_path: Path) -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    source_path = tmp_path / "source.mp4"
    candidate_path = tmp_path / "candidate.mp4"
    source_path.write_bytes(source_bytes)
    candidate_path.write_bytes(candidate_bytes)
    source = _source_fact(_sha256_bytes(source_bytes))
    remux_authorization = _authorization(remux_artifact_paid_stage_binding(source))
    calls: list[str] = []

    async def remux_executor(**kwargs: object) -> RemuxArtifactStageExecution:
        calls.append("remux")
        assert kwargs == {
            "source_path": source_path.resolve(),
            "expected_source_sha256": _sha256_bytes(source_bytes),
            "evidence_root": tmp_path.resolve(),
        }
        return RemuxArtifactStageExecution(
            artifact_path=candidate_path,
            media_metadata=_metadata(len(candidate_bytes)),
            transform_receipt=_remux_receipt(_sha256_bytes(source_bytes), len(source_bytes)),
        )

    artifact = await run_remux_artifact_stage(
        source_fact=source,
        source_path=source_path,
        authorization=remux_authorization,
        executor=remux_executor,
    )
    assert calls == ["remux"]

    async def inference_executor(**kwargs: object) -> VideoUnderstandingObservation:
        calls.append("chat")
        assert kwargs == {"remux_artifact": artifact}
        return _observation(
            candidate_sha256=artifact.artifact_sha256,
            provider_input_ref_sha256=artifact.runtime_url_sha256,
        )

    inference = await run_video_understanding_inference_stage(
        source_fact=source,
        remux_artifact=artifact,
        candidate_path=candidate_path,
        authorization=_authorization(
            video_understanding_paid_stage_binding(
                source_fact=source,
                remux_artifact=artifact,
            )
        ),
        executor=inference_executor,
    )
    assert calls == ["remux", "chat"]
    assert inference.input_binding == "remux_runtime_url_provider_unattested"


@pytest.mark.asyncio
async def test_missing_stage_authorization_never_calls_an_executor(tmp_path: Path) -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    source_path = tmp_path / "source.mp4"
    candidate_path = tmp_path / "candidate.mp4"
    source_path.write_bytes(source_bytes)
    candidate_path.write_bytes(candidate_bytes)
    source = _source_fact(_sha256_bytes(source_bytes))
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    calls = 0

    async def forbidden(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    with pytest.raises(EvidenceDerivedStageUnavailable, match="PAID_STAGE_AUTHORIZATION_REQUIRED"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=source_path,
            authorization=None,
            executor=forbidden,
        )
    with pytest.raises(EvidenceDerivedStageUnavailable, match="PAID_STAGE_AUTHORIZATION_REQUIRED"):
        await run_video_understanding_inference_stage(
            source_fact=source,
            remux_artifact=artifact,
            candidate_path=candidate_path,
            authorization=None,
            executor=forbidden,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_stage_authorizations_cannot_cross_or_change_source(tmp_path: Path) -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    source_path = tmp_path / "source.mp4"
    candidate_path = tmp_path / "candidate.mp4"
    source_path.write_bytes(source_bytes)
    candidate_path.write_bytes(candidate_bytes)
    source = _source_fact(_sha256_bytes(source_bytes))
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    remux_binding = remux_artifact_paid_stage_binding(source)
    visual_binding = video_understanding_paid_stage_binding(
        source_fact=source,
        remux_artifact=artifact,
    )
    calls = 0

    async def forbidden(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    with pytest.raises(EvidenceDerivedStageUnavailable, match="PAID_STAGE_AUTHORIZATION_MISMATCH"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=source_path,
            authorization=_authorization(visual_binding),
            executor=forbidden,
        )
    with pytest.raises(EvidenceDerivedStageUnavailable, match="PAID_STAGE_AUTHORIZATION_MISMATCH"):
        await run_video_understanding_inference_stage(
            source_fact=source,
            remux_artifact=artifact,
            candidate_path=candidate_path,
            authorization=_authorization(remux_binding),
            executor=forbidden,
        )
    with pytest.raises(EvidenceDerivedStageUnavailable, match="PAID_STAGE_AUTHORIZATION_MISMATCH"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=source_path,
            authorization=_authorization(remux_binding, source_sha256="f" * 64),
            executor=forbidden,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_provider_executor_error_cannot_expose_runtime_locator(tmp_path: Path) -> None:
    source_bytes = b"sealed-original-video"
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(source_bytes)

    async def leaking_executor(**_kwargs: object) -> RemuxArtifactStageExecution:
        raise RuntimeError(RUNTIME_URL)

    with pytest.raises(EvidenceDerivedStageUnavailable) as error:
        await run_remux_artifact_stage(
            source_fact=_source_fact(_sha256_bytes(source_bytes)),
            source_path=source_path,
            authorization=_authorization(remux_artifact_paid_stage_binding(_source_fact(_sha256_bytes(source_bytes)))),
            executor=leaking_executor,
        )
    assert error.value.code == "REMUX_ARTIFACT_EXECUTION_FAILED"
    assert RUNTIME_URL not in str(error.value)
    assert "runtime-secret" not in repr(error.value)


@pytest.mark.asyncio
async def test_private_upload_is_rejected_before_either_executor(tmp_path: Path) -> None:
    payload = b"private-upload"
    private_source = VideoSource.model_validate(
        {
            "ref": "/mnt/user-data/uploads/private.mp4",
            "content_sha256": _sha256_bytes(payload),
            "observed_at": "2026-08-03T00:00:00+00:00",
        }
    )
    path = tmp_path / "private.mp4"
    path.write_bytes(payload)
    calls = 0

    async def forbidden(**_kwargs: object) -> RemuxArtifactStageExecution:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    with pytest.raises(EvidenceDerivedStageUnavailable, match="EXACT_PUBLIC_DOUYIN_SOURCE_REQUIRED"):
        await run_remux_artifact_stage(
            source_fact=private_source,
            source_path=path,
            authorization=None,
            executor=forbidden,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_stage_paths_cannot_escape_current_thread_evidence_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "thread-evidence"
    root.mkdir()
    monkeypatch.setattr(
        reference_evidence_module,
        "_mcp_user_data_root",
        lambda: root,
    )
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    source = _source_fact(_sha256_bytes(source_bytes))
    authorization = _authorization(remux_artifact_paid_stage_binding(source))
    outside_source = tmp_path / "outside-source.mp4"
    outside_source.write_bytes(source_bytes)
    calls = 0

    async def forbidden(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    with pytest.raises(EvidenceDerivedStageUnavailable, match="DERIVED_ARTIFACT_OUTSIDE_THREAD_ROOT"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=outside_source,
            authorization=authorization,
            executor=forbidden,
        )
    assert calls == 0

    inside_source = root / "source.mp4"
    inside_source.write_bytes(source_bytes)
    outside_candidate = tmp_path / "outside-candidate.mp4"
    outside_candidate.write_bytes(candidate_bytes)

    async def outside_result(**_kwargs: object) -> RemuxArtifactStageExecution:
        return RemuxArtifactStageExecution(
            artifact_path=outside_candidate,
            media_metadata=_metadata(len(candidate_bytes)),
            transform_receipt=_remux_receipt(_sha256_bytes(source_bytes), len(source_bytes)),
        )

    with pytest.raises(EvidenceDerivedStageUnavailable, match="DERIVED_ARTIFACT_OUTSIDE_THREAD_ROOT"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=inside_source,
            authorization=authorization,
            executor=outside_result,
        )

    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    visual_authorization = _authorization(
        video_understanding_paid_stage_binding(
            source_fact=source,
            remux_artifact=artifact,
        )
    )
    chat_calls = 0

    async def forbidden_chat(**_kwargs: object) -> object:
        nonlocal chat_calls
        chat_calls += 1
        raise AssertionError("provider must not be called")

    with pytest.raises(EvidenceDerivedStageUnavailable, match="DERIVED_ARTIFACT_OUTSIDE_THREAD_ROOT"):
        await run_video_understanding_inference_stage(
            source_fact=source,
            remux_artifact=artifact,
            candidate_path=outside_candidate,
            authorization=visual_authorization,
            executor=forbidden_chat,
        )
    assert chat_calls == 0


def test_cross_stage_hash_or_provider_reference_mismatch_fails_closed() -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    source = _source_fact(_sha256_bytes(source_bytes))

    wrong_candidate = _observation(
        candidate_sha256="f" * 64,
        provider_input_ref_sha256=artifact.runtime_url_sha256,
    )
    with pytest.raises(ValidationError, match="remux artifact hash"):
        assemble_video_understanding_inference(
            source_fact=source,
            remux_artifact=artifact,
            observation=wrong_candidate,
        )

    wrong_ref = _observation(
        candidate_sha256=artifact.artifact_sha256,
        provider_input_ref_sha256="f" * 64,
    )
    with pytest.raises(ValidationError, match="provider-reference hash"):
        assemble_video_understanding_inference(
            source_fact=source,
            remux_artifact=artifact,
            observation=wrong_ref,
        )


@pytest.mark.parametrize(
    "unsafe_summary",
    [
        f"供应商返回了 {RUNTIME_URL}",
        "仅回显了 signature=runtime-secret 片段",
        "仅回显了 token:runtime-secret 片段",
    ],
)
def test_provider_locator_or_credential_fragment_in_inference_content_is_rejected(
    unsafe_summary: str,
) -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    with pytest.raises(ValidationError, match="provider locator"):
        VideoUnderstandingProviderInference.model_validate(
            {
                "original_source_sha256": _sha256_bytes(source_bytes),
                "candidate_artifact_sha256": artifact.artifact_sha256,
                "remux_transform_receipt_sha256": artifact.transform_receipt_sha256,
                "provider_input_ref_sha256": artifact.runtime_url_sha256,
                "observation": _observation(
                    candidate_sha256=artifact.artifact_sha256,
                    provider_input_ref_sha256=artifact.runtime_url_sha256,
                    summary=unsafe_summary,
                ),
            }
        )


def test_model_summary_projects_bindings_without_transform_details_or_locator() -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    inference = assemble_video_understanding_inference(
        source_fact=_source_fact(_sha256_bytes(source_bytes)),
        remux_artifact=artifact,
        observation=_observation(
            candidate_sha256=artifact.artifact_sha256,
            provider_input_ref_sha256=artifact.runtime_url_sha256,
        ),
    )
    summary = _reference_video_model_summary(
        {
            "items": [
                {
                    "source": _source_fact(_sha256_bytes(source_bytes)).model_dump(mode="json"),
                    "derived_artifacts": {"remux": artifact.model_dump(mode="json")},
                    "provider_inferences": {"video_understanding": inference.model_dump(mode="json")},
                }
            ]
        }
    )
    serialized = json.dumps(summary, ensure_ascii=False)
    assert summary["items"][0]["derived_artifacts"]["remux"]["artifact_sha256"] == artifact.artifact_sha256
    assert summary["items"][0]["provider_inferences"]["video_understanding"]["collection_status"] == "partial"
    assert '"transform_receipt":' not in serialized
    assert RUNTIME_URL not in serialized
    assert "runtime-secret" not in serialized


@pytest.mark.parametrize(
    "unsafe_error",
    [
        "https://provider.example/task?id=secret",
        "token=provider-secret",
        "authorization: Bearer provider-secret",
        "line one\nline two",
    ],
)
def test_provider_error_contract_rejects_locator_and_credential_fragments(
    unsafe_error: str,
) -> None:
    with pytest.raises(ValidationError):
        ProviderEvidence.model_validate(
            {
                "provider": "volcengine-mediakit",
                "error": unsafe_error,
            }
        )


def test_model_summary_declares_visual_projection_loss() -> None:
    source_bytes = b"sealed-original-video"
    candidate_bytes = b"provider-remux-candidate"
    artifact = _artifact(source_bytes=source_bytes, candidate_bytes=candidate_bytes)
    observation = _observation(
        candidate_sha256=artifact.artifact_sha256,
        provider_input_ref_sha256=artifact.runtime_url_sha256,
        summary="视" * 1_001,
    )
    inference = assemble_video_understanding_inference(
        source_fact=_source_fact(_sha256_bytes(source_bytes)),
        remux_artifact=artifact,
        observation=observation,
    )
    summary = _reference_video_model_summary(
        {
            "items": [
                {
                    "source": _source_fact(_sha256_bytes(source_bytes)).model_dump(mode="json"),
                    "derived_artifacts": {"remux": artifact.model_dump(mode="json")},
                    "provider_inferences": {"video_understanding": inference.model_dump(mode="json")},
                }
            ]
        }
    )
    projected = summary["items"][0]["provider_inferences"]["video_understanding"]
    assert len(projected["observation"]["content"]["visual_summary"]) == 1_000
    assert projected["model_projection_truncated"] is True
    assert projected["model_projection_reason_codes"] == ["VISUAL_INFERENCE_MODEL_LIMIT"]


@pytest.mark.asyncio
async def test_r1_rejects_symlinks_and_source_inode_reuse(tmp_path: Path) -> None:
    source_bytes = b"sealed-original-video"
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(source_bytes)
    source = _source_fact(_sha256_bytes(source_bytes))
    authorization = _authorization(remux_artifact_paid_stage_binding(source))
    source_link = tmp_path / "source-link.mp4"
    source_link.symlink_to(source_path)
    calls = 0

    async def should_not_run(**_kwargs: object) -> RemuxArtifactStageExecution:
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    with pytest.raises(EvidenceDerivedStageUnavailable, match="DERIVED_ARTIFACT_SYMLINK_FORBIDDEN"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=source_link,
            authorization=authorization,
            executor=should_not_run,
        )
    assert calls == 0

    async def source_reuse(**_kwargs: object) -> RemuxArtifactStageExecution:
        return RemuxArtifactStageExecution(
            artifact_path=source_path,
            media_metadata=_metadata(len(source_bytes)),
            transform_receipt=_remux_receipt(_sha256_bytes(source_bytes), len(source_bytes)),
        )

    with pytest.raises(EvidenceDerivedStageUnavailable, match="REMUX_ARTIFACT_REUSES_SOURCE_FILE"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=source_path,
            authorization=authorization,
            executor=source_reuse,
        )

    source_hardlink = tmp_path / "source-hardlink.mp4"
    source_hardlink.hardlink_to(source_path)

    async def hardlink_reuse(**_kwargs: object) -> RemuxArtifactStageExecution:
        return RemuxArtifactStageExecution(
            artifact_path=source_hardlink,
            media_metadata=_metadata(len(source_bytes)),
            transform_receipt=_remux_receipt(_sha256_bytes(source_bytes), len(source_bytes)),
        )

    with pytest.raises(EvidenceDerivedStageUnavailable, match="REMUX_ARTIFACT_REUSES_SOURCE_FILE"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=source_path,
            authorization=authorization,
            executor=hardlink_reuse,
        )

    candidate_target = tmp_path / "candidate-target.mp4"
    candidate_target.write_bytes(b"candidate")
    candidate_link = tmp_path / "candidate-link.mp4"
    candidate_link.symlink_to(candidate_target)

    async def symlink_candidate(**_kwargs: object) -> RemuxArtifactStageExecution:
        return RemuxArtifactStageExecution(
            artifact_path=candidate_link,
            media_metadata=_metadata(candidate_target.stat().st_size),
            transform_receipt=_remux_receipt(_sha256_bytes(source_bytes), len(source_bytes)),
        )

    with pytest.raises(EvidenceDerivedStageUnavailable, match="DERIVED_ARTIFACT_SYMLINK_FORBIDDEN"):
        await run_remux_artifact_stage(
            source_fact=source,
            source_path=source_path,
            authorization=authorization,
            executor=symlink_candidate,
        )
