from __future__ import annotations

from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from deerflow.agents.middlewares.dangling_tool_call_middleware import DanglingToolCallMiddleware
from deerflow.agents.middlewares.terminal_response_middleware import TerminalResponseMiddleware
from deerflow.agents.middlewares.todo_middleware import TodoMiddleware
from deerflow.runtime.context_keys import TERMINAL_RESPONSE_FAILURE_KEY, terminal_response_failure_payload
from deerflow.runtime.runs.worker import _extract_llm_error_fallback_message


@tool
def lookup_status() -> str:
    """Return a deterministic tool result."""
    _LOOKUP_EXECUTIONS.append("lookup_status")
    return "tool completed"


_LOOKUP_EXECUTIONS: list[str] = []
_IP_CONTENT_WRITE_EXECUTIONS: list[dict[str, Any]] = []


@tool
def ip_content_write(request: dict[str, Any]) -> str:
    """Persist one deterministic content request for middleware tests."""
    _IP_CONTENT_WRITE_EXECUTIONS.append(request)
    return "saved"


_PRIVATE_ARGUMENT_FRAGMENT = "OWNER_SECRET=fruit-owner-private-demand"
_PRIVATE_PROVIDER_ERROR = "Authorization: Bearer provider-secret; raw_body=/private/provider/request"


def _malformed_ip_content_write(*, visible_preamble: bool = False) -> AIMessage:
    return AIMessage(
        content="I will save the script now." if visible_preamble else "",
        invalid_tool_calls=[
            {
                "type": "invalid_tool_call",
                "id": "ip-write-malformed-1",
                "name": "ip_content_write",
                "args": '{"request":{"route_kind":"offer","owner_note":"' + _PRIVATE_ARGUMENT_FRAGMENT,
                "error": _PRIVATE_PROVIDER_ERROR,
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )


class _InvalidToolCallRepairModel(BaseChatModel):
    fail_repair: bool = False
    repair_kind: str = "valid"
    initial_tool_name: str | None = "ip_content_write"
    visible_preamble: bool = False
    call_count: int = 0
    observed_messages: list[list[Any]] = []

    @property
    def _llm_type(self) -> str:
        return "invalid-tool-call-repair"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.observed_messages.append(list(messages))
        self.call_count += 1
        if self.call_count == 1 or self.fail_repair or self.repair_kind == "invalid":
            message = _malformed_ip_content_write(visible_preamble=self.visible_preamble)
            message.invalid_tool_calls[0]["name"] = self.initial_tool_name
        elif self.call_count == 2:
            valid_call = {
                "id": "ip-write-valid-1",
                "name": "ip_content_write",
                "args": {"request": {"route_kind": "offer", "script": "complete"}},
            }
            if self.repair_kind == "no_call":
                message = AIMessage(content="The script was saved.")
            elif self.repair_kind == "provider_fallback":
                message = AIMessage(
                    content="Safe authentication failure.",
                    additional_kwargs={
                        "deerflow_error_fallback": True,
                        "error_type": "ProviderAuthError",
                        "error_reason": "auth",
                    },
                )
            elif self.repair_kind == "wrong_tool":
                message = AIMessage(content="", tool_calls=[{"id": "wrong-1", "name": "lookup_status", "args": {}}])
            elif self.repair_kind == "duplicate":
                message = AIMessage(
                    content="",
                    tool_calls=[
                        valid_call,
                        {
                            **valid_call,
                            "id": "ip-write-valid-2",
                        },
                    ],
                )
            elif self.repair_kind == "mixed":
                message = AIMessage(
                    content="",
                    tool_calls=[valid_call],
                    invalid_tool_calls=_malformed_ip_content_write().invalid_tool_calls,
                    response_metadata={"finish_reason": "tool_calls"},
                )
            else:
                message = AIMessage(
                    content="",
                    tool_calls=[valid_call],
                    response_metadata={"finish_reason": "tool_calls"},
                )
        else:
            message = AIMessage(content="The complete script was saved.", response_metadata={"finish_reason": "stop"})
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class _MixedValidAndInvalidToolCallModel(BaseChatModel):
    call_count: int = 0

    @property
    def _llm_type(self) -> str:
        return "mixed-valid-invalid-tool-call"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.call_count += 1
        if self.call_count == 1:
            malformed = _malformed_ip_content_write().invalid_tool_calls[0]
            message = AIMessage(
                content="I will check status and save.",
                tool_calls=[{"id": "valid-status-1", "name": "lookup_status", "args": {}}],
                invalid_tool_calls=[malformed],
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "ip-write-malformed-1",
                            "type": "function",
                            "function": {
                                "name": "ip_content_write",
                                "arguments": malformed["args"],
                            },
                        }
                    ]
                },
                response_metadata={"finish_reason": "tool_calls"},
            )
        else:
            message = AIMessage(content="Status checked; save was not claimed.")
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _invalid_tool_recovery_agent(model: BaseChatModel):
    # Production order: dangling-call request normalization wraps the later
    # terminal-response state machine. The invalid response must be removed by
    # TerminalResponseMiddleware before either routing or the next model request.
    return create_agent(
        model=model,
        tools=[ip_content_write],
        middleware=[DanglingToolCallMiddleware(), TerminalResponseMiddleware()],
    )


