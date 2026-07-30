from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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


def test_new_owner_orientation_injection_keeps_the_full_request_untouched():
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

    assert injected.tools == request.tools
    assert "first visible reply" not in injected.messages[1].content
    assert '"experience": "new_owner"' in injected.messages[2].content
    assert injected.system_message.content == request.system_message.content
    assert request.tools is injected.tools


def test_new_owner_orientation_opens_as_normal_conversation_without_calling_model():
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
    assert result.tool_calls == []
    assert "先不急着注册账号" in result.content
    assert "不是心理测评" in result.content
    assert "分成几章" in result.content
    assert "最早记忆" not in result.content
    assert result.content.count("？") == 1
    marker = result.additional_kwargs["personal_ip_narrative_interview"]
    assert marker == {
        "version": 1,
        "status": "active",
        "turn": 0,
        "entity_type": "brand",
    }
    handler.assert_not_called()


def test_new_owner_first_answer_uses_a_bounded_reflective_model_call():
    opening = PersonalIPContextMiddleware._first_use_response(
        ModelRequest(
            model=object(),
            messages=[HumanMessage(content="我是第一次使用，想从零做个人 IP。")],
            state={"messages": []},
            runtime=SimpleNamespace(
                context={
                    "agent_name": "ip-agent",
                    "personal_ip_portfolio": {"subjects": [], "accounts": []},
                }
            ),
        )
    )
    assert opening is not None
    request = ModelRequest(
        model=object(),
        system_message=SystemMessage(content="full operating prompt with every Skill"),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            opening,
            HumanMessage(content="我最有证据的是十年供应链采购经验，最难的一次是把一家断供工厂救回来。"),
        ],
        tools=[
            SimpleNamespace(name="read_file"),
            SimpleNamespace(name="browser_navigate"),
        ],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    compact_response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "personal_ip_narrative_turn",
                "args": {
                    "reflection": "你没有先拿“十年经验”证明自己，而是马上讲到一次真实的断供危机；目前看，能被验证的可能是你在高压下修复供应链的能力。",
                    "question": "那次工厂断供时，你做了哪个同行通常不会做的关键选择？",
                    "status": "continue",
                    "reason": "需要把抽象能力落到可观察选择。",
                },
                "id": "narrative-turn-1",
                "type": "tool_call",
            }
        ],
    )
    handler = Mock(return_value=compact_response)

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert isinstance(result, AIMessage)
    assert result.tool_calls == []
    assert "十年经验" in result.content
    assert "同行通常不会做的关键选择" in result.content
    assert result.content.count("？") == 1
    assert result.additional_kwargs["personal_ip_narrative_interview"]["turn"] == 1
    assert result.additional_kwargs["personal_ip_narrative_interview"]["status"] == "active"
    compact_request = handler.call_args.args[0]
    assert compact_request.system_message.content != request.system_message.content
    assert "reflective listening" in compact_request.system_message.content
    assert [tool["function"]["name"] for tool in compact_request.tools] == ["personal_ip_narrative_turn"]
    assert "browser_navigate" not in str(compact_request.tools)
    assert "供应链采购经验" in compact_request.messages[-1].content


def test_compact_interviewer_uses_original_visible_text_not_prompt_wrappers():
    request = ModelRequest(
        model=object(),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            AIMessage(
                content="如果把你的经历分成几章，你会怎么命名？",
                additional_kwargs={
                    "personal_ip_narrative_interview": {
                        "version": 1,
                        "status": "active",
                        "turn": 0,
                        "entity_type": "person",
                    }
                },
            ),
            HumanMessage(
                content="<system-reminder>hidden date</system-reminder>\n--- BEGIN USER INPUT ---\n原始可见回答\n--- END USER INPUT ---",
                additional_kwargs={"original_user_content": "原始可见回答"},
            ),
        ],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    marker = PersonalIPContextMiddleware._active_narrative_marker(request)

    assert marker is not None
    compact = PersonalIPContextMiddleware._compact_narrative_request(request, marker)
    assert compact.messages[-1].content == "原始可见回答"
    assert "system-reminder" not in compact.messages[-1].content


def test_new_owner_interviewer_hands_ready_evidence_to_the_full_agent():
    opening = AIMessage(
        content="先讲讲你走到今天真正改变你的几段经历？",
        additional_kwargs={
            "personal_ip_narrative_interview": {
                "version": 1,
                "status": "active",
                "turn": 1,
                "entity_type": "person",
            }
        },
    )
    request = ModelRequest(
        model=object(),
        system_message=SystemMessage(content="full operating prompt"),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            opening,
            HumanMessage(content="我服务小型制造企业，过去三年最稳定的结果是把采购成本降低 8% 到 15%。"),
        ],
        tools=[SimpleNamespace(name="personal_ip_record_strategy")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    compact_ready = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "personal_ip_narrative_turn",
                "args": {
                    "reflection": "目标人群、可重复结果和证明范围已经足以形成第一轮候选。",
                    "question": "",
                    "status": "ready",
                    "reason": "继续泛问的边际信息价值已经很低。",
                },
                "id": "narrative-ready",
                "type": "tool_call",
            }
        ],
    )
    expected = AIMessage(content="我先给出两个方向假设和一个验证选题。")
    handler = Mock(side_effect=[compact_ready, expected])

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert result is expected
    assert handler.call_count == 2
    transition_request = handler.call_args_list[1].args[0]
    assert transition_request.system_message.content == request.system_message.content
    assert any(isinstance(message, SystemMessage) and "Do not ask another broad intake question" in message.content for message in transition_request.messages)
    assert [tool.name for tool in transition_request.tools] == ["personal_ip_record_strategy"]


