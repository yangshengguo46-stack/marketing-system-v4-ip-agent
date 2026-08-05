"""Ensure tool-using lead-agent turns end with a visible assistant response."""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ExtendedModelResponse, ModelCallResult, ModelRequest, ModelResponse, hook_config
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.runtime import Runtime

from deerflow.agents.middlewares._bounded_dict import BoundedDict
from deerflow.runtime.context_keys import (
    TERMINAL_RESPONSE_FAILURE_KEY,
    TERMINAL_RESPONSE_FAILURES,
    terminal_response_failure_payload,
)
from deerflow.utils.tool_call_safety import sanitize_invalid_tool_calls

_RECOVERY_PROMPT = (
    "<system_reminder>\n"
    "Your previous response after the tool execution was empty. Review the tool results "
    "already present in the conversation and provide a concise, user-visible final response. "
    "Do not call another tool unless it is strictly necessary.\n"
    "</system_reminder>"
)

_FALLBACK_CONTENT = "The model completed the tool run but returned no final response, including after one automatic retry. Please try again or use a different model."

_INVALID_TOOL_FALLBACK_CONTENT = terminal_response_failure_payload("invalid_tool_call")["message"]

_EMPTY_TERMINAL_FAILURE = terminal_response_failure_payload("empty_terminal_response")
_INVALID_TOOL_FAILURE = terminal_response_failure_payload("invalid_tool_call")

_TOOL_CALL_FINISH_REASONS = {"tool_calls", "function_call"}


def _has_visible_content(message: AIMessage) -> bool:
    """Return whether an AI message contains user-visible text."""
    content = message.content
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str) and block.strip():
                return True
            if isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    return True
    return False


def _has_tool_call_intent_or_error(message: AIMessage) -> bool:
    """Keep tool routing and malformed tool-call handling out of this guard."""
    if message.tool_calls or getattr(message, "invalid_tool_calls", None):
        return True
    additional_kwargs = message.additional_kwargs or {}
    if additional_kwargs.get("tool_calls") or additional_kwargs.get("function_call"):
        return True
    response_metadata = message.response_metadata or {}
    return response_metadata.get("finish_reason") in _TOOL_CALL_FINISH_REASONS


def _tool_result_in_current_turn(messages: list[Any]) -> bool:
    """Return whether a tool result follows the latest real user message."""
    latest_user_index = -1
    for index, message in enumerate(messages):
        if not isinstance(message, HumanMessage):
            continue
        if (message.additional_kwargs or {}).get("hide_from_ui"):
            continue
        latest_user_index = index
    # Scope: #4027 covers interactive post-tool turns. Scheduled/internal
    # invocations without a real HumanMessage need a separate terminal-success
    # invariant rather than being inferred from arbitrary historical tools.
    if latest_user_index == -1:
        return False
    return any(isinstance(message, ToolMessage) for message in messages[latest_user_index + 1 :])


