#!/usr/bin/env python3
"""Validate a lifecycle or episode desire-behavior JSON record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EVIDENCE_STATUSES = {
    "sourced_fact",
    "testimony",
    "cross_source_synthesis",
    "analyst_inference",
    "creative_hypothesis",
    "unknown",
}
LIFECYCLE_REQUIRED = {
    "record_type",
    "subject",
    "root_drive",
    "conscious_want",
    "success_state",
    "failure_state",
    "counter_desires",
    "observable_progress",
    "ethical_boundaries",
}
EPISODE_REQUIRED = {
    "record_type",
    "episode_id",
    "subject",
    "root_drive",
    "conscious_want",
    "episode_goal",
    "trigger",
    "counterforces",
    "stakes",
    "tactics",
    "observable_actions",
    "costly_choice",
    "state_change",
    "viewer_desire",
    "silent_test",
}
SILENT_TEST_FIELDS = {
    "want_visible",
    "action_visible",
    "counterforce_visible",
    "stakes_or_consequence_visible",
    "state_change_visible",
}
COUNTERFORCE_TYPES = {
    "counter_desire",
    "internal_counter_desire",
    "time",
    "information",
    "rule",
    "resource",
    "environment",
    "body",
    "reciprocal_desire",
}


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_root_drive(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("root_drive must be an object")
        return
    if not nonempty_string(value.get("value")):
        errors.append("root_drive.value must be a non-empty string or 'unknown'")
    if value.get("evidence_status") not in EVIDENCE_STATUSES:
        errors.append("root_drive.evidence_status must be a supported evidence status")


def require_strings(
    record: dict[str, Any], fields: set[str], errors: list[str]
) -> None:
    for field in sorted(fields):
        if not nonempty_string(record.get(field)):
            errors.append(f"{field} must be a non-empty string")


def require_nonempty_list(
    record: dict[str, Any], field: str, errors: list[str]
) -> list[Any]:
    value = record.get(field)
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must be a non-empty array")
        return []
    return value


def validate_lifecycle(record: dict[str, Any], errors: list[str]) -> None:
    missing = sorted(LIFECYCLE_REQUIRED - set(record))
    if missing:
        errors.append(f"missing lifecycle fields: {missing}")
    require_strings(
        record,
        {"subject", "conscious_want", "success_state", "failure_state"},
        errors,
    )
    validate_root_drive(record.get("root_drive"), errors)
    for field in ("observable_progress", "ethical_boundaries"):
        values = require_nonempty_list(record, field, errors)
        if values and not all(nonempty_string(item) for item in values):
            errors.append(f"{field} entries must be non-empty strings")
    for index, item in enumerate(
        require_nonempty_list(record, "counter_desires", errors)
    ):
        if not isinstance(item, dict):
            errors.append(f"counter_desires[{index}] must be an object")
            continue
        require_strings(
            item,
            {"subject", "want", "relationship"},
            errors,
        )


def validate_episode(record: dict[str, Any], errors: list[str]) -> None:
    missing = sorted(EPISODE_REQUIRED - set(record))
    if missing:
        errors.append(f"missing episode fields: {missing}")
    require_strings(
        record,
        {
            "episode_id",
            "subject",
            "conscious_want",
            "episode_goal",
            "trigger",
            "costly_choice",
            "state_change",
            "viewer_desire",
        },
        errors,
    )
    validate_root_drive(record.get("root_drive"), errors)
    for field in ("tactics", "observable_actions"):
        values = require_nonempty_list(record, field, errors)
        if values and not all(nonempty_string(item) for item in values):
            errors.append(f"{field} entries must be non-empty strings")
    stakes = record.get("stakes")
    if not isinstance(stakes, dict):
        errors.append("stakes must be an object")
    else:
        require_strings(stakes, {"gain", "loss"}, errors)
    for index, item in enumerate(
        require_nonempty_list(record, "counterforces", errors)
    ):
        if not isinstance(item, dict):
            errors.append(f"counterforces[{index}] must be an object")
            continue
        require_strings(item, {"source", "want_or_pressure"}, errors)
        if item.get("type") not in COUNTERFORCE_TYPES:
            errors.append(
                f"counterforces[{index}].type must be one of {sorted(COUNTERFORCE_TYPES)}"
            )
    silent = record.get("silent_test")
    if not isinstance(silent, dict):
        errors.append("silent_test must be an object")
    else:
        missing_silent = sorted(SILENT_TEST_FIELDS - set(silent))
        if missing_silent:
            errors.append(f"silent_test is missing {missing_silent}")
        for field in sorted(SILENT_TEST_FIELDS):
            if silent.get(field) is not True:
                errors.append(f"silent_test.{field} must be true before script handoff")


def validate(record: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(record, dict):
        return {
            "status": "FAIL",
            "record_type": None,
            "errors": ["top-level JSON must be an object"],
            "warnings": [],
        }
    record_type = record.get("record_type")
    if record_type == "lifecycle_desire":
        validate_lifecycle(record, errors)
        if record.get("root_drive", {}).get("value") == "unknown":
            warnings.append(
                "root drive is unknown; preserve it until evidence improves"
            )
    elif record_type == "episode_desire_behavior":
        validate_episode(record, errors)
    else:
        errors.append("record_type must be lifecycle_desire or episode_desire_behavior")
    return {
        "status": "PASS" if not errors else "FAIL",
        "record_type": record_type,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    record = json.loads(args.path.read_text(encoding="utf-8"))
    result = validate(record)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