def test_new_owner_can_interrupt_the_interview_with_a_concrete_request():
    request = ModelRequest(
        model=object(),
        system_message=SystemMessage(content="full operating prompt"),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            AIMessage(
                content="如果把你的经历分成几章，你会怎么命名？",
                additional_kwargs={
                    "personal_ip_narrative_interview": {
                        "version": 1,
                        "status": "active",
                        "turn": 0,
                        "entity_type": "person",
                    }
                },
            ),
            HumanMessage(content="先别问了，直接给方案。"),
        ],
        tools=[SimpleNamespace(name="personal_ip_record_strategy")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    expected = AIMessage(content="这里是两个暂定方向。")
    handler = Mock(return_value=expected)

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert result is expected
    handler.assert_called_once()
    full_request = handler.call_args.args[0]
    assert full_request.system_message.content == "full operating prompt"
    assert [tool.name for tool in full_request.tools] == ["personal_ip_record_strategy"]


def test_narrative_stop_is_normal_text_and_deactivates_the_interview():
    request = ModelRequest(
        model=object(),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            AIMessage(
                content="如果把你的经历分成几章，你会怎么命名？",
                additional_kwargs={
                    "personal_ip_narrative_interview": {
                        "version": 1,
                        "status": "active",
                        "turn": 0,
                        "entity_type": "person",
                    }
                },
            ),
            HumanMessage(content="我不想继续聊了。"),
        ],
        tools=[],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    handler = Mock(
        return_value=ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "personal_ip_narrative_turn",
                            "args": {
                                "reflection": "你已经明确说不想继续，这个边界不需要解释。",
                                "question": "",
                                "status": "stop",
                                "reason": "用户撤回访谈授权。",
                                "control_note": "",
                            },
                            "id": "narrative-stop",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        )
    )

    result = PersonalIPContextMiddleware().wrap_model_call(request, handler)

    assert isinstance(result, ModelResponse)
    stopped = result.result[-1]
    assert isinstance(stopped, AIMessage)
    assert stopped.tool_calls == []
    assert "停在这里" in stopped.content
    assert stopped.additional_kwargs["personal_ip_narrative_interview"]["status"] == "stopped"


@pytest.mark.parametrize(
    ("request_text", "expected_question"),
    [
        ("我是第一次使用，想从零做个人 IP。", "经历分成几章"),
        ("第一次做一个产品 IP，这个产品刚有第一版。", "最初是被什么真实问题逼出来的"),
        (
            "我们是一个公益组织，第一次做机构 IP，应该从哪里开始？",
            "为什么聚在一起",
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
    assert expected_question in result.content
    assert result.tool_calls == []


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
    assert result.tool_calls == []
    assert "chapters" in result.content
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_new_owner_first_answer_uses_the_same_bounded_interviewer():
    request = ModelRequest(
        model=object(),
        system_message=SystemMessage(content="full operating prompt"),
        messages=[
            HumanMessage(content="我是第一次使用，想从零做个人 IP。"),
            AIMessage(
                content="如果把你的经历分成几章，你会怎么命名？",
                additional_kwargs={
                    "personal_ip_narrative_interview": {
                        "version": 1,
                        "status": "active",
                        "turn": 0,
                        "entity_type": "person",
                    }
                },
            ),
            HumanMessage(content="我做了十年护士，夜班时最常帮家属理解医生没有时间解释的事。"),
        ],
        tools=[SimpleNamespace(name="browser_navigate")],
        state={"messages": []},
        runtime=SimpleNamespace(
            context={
                "agent_name": "ip-agent",
                "personal_ip_portfolio": {"subjects": [], "accounts": []},
            }
        ),
    )
    handler = AsyncMock(
        return_value=AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "personal_ip_narrative_turn",
                    "args": {
                        "reflection": "你反复承担的不是抽象的护理知识输出，而是把家属听不懂的信息解释清楚。",
                        "question": "哪一次解释最能证明这种能力后来真正改变了家属的一个决定？",
                        "status": "continue",
                        "reason": "需要一项可观察的影响结果。",
                        "control_note": "",
                    },
                    "id": "narrative-async",
                    "type": "tool_call",
                }
            ],
        )
    )

    result = await PersonalIPContextMiddleware().awrap_model_call(request, handler)

    assert isinstance(result, AIMessage)
    assert "家属听不懂" in result.content
    assert result.content.count("？") == 1
    compact_request = handler.await_args.args[0]
    assert [tool["function"]["name"] for tool in compact_request.tools] == ["personal_ip_narrative_turn"]
    assert "browser_navigate" not in str(compact_request.tools)


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
