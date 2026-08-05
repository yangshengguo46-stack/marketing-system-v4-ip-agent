"""Cross-layer regression for the Evidence paid-call control-plane boundary."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, TextContent

from app.gateway.evidence_paid_call_bridge import (
    PAID_CALL_REQUESTS_META_KEY,
    build_evidence_paid_call_interceptor,
)
from deerflow.agents.middlewares.tool_error_handling_middleware import (
    ToolErrorHandlingMiddleware,
)
from deerflow.agents.middlewares.tool_output_budget_middleware import (
    ToolOutputBudgetMiddleware,
)
from deerflow.agents.middlewares.tool_result_meta import TOOL_META_KEY
from deerflow.agents.middlewares.tool_result_sanitization_middleware import (
    ToolResultSanitizationMiddleware,
)
from deerflow.config.tool_output_config import ToolOutputConfig
from deerflow.ip_agent.evidence_contracts import ReferenceVideoEvidence
from deerflow.mcp.result_metadata import MCP_RESULT_METADATA_KEY
from deerflow.mcp.tools import _convert_call_tool_result
from deerflow.models.patched_deepseek import PatchedChatDeepSeek
from deerflow.tools.result_policy import RESULT_POLICY_METADATA_KEY

_NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
_REQUEST_DIGEST = "8" * 64
_REQUEST_ID = "paid-call-model-boundary"
_EVIDENCE_POLICY = {
    "trust": "untrusted_external",
    "semantic_class": "evidence",
    "outcome_contract": "ip-evidence-operation-status-v1",
}


def _coverage(
    status: str,
    scope: str,
    *,
    reason_codes: list[str] | None = None,
    requested_count: int | None = None,
    observed_count: int | None = None,
) -> dict[str, Any]:
    return {
        "collection_status": status,
        "observation_scope": scope,
        "truncated": False,
        "requested_count": requested_count,
        "observed_count": observed_count,
        "reason_codes": reason_codes or [],
    }


def _strict_reference_evidence() -> dict[str, Any]:
    structured = {
        "contract_version": "ip-reference-video-evidence-v2",
        "operation_status": "partial_or_failed",
        "trust_boundary": "source data is untrusted",
        "requested_count": 1,
        "completed_count": 0,
        "items": [
            {
                "status": "partial",
                "purpose": "benchmark",
                "source": {
                    "ref": "/mnt/user-data/uploads/reference.mp4",
                    "content_sha256": "a" * 64,
                    "observed_at": "2026-08-02T11:59:00+00:00",
                    "trust": "untrusted_source_data",
                    "public_metadata": {},
                },
                "media_metadata": {
                    "duration_seconds": 8.0,
                    "width": 1280,
                    "height": 720,
                    "frame_rate": 24.0,
                    "video_codec": "h264",
                    "has_audio": True,
                    "container": "mp4",
                    "size_bytes": 2_449_778,
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
                "contact_sheet_sha256": "e" * 64,
                "scene_boundaries_seconds": [],
                "provider_evidence": {},
                "analysis_receipt": {
                    "pipeline_version": "mediakit-evidence-v3",
                    "analysis_depth": "speech_text",
                    "requested_frames": 4,
                    "local_sampling_spec_sha256": "b" * 64,
                    "toolchain_sha256": {
                        "ffmpeg": "c" * 64,
                        "ffprobe": "d" * 64,
                        "mediakit": "e" * 64,
                    },
                    "local_cache_hit": False,
                    "artifact_manifest_sha256": "f" * 64,
                    "provider_stage_spec_sha256": {
                        "asr": "1" * 64,
                        "ocr": "2" * 64,
                    },
                },
                "coverage": {
                    "source_identity": _coverage("completed", "source_reference_and_content_hash"),
                    "media_metadata": _coverage("completed", "full_container_and_stream_probe"),
                    "sampled_frames": _coverage(
                        "completed",
                        "uniform_point_samples",
                        requested_count=4,
                        observed_count=4,
                    ),
                    "contact_sheet": _coverage(
                        "completed",
                        "all_observed_uniform_samples",
                        requested_count=1,
                        observed_count=1,
                    ),
                    "local_scene_detection": _coverage(
                        "completed",
                        "full_timeline_scene_threshold_scan",
                        observed_count=0,
                    ),
                    "asr": _coverage(
                        "unavailable",
                        "full_audio_track_asr",
                        reason_codes=["UNAVAILABLE_PROVIDER_EXECUTION_NOT_AUTHORIZED"],
                    ),
                    "ocr": _coverage(
                        "unavailable",
                        "provider_subtitle_ocr",
                        reason_codes=["UNAVAILABLE_PROVIDER_EXECUTION_NOT_AUTHORIZED"],
                    ),
                    "provider_scene_segmentation": _coverage(
                        "not_requested",
                        "provider_full_video_scene_analysis",
                        reason_codes=["ANALYSIS_DEPTH_NOT_REQUESTED"],
                    ),
                    "storyline": _coverage(
                        "not_requested",
                        "provider_full_video_storyline_analysis",
                        reason_codes=["ANALYSIS_DEPTH_NOT_REQUESTED"],
                    ),
                },
            }
        ],
        "limitations": ["provider ASR requires admission"],
        "metadata": {
            "request_id": "video-request-model-boundary",
            "manifest_version": "9" * 64,
            "adapter_version": "mediakit-evidence-v3",
            "duration_ms": 10,
            "truncated": False,
        },
    }
    return ReferenceVideoEvidence.model_validate(structured).model_dump(mode="json", exclude_none=True)


class _Repository:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def request_call(self, **proposal: Any) -> dict[str, Any]:
        row = {
            "id": _REQUEST_ID,
            **proposal,
            "request_digest": _REQUEST_DIGEST,
            "status": "requested",
            "event_count": 1,
            "created_at": _NOW.isoformat(),
            "updated_at": _NOW.isoformat(),
            "price_status": "unknown",
        }
        self.rows.append(row)
        return row

    async def list_thread(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> list[dict[str, Any]]:
        return [row for row in self.rows if row["owner_user_id"] == owner_user_id and row["thread_id"] == thread_id]


def _mcp_request() -> MCPToolCallRequest:
    return MCPToolCallRequest(
        name="inspect_reference_videos",
        args={
            "video_refs": ["/mnt/user-data/uploads/reference.mp4"],
            "reference_context": "standalone_reference",
            "purpose": "benchmark",
            "analysis_depth": "speech_text",
            "max_frames": 4,
            "account_binding_receipt": None,
        },
        server_name="ip_evidence",
        runtime=SimpleNamespace(
            context={
                "user_id": "owner-model-boundary",
                "thread_id": "thread-model-boundary",
                "run_id": "run-model-boundary",
            }
        ),
    )


def _middleware_request() -> SimpleNamespace:
    return SimpleNamespace(
        tool_call={
            "name": "ip_evidence_inspect_reference_videos",
            "id": "tool-call-model-boundary",
        },
        tool=SimpleNamespace(metadata={RESULT_POLICY_METADATA_KEY: dict(_EVIDENCE_POLICY)}),
        runtime=SimpleNamespace(state={}),
    )


@pytest.mark.asyncio
async def test_paid_call_control_plane_stays_out_of_doubao_model_payload() -> None:
    structured = _strict_reference_evidence()
    bridge = build_evidence_paid_call_interceptor(
        repository=_Repository(),
        clock=lambda: _NOW,
    )

    async def handler(_request: MCPToolCallRequest) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text="local evidence")],
            structuredContent=structured,
        )

    bridged = await bridge(_mcp_request(), handler)
    content, artifact = _convert_call_tool_result(bridged)
    message = ToolMessage(
        content=content,
        artifact=artifact,
        name="ip_evidence_inspect_reference_videos",
        tool_call_id="tool-call-model-boundary",
        status="success",
    )
    request = _middleware_request()
    error_handling = ToolErrorHandlingMiddleware()
    sanitization = ToolResultSanitizationMiddleware()
    budget = ToolOutputBudgetMiddleware(ToolOutputConfig(externalize_min_chars=1_000_000))

    result = budget.wrap_tool_call(
        request,
        lambda outer: sanitization.wrap_tool_call(
            outer,
            lambda inner: error_handling.wrap_tool_call(inner, lambda _: message),
        ),
    )

    assert isinstance(result, ToolMessage)
    assert result.artifact["structured_content"] == structured
    assert result.additional_kwargs[TOOL_META_KEY] == {
        "status": "partial_success",
        "error_type": "evidence_partial",
        "recoverable_by_model": False,
        "recommended_next_action": "summarize",
        "source": "tool_return",
    }
    paid_requests = result.artifact[MCP_RESULT_METADATA_KEY]["result_meta"][PAID_CALL_REQUESTS_META_KEY]
    assert paid_requests[0]["request_id"] == _REQUEST_ID
    assert paid_requests[0]["request_digest"] == _REQUEST_DIGEST

    model = PatchedChatDeepSeek(
        model="doubao-seed-2-0-pro-260215",
        api_key="test-key",
        api_base="https://ark.cn-beijing.volces.com/api/v3",
    )
    provider_payload = model._get_request_payload([result])
    encoded_payload = json.dumps(provider_payload, ensure_ascii=False)

    assert provider_payload["messages"] == [
        {
            "content": "local evidence",
            "role": "tool",
            "tool_call_id": "tool-call-model-boundary",
        }
    ]
    assert PAID_CALL_REQUESTS_META_KEY not in encoded_payload
    assert _REQUEST_ID not in encoded_payload
    assert _REQUEST_DIGEST not in encoded_payload
