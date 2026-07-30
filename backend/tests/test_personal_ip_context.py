from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

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


def test_new_owner_orientation_filters_research_tools_before_first_reply():
    request = ModelRequest(
        model=object(),
        system_message=SystemMessage(content="full operating prompt with every Skill and execution policy"),
        messages=[
            SystemMessage(content="base"),
            HumanMessage(content=("我是第一次使用，想做一个面向职场女性的轻食品牌 IP，但还没注册账号，也没有对标。你先告诉我该从哪里开始。")),
        ],
        tools=[
            SimpleNamespace(name="ask_clarification"),
            SimpleNamespace(name="personal_ip_startup_context"),
            SimpleNamespace(name="read_file"),
            SimpleNamespace(name="browser_navigate"),
            SimpleNamespace(name="browser_get_text"),
            SimpleNamespace(name="task"),
        ],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )

    injected = PersonalIPContextMiddleware()._inject(request)

    assert [tool.name for tool in injected.tools] == ["ask_clarification"]
    assert "first visible reply" in injected.messages[1].content
    assert "Do not browse, search, load a Skill file" in injected.messages[1].content
    assert '"experience": "new_owner"' in injected.messages[2].content
    assert injected.system_message.content == request.system_message.content
    assert request.tools is not injected.tools


def test_new_owner_orientation_returns_one_bounded_question_without_calling_model():
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content=("我是第一次使用，想做一个面向职场女性的轻食品牌 IP，但还没注册账号，也没有对标。你先告诉我该从哪里开始。"))],
        tools=[SimpleNamespace(name="ask_clarification")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    handler = Mock()

    result = PersonalIPContextMiddleware().wrap_model_call(
        request,
        handler,
    )

    assert isinstance(result, AIMessage)
    assert result.content == ""
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "ask_clarification"
    args = result.tool_calls[0]["args"]
    assert "先不用注册账号" in args["context"]
    assert "两到三个定位假设" in args["context"]
    assert "还不能把定位当成结论" in args["context"]
    assert "最核心产品或服务" in args["question"]
    assert args["options"] is None
    handler.assert_not_called()


def test_new_owner_first_answer_asks_audience_question_without_calling_model():
    request = ModelRequest(
        model=object(),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_clarification",
                        "args": {},
                        "id": "first_use_orientation_example",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(
                content="你最有证据的能力是什么？",
                tool_call_id="first_use_orientation_example",
            ),
            HumanMessage(
                content="我最有证据的是十年供应链采购经验。",
                additional_kwargs={
                    "hide_from_ui": True,
                    "human_input_response": {
                        "version": 1,
                        "kind": "human_input_response",
                        "source": "ask_clarification",
                        "request_id": "first-use-request",
                        "response_kind": "text",
                        "value": "我最有证据的是十年供应链采购经验。",
                    },
                },
            ),
        ],
        tools=[SimpleNamespace(name="ask_clarification")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    handler = Mock()

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert isinstance(result, AIMessage)
    assert result.content == ""
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["id"].startswith("first_use_audience_")
    assert "服务哪一类人" in result.tool_calls[0]["args"]["question"]
    assert "采取行动或付费" in result.tool_calls[0]["args"]["question"]
    handler.assert_not_called()


def test_new_owner_second_intake_answer_reaches_normal_model_path():
    first_response = {
        "version": 1,
        "kind": "human_input_response",
        "source": "ask_clarification",
        "request_id": "first-use-request",
        "response_kind": "text",
        "value": "我最有证据的是十年供应链采购经验。",
    }
    second_response = {
        "version": 1,
        "kind": "human_input_response",
        "source": "ask_clarification",
        "request_id": "audience-request",
        "response_kind": "text",
        "value": "服务小型制造企业，解决采购成本失控。",
    }
    request = ModelRequest(
        model=object(),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_clarification",
                        "args": {},
                        "id": "first_use_orientation_example",
                        "type": "tool_call",
                    }
                ],
            ),
            HumanMessage(
                content=first_response["value"],
                additional_kwargs={
                    "hide_from_ui": True,
                    "human_input_response": first_response,
                },
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_clarification",
                        "args": {},
                        "id": "first_use_audience_example",
                        "type": "tool_call",
                    }
                ],
            ),
            HumanMessage(
                content=second_response["value"],
                additional_kwargs={
                    "hide_from_ui": True,
                    "human_input_response": second_response,
                },
            ),
        ],
        tools=[SimpleNamespace(name="ask_clarification")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    expected = AIMessage(content="给出定位假设")
    handler = Mock(return_value=expected)

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert result is expected
    handler.assert_called_once()


@pytest.mark.parametrize(
    ("request_text", "expected_question"),
    [
        ("我是第一次使用，想从零做个人 IP。", "专业能力或真实经历"),
        (
            "我们是一个公益组织，第一次做机构 IP，应该从哪里开始？",
            "目标人群采取的一个具体行动",
        ),
    ],
)
def test_new_owner_orientation_question_matches_the_ip_entity(
    request_text,
    expected_question,
):
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content=request_text)],
        tools=[SimpleNamespace(name="ask_clarification")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )

    result = PersonalIPContextMiddleware().wrap_model_call(
        request,
        Mock(),
    )

    assert isinstance(result, AIMessage)
    assert expected_question in result.tool_calls[0]["args"]["question"]