def _invalid_tool_recovery_plan_agent(model: BaseChatModel):
    return create_agent(
        model=model,
        tools=[ip_content_write],
        middleware=[
            DanglingToolCallMiddleware(),
            TodoMiddleware(),
            TerminalResponseMiddleware(),
        ],
    )


class _PostToolResponseModel(BaseChatModel):
    responses: list[str]
    call_count: int = 0
    observed_messages: list[list[Any]] = []

    @property
    def _llm_type(self) -> str:
        return "post-tool-response"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.observed_messages.append(list(messages))
        self.call_count += 1
        if self.call_count == 1:
            message = AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "lookup_status", "args": {}}],
                response_metadata={"finish_reason": "tool_calls"},
            )
        else:
            message = AIMessage(
                content=self.responses[self.call_count - 2],
                response_metadata={"finish_reason": "stop"},
            )
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


class _PerRunRetryBudgetModel(BaseChatModel):
    call_count: int = 0
    observed_messages: list[list[Any]] = []

    @property
    def _llm_type(self) -> str:
        return "per-run-retry-budget"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.observed_messages.append(list(messages))
        self.call_count += 1
        if self.call_count == 1:
            message = AIMessage(
                content="",
                tool_calls=[{"id": "call-budget-1", "name": "lookup_status", "args": {}}],
                response_metadata={"finish_reason": "tool_calls"},
            )
        elif self.call_count == 2:
            message = AIMessage(content="", response_metadata={"finish_reason": "stop"})
        elif self.call_count == 3:
            message = AIMessage(
                content="I need one more status check.",
                tool_calls=[{"id": "call-budget-2", "name": "lookup_status", "args": {}}],
                response_metadata={"finish_reason": "tool_calls"},
            )
        else:
            message = AIMessage(content="", response_metadata={"finish_reason": "stop"})
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _agent(model: BaseChatModel):
    return create_agent(
        model=model,
        tools=[lookup_status],
        middleware=[TerminalResponseMiddleware()],
    )


def _empty_terminal_messages(messages: list[Any]) -> list[AIMessage]:
    return [message for message in messages if isinstance(message, AIMessage) and not message.tool_calls and not message.invalid_tool_calls and not str(message.content).strip()]


