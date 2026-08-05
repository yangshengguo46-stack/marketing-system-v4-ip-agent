from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent

from app.gateway.evidence_paid_call_admission import (
    EVIDENCE_INSPECT_TOOL_NAME,
    EVIDENCE_MCP_CLIENT_NAME,
    MEDIAKIT_ASR_CAPABILITY,
    MEDIAKIT_PROVIDER,
    MEDIAKIT_REMUX_CAPABILITY,
    MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
)
from app.gateway.evidence_paid_call_composite import (
    DERIVED_PROVIDER_EXECUTION_BLOCKERS,
    CompositePaidStageAdmission,
    VerifiedPersistedRemux,
    build_evidence_paid_call_composite_interceptor,
)
from deerflow.config.database_config import DatabaseConfig
from deerflow.ip_agent.evidence_contracts import (
    MediaMetadata,
    ReferenceVideoEvidence,
    RemuxArtifactCandidate,
)
from deerflow.ip_agent.evidence_mcp import build_reference_video_call_result
from deerflow.ip_agent.mediakit_remux_ingress import MediaKitRemuxIngressReceipt
from deerflow.ip_agent.mediakit_video_understanding import (
    VideoUnderstandingObservation,
)
from deerflow.ip_agent.reference_evidence import (
    SEALED_SOURCE_HANDOFF_CONTRACT_VERSION,
    SEALED_SOURCE_HANDOFF_META_KEY,
    OpenVerifiedSealedSource,
    assemble_remux_artifact_candidate,
    assemble_video_understanding_inference,
)
from deerflow.mcp.paid_admission import (
    PAID_CALL_GRANT_HEADER,
    PAID_CALL_SELECTED_CAPABILITY_HEADER,
    PaidCallAdmissionRejected,
    canonical_tool_args_sha256,
)
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_paid_calls import (
    EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
    EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
    EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
    OperatorCappedEvidenceStagePolicy,
    PersonalIPPaidCallRepository,
)

NOW = datetime(2026, 8, 3, 22, 0, tzinfo=UTC)
SECRET = "composite-paid-route-secret-0000000000000000000000"
ARGS = {
    "video_refs": ["https://www.douyin.com/video/7658501922794432731"],
    "reference_context": "standalone_reference",
    "purpose": "benchmark",
    "analysis_depth": "full",
    "max_frames": 8,
    "account_binding_receipt": None,
}
WORK_ID = "7658501922794432731"
RUNTIME_URL = "https://output.volcvideo.com/candidate.mp4?signature=runtime-secret"


def test_real_derived_execution_remains_explicitly_blocked() -> None:
    assert "SEALED_SOURCE_DESCRIPTOR_LIFETIME_NOT_HELD_THROUGH_EXECUTOR" not in DERIVED_PROVIDER_EXECUTION_BLOCKERS
    assert "R1_PROVIDER_REQUEST_SHA256_AUTHORITY_SPLIT" in (DERIVED_PROVIDER_EXECUTION_BLOCKERS)
    assert "R2_DURABLE_PREDECESSOR_AND_ONCE_ONLY_JOURNAL_MISSING" in (DERIVED_PROVIDER_EXECUTION_BLOCKERS)


def _policies() -> tuple[OperatorCappedEvidenceStagePolicy, ...]:
    return (
        OperatorCappedEvidenceStagePolicy(
            capability="asr",
            policy_version=EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
            local_admission_limit_micros=200_000,
            max_source_duration_millis=120_000,
        ),
        OperatorCappedEvidenceStagePolicy(
            capability="managed_https_ingress_remux",
            policy_version=EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
            local_admission_limit_micros=100_000,
            max_source_duration_millis=120_000,
        ),
        OperatorCappedEvidenceStagePolicy(
            capability="video_understanding_chat",
            policy_version=(EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION),
            local_admission_limit_micros=900_000,
            max_source_duration_millis=120_000,
        ),
    )


async def _repository(tmp_path: Any) -> PersonalIPPaidCallRepository:
    await init_engine_from_config(
        DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path / "db")),
    )
    session_factory = get_session_factory()
    assert session_factory is not None
    return PersonalIPPaidCallRepository(session_factory)


async def _approved_asr(
    repository: PersonalIPPaidCallRepository,
) -> dict[str, Any]:
    return await _approved_stage(
        repository,
        capability=MEDIAKIT_ASR_CAPABILITY,
        source_sha256="a" * 64,
    )