@pytest.mark.asyncio
async def test_async_new_owner_orientation_does_not_await_the_model_handler():
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content="This is my first time. I want to build a brand from scratch.")],
        tools=[SimpleNamespace(name="ask_clarification")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    handler = AsyncMock()

    result = await PersonalIPContextMiddleware().awrap_model_call(
        request,
        handler,
    )

    assert isinstance(result, AIMessage)
    assert result.tool_calls[0]["name"] == "ask_clarification"
    assert "core product or service" in result.tool_calls[0]["args"]["question"]
    handler.assert_not_awaited()


def test_new_owner_concrete_task_keeps_execution_tools_available():
    tools = [
        SimpleNamespace(name="ask_clarification"),
        SimpleNamespace(name="read_file"),
        SimpleNamespace(name="browser_navigate"),
    ]
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content=("我是第一次使用。请直接把下面这个选题写成60秒口播脚本：为什么上班族总在下午三点想吃甜食？"))],
        tools=tools,
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )

    injected = PersonalIPContextMiddleware()._inject(request)

    assert injected.tools == tools
    assert "first visible reply" not in injected.messages[0].content
    assert '"experience": "new_owner"' in injected.messages[1].content


def test_new_owner_concrete_task_still_calls_the_model_handler():
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content=("我是第一次使用。请直接把下面这个选题写成60秒口播脚本：为什么上班族总在下午三点想吃甜食？"))],
        tools=[SimpleNamespace(name="ask_clarification")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    expected = AIMessage(content="脚本结果")

    result = PersonalIPContextMiddleware().wrap_model_call(
        request,
        lambda _: expected,
    )

    assert result is expected


def test_new_owner_plain_script_request_bypasses_first_use_orientation():
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content="我是第一次使用，想做一个下午茶短视频，帮我写脚本。")],
        tools=[SimpleNamespace(name="ask_clarification")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    expected = AIMessage(content="脚本结果")
    handler = Mock(return_value=expected)

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert result is expected
    handler.assert_called_once()


def test_returning_owner_orientation_keeps_research_tools_available():
    tools = [
        SimpleNamespace(name="ask_clarification"),
        SimpleNamespace(name="read_file"),
        SimpleNamespace(name="browser_navigate"),
    ]
    request = ModelRequest(
        model=object(),
        messages=[HumanMessage(content="我想重新梳理品牌 IP，应该从哪里开始？")],
        tools=tools,
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": _portfolio(),
            }
        ),
    )

    injected = PersonalIPContextMiddleware()._inject(request)

    assert injected.tools == tools
    assert '"experience": "returning_owner"' in injected.messages[1].content


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