@pytest.mark.parametrize("visible_preamble", [False, True])
def test_invalid_ip_content_write_is_removed_and_retried_once_without_leaking_or_fake_execution(visible_preamble):
    _IP_CONTENT_WRITE_EXECUTIONS.clear()
    model = _InvalidToolCallRepairModel(visible_preamble=visible_preamble)

    result = _invalid_tool_recovery_agent(model).invoke(
        {"messages": [HumanMessage(content="Create and save the complete fruit offer script")]},
        context={"thread_id": "thread-invalid-repair", "run_id": f"run-invalid-repair-{visible_preamble}"},
    )

    assert model.call_count == 3
    assert _IP_CONTENT_WRITE_EXECUTIONS == [{"route_kind": "offer", "script": "complete"}]
    retry_messages = model.observed_messages[1]
    repair_prompts = [message for message in retry_messages if isinstance(message, HumanMessage) and message.name == "invalid_tool_call_recovery"]
    assert len(repair_prompts) == 1
    repair_prompt = str(repair_prompts[0].content)
    assert "ip_content_write" in repair_prompt
    assert "complete" in repair_prompt.lower()
    assert "was not executed" in repair_prompt.lower()
    assert _PRIVATE_ARGUMENT_FRAGMENT not in repair_prompt
    assert _PRIVATE_PROVIDER_ERROR not in repair_prompt
    assert "Bearer" not in repair_prompt
    assert not any(isinstance(message, ToolMessage) for message in retry_messages)
    assert not any(isinstance(message, AIMessage) and message.invalid_tool_calls for message in retry_messages)

    final = result["messages"][-1]
    assert isinstance(final, AIMessage)
    assert final.content == "The complete script was saved."
    assert not any(isinstance(message, ToolMessage) and message.tool_call_id == "ip-write-malformed-1" for message in result["messages"])
    assert not any(isinstance(message, HumanMessage) and message.name == "invalid_tool_call_recovery" for message in result["messages"])


def test_second_invalid_tool_call_becomes_closed_safe_error_fallback_without_execution():
    _IP_CONTENT_WRITE_EXECUTIONS.clear()
    model = _InvalidToolCallRepairModel(fail_repair=True)

    result = _invalid_tool_recovery_agent(model).invoke(
        {"messages": [HumanMessage(content="Create and save the complete fruit offer script")]},
        context={"thread_id": "thread-invalid-failure", "run_id": "run-invalid-failure"},
    )

    assert model.call_count == 2
    assert _IP_CONTENT_WRITE_EXECUTIONS == []
    final = result["messages"][-1]
    assert isinstance(final, AIMessage)
    assert final.invalid_tool_calls == []
    assert final.tool_calls == []
    assert final.additional_kwargs == {
        "deerflow_error_fallback": True,
        "error_type": "InvalidToolCallResponse",
        "error_reason": "invalid_tool_call",
    }
    assert _extract_llm_error_fallback_message(result) == str(final.content)
    serialized = final.model_dump_json()
    assert _PRIVATE_ARGUMENT_FRAGMENT not in serialized
    assert _PRIVATE_PROVIDER_ERROR not in serialized
    assert "Bearer" not in serialized


@pytest.mark.parametrize("repair_kind", ["no_call", "wrong_tool", "duplicate", "mixed"])
def test_invalid_tool_repair_rejects_non_exact_response_before_any_tool_execution(repair_kind):
    _IP_CONTENT_WRITE_EXECUTIONS.clear()
    _LOOKUP_EXECUTIONS.clear()
    model = _InvalidToolCallRepairModel(repair_kind=repair_kind)

    result = _invalid_tool_recovery_agent(model).invoke(
        {"messages": [HumanMessage(content="Create and save the complete fruit offer script")]},
        context={"thread_id": "thread-invalid-exact", "run_id": f"run-invalid-exact-{repair_kind}"},
    )

    assert model.call_count == 2
    assert _IP_CONTENT_WRITE_EXECUTIONS == []
    assert _LOOKUP_EXECUTIONS == []
    final = result["messages"][-1]
    assert final.additional_kwargs == {
        "deerflow_error_fallback": True,
        "error_type": "InvalidToolCallResponse",
        "error_reason": "invalid_tool_call",
    }


