"""Operator-owned semantic policy for tool results.

Remote tools may describe themselves, but they may not decide how DeerFlow
trusts or interprets their output.  This module owns one reserved BaseTool
metadata key that is cleared from discovered tools and then written only from
local configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langchain.tools import BaseTool

RESULT_POLICY_METADATA_KEY = "deerflow_result_policy"

_EVIDENCE_RESULT_POLICY = {
    "trust": "untrusted_external",
    "semantic_class": "evidence",
    "outcome_contract": "ip-evidence-operation-status-v1",
}


def _validated_policy(policy: Mapping[str, Any]) -> dict[str, str]:
    normalized = dict(policy)
    if normalized != _EVIDENCE_RESULT_POLICY:
        raise ValueError("Unsupported tool result policy; expected the exact ip-evidence-operation-status-v1 policy")
    return dict(_EVIDENCE_RESULT_POLICY)


def tag_tool_result_policy(
    tool: BaseTool,
    policy: Mapping[str, Any],
) -> BaseTool:
    """Attach a validated, operator-owned result policy to ``tool``."""
    tool.metadata = {
        **(tool.metadata or {}),
        RESULT_POLICY_METADATA_KEY: _validated_policy(policy),
    }
    return tool


def clear_tool_result_policy(tool: BaseTool) -> BaseTool:
    """Remove any result-policy claim already present on ``tool``."""
    metadata = dict(tool.metadata or {})
    metadata.pop(RESULT_POLICY_METADATA_KEY, None)
    tool.metadata = metadata
    return tool


def get_tool_result_policy(tool: BaseTool | None) -> dict[str, str] | None:
    """Return a validated policy, failing closed if the reserved value drifted."""
    if tool is None:
        return None
    policy = (tool.metadata or {}).get(RESULT_POLICY_METADATA_KEY)
    if policy is None:
        return None
    if not isinstance(policy, Mapping):
        raise ValueError("Invalid tool result policy metadata")
    return _validated_policy(policy)
