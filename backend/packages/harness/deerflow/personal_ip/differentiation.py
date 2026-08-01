"""Shape-only contracts for immutable Personal-IP direction notes.

Direction, dramatic engines and distinctive expression are authored by the
agent's methods.  This module only keeps their stored JSON well formed; it does
not promote, reject or grade a direction from operating observations.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION = "ip-differentiation-thesis-v2"

# Compatibility labels retained by the existing database schema.  They are
# descriptive metadata, not a server-enforced maturity ladder.
DIFFERENTIATION_STATUSES = (
    "candidate",
    "pilot",
    "provisionally_adopted",
    "validated",
    "retired",
)

DIFFERENTIATION_ENTITY_TYPES = {
    "person",
    "brand",
    "product",
    "organization",
    "portfolio",
}

DIFFERENTIATION_OBSERVATION_TYPES = {
    "recognition",
    "trust",
    "intent",
    "adoption",
    "conversion",
    "economic",
    "extension",
}

DIFFERENTIATION_OBSERVATION_SOURCES = {
    "platform_metrics",
    "platform_observation",
    "retrospective",
    "audience_feedback",
    "user_research",
    "commercial_record",
    "product_telemetry",
}

_DOWNSTREAM_OBSERVATION_TYPES = {"intent", "adoption", "conversion", "economic"}


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


def differentiation_status_index(status: str) -> int:
    key = str(status or "").strip()
    try:
        return DIFFERENTIATION_STATUSES.index(key)
    except ValueError as exc:
        raise ValueError("unsupported differentiation status") from exc


def validate_differentiation_transition(
    previous_status: str | None,
    target_status: str,
) -> str:
    """Validate the status label without imposing a promotion sequence."""

    del previous_status
    return DIFFERENTIATION_STATUSES[differentiation_status_index(target_status)]


def _require_object(value: Any, *, field: str) -> None:
    if value is not None and not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    _ensure_json_size(dict(value or {}), field=field)


def _require_list(value: Any, *, field: str) -> None:
    if value is not None and (not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray))):
        raise ValueError(f"{field} must be a list")
    _ensure_json_size(list(value or []), field=field)


def validate_differentiation_snapshot(
    *,
    status: str,
    primary_entity: Mapping[str, Any] | None,
    supporting_entities: Sequence[Mapping[str, Any]] | None,
    decision_context: Mapping[str, Any] | None,
    contrast_field: Mapping[str, Any] | None,
    proprietary_truth: Mapping[str, Any] | None,
    strategic_difference: Mapping[str, Any] | None,
    dramatic_engine: Mapping[str, Any] | None,
    distinctive_encoding: Mapping[str, Any] | None,
    operating_fit: Mapping[str, Any] | None,
    validation: Mapping[str, Any] | None,
    evidence_refs: Sequence[Mapping[str, Any]],
) -> None:
    """Validate JSON shape only; never judge semantic completeness."""

    differentiation_status_index(status)
    for field, value in (
        ("primary_entity", primary_entity),
        ("decision_context", decision_context),
        ("contrast_field", contrast_field),
        ("proprietary_truth", proprietary_truth),
        ("strategic_difference", strategic_difference),
        ("dramatic_engine", dramatic_engine),
        ("distinctive_encoding", distinctive_encoding),
        ("operating_fit", operating_fit),
        ("validation", validation),
    ):
        _require_object(value, field=field)
    _require_list(supporting_entities, field="supporting_entities")
    _require_list(evidence_refs, field="evidence_refs")


def downstream_observation_types() -> frozenset[str]:
    """Return compatibility categories used in descriptive summaries."""

    return frozenset(_DOWNSTREAM_OBSERVATION_TYPES)