@pytest.mark.parametrize("initial_tool_name", [None, "unavailable_tool"])
def test_invalid_tool_repair_rejects_unvalidated_target_name_before_any_execution(initial_tool_name):
    _IP_CONTENT_WRITE_EXECUTIONS.clear()
    model = _InvalidToolCallRepairModel(initial_tool_name=initial_tool_name)

    result = _invalid_tool_recovery_agent(model).invoke(
        {"messages": [HumanMessage(content="Create and save the complete fruit offer script")]},
        context={"thread_id": "thread-invalid-name", "run_id": f"run-invalid-name-{initial_tool_name}"},
    )

    assert model.call_count == 1
    assert _IP_CONTENT_WRITE_EXECUTIONS == []
    assert result["messages"][-1].additional_kwargs["error_reason"] == "invalid_tool_call"


def test_provider_fallback_during_repair_preserves_reason_and_stops_todo_continuation():
    _IP_CONTENT_WRITE_EXECUTIONS.clear()
    model = _InvalidToolCallRepairModel(repair_kind="provider_fallback")

    result = _invalid_tool_recovery_plan_agent(model).invoke(
        {
            "messages": [HumanMessage(content="Create and save the complete fruit offer script")],
            "todos": [{"content": "Save the script", "status": "in_progress"}],
        },
        context={"thread_id": "thread-repair-auth", "run_id": "run-repair-auth"},
    )

    assert model.call_count == 2
    assert _IP_CONTENT_WRITE_EXECUTIONS == []
    final = result["messages"][-1]
    assert final.additional_kwargs["deerflow_error_fallback"] is True
    assert final.additional_kwargs["error_reason"] == "auth"
    assert not any(isinstance(message, HumanMessage) and message.name == "todo_completion_reminder" for request_messages in model.observed_messages for message in request_messages)


def test_second_invalid_tool_call_ends_plan_mode_without_todo_continuation_or_execution():
    _IP_CONTENT_WRITE_EXECUTIONS.clear()
    model = _InvalidToolCallRepairModel(fail_repair=True)

    result = _invalid_tool_recovery_plan_agent(model).invoke(
        {
            "messages": [HumanMessage(content="Create and save the complete fruit offer script")],
            "todos": [{"content": "Save the script", "status": "in_progress"}],
        },
        context={"thread_id": "thread-invalid-plan", "run_id": "run-invalid-plan"},
    )

    assert model.call_count == 2
    assert _IP_CONTENT_WRITE_EXECUTIONS == []
    assert result["messages"][-1].additional_kwargs["deerflow_error_fallback"] is True
    assert not any(isinstance(message, HumanMessage) and message.name == "todo_completion_reminder" for request_messages in model.observed_messages for message in request_messages)


def test_second_invalid_tool_call_sets_closed_run_terminal_signal():
    middleware = TerminalResponseMiddleware()
    context = {"thread_id": "thread-signal", "run_id": "run-signal"}
    runtime = type("RuntimeStub", (), {"context": context})()
    first = _malformed_ip_content_write().model_copy(update={"id": "invalid-first"})
    second = _malformed_ip_content_write().model_copy(update={"id": "invalid-second"})

    first_result = middleware.after_model(
        {"messages": [HumanMessage(content="Save it"), first]},
        runtime,
    )
    assert first_result is not None and first_result["jump_to"] == "model"
    result = middleware.after_model(
        {"messages": [HumanMessage(content="Save it"), second]},
        runtime,
    )

    assert result is not None and result["jump_to"] == "end"
    assert context[TERMINAL_RESPONSE_FAILURE_KEY] == terminal_response_failure_payload("invalid_tool_call")
    serialized = repr(context[TERMINAL_RESPONSE_FAILURE_KEY])
    assert _PRIVATE_ARGUMENT_FRAGMENT not in serialized
    assert _PRIVATE_PROVIDER_ERROR not in serialized


