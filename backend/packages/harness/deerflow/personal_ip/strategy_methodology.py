"""Shape-only helpers for immutable Personal-IP strategy snapshots.

The repository stores the agent's current working strategy for a person,
brand, product or organization.  It deliberately does not decide whether the
strategy is commercially sound, sufficiently researched or ready for a later
creative operation.  Those are model/method judgments, not persistence rules.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

PERSONAL_IP_STRATEGY_METHOD_VERSION = "personal-ip-strategy-v5"

# Kept for persisted-row and API compatibility.  A value is a descriptive
# label supplied by the agent, never an admission state for another tool.
STRATEGY_MODES = {"monetization_first", "influence_first"}
STRATEGY_STAGES = (
    "evidence_collecting",
    "person_model_draft",
    "business_model_draft",
    "benchmark_researching",
    "positioning_candidates",
    "launch_package_ready",
    "pilot_running",
    "commercial_signal_observed",
    "scaling",
)


def _ensure_json_size(value: Any, *, field: str, limit: int = 200_000) -> None:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} bytes")


def _require_object(value: Any, *, field: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    _ensure_json_size(value, field=field)


def _require_list(value: Any, *, field: str) -> None:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise ValueError(f"{field} must be a list")
    _ensure_json_size(value, field=field)


def normalize_evidence_refs(
    value: Sequence[Mapping[str, Any]] | None,
    *,
    required: bool = False,
) -> list[dict[str, str]]:
    """Normalize optional provenance pointers without making them prerequisites.

    ``required`` remains in the signature for source compatibility.  It no
    longer changes behavior: an empty list is a legitimate creative or
    cold-start snapshot.
    """

    del required
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise ValueError("evidence_refs must be a list")
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("each evidence reference must be an object")
        kind = " ".join(str(raw.get("kind") or "").split())
        evidence_id = " ".join(str(raw.get("id") or "").split())
        if not kind or len(kind) > 64:
            raise ValueError("evidence_refs.kind must contain 1 to 64 characters")
        if not evidence_id or len(evidence_id) > 128:
            raise ValueError("evidence_refs.id must contain 1 to 128 characters")
        key = (kind, evidence_id)
        if key not in seen:
            seen.add(key)
            result.append({"kind": kind, "id": evidence_id})
    if len(result) > 200:
        raise ValueError("evidence_refs may contain at most 200 items")
    return result


def strategy_stage_index(stage: str) -> int:
    """Return the compatibility ordering for display and old rows only."""

    try:
        return STRATEGY_STAGES.index(str(stage or "").strip())
    except ValueError as exc:
        raise ValueError("unsupported Personal-IP strategy stage") from exc


def validate_strategy_transition(
    previous_stage: str | None,
    target_stage: str,
) -> str:
    """Validate the label, without imposing a business workflow transition."""

    del previous_stage
    return STRATEGY_STAGES[strategy_stage_index(target_stage)]


def validate_strategy_snapshot(
    *,
    stage: str,
    mode: str,
    person_model: dict[str, Any],
    business_model: dict[str, Any],
    benchmark_research: dict[str, Any],
    positioning_candidates: list[Any],
    launch_package: dict[str, Any],
    validation: dict[str, Any],
    evidence_refs: list[dict[str, str]],
    subject_type: str = "creator",
) -> None:
    """Validate serialization shape only; never score business readiness."""

    strategy_stage_index(stage)
    if mode not in STRATEGY_MODES:
        raise ValueError("strategy mode must be monetization_first or influence_first")
    if subject_type not in {"creator", "brand", "product", "organization"}:
        raise ValueError("unsupported Personal-IP subject type")
    for field, value in (
        ("person_model", person_model),
        ("business_model", business_model),
        ("benchmark_research", benchmark_research),
        ("launch_package", launch_package),
        ("validation", validation),
    ):
        _require_object(value, field=field)
    _require_list(positioning_candidates, field="positioning_candidates")
    normalize_evidence_refs(evidence_refs)
