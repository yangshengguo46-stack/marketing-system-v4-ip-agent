"""Deterministic hard-budget accounting for Personal-IP video productions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

VIDEO_BUDGET_STATE_CONTRACT_VERSION = "personal-ip-video-budget-state-v1"
VIDEO_BUDGET_RESERVATION_CONTRACT_VERSION = "personal-ip-video-budget-reservation-v1"
VIDEO_BUDGET_REJECTION_CONTRACT_VERSION = "personal-ip-video-budget-rejection-v1"
VIDEO_BUDGET_SETTLEMENT_CONTRACT_VERSION = "personal-ip-video-budget-settlement-v1"
VIDEO_BUDGET_RELEASE_CONTRACT_VERSION = "personal-ip-video-budget-release-v1"

_MICRO_UNITS = Decimal("1000000")
_MAX_AMOUNT = Decimal("1000000000")
_KNOWN_PAID_PROVIDER_CAPABILITIES: dict[str, frozenset[str]] = {
    "doubaoseedance": frozenset({"video_generation"}),
    "doubaoseedream": frozenset({"image_generation"}),
    "doubaospeech": frozenset({"speech_generation"}),
    "mediakitcloud": frozenset({"media_processing"}),
    "seedance": frozenset({"video_generation"}),
    "seedream": frozenset({"image_generation"}),
    "volcengine": frozenset(
        {
            "image_generation",
            "media_processing",
            "speech_generation",
            "video_generation",
        }
    ),
    "volcenginemediakit": frozenset({"media_processing"}),
}


def amount_to_micros(value: Any, *, field: str, allow_zero: bool = True) -> int:
    """Normalize a finite non-negative amount to six-decimal integer units."""

    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite non-negative number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite non-negative number") from exc
    if not amount.is_finite() or amount < 0 or amount > _MAX_AMOUNT:
        raise ValueError(f"{field} must be a finite non-negative number")
    if not allow_zero and amount == 0:
        raise ValueError(f"{field} must be greater than zero")
    micros = amount * _MICRO_UNITS
    if micros != micros.to_integral_value():
        raise ValueError(f"{field} may contain at most six decimal places")
    return int(micros)


def micros_to_amount(value: int) -> float:
    """Return a stable JSON number for integer micro-units."""

    return float(Decimal(value) / _MICRO_UNITS)


def provider_requires_paid_admission(provider: str, capability: str) -> bool:
    """Classify known cloud executors independently of caller billing claims."""

    normalized_provider = "".join(character for character in str(provider).lower() if character.isalnum())
    normalized_capability = str(capability or "").strip().lower()
    return normalized_capability in _KNOWN_PAID_PROVIDER_CAPABILITIES.get(
        normalized_provider,
        frozenset(),
    )


def budget_limit(budget: dict[str, Any]) -> tuple[str, int]:
    """Read the immutable hard limit, including the old local-acceptance alias."""

    if not isinstance(budget, dict):
        raise ValueError("video production budget must be an object")
    approval_required = budget.get("paid_calls_require_explicit_approval", True)
    if not isinstance(approval_required, bool):
        raise ValueError("video production budget paid_calls_require_explicit_approval must be a boolean")
    raw_limit = budget.get("hard_limit")
    if raw_limit is None:
        raw_limit = budget.get("local_acceptance_limit")
    if raw_limit is None:
        raise ValueError("video production has no enforceable hard_limit")
    currency = str(budget.get("currency") or "").strip().upper()
    if not currency or len(currency) > 8:
        raise ValueError("video production budget currency is required")
    return currency, amount_to_micros(
        raw_limit,
        field="video production budget hard_limit",
    )


def fold_video_budget(
    budget: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fold server-owned reservation events into an exact current balance."""

    currency, hard_limit_micros = budget_limit(budget)
    active: dict[str, int] = {}
    settled_ids: set[str] = set()
    released_ids: set[str] = set()
    spent_micros = 0

    for event in events:
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        event_type = event.get("event_type")
        reservation_id = str(payload.get("reservation_id") or "").strip()
        if not reservation_id:
            continue
        if event_type == "budget_reserved":
            if payload.get("contract_version") != VIDEO_BUDGET_RESERVATION_CONTRACT_VERSION:
                continue
            active[reservation_id] = amount_to_micros(
                payload.get("maximum_amount"),
                field="budget reservation maximum_amount",
                allow_zero=False,
            )
        elif event_type == "budget_settled":
            if payload.get("contract_version") != VIDEO_BUDGET_SETTLEMENT_CONTRACT_VERSION:
                continue
            active.pop(reservation_id, None)
            if reservation_id not in settled_ids:
                spent_micros += amount_to_micros(
                    payload.get("actual_amount"),
                    field="budget settlement actual_amount",
                )
                settled_ids.add(reservation_id)
        elif event_type == "budget_released":
            if payload.get("contract_version") != VIDEO_BUDGET_RELEASE_CONTRACT_VERSION:
                continue
            active.pop(reservation_id, None)
            released_ids.add(reservation_id)

    reserved_micros = sum(active.values())
    available_micros = max(0, hard_limit_micros - reserved_micros - spent_micros)
    return {
        "contract_version": VIDEO_BUDGET_STATE_CONTRACT_VERSION,
        "currency": currency,
        "hard_limit": micros_to_amount(hard_limit_micros),
        "reserved": micros_to_amount(reserved_micros),
        "spent": micros_to_amount(spent_micros),
        "available": micros_to_amount(available_micros),
        "active_reservation_count": len(active),
        "settled_reservation_count": len(settled_ids),
        "released_reservation_count": len(released_ids),
        "_hard_limit_micros": hard_limit_micros,
        "_reserved_micros": reserved_micros,
        "_spent_micros": spent_micros,
        "_available_micros": available_micros,
    }


def public_budget_state(state: dict[str, Any]) -> dict[str, Any]:
    """Remove integer accounting internals from an API/tool projection."""

    return {key: value for key, value in state.items() if not key.startswith("_")}