def test_existing_server_fallback_ends_and_sets_closed_reason_without_trusting_content_or_type():
    middleware = TerminalResponseMiddleware()
    context = {"thread_id": "thread-provider-fallback", "run_id": "run-provider-fallback"}
    runtime = type("RuntimeStub", (), {"context": context})()
    fallback = AIMessage(
        content="untrusted provider-facing text",
        additional_kwargs={
            "deerflow_error_fallback": True,
            "error_type": "RawProviderSecretType",
            "error_reason": "auth",
        },
    )

    result = middleware.after_model(
        {"messages": [HumanMessage(content="Hello"), fallback]},
        runtime,
    )

    assert result == {"jump_to": "end"}
    assert context[TERMINAL_RESPONSE_FAILURE_KEY] == terminal_response_failure_payload("auth")
    assert "untrusted provider-facing text" not in repr(context[TERMINAL_RESPONSE_FAILURE_KEY])
    assert "RawProviderSecretType" not in repr(context[TERMINAL_RESPONSE_FAILURE_KEY])


def test_retries_empty_post_tool_response_once_and_returns_model_answer():
    model = _PostToolResponseModel(responses=["", "The tool completed successfully."])

    result = _agent(model).invoke(
        {"messages": [HumanMessage(content="Check the status")]},
        context={"thread_id": "thread-1", "run_id": "run-1"},
    )

    assert model.call_count == 3
    final = result["messages"][-1]
    assert isinstance(final, AIMessage)
    assert final.content == "The tool completed successfully."
    assert _empty_terminal_messages(result["messages"]) == []
    assert any(isinstance(message, HumanMessage) and message.name == "terminal_response_recovery" and message.additional_kwargs.get("hide_from_ui") is True for message in model.observed_messages[-1])
    assert not any(isinstance(message, HumanMessage) and message.name == "terminal_response_recovery" for message in result["messages"])


def test_second_empty_post_tool_response_becomes_visible_error_fallback():
    model = _PostToolResponseModel(responses=["", ""])

    result = _agent(model).invoke(
        {"messages": [HumanMessage(content="Check the status")]},
        context={"thread_id": "thread-2", "run_id": "run-2"},
    )

    assert model.call_count == 3
    final = result["messages"][-1]
    assert isinstance(final, AIMessage)
    assert "returned no final response" in str(final.content)
    assert final.additional_kwargs["deerflow_error_fallback"] is True
    assert _empty_terminal_messages(result["messages"]) == []
    assert final.additional_kwargs == {
        "deerflow_error_fallback": True,
        "error_type": "EmptyTerminalResponse",
        "error_reason": "empty_terminal_response",
    }
    assert _extract_llm_error_fallback_message(result) == str(final.content)


@pytest.mark.asyncio
async def test_async_graph_retries_empty_post_tool_response_once():
    model = _PostToolResponseModel(responses=["", "Recovered asynchronously."])

    result = await _agent(model).ainvoke(
        {"messages": [HumanMessage(content="Check the status")]},
        context={"thread_id": "thread-async", "run_id": "run-async"},
    )

    assert model.call_count == 3
    assert result["messages"][-1].content == "Recovered asynchronously."
    assert _empty_terminal_messages(result["messages"]) == []


def test_graph_with_thread_id_only_keeps_recovery_state_across_model_loop():
    model = _PostToolResponseModel(responses=["", "Recovered without a run id."])

    result = _agent(model).invoke(
        {"messages": [HumanMessage(content="Check the status")]},
        context={"thread_id": "thread-only"},
    )

    assert model.call_count == 3
    assert result["messages"][-1].content == "Recovered without a run id."
    assert _empty_terminal_messages(result["messages"]) == []


