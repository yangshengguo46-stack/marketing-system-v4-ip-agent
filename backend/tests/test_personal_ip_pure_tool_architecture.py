from __future__ import annotations

from pathlib import Path

from deerflow.personal_ip.differentiation import (
    validate_differentiation_snapshot,
    validate_differentiation_transition,
)
from deerflow.personal_ip.strategy_methodology import (
    validate_strategy_snapshot,
    validate_strategy_transition,
)
from deerflow.tools.tools import BUILTIN_TOOLS

HARNESS_ROOT = Path(__file__).parents[1] / "packages" / "harness" / "deerflow"


def test_strategy_storage_has_no_business_stage_prerequisites() -> None:
    assert validate_strategy_transition(None, "scaling") == "scaling"
    validate_strategy_snapshot(
        stage="scaling",
        mode="monetization_first",
        person_model={},
        business_model={},
        benchmark_research={},
        positioning_candidates=[],
        launch_package={},
        validation={},
        evidence_refs=[],
        subject_type="product",
    )


def test_differentiation_storage_has_no_promotion_or_semantic_gate() -> None:
    assert validate_differentiation_transition(None, "validated") == "validated"
    validate_differentiation_snapshot(
        status="validated",
        primary_entity={},
        supporting_entities=[],
        decision_context={},
        contrast_field={},
        proprietary_truth={},
        strategic_difference={},
        dramatic_engine={},
        distinctive_encoding={},
        operating_fit={},
        validation={},
        evidence_refs=[],
    )


def test_account_diagnosis_is_read_context_not_a_server_judge() -> None:
    names = {tool.name for tool in BUILTIN_TOOLS}
    assert "personal_ip_account_diagnostic_context" in names
    assert "personal_ip_compile_account_diagnosis" not in names
    assert "personal_ip_promote_evidence" not in names

    source = (HARNESS_ROOT / "personal_ip" / "account_diagnosis.py").read_text(encoding="utf-8")
    forbidden = (
        "minimum_post_count",
        "decision_ready",
        "compile_account_diagnosis",
        "PERSISTENT_RESTRICTION_MIN_DURATION",
        "STRUCTURAL_EVIDENCE_MAX_AGE",
        '"guardrails"',
    )
    assert not [token for token in forbidden if token in source]

    tool_by_name = {tool.name: tool for tool in BUILTIN_TOOLS}
    strategy_schema = tool_by_name["personal_ip_record_strategy"].tool_call_schema.model_json_schema()
    direction_schema = tool_by_name["personal_ip_record_differentiation"].tool_call_schema.model_json_schema()
    assert "stage" not in strategy_schema.get("required", [])
    assert "status" not in direction_schema.get("required", [])
    assert "thesis_key" not in direction_schema.get("required", [])


def test_audience_preflight_does_not_require_strategy_or_thesis_readiness() -> None:
    source = (HARNESS_ROOT / "tools" / "builtins" / "personal_ip_workflow_tools.py").read_text(encoding="utf-8")
    forbidden = (
        "strategy_stage_index",
        "launch package is not ready",
        "differentiation thesis is not ready",
    )
    assert not [token for token in forbidden if token in source]


def test_legacy_promotions_do_not_enter_current_compilers_or_cockpit() -> None:
    sources = [
        (HARNESS_ROOT / "personal_ip" / "video_skill_compiler.py").read_text(encoding="utf-8"),
        (HARNESS_ROOT / "personal_ip" / "video_method_distillation.py").read_text(encoding="utf-8"),
        (HARNESS_ROOT / "personal_ip" / "operating_cockpit.py").read_text(encoding="utf-8"),
    ]
    assert all("evidence_promotions" not in source for source in sources)
    assert all('"promotion"' not in source for source in sources[:2])
