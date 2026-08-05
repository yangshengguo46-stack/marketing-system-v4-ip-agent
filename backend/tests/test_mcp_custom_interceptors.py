"""Tests for custom MCP tool interceptors loaded via extensions_config.json."""

import asyncio
import builtins
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.mcp.paid_admission import (
    PaidCallRouteGroupResolution,
    PaidMCPToolRoute,
    PaidMCPToolRouteGroup,
    build_paid_call_grant_interceptor,
)
from deerflow.mcp.tools import RequiredMCPConfigurationError, get_mcp_tools


def _make_patches(*, interceptor_paths=None, required: bool = False):
    """Set up mocks for get_mcp_tools() with optional custom interceptors.

    Returns a dict of patch context managers.
    """
    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[])

    extra = {}
    if interceptor_paths is not None:
        extra["mcpInterceptors"] = interceptor_paths
    if required:
        extra["mcpInterceptorsRequired"] = True

    return {
        "mock_client": mock_client,
        "client_cls": patch(
            "langchain_mcp_adapters.client.MultiServerMCPClient",
            return_value=mock_client,
        ),
        "from_file": patch(
            "deerflow.config.extensions_config.ExtensionsConfig.from_file",
            return_value=MagicMock(
                model_extra=extra,
                get_enabled_mcp_servers=MagicMock(return_value={}),
            ),
        ),
        "build_servers": patch(
            "deerflow.mcp.tools.build_servers_config",
            return_value={"test-server": {}},
        ),
        "oauth_headers": patch(
            "deerflow.mcp.tools.get_initial_oauth_headers",
            new_callable=AsyncMock,
            return_value={},
        ),
        "oauth_interceptor": patch(
            "deerflow.mcp.tools.build_oauth_tool_interceptor",
            return_value=None,
        ),
    }


def _get_interceptors(mock_cls):
    """Extract the tool_interceptors list passed to MultiServerMCPClient."""
    kw = mock_cls.call_args
    return kw.kwargs.get("tool_interceptors") or kw[1].get("tool_interceptors", [])


def test_custom_interceptor_loaded_and_appended():
    """A valid interceptor builder path is resolved, called, and appended to tool_interceptors."""

    async def fake_interceptor(request, handler):
        return await handler(request)

    def fake_builder():
        return fake_interceptor

    p = _make_patches(interceptor_paths=["my_package.auth:build_interceptor"])

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.resolve_variable", return_value=fake_builder),
    ):
        asyncio.run(get_mcp_tools())

        interceptors = _get_interceptors(mock_cls)
        assert len(interceptors) == 1
        assert interceptors[0] is fake_interceptor


def test_multiple_custom_interceptors():
    """Multiple interceptor paths are all loaded in order."""

    async def interceptor_a(request, handler):
        return await handler(request)

    async def interceptor_b(request, handler):
        return await handler(request)

    builders = {
        "pkg.a:build_a": lambda: interceptor_a,
        "pkg.b:build_b": lambda: interceptor_b,
    }

    p = _make_patches(interceptor_paths=["pkg.a:build_a", "pkg.b:build_b"])

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.resolve_variable", side_effect=lambda path: builders[path]),
    ):
        asyncio.run(get_mcp_tools())

        interceptors = _get_interceptors(mock_cls)
        assert len(interceptors) == 2
        assert interceptors[0] is interceptor_a
        assert interceptors[1] is interceptor_b


def test_overlapping_paid_interceptors_fail_closed_even_when_not_required():
    """ASR single-route and R1/R2 group cannot be installed in parallel."""

    class SingleResolver:
        async def reserve_approved_call(self, scope):
            del scope
            return None

    class GroupResolver:
        async def reserve_approved_call_for_group(self, scope):
            del scope
            return PaidCallRouteGroupResolution()

        async def compensate_admitted_call_for_group(self, scope, **kwargs):
            del scope, kwargs

    route_key = ("ip_evidence", "inspect_reference_videos")
    single = build_paid_call_grant_interceptor(
        routes=[PaidMCPToolRoute(*route_key, "volcengine-mediakit", "asr")],
        resolver=SingleResolver(),
    )
    group = build_paid_call_grant_interceptor(
        routes=[
            PaidMCPToolRouteGroup(
                *route_key,
                "volcengine-mediakit",
                ("managed_https_ingress_remux", "video_understanding_chat"),
            )
        ],
        resolver=GroupResolver(),
    )
    builders = {
        "paid.asr:build": lambda: single,
        "paid.derived:build": lambda: group,
    }
    p = _make_patches(
        interceptor_paths=["paid.asr:build", "paid.derived:build"],
    )

    with (
        p["client_cls"] as client_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch(
            "deerflow.mcp.tools.resolve_variable",
            side_effect=lambda path: builders[path],
        ),
        pytest.raises(
            RequiredMCPConfigurationError,
            match="one composite dispatcher",
        ),
    ):
        asyncio.run(get_mcp_tools())

    client_cls.assert_not_called()


