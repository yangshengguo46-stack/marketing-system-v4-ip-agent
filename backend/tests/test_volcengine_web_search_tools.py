"""Unit tests for the Volcengine Ark Responses Web Search provider."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest


@pytest.fixture(autouse=True)
def reset_unavailable_capabilities():
    import deerflow.community.volcengine_web_search.tools as search_mod

    search_mod._unavailable_capabilities.clear()
    yield
    search_mod._unavailable_capabilities.clear()


def _mock_config(**extra):
    app = MagicMock()
    tool_config = MagicMock()
    tool_config.model_extra = extra
    app.get_tool_config.return_value = tool_config
    return app


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.request = MagicMock()
    response.text = json.dumps(payload)
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code),
            request=response.request,
            response=response,
        )
    return response


def _patch_client(response: MagicMock):
    patcher = patch("deerflow.community.volcengine_web_search.tools.httpx.Client")
    client = patcher.start()
    client.return_value.__enter__.return_value.post.return_value = response
    return patcher, client


def test_search_calls_responses_web_search_and_returns_citations(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import web_search_tool

    monkeypatch.setenv("VOLCENGINE_API_KEY", "secret-key")
    app = _mock_config(
        model="doubao-seed-2-0-pro-260215",
        api_base="https://ark.cn-beijing.volces.com/api/v3",
        sources=["search_engine"],
        max_results=4,
        max_keyword=2,
        max_output_tokens=700,
    )
    response = _mock_response(
        {
            "status": "completed",
            "output": [
                {"type": "web_search_call", "status": "completed"},
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "方舟支持联网搜索。",
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "title": "官方文档",
                                    "url": "https://www.volcengine.com/docs/example",
                                    "summary": "Responses API 支持 Web Search。",
                                    "site_name": "火山引擎",
                                    "publish_time": "2026-03-10",
                                },
                                {
                                    "type": "url_citation",
                                    "title": "重复文档",
                                    "url": "https://www.volcengine.com/docs/example",
                                },
                                {
                                    "type": "url_citation",
                                    "title": "不安全地址",
                                    "url": "http://127.0.0.1/private",
                                },
                            ],
                        }
                    ],
                },
            ],
        }
    )
    patcher, client = _patch_client(response)
    try:
        with patch(
            "deerflow.community.volcengine_web_search.tools.get_app_config",
            return_value=app,
        ):
            result = json.loads(web_search_tool.invoke({"query": " 方舟联网搜索 "}))
    finally:
        patcher.stop()

    call = client.return_value.__enter__.return_value.post.call_args
    assert call.args[0] == "https://ark.cn-beijing.volces.com/api/v3/responses"
    assert call.kwargs["headers"]["Authorization"] == "Bearer secret-key"
    assert call.kwargs["headers"]["ark-beta-web-search"] == "true"
    assert call.kwargs["json"]["store"] is False
    assert call.kwargs["json"]["thinking"] == {"type": "disabled"}
    assert call.kwargs["json"]["tool_choice"] == "required"
    assert call.kwargs["json"]["tools"] == [
        {
            "type": "web_search",
            "sources": ["search_engine"],
            "limit": 4,
            "max_keyword": 2,
        }
    ]
    assert call.kwargs["json"]["max_output_tokens"] == 700
    assert result == {
        "query": "方舟联网搜索",
        "search_backend": "volcengine_ark",
        "answer": "方舟支持联网搜索。",
        "total_results": 1,
        "results": [
            {
                "title": "官方文档",
                "url": "https://www.volcengine.com/docs/example",
                "content": "Responses API 支持 Web Search。",
                "site_name": "火山引擎",
                "published_at": "2026-03-10",
            }
        ],
    }


def test_tool_not_open_falls_back_and_is_cached(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import web_search_tool

    monkeypatch.setenv("VOLCENGINE_API_KEY", "secret-key")
    app = _mock_config(fallback_to_ddg=True)
    response = _mock_response(
        {
            "error": {
                "code": "ToolNotOpen",
                "message": "account has not activated web search; secret provider detail",
            }
        },
        status_code=404,
    )
    patcher, client = _patch_client(response)
    fallback = {
        "query": "热点",
        "total_results": 1,
        "results": [{"title": "A", "url": "https://example.com", "content": "B"}],
    }
    try:
        with (
            patch(
                "deerflow.community.volcengine_web_search.tools.get_app_config",
                return_value=app,
            ),
            patch(
                "deerflow.community.volcengine_web_search.tools._run_ddg_fallback",
                return_value=fallback,
            ) as fallback_call,
        ):
            first = json.loads(web_search_tool.invoke({"query": "热点"}))
            second = json.loads(web_search_tool.invoke({"query": "热点"}))
    finally:
        patcher.stop()

    assert client.return_value.__enter__.return_value.post.call_count == 1
    assert fallback_call.call_count == 2
    assert first["search_backend"] == "public_web_fallback"
    assert first["fallback_reason"] == "volcengine_web_search_not_activated"
    assert first["results"] == fallback["results"]
    assert second == first
    assert "secret provider detail" not in json.dumps(first, ensure_ascii=False)


def test_tool_not_open_without_fallback_returns_safe_error(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import web_search_tool

    monkeypatch.setenv("VOLCENGINE_API_KEY", "secret-key")
    app = _mock_config(fallback_to_ddg=False)
    response = _mock_response(
        {"error": {"code": "ToolNotOpen", "message": "raw internal response"}},
        status_code=404,
    )
    patcher, _ = _patch_client(response)
    try:
        with patch(
            "deerflow.community.volcengine_web_search.tools.get_app_config",
            return_value=app,
        ):
            result = json.loads(web_search_tool.invoke({"query": "热点"}))
    finally:
        patcher.stop()

    assert result == {
        "error": "Volcengine Web Search is not activated for this account",
        "error_code": "ToolNotOpen",
        "query": "热点",
    }


def test_missing_key_returns_structured_error(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import web_search_tool

    monkeypatch.delenv("VOLCENGINE_API_KEY", raising=False)
    app = _mock_config()
    with patch(
        "deerflow.community.volcengine_web_search.tools.get_app_config",
        return_value=app,
    ):
        result = json.loads(web_search_tool.invoke({"query": "热点"}))

    assert result == {
        "error": "VOLCENGINE_API_KEY is not configured",
        "query": "热点",
    }


def test_literal_key_is_read_from_tool_config(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import _get_api_key

    monkeypatch.setenv("VOLCENGINE_API_KEY", "env-key")
    assert _get_api_key({"api_key": "config-key"}) == "config-key"


def test_env_reference_is_resolved(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import _get_api_key

    monkeypatch.setenv("CUSTOM_ARK_KEY", "custom-key")
    assert _get_api_key({"api_key": "$CUSTOM_ARK_KEY"}) == "custom-key"


def test_limits_and_sources_are_bounded(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import web_search_tool

    monkeypatch.setenv("VOLCENGINE_API_KEY", "secret-key")
    app = _mock_config(
        max_results=999,
        max_keyword=999,
        max_output_tokens=99999,
        sources=["search_engine", "unknown", "douyin"],
    )
    response = _mock_response(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "结果",
                            "annotations": [],
                        }
                    ],
                }
            ],
        }
    )
    patcher, client = _patch_client(response)
    try:
        with patch(
            "deerflow.community.volcengine_web_search.tools.get_app_config",
            return_value=app,
        ):
            web_search_tool.invoke({"query": "热点"})
    finally:
        patcher.stop()

    payload = client.return_value.__enter__.return_value.post.call_args.kwargs["json"]
    assert payload["tools"][0]["limit"] == 10
    assert payload["tools"][0]["max_keyword"] == 3
    assert payload["tools"][0]["sources"] == ["search_engine", "douyin"]
    assert payload["max_output_tokens"] == 2048


def test_http_failure_does_not_return_raw_provider_body(monkeypatch):
    from deerflow.community.volcengine_web_search.tools import web_search_tool

    monkeypatch.setenv("VOLCENGINE_API_KEY", "secret-key")
    app = _mock_config(fallback_to_ddg=False)
    response = _mock_response(
        {"error": {"code": "UpstreamFailure", "message": "credential-shaped-secret"}},
        status_code=503,
    )
    patcher, _ = _patch_client(response)
    try:
        with patch(
            "deerflow.community.volcengine_web_search.tools.get_app_config",
            return_value=app,
        ):
            result = json.loads(web_search_tool.invoke({"query": "热点"}))
    finally:
        patcher.stop()

    assert result == {
        "error": "Volcengine Web Search request failed",
        "error_code": "UpstreamFailure",
        "status_code": 503,
        "query": "热点",
    }
    assert "credential-shaped-secret" not in json.dumps(result)
