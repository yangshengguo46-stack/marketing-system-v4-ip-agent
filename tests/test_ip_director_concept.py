from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "product" / "research" / "ip-agent" / "director-core"
MODULE_PATH = ROOT / "product" / "research" / "ip-agent" / "python" / "ip_director_concept.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ip_director_concept", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(name: str):
    return json.loads((ASSET_ROOT / name).read_text(encoding="utf-8"))


def test_director_method_is_sample_agnostic_and_research_only() -> None:
    method = (ASSET_ROOT / "director-method-v1.md").read_text(encoding="utf-8")
    schema = (ASSET_ROOT / "ip-director-concept-v1.schema.json").read_text(encoding="utf-8")

    for leaked_sample in (
        "黄金礼品",
        "黄金小礼品",
        "宝妈",
        "贵厨笔记",
        "领导送礼升职",
        "云沐荟",
    ):
        assert leaked_sample not in method
        assert leaked_sample not in schema

    assert "research_quarantined" in schema
    assert "不得接入默认 Agent" in method


def test_valid_person_product_and_organization_contracts() -> None:
    module = _load_module()
    fixtures = _load_json("valid-contracts.json")

    assert {item["ontology"]["operated_subject_kind"] for item in fixtures} == {
        "person",
        "product",
        "organization",
    }
    for contract in fixtures:
        assert module.validate_contract(contract) == []
        assert len(module.canonical_sha256(contract)) == 64


def test_invalid_contracts_fail_for_the_declared_reason() -> None:
    module = _load_module()
    base = _load_json("valid-contracts.json")[0]
    cases = _load_json("invalid-contracts.json")

    assert len(cases) >= 6
    for case in cases:
        contract = copy.deepcopy(base)
        target = contract
        path = case["path"]
        for component in path[:-1]:
            target = target[component]
        target[path[-1]] = case["value"]
        issue_codes = {issue["code"] for issue in module.validate_contract(contract)}
        assert case["expected_code"] in issue_codes, case["id"]


def test_story_modes_compile_selected_association_into_one_line_causality() -> None:
    fixtures = _load_json("valid-contracts.json")
    story_contracts = [item for item in fixtures if item["direction"]["communication"]["mode"] in {"story", "hybrid"}]

    assert story_contracts
    causal_fields = {
        "semantic_action",
        "relationship_at_stake",
        "trigger",
        "want",
        "goal",
        "initial_tactic",
        "counterforce",
        "feedback",
        "strategy_change",
        "costly_choice",
        "cost",
        "state_change",
        "viewer_desire",
        "logline",
    }
    for contract in story_contracts:
        direction = contract["direction"]
        story = direction["communication"]["desire_behavior"]
        assert story["source_candidate_ref"] == direction["selected_candidate_ref"]
        assert story["epistemic_state"] in {"source_observed", "creative"}
        assert story["commercial_object_mode"] in {"absent", "causal"}
        assert story["substitution_test"].strip()
        assert story["fact_refs"]
        assert causal_fields.issubset(story)
        assert all(story[field].strip() for field in causal_fields)
        assert "\n" not in story["logline"]


def test_fixed_scenarios_cover_identity_product_and_portfolio_traps() -> None:
    suite = _load_json("scenarios.json")
    scenarios = suite["scenarios"]

    assert suite["schema_version"] == "ip-director-scenario-suite-v1"
    assert len(scenarios) == 6
    assert {scenario["route"] for scenario in scenarios} == {
        "person_led",
        "product_led",
        "organization_led",
        "portfolio",
    }
    assert all(scenario["failure_conditions"] for scenario in scenarios)
    assert all(scenario["discriminating_observation"] for scenario in scenarios)


def test_failed_direct_canary_cannot_be_reported_as_product_capability() -> None:
    canary = _load_json("canary-s4-direct-20260804.json")

    assert canary["scope"] == "research_direct_provider_only"
    assert canary["product_capability"] is False
    assert canary["verdict"] == "failed"
    assert canary["output_evidence"]["raw_output_persisted"] is False
    assert len(canary["output_evidence"]["validator_issues"]) == 2
    assert canary["next_experiment"]["limits"]["automatic_retry"] is False


def test_causal_logline_canary_rejects_incidental_product_placement() -> None:
    failed = _load_json("canary-s1-causal-logline-evolving-20260804.json")
    revised = _load_json("canary-s1-causal-logline-evolving-v2-20260804.json")

    assert failed["evaluation"]["verdict"] == "failed"
    assert revised["evaluation"]["verdict"] == "failed"
    assert revised["product_capability"] is False
    assert revised["response"]["json_parse_error"] is None

    content = revised["response"]["content"]
    assert content["story_world"]
    assert content["business_bridge"]
    assert content["logline"]
    for business_term in ("账号", "流量", "平台", "粉丝", "咨询", "订单", "成交"):
        assert business_term not in content["logline"]
    assert "小金牌" in content["logline"]
    assert any("可替换" in failure for failure in revised["evaluation"]["failures"])


def test_absent_mode_canary_consumes_the_commercial_object_seed() -> None:
    canary = _load_json("canary-s1-causal-logline-evolving-v3-20260804.json")

    assert canary["evaluation"]["verdict"] == "passed_for_absent_mode_only"
    assert canary["product_capability"] is False
    assert canary["response"]["json_parse_error"] is None

    content = canary["response"]["content"]
    assert content["commercial_object_mode"] == "absent"
    assert content["substitution_test"].strip()
    story_text = json.dumps(content["story_world"], ensure_ascii=False) + content["logline"]
    for fixture_specific_proxy in (
        "黄金",
        "小金牌",
        "礼品",
        "礼物",
        "纪念物",
        "信物",
        "商品",
        "饰物",
        "首饰",
    ):
        assert fixture_specific_proxy not in story_text


def test_research_prototype_is_not_imported_by_product_runtime() -> None:
    needle = "ip_director_concept"
    searched_roots = (
        ROOT / "backend",
        ROOT / "frontend",
        ROOT / "product" / "defaults",
    )
    violations: list[str] = []
    for searched_root in searched_roots:
        for path in searched_root.rglob("*"):
            if not path.is_file() or any(part in {".venv", ".next", "node_modules"} for part in path.parts):
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if needle in text:
                violations.append(str(path.relative_to(ROOT)))

    assert violations == []
