from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
import yaml
from langchain_core.messages import HumanMessage

from deerflow.agents.middlewares.mcp_routing_middleware import McpRoutingMiddleware
from deerflow.ip_agent import evidence_mcp, reference_evidence
from deerflow.ip_agent.evidence_contracts import InspectReferenceVideosInput

ROOT = Path(__file__).resolve().parents[2]
MEDIAKIT_AGENT_TOOLS = {
    "ip_evidence_collect_douyin_benchmark_account",
    "ip_evidence_inspect_reference_videos",
}


def test_default_ip_agent_exposes_mediakit_evidence_tools() -> None:
    agent_config = yaml.safe_load((ROOT / "product/defaults/agents/ip-agent/config.yaml").read_text(encoding="utf-8"))
    runtime_profile = yaml.safe_load((ROOT / "product/defaults/product-runtime-profile.yaml").read_text(encoding="utf-8"))

    assert MEDIAKIT_AGENT_TOOLS <= set(agent_config["tool_allowlist"])
    assert runtime_profile["capability_contract"]["tool_allowlist"] == agent_config["tool_allowlist"]


def test_default_extensions_start_mediakit_evidence_without_paid_interceptors() -> None:
    extensions = json.loads((ROOT / "extensions_config.example.json").read_text(encoding="utf-8"))
    server = extensions["mcpServers"]["ip_evidence"]

    assert server["enabled"] is True
    assert server["required"] is True
    assert server["command"] == "$DEER_FLOW_PYTHON_EXECUTABLE"
    assert server["env"]["MEDIAKIT_API_KEY"] == "$MEDIAKIT_API_KEY"
    assert server["tool_call_timeout"] == 3600
    assert server["tools"]["inspect_reference_videos"]["required"] is True
    assert all("paid" not in interceptor.lower() for interceptor in extensions.get("mcpInterceptors", []))
    assert evidence_mcp.capability_registry.exact("reference_video", "inspect").timeout_seconds == 3600
    manifest = evidence_mcp.evidence_manifest()
    inspect_capability = next(capability for capability in manifest["capabilities"] if capability["tool"] == "inspect_reference_videos")
    assert inspect_capability["provider_cost"] == "configured_key_direct_execution"
    assert all("paid-call admission" not in invariant for invariant in manifest["invariants"])
    assert any("MEDIAKIT_API_KEY" in invariant for invariant in manifest["invariants"])


def test_uploaded_video_path_auto_promotes_mediakit_tool() -> None:
    extensions = json.loads((ROOT / "extensions_config.example.json").read_text(encoding="utf-8"))
    routing = extensions["mcpServers"]["ip_evidence"]["tools"]["inspect_reference_videos"]["routing"]
    tool_name = "ip_evidence_inspect_reference_videos"
    middleware = McpRoutingMiddleware(
        {
            tool_name: {
                "priority": routing["priority"],
                "keywords": routing["keywords"],
            }
        },
        "catalog-hash",
        3,
    )

    update = middleware.before_model(
        {"messages": [HumanMessage(content=("请分析我上传的 /mnt/user-data/uploads/final.mp4，告诉我实际识别到的内容。"))]},
        runtime=None,
    )

    assert update is not None
    assert update["promoted"]["names"] == [tool_name]


def test_full_video_request_has_an_explicit_analysis_depth_contract() -> None:
    soul = (ROOT / "product/defaults/agents/ip-agent/SOUL.md").read_text(encoding="utf-8")
    signature = inspect.signature(evidence_mcp.inspect_reference_videos_tool)

    assert "默认一次跑完" in soul
    assert "场景切分和故事线" in soul
    assert "analysis_depth" not in signature.parameters
    assert "max_frames" not in signature.parameters


@pytest.mark.asyncio
async def test_default_agent_video_tool_always_dispatches_full_maximum_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DispatchReached(RuntimeError):
        pass

    observed: dict[str, object] = {}

    async def dispatch(**kwargs: object) -> object:
        observed.update(kwargs)
        raise DispatchReached

    monkeypatch.setattr(evidence_mcp.capability_dispatcher, "dispatch", dispatch)

    with pytest.raises(DispatchReached):
        await evidence_mcp.inspect_reference_videos_tool(
            ["/mnt/user-data/uploads/final.mp4"],
            ctx=object(),
        )

    arguments = observed["arguments"]
    assert isinstance(arguments, dict)
    assert arguments["analysis_depth"] == "full"
    assert arguments["max_frames"] == 12


@pytest.mark.asyncio
async def test_reference_video_pipeline_can_authorize_mediakit_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[dict[str, object]] = []

    async def fail_after_observing(**kwargs: object) -> dict[str, object]:
        observed.append(kwargs)
        raise ValueError("fixture stops before media download")

    monkeypatch.setattr(reference_evidence, "_inspect_one_video", fail_after_observing)

    result = await reference_evidence.inspect_reference_videos(
        ["https://example.com/video.mp4"],
        analysis_depth="full",
    )

    assert len(observed) == 1
    assert "provider_execution_authorized" not in observed[0]
    assert "provider_admission" not in observed[0]
    assert result["operation_status"] == "failed"


@pytest.mark.asyncio
async def test_evidence_mcp_uses_configured_mediakit_key_without_one_shot_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PipelineReached(RuntimeError):
        pass

    observed: dict[str, object] = {}

    async def inspect_pipeline(_video_refs: list[str], **kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        raise PipelineReached

    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-environment")
    monkeypatch.setattr(evidence_mcp, "inspect_reference_videos", inspect_pipeline)
    arguments = InspectReferenceVideosInput.model_validate(
        {
            "video_refs": ["https://example.com/video.mp4"],
            "analysis_depth": "full",
        }
    )

    with pytest.raises(PipelineReached):
        await evidence_mcp._inspect_handler(arguments)

    assert "provider_execution_authorized" not in observed
    assert "provider_admission" not in observed
    assert "provider_admission" not in inspect.signature(evidence_mcp._inspect_handler).parameters
    assert not hasattr(evidence_mcp, "_optional_asr_admission")
    assert not hasattr(evidence_mcp, "_paid_grant_verifier")