async def _approved_stage(
    repository: PersonalIPPaidCallRepository,
    *,
    capability: str,
    source_sha256: str,
) -> dict[str, Any]:
    policy_by_capability = {policy.capability: policy for policy in _policies()}
    policy = policy_by_capability[capability]
    requested = await repository.request_call(
        owner_user_id="owner-1",
        request_key=f"composite:{capability}:{source_sha256[:12]}",
        scope_kind="run",
        thread_id="thread-1",
        origin_run_id="origin-run-1",
        server_name=EVIDENCE_MCP_CLIENT_NAME,
        tool_name=EVIDENCE_INSPECT_TOOL_NAME,
        tool_args_sha256=canonical_tool_args_sha256(ARGS),
        provider=MEDIAKIT_PROVIDER,
        capability=capability,
        model=f"test-{capability}",
        sku=f"test-{capability}",
        provider_label="火山引擎 AI MediaKit",
        capability_label=capability,
        object_ref_label="参考视频 aaaaaaaa…aaaaaaaa",
        source_duration_millis=70_867,
        source_sha256=source_sha256,
        stage_digest="b" * 64,
        provider_request_sha256="c" * 64,
        maximum_amount_micros=policy.local_admission_limit_micros,
        currency="CNY",
        billing_basis="Owner 接受本地风险上限",
        policy_version=policy.policy_version,
        price_version="provider-price-unknown-local-admission-cap-v1",
        provider_input_attested=False,
        evidence_coverage="partial",
        warning_code="provider_content_hash_unattested",
        expires_at=NOW + timedelta(minutes=15),
        price_status="operator_capped",
        now=NOW,
    )
    approved = await repository.approve(
        requested["id"],
        owner_user_id="owner-1",
        event_key=f"approve:composite:{capability}:{source_sha256[:12]}",
        expected_request_digest=requested["request_digest"],
        approval_digest="d" * 64,
        expected_event_count=1,
        now=NOW + timedelta(seconds=1),
    )
    assert approved is not None
    return approved


def _completed(
    scope: str,
    *,
    requested: int | None = None,
    observed: int | None = None,
) -> dict[str, Any]:
    return {
        "collection_status": "completed",
        "observation_scope": scope,
        "truncated": False,
        "requested_count": requested,
        "observed_count": observed,
        "reason_codes": [],
    }


def _not_requested(scope: str) -> dict[str, Any]:
    return {
        "collection_status": "not_requested",
        "observation_scope": scope,
        "truncated": False,
        "requested_count": None,
        "observed_count": None,
        "reason_codes": ["ANALYSIS_DEPTH_NOT_REQUESTED"],
    }


def _free_evidence(source_bytes: bytes) -> ReferenceVideoEvidence:
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    item = {
        "status": "ok",
        "purpose": "benchmark",
        "source": {
            "ref": f"https://www.douyin.com/video/{WORK_ID}",
            "content_sha256": source_sha256,
            "requested_work_id": WORK_ID,
            "resolved_work_id": WORK_ID,
            "observed_work_id": WORK_ID,
            "author_sec_uid": "MS4wLjABAAAAexact-author",
            "identity_verification": "api_work_id_match",
            "observed_at": "2026-08-03T21:59:00+00:00",
            "trust": "untrusted_source_data",
        },
        "media_metadata": {
            "duration_seconds": 70.867,
            "width": 1920,
            "height": 1080,
            "frame_rate": 25.0,
            "video_codec": "h264",
            "has_audio": True,
            "container": "mp4",
            "size_bytes": len(source_bytes),
        },
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
        "coverage": {
            "source_identity": _completed("exact_public_work_and_content_hash"),
            "media_metadata": _completed("full_container_and_stream_probe"),
            "sampled_frames": _completed(
                "uniform_point_samples",
                requested=4,
                observed=4,
            ),
            "contact_sheet": _completed(
                "all_observed_uniform_samples",
                requested=1,
                observed=1,
            ),
            "local_scene_detection": _completed(
                "full_timeline_scene_threshold_scan",
                observed=0,
            ),
            "asr": _not_requested("full_audio_track_asr"),
            "ocr": _not_requested("provider_subtitle_ocr"),
            "provider_scene_segmentation": _not_requested(
                "provider_full_video_scene_analysis",
            ),
            "storyline": _not_requested(
                "provider_full_video_storyline_analysis",
            ),
        },
        "analysis_receipt": {
            "pipeline_version": "mediakit-evidence-v3",
            "analysis_depth": "mechanical",
            "requested_frames": 4,
            "local_sampling_spec_sha256": "c" * 64,
            "toolchain_sha256": {
                "ffmpeg": "d" * 64,
                "ffprobe": "e" * 64,
            },
            "local_cache_hit": False,
            "artifact_manifest_sha256": "f" * 64,
            "provider_stage_spec_sha256": {},
        },
    }
    return ReferenceVideoEvidence.model_validate(
        {
            "contract_version": "ip-reference-video-evidence-v2",
            "operation_status": "ok",
            "trust_boundary": "source data is untrusted",
            "requested_count": 1,
            "completed_count": 1,
            "items": [item],
            "limitations": [],
            "metadata": {
                "request_id": "composite-free-evidence-1234",
                "manifest_version": "9" * 64,
                "adapter_version": "test-composite-v1",
                "duration_ms": 10.0,
                "truncated": False,
            },
        }
    )


