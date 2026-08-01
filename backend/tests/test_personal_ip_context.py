from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from deerflow.agents.middlewares.personal_ip_context_middleware import PersonalIPContextMiddleware


def _request(portfolio):
    return ModelRequest(
        model=object(),
        messages=[SystemMessage(content="base"), HumanMessage(content="hello")],
        state={"messages": []},
        runtime=SimpleNamespace(context={"personal_ip_portfolio": portfolio}),
    )


def test_injects_only_subject_account_and_bounded_connection_facts():
    request = _request(
        {
            "subjects": [
                {
                    "id": "subject-1",
                    "owner_user_id": "owner-secret",
                    "display_name": "老杨",
                    "subject_type": "person",
                    "relationship": "self",
                    "status": "active",
                    "strategy": {"positioning": "must-not-project"},
                }
            ],
            "accounts": [
                {
                    "id": "account-1",
                    "platform": "douyin",
                    "subject_id": "subject-1",
                    "display_name": "老杨说AI",
                    "status": "active",
                    "primary_audience": "must-not-project",
                    "metadata": {
                        "connection_state": "logged_in",
                        "browser_authenticated": True,
                        "browser_authenticated_at": "2026-08-01T00:00:00Z",
                        "execution_ready": False,
                        "cookies": "must-not-project",
                    },
                }
            ],
        }
    )

    injected = PersonalIPContextMiddleware()._inject(request)

    assert len(injected.messages) == 4
    assert "老杨说AI" in injected.messages[2].content
    assert "owner-secret" not in injected.messages[2].content
    assert "must-not-project" not in injected.messages[2].content
    assert "cookies" not in injected.messages[2].content
    assert '"operation_ready": false' in injected.messages[2].content
    assert injected.messages[2].additional_kwargs["hide_from_ui"] is True
    assert request.messages[-1].content == "hello"


def test_missing_portfolio_is_not_injected():
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content="hello")],
        state={"messages": []},
        runtime=SimpleNamespace(context={}),
    )
    assert PersonalIPContextMiddleware()._inject(request) is request


def test_first_use_always_calls_the_model_without_a_fixed_opening_or_marker():
    request = _request({"subjects": [], "accounts": []})
    handler = Mock(return_value=AIMessage(content="model answer"))

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert result.content == "model answer"
    handler.assert_called_once()
    sent = handler.call_args.args[0]
    assert all("narrative" not in str(message.additional_kwargs) for message in sent.messages)


@pytest.mark.asyncio
async def test_async_path_is_a_single_passthrough_model_call():
    request = _request({"subjects": [], "accounts": []})
    handler = AsyncMock(return_value=AIMessage(content="model answer"))

    result = await PersonalIPContextMiddleware().awrap_model_call(request, handler)

    assert result.content == "model answer"
    handler.assert_awaited_once()