def test_custom_interceptor_builder_returning_none_is_skipped():
    """If a builder returns None, it is not appended to the interceptor list."""
    p = _make_patches(interceptor_paths=["pkg.noop:build_noop"])

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.resolve_variable", return_value=lambda: None),
    ):
        asyncio.run(get_mcp_tools())

        assert len(_get_interceptors(mock_cls)) == 0


def test_custom_interceptor_resolve_error_logs_warning_and_continues():
    """A broken interceptor path logs a warning and does not block tool loading."""
    p = _make_patches(interceptor_paths=["broken.path:does_not_exist"])

    with (
        p["client_cls"],
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.resolve_variable", side_effect=ImportError("no such module")),
        patch("deerflow.mcp.tools.logger.warning") as mock_warn,
    ):
        tools = asyncio.run(get_mcp_tools())

        assert tools == []
        mock_warn.assert_called_once()
        assert "broken.path:does_not_exist" in mock_warn.call_args[0][0]


def test_custom_interceptor_builder_exception_logs_warning_and_continues():
    """If the builder function itself raises, the error is caught and logged."""

    def exploding_builder():
        raise RuntimeError("builder exploded")

    p = _make_patches(interceptor_paths=["pkg.bad:exploding_builder"])

    with (
        p["client_cls"],
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.resolve_variable", return_value=exploding_builder),
        patch("deerflow.mcp.tools.logger.warning") as mock_warn,
    ):
        tools = asyncio.run(get_mcp_tools())

        assert tools == []
        mock_warn.assert_called_once()
        assert "pkg.bad:exploding_builder" in mock_warn.call_args[0][0]


def test_no_mcp_interceptors_field_is_safe():
    """When mcpInterceptors is absent from config, no interceptors are added."""
    p = _make_patches(interceptor_paths=None)

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
    ):
        asyncio.run(get_mcp_tools())

        assert len(_get_interceptors(mock_cls)) == 0


def test_custom_interceptor_coexists_with_oauth_interceptor():
    """Custom interceptors are appended after the OAuth interceptor."""

    async def oauth_fn(request, handler):
        return await handler(request)

    async def custom_fn(request, handler):
        return await handler(request)

    p = _make_patches(interceptor_paths=["pkg.custom:build_custom"])

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        patch("deerflow.mcp.tools.build_oauth_tool_interceptor", return_value=oauth_fn),
        patch("deerflow.mcp.tools.resolve_variable", return_value=lambda: custom_fn),
    ):
        asyncio.run(get_mcp_tools())

        interceptors = _get_interceptors(mock_cls)
        assert len(interceptors) == 2
        assert interceptors[0] is oauth_fn
        assert interceptors[1] is custom_fn


def test_mcp_interceptors_single_string_is_normalized():
    """A single string value for mcpInterceptors is normalized to a list."""

    async def fake_interceptor(request, handler):
        return await handler(request)

    p = _make_patches(interceptor_paths="pkg.single:build_it")

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.resolve_variable", return_value=lambda: fake_interceptor),
    ):
        asyncio.run(get_mcp_tools())

        assert len(_get_interceptors(mock_cls)) == 1


def test_mcp_interceptors_invalid_type_logs_warning():
    """A non-list, non-string value for mcpInterceptors logs a warning and is skipped."""
    p = _make_patches(interceptor_paths=42)

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.logger.warning") as mock_warn,
    ):
        asyncio.run(get_mcp_tools())

        assert len(_get_interceptors(mock_cls)) == 0
        mock_warn.assert_called_once()
        assert "must be a list" in mock_warn.call_args[0][0]


