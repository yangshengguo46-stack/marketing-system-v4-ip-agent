from __future__ import annotations

import pytest
from langchain_core.tools import StructuredTool
from pydantic import ValidationError

from deerflow.config.extensions_config import ExtensionsConfig
from deerflow.tools.result_policy import (
    RESULT_POLICY_METADATA_KEY,
    clear_tool_result_policy,
    get_tool_result_policy,
    tag_tool_result_policy,
)

EVIDENCE_POLICY = {
    "trust": "untrusted_external",
    "semantic_class": "evidence",
    "outcome_contract": "ip-evidence-operation-status-v1",
}


def _tool(*, metadata: dict[str, object] | None = None) -> StructuredTool:
    def invoke(value: str) -> str:
        return value

    return StructuredTool.from_function(
        invoke,
        name="remote_evidence",
        description="Return test evidence.",
        metadata=metadata,
    )


def test_result_policy_is_operator_tagged_and_round_trips() -> None:
    tool = _tool(metadata={"existing": "kept"})

    tagged = tag_tool_result_policy(tool, EVIDENCE_POLICY)

    assert tagged is tool
    assert get_tool_result_policy(tool) == EVIDENCE_POLICY
    assert tool.metadata["existing"] == "kept"


def test_result_policy_rejects_unknown_values() -> None:
    tool = _tool()

    with pytest.raises(ValueError, match="result policy"):
        tag_tool_result_policy(
            tool,
            {
                **EVIDENCE_POLICY,
                "trust": "remote_tool_claimed_trusted",
            },
        )


def test_clear_result_policy_removes_only_reserved_metadata() -> None:
    tool = _tool(
        metadata={
            "existing": "kept",
            RESULT_POLICY_METADATA_KEY: dict(EVIDENCE_POLICY),
        }
    )

    clear_tool_result_policy(tool)

    assert get_tool_result_policy(tool) is None
    assert tool.metadata == {"existing": "kept"}


def test_extensions_config_accepts_typed_evidence_result_policy() -> None:
    config = ExtensionsConfig.model_validate(
        {
            "mcpServers": {
                "evidence": {
                    "result_policy": EVIDENCE_POLICY,
                }
            }
        }
    )

    assert config.mcp_servers["evidence"].result_policy.model_dump() == EVIDENCE_POLICY


def test_extensions_config_rejects_unknown_result_policy_contract() -> None:
    with pytest.raises(ValidationError):
        ExtensionsConfig.model_validate(
            {
                "mcpServers": {
                    "evidence": {
                        "result_policy": {
                            **EVIDENCE_POLICY,
                            "outcome_contract": "server-invented-v9",
                        },
                    }
                }
            }
        )