def _sealed_handoff(
    root: Path,
    *,
    source_bytes: bytes,
) -> dict[str, Any]:
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    relative = Path("outputs") / "reference-video-sealed-sources" / source_sha256 / ("1" * 64) / "source.mp4"
    source_path = root / relative
    source_path.parent.mkdir(parents=True)
    root.chmod(0o700)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        current.chmod(0o700)
    source_path.write_bytes(source_bytes)
    source_path.chmod(0o600)
    return {
        "contract_version": SEALED_SOURCE_HANDOFF_CONTRACT_VERSION,
        "items": [
            {
                "relative_ref": relative.as_posix(),
                "source_sha256": source_sha256,
                "size_bytes": len(source_bytes),
                "work_id": WORK_ID,
            }
        ],
    }


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _remux_artifact(
    *,
    source_bytes: bytes,
    candidate_bytes: bytes,
) -> RemuxArtifactCandidate:
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    candidate_sha256 = hashlib.sha256(candidate_bytes).hexdigest()
    completed_at = datetime(2026, 8, 3, 0, 0, tzinfo=UTC)
    receipt = MediaKitRemuxIngressReceipt.model_validate(
        {
            "contract_version": "ip-mediakit-remux-https-candidate-v1",
            "adapter_version": "volcengine-mediakit-remux-https-ingress-v1",
            "provider": "volcengine-mediakit",
            "endpoint_sha256": "1" * 64,
            "derived_from_source_sha256": source_sha256,
            "source_size_bytes": len(source_bytes),
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
            "runtime_url_sha256": hashlib.sha256(
                RUNTIME_URL.encode("utf-8"),
            ).hexdigest(),
            "request_sha256": "6" * 64,
            "provider_response_sha256s": [
                "7" * 64,
                "8" * 64,
                "9" * 64,
                "a" * 64,
            ],
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
    return assemble_remux_artifact_candidate(
        source_fact=_free_evidence(source_bytes).items[0].source,
        artifact_sha256=candidate_sha256,
        artifact_size_bytes=len(candidate_bytes),
        media_metadata=MediaMetadata.model_validate(
            {
                "duration_seconds": 70.867,
                "width": 1920,
                "height": 1080,
                "frame_rate": 25.0,
                "video_codec": "h264",
                "has_audio": True,
                "container": "mp4",
                "size_bytes": len(candidate_bytes),
            }
        ),
        transform_receipt=receipt,
    )


def _video_understanding_observation(
    artifact: RemuxArtifactCandidate,
) -> VideoUnderstandingObservation:
    content = {
        "visual_summary": "雨巷中可见两人共撑一把伞。",
        "observations": [
            {
                "category": "action",
                "description": "两人沿小巷移动。",
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
            "source_sha256": artifact.artifact_sha256,
            "content": content,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "reasoning_tokens": 5,
                "total_tokens": 120,
            },
            "receipt": {
                "adapter_version": ("volcengine-mediakit-video-understanding-chat-v2"),
                "profile_version": "ip-visible-events-120-frames-v3",
                "endpoint_sha256": "b" * 64,
                "model": "doubao-seed-2-0-pro-260215",
                "source_sha256": artifact.artifact_sha256,
                "provider_input_ref_sha256": artifact.runtime_url_sha256,
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


def _request() -> MCPToolCallRequest:
    return MCPToolCallRequest(
        name=EVIDENCE_INSPECT_TOOL_NAME,
        args=dict(ARGS),
        server_name=EVIDENCE_MCP_CLIENT_NAME,
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-1",
                "thread_id": "thread-1",
                "run_id": "execution-run-1",
            }
        ),
    )


def _assert_descriptor_closed(file_descriptor: int) -> None:
    with pytest.raises(OSError):
        os.fstat(file_descriptor)


@pytest.mark.asyncio
async def test_composite_asr_cancel_after_commit_is_exactly_compensated(
    tmp_path: Any,
) -> None:
    repository = await _repository(tmp_path)

    class CommitWindowRepository:
        def __init__(self) -> None:
            self.committed = asyncio.Event()
            self.release_result = asyncio.Event()

        async def admit_next_operator_capped_evidence_stage_exact(
            self,
            **kwargs: Any,
        ) -> dict[str, Any] | None:
            row = await repository.admit_next_operator_capped_evidence_stage_exact(
                **kwargs,
            )
            self.committed.set()
            await self.release_result.wait()
            return row

        async def mark_operator_capped_evidence_stage_invocation_unresolved(
            self,
            **kwargs: Any,
        ) -> dict[str, Any] | None:
            return await repository.mark_operator_capped_evidence_stage_invocation_unresolved(
                **kwargs,
            )

    commit_window_repository = CommitWindowRepository()
    provider_calls = 0

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=commit_window_repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_ASR_CAPABILITY,
        user_data_root_resolver=lambda _request: tmp_path,
        remux_executor=None,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )
    handler_called = False

    async def handler(_observed: MCPToolCallRequest) -> None:
        nonlocal handler_called
        handler_called = True

    try:
        approved = await _approved_asr(repository)
        task = asyncio.create_task(interceptor(_request(), handler))
        await commit_window_repository.committed.wait()
        task.cancel()
        commit_window_repository.release_result.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert handler_called is False
        assert provider_calls == 0
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
        assert current["capability"] == MEDIAKIT_ASR_CAPABILITY
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_composite_asr_is_the_only_grant_forwarded_to_mcp(
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    derived_calls = 0

    async def forbidden_remux(**_kwargs: Any) -> RemuxArtifactCandidate:
        nonlocal derived_calls
        derived_calls += 1
        raise AssertionError("derived executor must not run for ASR")

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_ASR_CAPABILITY,
        user_data_root_resolver=lambda _request: tmp_path,
        remux_executor=forbidden_remux,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )
    observed_headers: dict[str, Any] | None = None

    async def handler(observed: MCPToolCallRequest) -> CallToolResult:
        nonlocal observed_headers
        observed_headers = dict(observed.headers or {})
        return CallToolResult(content=[], isError=False)

    try:
        await _approved_asr(repository)
        result = await interceptor(_request(), handler)
        assert result.isError is False
        assert observed_headers is not None
        assert PAID_CALL_GRANT_HEADER in observed_headers
        assert observed_headers[PAID_CALL_SELECTED_CAPABILITY_HEADER] == MEDIAKIT_ASR_CAPABILITY
        assert derived_calls == 0
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_composite_rejects_ambiguous_capabilities_before_any_transport(
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    handler_calls = 0
    executor_calls = 0

    async def forbidden_remux(**_kwargs: Any) -> RemuxArtifactCandidate:
        nonlocal executor_calls
        executor_calls += 1
        raise AssertionError("ambiguous route must not run an executor")

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda _capability: True,
        user_data_root_resolver=lambda _request: tmp_path,
        remux_executor=forbidden_remux,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
        nonlocal handler_calls
        handler_calls += 1
        return CallToolResult(content=[])

    try:
        approved_asr = await _approved_asr(repository)
        approved_remux = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            source_sha256="b" * 64,
        )
        with pytest.raises(
            PaidCallAdmissionRejected,
            match="PAID_CALL_CAPABILITY_AMBIGUOUS",
        ):
            await interceptor(_request(), handler)
        assert handler_calls == 0
        assert executor_calls == 0
        for approved in (approved_asr, approved_remux):
            current = await repository.get(
                approved["id"],
                owner_user_id="owner-1",
            )
            assert current is not None
            assert current["status"] == "approved"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_composite_r1_uses_free_mcp_exact_handoff_and_rebuilds_one_result(
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    user_data_root = tmp_path / "user-data"
    user_data_root.mkdir()
    source_bytes = b"composite-exact-public-source"
    candidate_bytes = b"local-zero-provider-remux-candidate"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    free_evidence = _free_evidence(source_bytes)
    handoff = _sealed_handoff(user_data_root, source_bytes=source_bytes)
    artifact = _remux_artifact(
        source_bytes=source_bytes,
        candidate_bytes=candidate_bytes,
    )
    free_result = build_reference_video_call_result(
        free_evidence,
        sealed_source_handoff_meta=handoff,
    )
    handler_calls = 0
    executor_calls = 0

    async def local_remux_executor(
        *,
        admission: CompositePaidStageAdmission,
        source: OpenVerifiedSealedSource,
        free_evidence: ReferenceVideoEvidence,
    ) -> RemuxArtifactCandidate:
        nonlocal executor_calls
        executor_calls += 1
        assert admission.selected_capability == MEDIAKIT_REMUX_CAPABILITY
        assert source.source_sha256 == source_sha256
        assert os.pread(source.file_descriptor, source.size_bytes, 0) == source_bytes
        assert free_evidence.items[0].source.content_sha256 == source_sha256
        assert not hasattr(source, "relative_ref")
        assert handoff["items"][0]["relative_ref"] not in repr(source)
        assert admission.claim.call_id not in repr(admission)
        assert admission.claim.jti not in repr(admission)
        return artifact

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_REMUX_CAPABILITY,
        user_data_root_resolver=lambda _request: user_data_root,
        remux_executor=local_remux_executor,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    async def handler(observed: MCPToolCallRequest) -> CallToolResult:
        nonlocal handler_calls
        handler_calls += 1
        headers = {str(key).casefold(): value for key, value in (observed.headers or {}).items()}
        assert PAID_CALL_GRANT_HEADER.casefold() not in headers
        assert PAID_CALL_SELECTED_CAPABILITY_HEADER.casefold() not in headers
        return free_result

    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            source_sha256=source_sha256,
        )
        result = await interceptor(_request(), handler)
        assert handler_calls == 1
        assert executor_calls == 1
        validated = ReferenceVideoEvidence.model_validate(
            result.structuredContent,
        )
        assert validated.items[0].derived_artifacts is not None
        assert validated.items[0].derived_artifacts.remux.artifact_sha256 == artifact.artifact_sha256
        text_blocks = [json.loads(block.text) for block in result.content if isinstance(block, TextContent)]
        assert len(text_blocks) == 1
        assert text_blocks[0]["items"][0]["derived_artifacts"]["remux"]["artifact_sha256"] == artifact.artifact_sha256
        serialized = json.dumps(
            result.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
        )
        assert SEALED_SOURCE_HANDOFF_META_KEY not in serialized
        assert handoff["items"][0]["relative_ref"] not in serialized
        assert RUNTIME_URL not in serialized
        assert approved["id"] not in serialized
    finally:
        await close_engine()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["root_swap", "file_swap", "consumer_close"])
async def test_composite_r1_fd_window_fails_closed_on_executor_mutation(
    mutation: str,
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    user_data_root = tmp_path / "user-data"
    user_data_root.mkdir()
    source_bytes = b"composite-r1-context-owned-source"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    handoff = _sealed_handoff(user_data_root, source_bytes=source_bytes)
    source_path = user_data_root / handoff["items"][0]["relative_ref"]
    artifact = _remux_artifact(
        source_bytes=source_bytes,
        candidate_bytes=b"context-owned-candidate",
    )
    free_result = build_reference_video_call_result(
        _free_evidence(source_bytes),
        sealed_source_handoff_meta=handoff,
    )
    observed_descriptor: int | None = None

    async def mutating_executor(
        *,
        admission: CompositePaidStageAdmission,
        source: OpenVerifiedSealedSource,
        free_evidence: ReferenceVideoEvidence,
    ) -> RemuxArtifactCandidate:
        nonlocal observed_descriptor
        del admission, free_evidence
        observed_descriptor = source.file_descriptor
        assert os.pread(source.file_descriptor, source.size_bytes, 0) == source_bytes
        if mutation == "root_swap":
            displaced = tmp_path / "displaced-user-data"
            user_data_root.rename(displaced)
            user_data_root.mkdir(mode=0o700)
        elif mutation == "file_swap":
            displaced = source_path.with_name("displaced-source.mp4")
            source_path.replace(displaced)
            source_path.write_bytes(source_bytes)
            source_path.chmod(0o600)
        else:
            os.close(source.file_descriptor)
        return artifact

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_REMUX_CAPABILITY,
        user_data_root_resolver=lambda _request: user_data_root,
        remux_executor=mutating_executor,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
        return free_result

    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            source_sha256=source_sha256,
        )
        with pytest.raises(
            PaidCallAdmissionRejected,
            match="PAID_CALL_SEALED_HANDOFF_FILE_INVALID",
        ):
            await interceptor(_request(), handler)
        assert observed_descriptor is not None
        _assert_descriptor_closed(observed_descriptor)
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_composite_r1_executor_exception_closes_context_owned_fd(
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    user_data_root = tmp_path / "user-data"
    user_data_root.mkdir()
    source_bytes = b"composite-r1-executor-exception-source"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    free_result = build_reference_video_call_result(
        _free_evidence(source_bytes),
        sealed_source_handoff_meta=_sealed_handoff(
            user_data_root,
            source_bytes=source_bytes,
        ),
    )
    observed_descriptor: int | None = None

    async def failing_executor(
        *,
        admission: CompositePaidStageAdmission,
        source: OpenVerifiedSealedSource,
        free_evidence: ReferenceVideoEvidence,
    ) -> RemuxArtifactCandidate:
        nonlocal observed_descriptor
        del admission, free_evidence
        observed_descriptor = source.file_descriptor
        assert os.pread(source.file_descriptor, source.size_bytes, 0) == source_bytes
        raise RuntimeError("test-only executor failure")

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_REMUX_CAPABILITY,
        user_data_root_resolver=lambda _request: user_data_root,
        remux_executor=failing_executor,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
        return free_result

    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            source_sha256=source_sha256,
        )
        with pytest.raises(
            PaidCallAdmissionRejected,
            match="PAID_CALL_REMUX_EXECUTION_FAILED",
        ):
            await interceptor(_request(), handler)
        assert observed_descriptor is not None
        _assert_descriptor_closed(observed_descriptor)
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_composite_r1_repeated_cancellation_closes_context_owned_fd(
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    user_data_root = tmp_path / "user-data"
    user_data_root.mkdir()
    source_bytes = b"composite-r1-cancelled-executor-source"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    free_result = build_reference_video_call_result(
        _free_evidence(source_bytes),
        sealed_source_handoff_meta=_sealed_handoff(
            user_data_root,
            source_bytes=source_bytes,
        ),
    )
    entered = asyncio.Event()
    never = asyncio.Event()
    observed_descriptor: int | None = None

    async def waiting_executor(
        *,
        admission: CompositePaidStageAdmission,
        source: OpenVerifiedSealedSource,
        free_evidence: ReferenceVideoEvidence,
    ) -> RemuxArtifactCandidate:
        nonlocal observed_descriptor
        del admission, free_evidence
        observed_descriptor = source.file_descriptor
        assert os.pread(source.file_descriptor, source.size_bytes, 0) == source_bytes
        entered.set()
        await never.wait()
        raise AssertionError("cancelled executor must not resume")

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_REMUX_CAPABILITY,
        user_data_root_resolver=lambda _request: user_data_root,
        remux_executor=waiting_executor,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
        return free_result

    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            source_sha256=source_sha256,
        )
        task = asyncio.create_task(interceptor(_request(), handler))
        await entered.wait()
        task.cancel()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert observed_descriptor is not None
        _assert_descriptor_closed(observed_descriptor)
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reconciliation_required"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_composite_r1_missing_handoff_compensates_and_calls_no_executor(
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    source_bytes = b"composite-source-without-handoff"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    executor_calls = 0

    async def forbidden_remux(**_kwargs: Any) -> RemuxArtifactCandidate:
        nonlocal executor_calls
        executor_calls += 1
        raise AssertionError("missing handoff must not reach executor")

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_REMUX_CAPABILITY,
        user_data_root_resolver=lambda _request: tmp_path,
        remux_executor=forbidden_remux,
        video_understanding_executor=None,
        derived_stage_journal=None,
        clock=lambda: NOW + timedelta(seconds=2),
    )

    async def handler(_observed: MCPToolCallRequest) -> CallToolResult:
        return build_reference_video_call_result(_free_evidence(source_bytes))

    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_REMUX_CAPABILITY,
            source_sha256=source_sha256,
        )
        with pytest.raises(
            PaidCallAdmissionRejected,
            match="PAID_CALL_SEALED_HANDOFF_INVALID",
        ):
            await interceptor(_request(), handler)
        assert executor_calls == 0
        current = await repository.get(
            approved["id"],
            owner_user_id="owner-1",
        )
        assert current is not None
        assert current["status"] == "reconciliation_required"
        assert current["capability"] == MEDIAKIT_REMUX_CAPABILITY
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_composite_r2_uses_durable_predecessor_and_keeps_runtime_url_private(
    tmp_path: Path,
) -> None:
    repository = await _repository(tmp_path)
    user_data_root = tmp_path / "user-data"
    user_data_root.mkdir()
    source_bytes = b"composite-r2-exact-public-source"
    candidate_bytes = b"persisted-remux-candidate"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    artifact = _remux_artifact(
        source_bytes=source_bytes,
        candidate_bytes=candidate_bytes,
    )
    persisted = VerifiedPersistedRemux(
        artifact=artifact,
        runtime_url=RUNTIME_URL,
        journal_record_sha256="a" * 64,
    )
    inference = assemble_video_understanding_inference(
        source_fact=_free_evidence(source_bytes).items[0].source,
        remux_artifact=artifact,
        observation=_video_understanding_observation(artifact),
    )
    free_result = build_reference_video_call_result(
        _free_evidence(source_bytes),
        sealed_source_handoff_meta=_sealed_handoff(
            user_data_root,
            source_bytes=source_bytes,
        ),
    )
    executor_calls = 0
    journal_calls = 0

    class DurableJournalFake:
        async def load_verified_remux(self, **kwargs: Any) -> VerifiedPersistedRemux:
            nonlocal journal_calls
            journal_calls += 1
            assert kwargs == {
                "owner_user_id": "owner-1",
                "thread_id": "thread-1",
                "original_source_sha256": source_sha256,
                "candidate_artifact_sha256": artifact.artifact_sha256,
            }
            return persisted

    async def local_visual_executor(
        *,
        admission: CompositePaidStageAdmission,
        source: OpenVerifiedSealedSource,
        persisted_remux: VerifiedPersistedRemux,
        free_evidence: ReferenceVideoEvidence,
    ):
        nonlocal executor_calls
        executor_calls += 1
        assert admission.selected_capability == MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY
        assert source.source_sha256 == source_sha256
        assert os.pread(source.file_descriptor, source.size_bytes, 0) == source_bytes
        assert persisted_remux is persisted
        assert free_evidence.items[0].source.content_sha256 == source_sha256
        assert RUNTIME_URL not in repr(persisted_remux)
        return inference

    interceptor = build_evidence_paid_call_composite_interceptor(
        repository=repository,
        trusted_stage_policies=_policies(),
        signing_secret=SECRET,
        capability_configured=lambda capability: capability == MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
        user_data_root_resolver=lambda _request: user_data_root,
        remux_executor=None,
        video_understanding_executor=local_visual_executor,
        derived_stage_journal=DurableJournalFake(),
        clock=lambda: NOW + timedelta(seconds=2),
    )

    async def handler(observed: MCPToolCallRequest) -> CallToolResult:
        headers = {str(key).casefold(): value for key, value in (observed.headers or {}).items()}
        assert PAID_CALL_GRANT_HEADER.casefold() not in headers
        assert PAID_CALL_SELECTED_CAPABILITY_HEADER.casefold() not in headers
        return free_result

    try:
        approved = await _approved_stage(
            repository,
            capability=MEDIAKIT_VIDEO_UNDERSTANDING_CHAT_CAPABILITY,
            source_sha256=artifact.artifact_sha256,
        )
        result = await interceptor(_request(), handler)
        assert journal_calls == 1
        assert executor_calls == 1
        validated = ReferenceVideoEvidence.model_validate(
            result.structuredContent,
        )
        assert validated.operation_status == "partial_or_failed"
        assert validated.completed_count == 0
        assert validated.items[0].status == "partial"
        assert validated.items[0].provider_inferences is not None
        assert validated.items[0].provider_inferences.video_understanding.candidate_artifact_sha256 == artifact.artifact_sha256
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        assert artifact.artifact_sha256 in text
        serialized = json.dumps(
            result.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
        )
        assert RUNTIME_URL not in serialized
        assert SEALED_SOURCE_HANDOFF_META_KEY not in serialized
        assert approved["id"] not in serialized
    finally:
        await close_engine()
