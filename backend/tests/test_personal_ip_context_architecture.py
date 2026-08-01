from __future__ import annotations

from pathlib import Path

from deerflow.config.app_config import AppConfig
from deerflow.tools.tools import get_available_tools

MIDDLEWARE_SOURCE = Path(__file__).parents[1] / "packages" / "harness" / "deerflow" / "agents" / "middlewares" / "personal_ip_context_middleware.py"


def test_personal_ip_context_does_not_own_benchmark_or_skill_orchestration() -> None:
    """Portfolio/onboarding context must not become a second agent runtime."""

    source = MIDDLEWARE_SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "_BENCHMARK_",
        "personal_ip_benchmark",
        "_guard_benchmark",
        "_tool_call_count",
        "describe_skill",
        "read_file",
    )

    assert not [token for token in forbidden if token in source]


def test_retired_semantic_tools_are_absent_from_the_runtime_registry() -> None:
    app_config = AppConfig.from_file(str(Path(__file__).resolve().parents[2] / "config.example.yaml"))
    tools = {tool.name: tool for tool in get_available_tools(include_mcp=False, app_config=app_config)}

    for name in (
        "personal_ip_record_strategy",
        "personal_ip_compile_video_pattern",
        "personal_ip_account_diagnostic_context",
        "personal_ip_run_preflight",
        "personal_ip_seal_retrospective",
        "personal_ip_operating_cockpit",
    ):
        assert name not in tools
    assert "personal_ip_compile_video_plan" in tools