class TerminalResponseMiddleware(AgentMiddleware[AgentState]):
    """Repair one malformed tool call or empty post-tool response per run."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._retry_counts: BoundedDict[tuple[str, str], int] = BoundedDict(1000)
        self._pending_prompts: BoundedDict[tuple[str, str], bool] = BoundedDict(1000)
        self._invalid_retry_counts: BoundedDict[tuple[str, str], int] = BoundedDict(1000)
        self._pending_invalid_tool_names: BoundedDict[tuple[str, str], str] = BoundedDict(1000)
        self._expected_repair_tool_names: BoundedDict[tuple[str, str], str] = BoundedDict(1000)
        self._unavailable_repair_targets: BoundedDict[tuple[str, str], bool] = BoundedDict(1000)

    @staticmethod
    def _key(runtime: Runtime) -> tuple[str, str]:
        context = getattr(runtime, "context", None)
        if isinstance(context, dict):
            thread_id = str(context.get("thread_id") or "unknown-thread")
            run_id = str(context.get("run_id") or context.get("run_attempt_id") or id(runtime))
            return thread_id, run_id
        # Defensive fallback for tests/custom embeddings. Production Gateway
        # runs always provide thread_id and run_id in Runtime.context.
        return "unknown-thread", str(id(runtime))

    def _clear(self, runtime: Runtime) -> None:
        key = self._key(runtime)
        with self._lock:
            self._retry_counts.pop(key, None)
            self._pending_prompts.pop(key, None)
            self._invalid_retry_counts.pop(key, None)
            self._pending_invalid_tool_names.pop(key, None)
            self._expected_repair_tool_names.pop(key, None)
            self._unavailable_repair_targets.pop(key, None)

    def _clear_other_runs(self, runtime: Runtime) -> None:
        thread_id, run_id = self._key(runtime)
        with self._lock:
            known_keys = set(self._retry_counts) | set(self._invalid_retry_counts) | set(self._expected_repair_tool_names) | set(self._unavailable_repair_targets)
            stale = [key for key in known_keys if key[0] == thread_id and key[1] != run_id]
            for key in stale:
                self._retry_counts.pop(key, None)
                self._pending_prompts.pop(key, None)
                self._invalid_retry_counts.pop(key, None)
                self._pending_invalid_tool_names.pop(key, None)
                self._expected_repair_tool_names.pop(key, None)
                self._unavailable_repair_targets.pop(key, None)

    @staticmethod
    def _clear_failure_signal(runtime: Runtime) -> None:
        context = getattr(runtime, "context", None)
        if isinstance(context, dict):
            context.pop(TERMINAL_RESPONSE_FAILURE_KEY, None)

    @staticmethod
    def _signal_failure(runtime: Runtime, failure: dict[str, str]) -> None:
        context = getattr(runtime, "context", None)
        if isinstance(context, dict):
            # Fixed, locally-owned fields only. Raw model arguments and provider
            # parse errors never enter the run-scoped terminal signal.
            context[TERMINAL_RESPONSE_FAILURE_KEY] = dict(failure)
            journal = context.get("__run_journal")
            marker = getattr(journal, "mark_terminal_response_failure", None)
            if callable(marker):
                marker(failure["error_reason"])

    @staticmethod
    def _invalid_tool_name(message: AIMessage) -> str:
        names = {call.get("name").strip() for call in (getattr(message, "invalid_tool_calls", None) or []) if isinstance(call, dict) and isinstance(call.get("name"), str) and call.get("name").strip()}
        return next(iter(names)) if len(names) == 1 else ""

    @staticmethod
    def _invalid_tool_fallback(message: AIMessage) -> AIMessage:
        return message.model_copy(
            update={
                "content": _INVALID_TOOL_FALLBACK_CONTENT,
                "tool_calls": [],
                "invalid_tool_calls": [],
                "additional_kwargs": {
                    "deerflow_error_fallback": True,
                    "error_type": "InvalidToolCallResponse",
                    "error_reason": "invalid_tool_call",
                },
                "response_metadata": {"finish_reason": "stop"},
            }
        )

    @staticmethod
    def _sanitize_mixed_invalid_tool_call(message: AIMessage) -> AIMessage:
        additional_kwargs = dict(message.additional_kwargs or {})
        additional_kwargs.pop("tool_calls", None)
        additional_kwargs.pop("function_call", None)
        return message.model_copy(
            update={
                "invalid_tool_calls": [],
                "additional_kwargs": additional_kwargs,
            }
        )

    @staticmethod
    def _sanitize_model_ai_message(message: AIMessage) -> AIMessage:
        invalid_tool_calls = getattr(message, "invalid_tool_calls", None) or []
        if not invalid_tool_calls:
            return message
        projected = sanitize_invalid_tool_calls({"invalid_tool_calls": invalid_tool_calls})["invalid_tool_calls"]
        safe_invalid_tool_calls = [
            {
                "type": "invalid_tool_call",
                "id": call["id"],
                "name": call["name"],
                "args": "{}",
                "error": "invalid_tool_arguments",
            }
            for call in projected
        ]
        additional_kwargs = dict(message.additional_kwargs or {})
        additional_kwargs.pop("tool_calls", None)
        additional_kwargs.pop("function_call", None)
        return message.model_copy(
            update={
                "invalid_tool_calls": safe_invalid_tool_calls,
                "additional_kwargs": additional_kwargs,
            }
        )

    @classmethod
    def _sanitize_model_result(cls, result: ModelCallResult) -> ModelCallResult:
        if isinstance(result, AIMessage):
            return cls._sanitize_model_ai_message(result)
        if isinstance(result, ExtendedModelResponse):
            sanitized = cls._sanitize_model_result(result.model_response)
            if isinstance(sanitized, ModelResponse):
                return replace(result, model_response=sanitized)
            return result
        if isinstance(result, ModelResponse):
            messages = [cls._sanitize_model_ai_message(message) if isinstance(message, AIMessage) else message for message in result.result]
            return replace(result, result=messages)
        return result

    @staticmethod
    def _model_result_ai_messages(result: ModelCallResult) -> list[AIMessage]:
        if isinstance(result, AIMessage):
            return [result]
        if isinstance(result, ExtendedModelResponse):
            return TerminalResponseMiddleware._model_result_ai_messages(result.model_response)
        if isinstance(result, ModelResponse):
            return [message for message in result.result if isinstance(message, AIMessage)]
        return []

    @classmethod
    def _replace_model_result_with_invalid_fallback(cls, result: ModelCallResult) -> ModelCallResult:
        fallback = cls._direct_invalid_tool_fallback()
        if isinstance(result, AIMessage):
            return fallback
        if isinstance(result, ExtendedModelResponse):
            replaced = cls._replace_model_result_with_invalid_fallback(result.model_response)
            if isinstance(replaced, ModelResponse):
                return replace(result, model_response=replaced)
            return fallback
        if isinstance(result, ModelResponse):
            return replace(result, result=[fallback], structured_response=None)
        return fallback

    def _enforce_expected_repair_result(self, result: ModelCallResult, runtime: Runtime) -> ModelCallResult:
        key = self._key(runtime)
        with self._lock:
            repair_expected = key in self._expected_repair_tool_names
            expected_tool_name = self._expected_repair_tool_names.get(key, "")
        if not repair_expected:
            return result

        ai_messages = self._model_result_ai_messages(result)
        if len(ai_messages) == 1 and (ai_messages[0].additional_kwargs or {}).get("deerflow_error_fallback") is True:
            return result
        exact_single_call = (
            bool(expected_tool_name) and len(ai_messages) == 1 and len(ai_messages[0].tool_calls or []) == 1 and not getattr(ai_messages[0], "invalid_tool_calls", None) and ai_messages[0].tool_calls[0].get("name") == expected_tool_name
        )
        if exact_single_call:
            return result

        with self._lock:
            self._expected_repair_tool_names.pop(key, None)
        self._signal_failure(runtime, _INVALID_TOOL_FAILURE)
        return self._replace_model_result_with_invalid_fallback(result)

    def _apply_invalid_tool_call(self, message: AIMessage, runtime: Runtime) -> dict[str, Any]:
        key = self._key(runtime)
        with self._lock:
            retry_count = self._invalid_retry_counts.get(key, 0)
            if retry_count == 0:
                self._invalid_retry_counts[key] = 1
                invalid_tool_name = self._invalid_tool_name(message)
                self._pending_invalid_tool_names[key] = invalid_tool_name
                self._expected_repair_tool_names[key] = invalid_tool_name

        if retry_count == 0 and message.id:
            # A malformed call did not execute. Remove it before jumping so the
            # tool router cannot run it and the dangling-call normalizer cannot
            # manufacture a ToolMessage or echo provider parsing details.
            return {"messages": [RemoveMessage(id=message.id)], "jump_to": "model"}
        self._signal_failure(runtime, _INVALID_TOOL_FAILURE)
        return {"messages": [self._invalid_tool_fallback(message)], "jump_to": "end"}

    def _apply_expected_repair(self, message: AIMessage, runtime: Runtime, expected_tool_name: str) -> dict[str, Any] | None:
        tool_calls = list(message.tool_calls or [])
        has_invalid_sibling = bool(getattr(message, "invalid_tool_calls", None))
        exact_single_call = bool(expected_tool_name) and len(tool_calls) == 1 and not has_invalid_sibling and tool_calls[0].get("name") == expected_tool_name

        key = self._key(runtime)
        with self._lock:
            self._expected_repair_tool_names.pop(key, None)
        if exact_single_call:
            # Admit exactly one executable repair call, then clear the phase
            # before its ToolMessage/final-answer cycle.
            return None

        self._signal_failure(runtime, _INVALID_TOOL_FAILURE)
        return {"messages": [self._invalid_tool_fallback(message)], "jump_to": "end"}

    def _apply(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        if not messages or not isinstance(messages[-1], AIMessage):
            return None

        last = messages[-1]
        if (last.additional_kwargs or {}).get("deerflow_error_fallback") is True:
            # A provider fallback during repair keeps its own closed reason;
            # it is not a malformed-tool repair failure.
            reason = (last.additional_kwargs or {}).get("error_reason")
            safe_reason = reason if isinstance(reason, str) and reason in TERMINAL_RESPONSE_FAILURES else "generic"
            self._signal_failure(runtime, terminal_response_failure_payload(safe_reason))
            return {"jump_to": "end"}
        key = self._key(runtime)
        with self._lock:
            repair_expected = key in self._expected_repair_tool_names
            expected_tool_name = self._expected_repair_tool_names.get(key, "")
        if repair_expected:
            return self._apply_expected_repair(last, runtime, expected_tool_name)
        # A provider may emit a short preamble alongside malformed arguments.
        # With no executable structured call, visible text must not turn that
        # failed action into a successful terminal response. Mixed valid +
        # invalid calls keep the existing tool-routing semantics to avoid
        # executing a valid call twice.
        if getattr(last, "invalid_tool_calls", None):
            if last.tool_calls:
                # Preserve executable structured calls exactly once, but do
                # not checkpoint or expose a malformed sibling that never ran.
                return {"messages": [self._sanitize_mixed_invalid_tool_call(last)]}
            return self._apply_invalid_tool_call(last, runtime)
        if _has_visible_content(last) or _has_tool_call_intent_or_error(last):
            return None
        if not _tool_result_in_current_turn(messages):
            return None

        key = self._key(runtime)
        with self._lock:
            # The recovery budget is once per run, not once per empty message.
            # A retry that calls another tool must not refresh the budget and
            # create an unbounded empty -> retry -> tool loop.
            retry_count = self._retry_counts.get(key, 0)
            if retry_count == 0:
                self._retry_counts[key] = 1
                self._pending_prompts[key] = True

        if retry_count == 0:
            # The next model call gets a new message id. Remove this empty
            # terminal message now so a successful recovery does not leave it
            # in checkpoint history or future model context.
            message_updates = [RemoveMessage(id=last.id)] if last.id else []
            return {"messages": message_updates, "jump_to": "model"}

        fallback = last.model_copy(
            update={
                "content": _FALLBACK_CONTENT,
                "additional_kwargs": {
                    "deerflow_error_fallback": True,
                    "error_type": "EmptyTerminalResponse",
                    "error_reason": "empty_terminal_response",
                },
            }
        )
        self._signal_failure(runtime, _EMPTY_TERMINAL_FAILURE)
        return {"messages": [fallback], "jump_to": "end"}

    def _augment_request(self, request: ModelRequest) -> ModelRequest:
        key = self._key(request.runtime)
        with self._lock:
            pending = key in self._pending_prompts
            self._pending_prompts.pop(key, None)
            invalid_tool_name = self._pending_invalid_tool_names.pop(key, None)
        if not pending and invalid_tool_name is None:
            return request

        reminders: list[HumanMessage] = []
        if pending:
            reminders.append(
                HumanMessage(
                    content=_RECOVERY_PROMPT,
                    name="terminal_response_recovery",
                    additional_kwargs={"hide_from_ui": True},
                )
            )
        if invalid_tool_name is not None:
            available_tool_names: set[str] = set()
            for tool in request.tools:
                name = getattr(tool, "name", None)
                if isinstance(tool, dict):
                    name = tool.get("name")
                    function = tool.get("function")
                    if not name and isinstance(function, dict):
                        name = function.get("name")
                if isinstance(name, str) and name:
                    available_tool_names.add(name)
            validated_tool_name = invalid_tool_name if invalid_tool_name in available_tool_names else ""
            with self._lock:
                self._expected_repair_tool_names[key] = validated_tool_name
                if not validated_tool_name:
                    self._unavailable_repair_targets[key] = True
            target = f"`{validated_tool_name}`" if validated_tool_name else "the same intended available tool"
            reminders.append(
                HumanMessage(
                    content=(
                        f"Your previous attempt to call {target} had malformed arguments and was not executed. "
                        f"Call {target} again now with one complete, valid JSON argument object containing every "
                        "required field, reconstructed from the conversation. Do not reuse truncated arguments or "
                        "claim success before the tool returns."
                    ),
                    name="invalid_tool_call_recovery",
                    additional_kwargs={"hide_from_ui": True},
                )
            )
        return request.override(messages=[*request.messages, *reminders])

    def _consume_unavailable_repair_target(self, runtime: Runtime) -> bool:
        key = self._key(runtime)
        with self._lock:
            unavailable = self._unavailable_repair_targets.pop(key, False)
            if unavailable:
                self._expected_repair_tool_names.pop(key, None)
        if unavailable:
            self._signal_failure(runtime, _INVALID_TOOL_FAILURE)
        return unavailable

    @staticmethod
    def _direct_invalid_tool_fallback() -> AIMessage:
        return AIMessage(
            content=_INVALID_TOOL_FALLBACK_CONTENT,
            additional_kwargs={
                "deerflow_error_fallback": True,
                "error_type": "InvalidToolCallResponse",
                "error_reason": "invalid_tool_call",
            },
            response_metadata={"finish_reason": "stop"},
        )

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._clear_other_runs(runtime)
        # A prior invocation can bypass after_agent via Command(goto=END).
        # Reset the same run id here so resume starts with a fresh one-retry
        # budget; internal jump_to=model loops do not re-run before_agent.
        self._clear(runtime)
        self._clear_failure_signal(runtime)
        return None

    @override
    async def abefore_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._clear_other_runs(runtime)
        self._clear(runtime)
        self._clear_failure_signal(runtime)
        return None

    @hook_config(can_jump_to=["model", "end"])
    @override
    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._apply(state, runtime)

    @hook_config(can_jump_to=["model", "end"])
    @override
    async def aafter_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        return self._apply(state, runtime)

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        augmented = self._augment_request(request)
        if self._consume_unavailable_repair_target(request.runtime):
            return self._direct_invalid_tool_fallback()
        sanitized = self._sanitize_model_result(handler(augmented))
        return self._enforce_expected_repair_result(sanitized, request.runtime)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        augmented = self._augment_request(request)
        if self._consume_unavailable_repair_target(request.runtime):
            return self._direct_invalid_tool_fallback()
        sanitized = self._sanitize_model_result(await handler(augmented))
        return self._enforce_expected_repair_result(sanitized, request.runtime)

    @override
    def after_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._clear(runtime)
        return None

    @override
    async def aafter_agent(self, state: AgentState, runtime: Runtime) -> dict | None:
        self._clear(runtime)
        return None
