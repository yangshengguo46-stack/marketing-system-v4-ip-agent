"""Validated receipts emitted by media generation and finishing executors."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from deerflow.persistence.personal_ip_platform_observations.sql import validate_credential_free_payload

MEDIA_EXECUTION_CONTRACT_VERSION = "personal-ip-media-execution-v1"

_CAPABILITY_EVENTS: dict[str, dict[str, str]] = {
    "video_generation": {
        "running": "shot_generation_requested",
        "succeeded": "shot_generation_completed",
        "failed": "shot_generation_failed",
    },
    "image_generation": {
        "running": "asset_generation_requested",
        "succeeded": "asset_generation_completed",
        "failed": "asset_generation_failed",
    },
    "speech_generation": {
        "running": "voice_generation_requested",
        "succeeded": "voice_generated",
        "failed": "voice_generated",
    },
    "media_processing": {
        "running": "media_processing_requested",
        "succeeded": "media_processing_completed",
        "failed": "media_processing_failed",
    },
}

_CAPABILITY_ENTITY_TYPES: dict[str, set[str]] = {
    "video_generation": {"shot", "candidate"},
    "image_generation": {"character", "scene", "prop", "shot", "candidate"},
    "speech_generation": {"audio"},
    "media_processing": {"audio", "timeline", "delivery"},
}


def _required_text(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _optional_text(value: Any, *, field: str, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    if len(text) > limit:
        raise ValueError(f"{field} must contain at most {limit} characters")
    return text


def _timestamp(value: Any, *, field: str) -> datetime:
    text = _required_text(value, field=field, limit=64)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime with timezone") from exc
    if result.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return result.astimezone(UTC)


def _json_snapshot(value: Any, *, field: str, expected: type, byte_limit: int = 1_000_000) -> Any:
    if not isinstance(value, expected):
        kind = "object" if expected is dict else "array"
        raise ValueError(f"{field} must be an {kind}")
    validate_credential_free_payload(value, field=field)
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(serialized.encode("utf-8")) > byte_limit:
        raise ValueError(f"{field} exceeds the snapshot limit")
    return json.loads(serialized)


def _artifact_list(value: Any, *, field: str, require_verified: bool) -> list[dict[str, Any]]:
    items = _json_snapshot(value, field=field, expected=list)
    if len(items) > 500:
        raise ValueError(f"{field} may contain at most 500 artifacts")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        ref = _required_text(raw.get("ref"), field=f"{field}[{index}].ref", limit=2_048)
        if ref in seen:
            raise ValueError(f"{field} contains duplicate ref: {ref}")
        seen.add(ref)
        item: dict[str, Any] = {"ref": ref}
        digest = _optional_text(raw.get("sha256"), field=f"{field}[{index}].sha256", limit=64)
        if digest is not None:
            digest = digest.lower()
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError(f"{field}[{index}].sha256 must be a lowercase SHA-256 digest")
            item["sha256"] = digest
        size = raw.get("size_bytes")
        if size is not None:
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError(f"{field}[{index}].size_bytes must be a non-negative integer")
            item["size_bytes"] = size
        mime_type = _optional_text(raw.get("mime_type"), field=f"{field}[{index}].mime_type", limit=128)
        if mime_type is not None:
            item["mime_type"] = mime_type
        if require_verified and (digest is None or size is None):
            raise ValueError(f"{field}[{index}] must include sha256 and size_bytes")
        normalized.append(item)
    return normalized


def _cost(value: Any) -> dict[str, Any]:
    cost = _json_snapshot(value, field="receipt.cost", expected=dict, byte_limit=64_000)
    status = str(cost.get("status") or "").strip()
    if status not in {"known", "estimated", "unknown"}:
        raise ValueError("receipt.cost.status must be known, estimated or unknown")
    normalized: dict[str, Any] = {"status": status}
    if status == "unknown":
        normalized["reason"] = _required_text(cost.get("reason"), field="receipt.cost.reason", limit=256)
        return normalized
    amount = cost.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
        raise ValueError("receipt.cost.amount must be a non-negative number")
    currency = _required_text(cost.get("currency"), field="receipt.cost.currency", limit=8).upper()
    normalized.update({"amount": amount, "currency": currency})
    if cost.get("basis") is not None:
        normalized["basis"] = _required_text(cost.get("basis"), field="receipt.cost.basis", limit=256)
    return normalized


def normalize_media_execution_receipt(receipt: dict[str, Any], *, entity_type: str) -> dict[str, Any]:
    """Validate one executor receipt and derive its immutable video-ledger event."""

    snapshot = _json_snapshot(receipt, field="receipt", expected=dict)
    if snapshot.get("contract_version") != MEDIA_EXECUTION_CONTRACT_VERSION:
        raise ValueError(f"receipt.contract_version must be {MEDIA_EXECUTION_CONTRACT_VERSION}")
    capability = str(snapshot.get("capability") or "").strip()
    if capability not in _CAPABILITY_EVENTS:
        raise ValueError("unsupported media execution capability")
    status = str(snapshot.get("status") or "").strip()
    if status not in _CAPABILITY_EVENTS[capability]:
        raise ValueError("receipt.status must be running, succeeded or failed")
    if entity_type not in _CAPABILITY_ENTITY_TYPES[capability]:
        allowed = ", ".join(sorted(_CAPABILITY_ENTITY_TYPES[capability]))
        raise ValueError(f"{capability} entity_type must be one of: {allowed}")

    provider = _required_text(snapshot.get("provider"), field="receipt.provider", limit=80)
    executor = _required_text(snapshot.get("executor"), field="receipt.executor", limit=160)
    model = _optional_text(snapshot.get("model"), field="receipt.model", limit=160)
    task_id = _optional_text(snapshot.get("task_id"), field="receipt.task_id", limit=256)
    request_id = _optional_text(snapshot.get("request_id"), field="receipt.request_id", limit=256)
    started_at = _timestamp(snapshot.get("started_at"), field="receipt.started_at")
    completed_at = None
    if status != "running":
        completed_at = _timestamp(snapshot.get("completed_at"), field="receipt.completed_at")
        if completed_at < started_at:
            raise ValueError("receipt.completed_at cannot precede receipt.started_at")
    elif snapshot.get("completed_at") is not None:
        raise ValueError("running receipt.completed_at must be null")
    if status == "running" and not (task_id or request_id):
        raise ValueError("running receipt must include task_id or request_id")
    if capability == "video_generation" and status == "succeeded" and not task_id:
        raise ValueError("succeeded video generation receipt must include task_id")

    inputs = _artifact_list(snapshot.get("inputs", []), field="receipt.inputs", require_verified=False)
    outputs = _artifact_list(
        snapshot.get("outputs", []),
        field="receipt.outputs",
        require_verified=status == "succeeded",
    )
    if status == "succeeded" and not outputs:
        raise ValueError("succeeded receipt must include at least one verified output")
    if status == "running" and outputs:
        raise ValueError("running receipt cannot include outputs")
    failure = None
    if status == "failed":
        failure = _json_snapshot(snapshot.get("failure"), field="receipt.failure", expected=dict, byte_limit=64_000)
        retryable = failure.get("retryable", False)
        if not isinstance(retryable, bool):
            raise ValueError("receipt.failure.retryable must be a boolean")
        failure = {
            "category": _required_text(failure.get("category"), field="receipt.failure.category", limit=128),
            "message": _required_text(failure.get("message"), field="receipt.failure.message", limit=1_000),
            "retryable": retryable,
        }
    elif snapshot.get("failure") is not None:
        raise ValueError("only failed receipts may include failure")
    parameters = _json_snapshot(snapshot.get("parameters", {}), field="receipt.parameters", expected=dict)
    cost = _cost(snapshot.get("cost"))

    normalized = {
        "contract_version": MEDIA_EXECUTION_CONTRACT_VERSION,
        "capability": capability,
        "provider": provider,
        "executor": executor,
        "model": model,
        "status": status,
        "task_id": task_id,
        "request_id": request_id,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat() if completed_at else None,
        "parameters": parameters,
        "inputs": inputs,
        "outputs": outputs,
        "cost": cost,
        "failure": failure,
    }
    return {
        "event_type": _CAPABILITY_EVENTS[capability][status],
        "event_status": "running" if status == "running" else status,
        "provider": provider,
        "model": model,
        "provider_task_id": task_id or request_id,
        "occurred_at": completed_at or started_at,
        "input_refs": [item["ref"] for item in inputs],
        "output_refs": [item["ref"] for item in outputs],
        "cost": cost,
        "payload": normalized,
    }