def test_recovery_budget_is_once_per_run_even_when_retry_calls_another_tool():
    model = _PerRunRetryBudgetModel()

    result = _agent(model).invoke(
        {"messages": [HumanMessage(content="Check the status twice")]},
        context={"thread_id": "thread-budget", "run_id": "run-budget"},
    )

    assert model.call_count == 4
    final = result["messages"][-1]
    assert final.additional_kwargs["deerflow_error_fallback"] is True
    assert _empty_terminal_messages(result["messages"]) == []
    recovery_prompt_count = sum(1 for request_messages in model.observed_messages for message in request_messages if isinstance(message, HumanMessage) and message.name == "terminal_response_recovery")
    assert recovery_prompt_count == 1


def test_empty_response_without_tool_result_is_not_retried():
    middleware = TerminalResponseMiddleware()
    message = AIMessage(content="", response_metadata={"finish_reason": "stop"})
    state = {"messages": [HumanMessage(content="Hello"), message]}
    runtime = type("RuntimeStub", (), {"context": {"thread_id": "thread-3", "run_id": "run-3"}})()

    assert middleware.after_model(state, runtime) is None


def test_tool_call_intent_is_not_treated_as_empty_terminal_response():
    middleware = TerminalResponseMiddleware()
    message = AIMessage(
        content="",
        tool_calls=[{"id": "call-2", "name": "lookup_status", "args": {}}],
        response_metadata={"finish_reason": "tool_calls"},
    )
    state = {"messages": [HumanMessage(content="Hello"), message]}
    runtime = type("RuntimeStub", (), {"context": {"thread_id": "thread-4", "run_id": "run-4"}})()

    assert middleware.after_model(state, runtime) is None


