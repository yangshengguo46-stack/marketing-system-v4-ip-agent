from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from app.gateway.services import (
    inject_personal_ip_portfolio_context,
    strip_internal_context_keys,
)
from deerflow.agents.middlewares.personal_ip_context_middleware import (
    PersonalIPContextMiddleware,
)


def _portfolio() -> dict:
    subject = {
        "id": "subject-1",
        "owner_user_id": "user-1",
        "display_name": "老杨",
        "subject_type": "creator",
        "relationship": "self",
        "status": "active",
    }
    return {
        "subjects": [subject],
        "accounts": [
            {
                "id": "acct-douyin",
                "owner_user_id": "user-1",
                "platform": "douyin",
                "subject_id": "subject-1",
                "subject": subject,
                "display_name": "老杨说 AI",
                "metadata": {
                    "connection_state": "logged_in",
                    "browser_authenticated": True,
                    "browser_authenticated_at": "2026-07-29T08:00:00+08:00",
                    "execution_ready": False,
                    "logged_out_at": "2026-07-28T08:00:00+08:00",
                    "private_debug": "do-not-project",
                },
                "primary_audience": "个体创业者",
                "content_pillars": ["AI 智能体"],
                "status": "active",
            },
            {
                "id": "acct-xhs",
                "owner_user_id": "user-1",
                "platform": "xiaohongshu",
                "subject_id": "subject-1",
                "subject": subject,
                "display_name": "老杨的智能体笔记",
                "status": "active",
            },
        ],
    }


def test_personal_ip_context_middleware_injects_the_full_portfolio():
    original_messages = [
        SystemMessage(content="base"),
        HumanMessage(content="今天全平台表现怎么样？"),
    ]
    request = ModelRequest(
        model=object(),
        messages=original_messages,
        state={"messages": []},
        runtime=SimpleNamespace(context={"personal_ip_portfolio": _portfolio()}),
    )

    injected = PersonalIPContextMiddleware()._inject(request)

    assert len(injected.messages) == 4
    assert isinstance(injected.messages[0], SystemMessage)
    assert isinstance(injected.messages[1], SystemMessage)
    assert isinstance(injected.messages[2], HumanMessage)
    assert "老杨说 AI" in injected.messages[2].content
    assert "老杨的智能体笔记" in injected.messages[2].content
    assert "owner_user_id" not in injected.messages[2].content
    assert '"relationship": "self"' in injected.messages[2].content
    assert '"browser_authenticated": true' in injected.messages[2].content
    assert '"operation_ready": false' in injected.messages[2].content
    assert "logged_out_at" not in injected.messages[2].content
    assert "private_debug" not in injected.messages[2].content
    assert "never bound to one account" in injected.messages[1].content
    assert injected.messages[2].additional_kwargs["hide_from_ui"] is True
    assert request.messages == original_messages


def test_personal_ip_context_middleware_skips_missing_portfolio():
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content="hello")],
        state={"messages": []},
        runtime=SimpleNamespace(context={}),
    )
    assert PersonalIPContextMiddleware()._inject(request) is request


@pytest.mark.asyncio
async def test_gateway_resolves_every_active_account_without_thread_binding():
    subjects = _portfolio()["subjects"]
    accounts = [{key: value for key, value in account.items() if key != "subject"} for account in _portfolio()["accounts"]]
    account_repo = SimpleNamespace(list=AsyncMock(return_value=accounts))
    subject_repo = SimpleNamespace(list=AsyncMock(return_value=subjects))
    config = {
        "context": {
            "user_id": "user-1",
            "personal_ip_account_id": "acct-forged",
            "personal_ip_portfolio": {"accounts": [{"id": "acct-forged"}]},
        }
    }

    await inject_personal_ip_portfolio_context(
        config,
        account_repo=account_repo,
        subject_repo=subject_repo,
    )

    account_repo.list.assert_awaited_once_with("user-1")
    subject_repo.list.assert_awaited_once_with("user-1")
    portfolio = config["context"]["personal_ip_portfolio"]
    assert [account["id"] for account in portfolio["accounts"]] == [
        "acct-douyin",
        "acct-xhs",
    ]
    assert all(account["subject"]["id"] == "subject-1" for account in portfolio["accounts"])
    assert "personal_ip_account_id" not in config["context"]


def test_personal_ip_context_does_not_project_private_strategy_documents():
    portfolio = _portfolio()
    portfolio["subjects"][0]["private_strategy"] = {
        "business_model": {"offer": "部署服务"},
        "launch_package": {"name_options": ["内部候选"]},
    }
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content="给我看看经营情况")],
        state={"messages": []},
        runtime=SimpleNamespace(context={"personal_ip_portfolio": portfolio}),
    )

    injected = PersonalIPContextMiddleware()._inject(request)
    payload = injected.messages[1].content

    assert '"id": "subject-1"' in payload
    assert "private_strategy" not in payload
    assert "name_options" not in payload


@pytest.mark.asyncio
async def test_gateway_skips_portfolio_lookup_without_authenticated_owner():
    account_repo = SimpleNamespace(list=AsyncMock())
    subject_repo = SimpleNamespace(list=AsyncMock())
    config = {"context": {}}

    await inject_personal_ip_portfolio_context(
        config,
        account_repo=account_repo,
        subject_repo=subject_repo,
    )

    account_repo.list.assert_not_awaited()
    subject_repo.list.assert_not_awaited()
    assert "personal_ip_portfolio" not in config["context"]


def test_free_form_run_config_cannot_forge_product_context():
    config = {
        "context": {
            "personal_ip_account_id": "acct-forged",
            "personal_ip_account": {"id": "acct-forged"},
            "personal_ip_portfolio": {"accounts": [{"id": "acct-forged"}]},
            "model_name": "safe-model",
        },
        "configurable": {
            "personal_ip_account_id": "acct-forged",
            "personal_ip_portfolio": {"accounts": []},
        },
    }
    strip_internal_context_keys(config)
    assert "personal_ip_account_id" not in config["context"]
    assert "personal_ip_account" not in config["context"]
    assert "personal_ip_portfolio" not in config["context"]
    assert "personal_ip_account_id" not in config["configurable"]
    assert "personal_ip_portfolio" not in config["configurable"]
    assert config["context"]["model_name"] == "safe-model"
