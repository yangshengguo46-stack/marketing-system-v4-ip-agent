"""Native DeerFlow surface for the optional single-step UI-TARS organ."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from langchain.tools import tool

from deerflow.agents.human_input import read_human_input_response
from deerflow.community.ui_tars.audit import append_receipt, build_receipt
from deerflow.community.ui_tars.client import UITarsOperatorClient, UITarsOperatorError
from deerflow.community.ui_tars.privacy import contains_secret_material, high_impact_categories, sanitize_mapping
from deerflow.config import get_app_config
from deerflow.personal_ip.runtime import get_personal_ip_runtime
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime

_BROWSER_CONTROL_TOOLS = {
    "browser_back",
    "browser_click",
    "browser_close",
    "browser_get_text",
    "browser_navigate",
    "browser_screenshot",
    "browser_snapshot",
    "browser_type",
}


def _json(value: dict) -> str:
    return json.dumps(sanitize_mapping(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _risk_confirmation(runtime: Runtime, request_id: str) -> bool:
    """Require a structured affirmative response to the matching risk request."""
    if not request_id or runtime.state is None:
        return False
    request_index: int | None = None
    messages = runtime.state.get("messages") or []
    for index, message in enumerate(messages):
        artifact = getattr(message, "artifact", None)
        human_input = artifact.get("human_input") if isinstance(artifact, dict) else None
        if isinstance(human_input, dict) and human_input.get("request_id") == request_id and human_input.get("source") == "ask_clarification" and human_input.get("clarification_type") == "risk_confirmation":
            request_index = index
            continue
        if request_index is None or index <= request_index:
            continue
        response = read_human_input_response(getattr(message, "additional_kwargs", None))
        if response is None or response.get("request_id") != request_id:
            continue
        value = str(response.get("value") or "").strip().lower()
        negative = {"cancel", "deny", "no", "reject", "stop", "不同意", "取消", "否", "拒绝", "停止"}
        affirmative = {"approve", "approved", "confirm", "continue", "yes", "同意", "确认", "继续", "批准", "是"}
        return value in affirmative and value not in negative
    return False


def _browser_control_observed(runtime: Runtime) -> bool:
    """Require a completed Browser Control call before a web visual fallback."""
    if runtime.state is None:
        return False
    browser_call_ids: set[str] = set()
    for message in runtime.state.get("messages") or []:
        for call in getattr(message, "tool_calls", None) or []:
            if isinstance(call, dict) and call.get("name") in _BROWSER_CONTROL_TOOLS and call.get("id"):
                browser_call_ids.add(str(call["id"]))
        message_name = str(getattr(message, "name", None) or "")
        tool_call_id = str(getattr(message, "tool_call_id", None) or "")
        if message_name in _BROWSER_CONTROL_TOOLS or tool_call_id in browser_call_ids:
            return True
    return False


async def _failure_receipt(
    *,
    config,
    intent: str,
    target_app: str,
    target_window: str,
    task_id: str,
    fallback_reason: str,
    account_id: str | None,
    category: str,
    approval_request_id: str | None,
) -> dict:
    receipt = build_receipt(
        intent=intent,
        target_app=target_app,
        target_window=target_window,
        task_id=task_id,
        model_id=config.model,
        result="failed",
        fallback_reason=fallback_reason,
        account_id=account_id,
        failure_category=category,
        approval_request_id=approval_request_id,
    )
    audit_ref = await asyncio.to_thread(append_receipt, receipt)
    return {"status": "error", "category": category, "receipt": receipt, "audit_ref": audit_ref}


async def _ui_tars_desktop_step(
    runtime: Runtime,
    intent: str,
    target_app: str,
    target_window: str,
    task_id: str,
    fallback_reason: Literal[
        "browser_dom_unavailable",
        "browser_action_failed",
        "native_desktop_required",
    ],
    account_id: str,
    approval_request_id: str,
) -> str:
    """Perform one privacy-bounded UI-TARS desktop fallback step.

    DeerFlow remains the sole planner. Use Browser Control first for web work;
    call this only after its DOM/action path is unavailable or when a task truly
    requires a native desktop application. One call captures one locally
    pixelated screenshot, asks the configured UI-TARS model for one allowlisted
    action, executes at most that action, and returns an auditable receipt.

    Never pass cookies, tokens, passwords, browser profile paths, authorization
    headers or copied sensitive screen text. Account ids select only the exact
    operation target and never narrow the conversation's portfolio authority.

    Args:
        intent: Concise action intent; omit credentials and sensitive screen text.
        target_app: Expected desktop application name.
        target_window: Expected window title or a non-sensitive summary; empty when unknown.
        task_id: Current DeerFlow run/task identifier for the receipt.
        fallback_reason: Browser failure category or native-desktop necessity.
        account_id: Optional server-issued Personal-IP account target; pass an empty string when absent.
        approval_request_id: Matching structured risk-confirmation request id for irreversible work; pass an empty string for reversible work.

    Returns:
        JSON execution result and credential-free receipt/evidence references.
    """
    config = get_app_config().ui_tars
    selected_account_id = account_id.strip() or None
    approval_id = approval_request_id.strip() or None
    if not config.enabled:
        return _json(
            await _failure_receipt(
                config=config,
                intent=intent,
                target_app=target_app,
                target_window=target_window,
                task_id=task_id,
                fallback_reason=fallback_reason,
                account_id=selected_account_id,
                category="disabled",
                approval_request_id=approval_id,
            )
        )
    if contains_secret_material(intent):
        return _json(
            await _failure_receipt(
                config=config,
                intent=intent,
                target_app=target_app,
                target_window=target_window,
                task_id=task_id,
                fallback_reason=fallback_reason,
                account_id=selected_account_id,
                category="sensitive_input_blocked",
                approval_request_id=approval_id,
            )
        )
    if fallback_reason != "native_desktop_required" and not _browser_control_observed(runtime):
        return _json(
            await _failure_receipt(
                config=config,
                intent=intent,
                target_app=target_app,
                target_window=target_window,
                task_id=task_id,
                fallback_reason=fallback_reason,
                account_id=selected_account_id,
                category="browser_control_required",
                approval_request_id=approval_id,
            )
        )
    if selected_account_id:
        try:
            services = get_personal_ip_runtime()
            if services.accounts is None:
                raise RuntimeError
            account = await services.accounts.get(
                selected_account_id,
                owner_user_id=resolve_runtime_user_id(runtime),
            )
        except RuntimeError:
            account = None
        if account is None or account.get("status") != "active":
            return _json(
                await _failure_receipt(
                    config=config,
                    intent=intent,
                    target_app=target_app,
                    target_window=target_window,
                    task_id=task_id,
                    fallback_reason=fallback_reason,
                    account_id=selected_account_id,
                    category="account_target_not_found",
                    approval_request_id=approval_id,
                )
            )
    risks = high_impact_categories(intent)
    approved = bool(risks and approval_id and _risk_confirmation(runtime, approval_id))
    if risks and not approved:
        return _json(
            await _failure_receipt(
                config=config,
                intent=intent,
                target_app=target_app,
                target_window=target_window,
                task_id=task_id,
                fallback_reason=fallback_reason,
                account_id=selected_account_id,
                category="approval_required",
                approval_request_id=approval_id,
            )
        )
    client = UITarsOperatorClient(config.endpoint, timeout_seconds=config.request_timeout_seconds)
    try:
        result = await client.step(
            {
                "intent": intent,
                "target_app": target_app,
                "target_window": target_window,
                "task_id": task_id,
                "fallback_reason": fallback_reason,
                "account_id": selected_account_id,
                "approved": approved,
                "approval_request_id": approval_id,
            }
        )
        return _json(result)
    except UITarsOperatorError as exc:
        result = await _failure_receipt(
            config=config,
            intent=intent,
            target_app=target_app,
            target_window=target_window,
            task_id=task_id,
            fallback_reason=fallback_reason,
            account_id=selected_account_id,
            category=exc.category,
            approval_request_id=approval_id,
        )
        result["message"] = str(exc)
        return _json(result)


ui_tars_desktop_step_tool = tool(
    "ui_tars_desktop_step",
    parse_docstring=True,
)(_ui_tars_desktop_step)
