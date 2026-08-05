"""Private runtime context keys shared across DeerFlow runtime components."""

from types import MappingProxyType
from typing import Any, Final, NamedTuple

CURRENT_RUN_PRE_EXISTING_MESSAGE_IDS_KEY: Final[str] = "__deerflow_pre_run_message_ids"
TERMINAL_RESPONSE_FAILURE_KEY: Final[str] = "__deerflow_terminal_response_failure"


class TerminalResponseFailureSpec(NamedTuple):
    error_type: str
    message: str


TERMINAL_RESPONSE_FAILURES: Final = MappingProxyType(
    {
        "auth": TerminalResponseFailureSpec(
            "LlmAuthenticationFailure",
            "The configured LLM provider rejected the request because authentication or access is invalid. Please check the provider credentials and try again.",
        ),
        "burst_rate": TerminalResponseFailureSpec(
            "LlmBurstRateFailure",
            "The configured LLM provider is temporarily throttling requests because the request rate increased too quickly (burst-rate limit). Please wait a moment and try again.",
        ),
        "busy": TerminalResponseFailureSpec(
            "LlmTransientFailure",
            "The configured LLM provider is temporarily unavailable after multiple retries. Please wait a moment and continue the conversation.",
        ),
        "circuit_open": TerminalResponseFailureSpec(
            "LlmCircuitOpenFailure",
            "The configured LLM provider is currently unavailable due to continuous failures. Circuit breaker is engaged to protect the system. Please wait a moment before trying again.",
        ),
        "empty_terminal_response": TerminalResponseFailureSpec(
            "EmptyTerminalResponse",
            "The model completed the tool run but returned no final response, including after one automatic retry. Please try again or use a different model.",
        ),
        "invalid_tool_call": TerminalResponseFailureSpec(
            "InvalidToolCallResponse",
            ("The model could not produce a valid tool call, including after one automatic repair attempt. The tool was not executed. Please try again or use a different model."),
        ),
        "generic": TerminalResponseFailureSpec(
            "LlmProviderFailure",
            "The configured LLM provider rejected the request. Please check the model configuration and try again.",
        ),
        "quota": TerminalResponseFailureSpec(
            "LlmQuotaFailure",
            "The configured LLM provider rejected the request because the account is out of quota, billing is unavailable, or usage is restricted. Please fix the provider account and try again.",
        ),
        "transient": TerminalResponseFailureSpec(
            "LlmTransientFailure",
            "The configured LLM provider is temporarily unavailable after multiple retries. Please wait a moment and continue the conversation.",
        ),
    }
)


def terminal_response_failure_payload(reason: str) -> dict[str, str]:
    """Build one closed, safe terminal failure payload."""
    spec = TERMINAL_RESPONSE_FAILURES[reason]
    return {
        "error_type": spec.error_type,
        "error_reason": reason,
        "message": spec.message,
    }


def read_terminal_response_failure(context: Any) -> dict[str, str] | None:
    """Validate a run context's server-owned terminal failure signal."""
    if not isinstance(context, dict):
        return None
    raw = context.get(TERMINAL_RESPONSE_FAILURE_KEY)
    if not isinstance(raw, dict):
        return None
    reason = raw.get("error_reason")
    if not isinstance(reason, str) or reason not in TERMINAL_RESPONSE_FAILURES:
        return None
    expected = terminal_response_failure_payload(reason)
    return expected if raw == expected else None
