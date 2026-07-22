"""Append-only, credential-free UI-TARS execution receipts."""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.config.runtime_paths import runtime_home

from .privacy import sanitize_mapping, sanitize_text

RECEIPT_CONTRACT_VERSION = "deerflow-ui-tars-receipt-v1"


def ui_tars_state_dir(base_dir: Path | None = None) -> Path:
    return (base_dir or runtime_home()) / "ui-tars"


def build_receipt(
    *,
    intent: str,
    target_app: str,
    target_window: str,
    task_id: str,
    model_id: str,
    result: str,
    fallback_reason: str,
    account_id: str | None = None,
    action_type: str | None = None,
    evidence: dict[str, Any] | None = None,
    failure_category: str | None = None,
    approval_request_id: str | None = None,
) -> dict[str, Any]:
    return sanitize_mapping(
        {
            "contract_version": RECEIPT_CONTRACT_VERSION,
            "receipt_id": f"uitars-{uuid.uuid4().hex}",
            "created_at": datetime.now(UTC).isoformat(),
            "action_intent": sanitize_text(intent),
            "target": {
                "application": sanitize_text(target_app, max_chars=160),
                "window": sanitize_text(target_window, max_chars=240),
                "account_id": account_id or None,
            },
            "task_id": sanitize_text(task_id, max_chars=160),
            "model_id": sanitize_text(model_id, max_chars=160),
            "result": result,
            "action_type": action_type,
            "fallback_reason": fallback_reason,
            "evidence": evidence or {},
            "failure_category": failure_category,
            "approval_request_id": approval_request_id,
        }
    )


def append_receipt(receipt: dict[str, Any], *, base_dir: Path | None = None) -> str:
    """Append one compact JSON record and return a non-absolute evidence reference."""
    state_dir = ui_tars_state_dir(base_dir)
    audit_dir = state_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = audit_dir / "receipts.jsonl"
    payload = json.dumps(sanitize_mapping(receipt), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, (payload + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)
    return "ui-tars/audit/receipts.jsonl"