def test_mixed_valid_and_invalid_tool_calls_keep_existing_tool_routing_semantics():
    middleware = TerminalResponseMiddleware()
    message = AIMessage(
        content="I will run the valid call.",
        tool_calls=[{"id": "call-valid", "name": "lookup_status", "args": {}}],
        invalid_tool_calls=[
            {
                "id": "call-invalid",
                "name": "ip_content_write",
                "args": "{",
                "error": _PRIVATE_PROVIDER_ERROR,
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )
    state = {"messages": [HumanMessage(content="Hello"), message]}
    runtime = type("RuntimeStub", (), {"context": {"thread_id": "thread-mixed", "run_id": "run-mixed"}})()

    result = middleware.after_model(state, runtime)

    assert result is not None and "jump_to" not in result
    sanitized = result["messages"][0]
    assert sanitized.tool_calls == message.tool_calls
    assert sanitized.invalid_tool_calls == []
    assert "tool_calls" not in sanitized.additional_kwargs
    assert _PRIVATE_PROVIDER_ERROR not in sanitized.model_dump_json()


def test_mixed_valid_and_invalid_call_executes_valid_once_and_checkpoint_drops_invalid_secrets():
    _LOOKUP_EXECUTIONS.clear()
    _IP_CONTENT_WRITE_EXECUTIONS.clear()
    model = _MixedValidAndInvalidToolCallModel()
    checkpointer = InMemorySaver()
    agent = create_agent(
        model=model,
        tools=[lookup_status, ip_content_write],
        middleware=[DanglingToolCallMiddleware(), TerminalResponseMiddleware()],
        checkpointer=checkpointer,
    )
    config = {"configurable": {"thread_id": "mixed-checkpoint-thread"}}

    result = agent.invoke(
        {"messages": [HumanMessage(content="Check status and save")]},
        config=config,
        context={"thread_id": "mixed-checkpoint-thread", "run_id": "mixed-checkpoint-run"},
    )
    snapshot = agent.get_state(config)
    history = list(agent.get_state_history(config))

    assert model.call_count == 2
    assert _LOOKUP_EXECUTIONS == ["lookup_status"]
    assert _IP_CONTENT_WRITE_EXECUTIONS == []
    tool_results = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [message.tool_call_id for message in tool_results] == ["valid-status-1"]
    checkpoint_text = repr(snapshot.values["messages"])
    assert "invalid_tool_arguments" not in checkpoint_text
    assert "ip-write-malformed-1" not in checkpoint_text
    for forbidden in (_PRIVATE_ARGUMENT_FRAGMENT, _PRIVATE_PROVIDER_ERROR, "Bearer", "raw_body"):
        assert forbidden not in checkpoint_text
        assert all(forbidden not in repr(item.values.get("messages", [])) for item in history)


@pytest.mark.parametrize(
    "message",
    [
        AIMessage(content="", additional_kwargs={"function_call": {"name": "lookup_status", "arguments": "{}"}}),
        AIMessage(content="", response_metadata={"finish_reason": "function_call"}),
    ],
)
def test_legacy_tool_call_intent_is_not_treated_as_empty_terminal_response(message):
    middleware = TerminalResponseMiddleware()
    state = {"messages": [HumanMessage(content="Hello"), message]}
    runtime = type("RuntimeStub", (), {"context": {"thread_id": "thread-5", "run_id": "run-5"}})()

    assert middleware.after_model(state, runtime) is None


def test_after_agent_clears_retry_state_for_the_run():
    middleware = TerminalResponseMiddleware()
    runtime = type("RuntimeStub", (), {"context": {"thread_id": "thread-6", "run_id": "run-6"}})()
    empty_after_tool = {
        "messages": [
            HumanMessage(content="Check the status"),
            ToolMessage(content="tool completed", tool_call_id="call-6"),
            AIMessage(content="", response_metadata={"finish_reason": "stop"}),
        ]
    }

    first = middleware.after_model(empty_after_tool, runtime)
    assert first is not None and first["jump_to"] == "model"
    middleware.after_agent(empty_after_tool, runtime)
    second = middleware.after_model(empty_after_tool, runtime)
    assert second is not None and second["jump_to"] == "model"


def test_before_agent_clears_same_run_state_for_resumed_invocation():
    middleware = TerminalResponseMiddleware()
    runtime = type("RuntimeStub", (), {"context": {"thread_id": "thread-7", "run_id": "run-7"}})()
    empty_after_tool = {
        "messages": [
            HumanMessage(content="Check the status"),
            ToolMessage(content="tool completed", tool_call_id="call-7"),
            AIMessage(content="", response_metadata={"finish_reason": "stop"}),
        ]
    }

    first = middleware.after_model(empty_after_tool, runtime)
    assert first is not None and first["jump_to"] == "model"
    middleware.before_agent(empty_after_tool, runtime)
    resumed = middleware.after_model(empty_after_tool, runtime)
    assert resumed is not None and resumed["jump_to"] == "model"


def test_tool_history_without_real_user_message_does_not_trigger_recovery():
    middleware = TerminalResponseMiddleware()
    runtime = type("RuntimeStub", (), {"context": {"thread_id": "thread-8", "run_id": "run-8"}})()
    state = {
        "messages": [
            HumanMessage(content="internal", additional_kwargs={"hide_from_ui": True}),
            ToolMessage(content="tool completed", tool_call_id="call-8"),
            AIMessage(content="", response_metadata={"finish_reason": "stop"}),
        ]
    }

    assert middleware.after_model(state, runtime) is None


def test_abandoned_run_state_is_bounded():
    middleware = TerminalResponseMiddleware()

    for index in range(1001):
        key = (f"thread-{index}", f"run-{index}")
        middleware._retry_counts[key] = 1
        middleware._pending_prompts[key] = True
        middleware._invalid_retry_counts[key] = 1
        middleware._pending_invalid_tool_names[key] = "ip_content_write"
        middleware._expected_repair_tool_names[key] = "ip_content_write"
        middleware._unavailable_repair_targets[key] = True

    bounded_maps = (
        middleware._retry_counts,
        middleware._pending_prompts,
        middleware._invalid_retry_counts,
        middleware._pending_invalid_tool_names,
        middleware._expected_repair_tool_names,
        middleware._unavailable_repair_targets,
    )
    assert all(len(state) == 1000 for state in bounded_maps)
    assert all(("thread-0", "run-0") not in state for state in bounded_maps)
