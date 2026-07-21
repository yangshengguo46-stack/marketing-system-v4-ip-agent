from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from app.gateway.services import (
    inject_personal_ip_account_context,
    strip_internal_context_keys,
)
from deerflow.agents.middlewares.personal_ip_context_middleware import (
    PersonalIPContextMiddleware,
)


def test_personal_ip_context_middleware_injects_ephemeral_account_data():
    account = {
        "id": "acct-1",
        "owner_user_id": "user-1",
        "platform": "douyin",
        "display_name": "老杨说 AI",
        "primary_audience": "个体创业者",
        "content_pillars": ["AI 智能体"],
        "status": "active",
    }
    original_messages = [
        SystemMessage(content="base"),
        HumanMessage(content="今天发什么？"),
    ]
    request = ModelRequest(
        model=object(),
        messages=original_messages,
        state={"messages": []},
        runtime=SimpleNamespace(context={"personal_ip_account": account}),
    )

    injected = PersonalIPContextMiddleware()._inject(request)

    assert len(injected.messages) == 4
    assert isinstance(injected.messages[0], SystemMessage)
    assert isinstance(injected.messages[1], SystemMessage)
    assert isinstance(injected.messages[2], HumanMessage)
    assert "老杨说 AI" in injected.messages[2].content
    assert "owner_user_id" not in injected.messages[2].content
    assert injected.messages[2].additional_kwargs["hide_from_ui"] is True
    assert request.messages == original_messages


def test_personal_ip_context_middleware_skips_missing_account():
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content="hello")],
        state={"messages": []},
        runtime=SimpleNamespace(context={}),
    )
    assert PersonalIPContextMiddleware()._inject(request) is request


@pytest.mark.asyncio
async def test_gateway_resolves_requested_account_and_persists_thread_binding():
    account = {
        "id": "acct-1",
        "owner_user_id": "user-1",
        "display_name": "账号一",
        "platform": "douyin",
        "status": "active",
    }
    account_repo = SimpleNamespace(get=AsyncMock(return_value=account))
    thread_store = SimpleNamespace(
        get=AsyncMock(return_value={"metadata": {}}),
        update_metadata=AsyncMock(),
    )
    config = {
        "context": {
            "user_id": "user-1",
            "personal_ip_account": {"id": "forged"},
        }
    }

    await inject_personal_ip_account_context(
        config,
        {"personal_ip_account_id": "acct-1"},
        account_repo=account_repo,
        thread_store=thread_store,
        thread_id="thread-1",
    )

    account_repo.get.assert_awaited_once_with("acct-1", owner_user_id="user-1")
    assert config["context"]["personal_ip_account"] == account
    assert config["context"]["personal_ip_account_id"] == "acct-1"
    thread_store.update_metadata.assert_awaited_once_with(
        "thread-1",
        {"personal_ip_account_id": "acct-1"},
        user_id="user-1",
    )


@pytest.mark.asyncio
async def test_gateway_falls_back_to_thread_binding_and_rejects_cross_owner_account():
    account_repo = SimpleNamespace(get=AsyncMock(return_value=None))
    thread_store = SimpleNamespace(
        get=AsyncMock(return_value={"metadata": {"personal_ip_account_id": "acct-other"}}),
        update_metadata=AsyncMock(),
    )
    config = {"context": {"user_id": "user-1"}}

    with pytest.raises(HTTPException) as exc:
        await inject_personal_ip_account_context(
            config,
            None,
            account_repo=account_repo,
            thread_store=thread_store,
            thread_id="thread-1",
        )

    assert exc.value.status_code == 404
    assert "personal_ip_account" not in config["context"]


def test_free_form_run_config_cannot_forge_product_context():
    config = {
        "context": {
            "personal_ip_account_id": "acct-forged",
            "personal_ip_account": {"id": "acct-forged"},
            "model_name": "safe-model",
        },
        "configurable": {"personal_ip_account_id": "acct-forged"},
    }
    strip_internal_context_keys(config)
    assert "personal_ip_account_id" not in config["context"]
    assert "personal_ip_account" not in config["context"]
    assert "personal_ip_account_id" not in config["configurable"]
    assert config["context"]["model_name"] == "safe-model"