def test_custom_interceptor_non_callable_return_logs_warning():
    """If a builder returns a non-callable value, it is skipped with a warning."""
    p = _make_patches(interceptor_paths=["pkg.bad:returns_string"])

    with (
        p["client_cls"] as mock_cls,
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch("deerflow.mcp.tools.resolve_variable", return_value=lambda: "not_a_callable"),
        patch("deerflow.mcp.tools.logger.warning") as mock_warn,
    ):
        asyncio.run(get_mcp_tools())

        assert len(_get_interceptors(mock_cls)) == 0
        mock_warn.assert_called_once()
        assert "non-callable" in mock_warn.call_args[0][0]


def test_required_custom_interceptor_import_failure_stops_tool_loading():
    p = _make_patches(
        interceptor_paths=["broken.path:does_not_exist"],
        required=True,
    )

    with (
        p["client_cls"],
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch(
            "deerflow.mcp.tools.resolve_variable",
            side_effect=ImportError("no such module"),
        ),
        pytest.raises(RuntimeError, match="Required MCP interceptor failed"),
    ):
        asyncio.run(get_mcp_tools())


def test_required_mcp_server_discovery_failure_stops_tool_loading():
    p = _make_patches(
        interceptor_paths=["pkg.required:build"],
        required=True,
    )
    p["mock_client"].get_tools = AsyncMock(side_effect=RuntimeError("server unavailable"))

    async def interceptor(request, handler):
        return await handler(request)

    with (
        p["client_cls"],
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch(
            "deerflow.mcp.tools.resolve_variable",
            return_value=lambda: interceptor,
        ),
        pytest.raises(RuntimeError, match="Required MCP server failed discovery"),
    ):
        asyncio.run(get_mcp_tools())


def test_required_mcp_server_returning_no_tools_stops_tool_loading():
    p = _make_patches(
        interceptor_paths=["pkg.required:build"],
        required=True,
    )

    async def interceptor(request, handler):
        return await handler(request)

    with (
        p["client_cls"],
        p["from_file"],
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch(
            "deerflow.mcp.tools.resolve_variable",
            return_value=lambda: interceptor,
        ),
        pytest.raises(RuntimeError, match="Required MCP capabilities missing"),
    ):
        asyncio.run(get_mcp_tools())


def test_required_mcp_adapter_dependency_failure_stops_tool_loading():
    p = _make_patches(
        interceptor_paths=["pkg.required:build"],
        required=True,
    )
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "langchain_mcp_adapters.client":
            raise ImportError("adapter unavailable")
        return real_import(name, *args, **kwargs)

    with (
        p["from_file"],
        patch("builtins.__import__", side_effect=guarded_import),
        pytest.raises(RuntimeError, match="adapter dependency is unavailable"),
    ):
        asyncio.run(get_mcp_tools())


def test_required_mcp_server_missing_one_named_tool_stops_tool_loading():
    p = _make_patches(
        interceptor_paths=["pkg.required:build"],
        required=True,
    )
    discovered = MagicMock()
    discovered.name = "test-server_collect_douyin_benchmark_account"
    p["mock_client"].get_tools = AsyncMock(return_value=[discovered])
    config = ExtensionsConfig.model_validate(
        {
            "mcpInterceptors": ["pkg.required:build"],
            "mcpInterceptorsRequired": True,
            "mcpServers": {
                "test-server": {
                    "enabled": True,
                    "required": True,
                    "type": "stdio",
                    "command": "fake-server",
                    "tools": {
                        "collect_douyin_benchmark_account": {"required": True},
                        "inspect_reference_videos": {"required": True},
                    },
                }
            },
        }
    )

    async def interceptor(request, handler):
        return await handler(request)

    with (
        p["client_cls"],
        p["from_file"] as from_file,
        p["build_servers"],
        p["oauth_headers"],
        p["oauth_interceptor"],
        patch(
            "deerflow.mcp.tools.resolve_variable",
            return_value=lambda: interceptor,
        ),
        pytest.raises(RuntimeError, match="inspect_reference_videos"),
    ):
        from_file.return_value = config
        asyncio.run(get_mcp_tools())
