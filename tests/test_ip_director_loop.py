from __future__ import annotations

import copy
import importlib.util
import json
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "product" / "research" / "ip-agent" / "director-core"
MODULE_PATH = ROOT / "product" / "research" / "ip-agent" / "python" / "ip_director_loop.py"
RUNNER_PATH = ROOT / "scripts" / "ip_agent_director_loop_ab.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ip_director_loop", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runner():
    spec = importlib.util.spec_from_file_location("ip_agent_director_loop_ab", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _suite():
    return json.loads((ASSET_ROOT / "director-loop-scenarios-v1.json").read_text(encoding="utf-8"))


def _fruit_brief():
    return copy.deepcopy(_suite()["cases"][0])


def _valid_route():
    return {
        "schema_version": "ip-director-route-result-v1",
        "epistemic_state": "creative",
        "facts_used": ["f1", "f2", "f3", "f4", "f5"],
        "creative_assumptions": ["观众需要和具体方向仍待验证"],
        "semantic_kernel": {
            "surface_terms": ["果农", "果园", "水果"],
            "head_concept": "长期照料有生命的对象",
            "modifiers": ["十五年", "河南", "方言表达"],
            "literal_action": "判断哪些枝果应当保留并承担结果",
            "human_action": "在有限资源下判断什么该保留、什么该放弃",
            "relationship_at_stake": "一个人与旧选择之间的责任和边界",
            "social_rule": "承担过的事往往被期待一直承担",
            "desire_conflict": "保住所有既有承诺与给未来腾出空间不能同时满足",
        },
        "directions": [
            {
                "id": "d-near",
                "semantic_distance": "near",
                "industry_role": "subject",
                "content_subject": "果园里的真实种植判断",
                "association_path": ["果园", "种植决策", "结果验证"],
                "structure_mapping": [
                    {"source_edge": "种植动作影响收成", "target_edge": "公开判断影响专业信任"}
                ],
                "audience_tension": "外行无法判断一个种植决定是否可靠",
                "expression_mode": "现场证明",
                "subject_ownership": "十五年经营和真实场地由本人持有",
                "business_attribution": "种植判断直接归因给本人和果园",
                "evidence_refs": ["f1", "f5"],
                "creative_assumptions": ["观众可能对判断过程感兴趣"],
            },
            {
                "id": "d-mid",
                "semantic_distance": "mid",
                "industry_role": "metaphor",
                "content_subject": "普通人在取舍中的责任",
                "association_path": ["照料果树", "有限资源", "主动取舍", "人的责任边界"],
                "structure_mapping": [
                    {"source_edge": "资源不足迫使舍弃枝条", "target_edge": "精力不足迫使放弃旧承诺"},
                    {"source_edge": "保留决定未来生长", "target_edge": "选择改变人的未来关系"},
                ],
                "audience_tension": "什么都舍不得的人怎样承认自己无法同时负责",
                "expression_mode": "物性观察引出人物短故事",
                "subject_ownership": "本人长期观察果园且能用方言讲述",
                "business_attribution": "独特观察和语言归因本人，产品留在故事之外",
                "evidence_refs": ["f1", "f3", "f4", "f5"],
                "creative_assumptions": ["虚构人物可以承载取舍冲突"],
            },
            {
                "id": "d-far",
                "semantic_distance": "far",
                "industry_role": "stage",
                "content_subject": "村庄里成年人如何保住体面又承认改变",
                "association_path": ["收工聊天", "旁观人情", "方言短段子", "关系喜剧"],
                "structure_mapping": [
                    {"source_edge": "闲谈暴露彼此立场", "target_edge": "对话逼人物公开真实选择"},
                    {"source_edge": "笑话保护说话者体面", "target_edge": "幽默让人物承认难堪事实"},
                ],
                "audience_tension": "成年人如何在不丢体面的情况下承认自己错了",
                "expression_mode": "果园里的乡村开放麦式人物短剧",
                "subject_ownership": "收工聊天经验、方言表达和真实场地共同属于本人",
                "business_attribution": "人物表达归因本人，果园只作为稳定舞台",
                "evidence_refs": ["f2", "f3", "f4", "f5"],
                "creative_assumptions": ["本人能把短段子发展成有行动的虚构场景"],
            },
        ],
        "recommendation": {
            "selected_direction_ref": "d-mid",
            "reason": "它既跨出行业科普，又仍由长期观察和低成本场地支撑",
            "tradeoff": "主动放弃直接讲解全部种植知识",
            "why_not_near": "近距离只能证明专业，不能检验人的处境是否形成更广泛共鸣",
        },
    }


def _valid_route_v2():
    facts = _fruit_brief()["facts"]
    shared = {
        "association_path_hypothesis": ["表面动作", "人的动作", "关系变化", "欲望冲突"],
        "structure_mapping_hypothesis": [
            {"source_edge": "动作产生反馈", "target_edge": "选择改变关系"},
            {"source_edge": "反馈迫使换招", "target_edge": "换招产生代价"},
        ],
        "subject_ownership": {
            "fact_refs": ["f2", "f3", "f4"],
            "hypothesis": "聊天、方言表达和本人出镜可能使方向属于当前主体",
        },
        "audience_tension_hypothesis": "观众可能想看一个人如何处理不能兼得的选择",
        "expression_mode_hypothesis": "一人正脸讲述并用可见动作承载冲突",
        "business_attribution_hypothesis": "观众可能把表达方式归因给本人",
        "assumptions": ["具体受众反应仍待真实样片验证"],
    }
    return {
        "schema_version": "ip-director-route-result-v2",
        "epistemic_state": "creative_hypothesis",
        "facts_used": copy.deepcopy(facts),
        "semantic_kernel": {
            "surface_terms": ["果农", "果园", "水果"],
            "head_concept_hypothesis": "长期观察如何变成人的表达",
            "literal_action": {
                "statement": "本人经营果园并把观察讲成方言短段子",
                "fact_refs": ["f1", "f3"],
            },
            "human_action_hypothesis": "把日常观察翻译成人的选择",
            "relationship_hypothesis": "讲述者和听众重新理解彼此",
            "social_rule_hypothesis": "普通经验被说清后可能获得公共意义",
            "desire_conflict_hypothesis": "既要保留自己的语言又要让陌生人理解",
        },
        "directions": [
            {
                "id": "d-near",
                "semantic_distance": "near",
                "industry_role": "subject",
                "content_subject_hypothesis": "现场行业判断",
                **{**shared, "association_path_hypothesis": ["果园", "判断", "结果"]},
                "far_deletion_test": None,
            },
            {
                "id": "d-mid",
                "semantic_distance": "mid",
                "industry_role": "metaphor",
                "content_subject_hypothesis": "普通人的取舍与责任",
                **shared,
                "far_deletion_test": None,
            },
            {
                "id": "d-far",
                "semantic_distance": "far",
                "industry_role": "absent",
                "content_subject_hypothesis": "成年人如何解释自己的选择",
                **shared,
                "far_deletion_test": {
                    "removed_surface_terms": ["果农", "果园", "水果"],
                    "remaining_human_subject_hypothesis": "成年人如何解释自己的选择",
                    "ownership_fact_refs": ["f2", "f3", "f4"],
                },
            },
        ],
        "recommendation": {
            "selected_direction_ref": "d-mid",
            "fact_refs": ["f2", "f3", "f4"],
            "assumptions": ["本人能持续把观察转成具体冲突"],
            "reason_hypothesis": "它可能兼顾主体所有权与更广的人类矛盾",
            "tradeoff_hypothesis": "放弃一部分直接行业证明",
            "why_not_near_hypothesis": "近路线不足以验证跨行业的人物吸引力",
        },
    }


def _valid_story():
    module = _load_module()
    route = _valid_route()
    return {
        "schema_version": "ip-director-story-result-v1",
        "epistemic_state": "creative",
        "source_route_sha256": module.canonical_sha256(route),
        "selected_direction_ref": "d-mid",
        "facts_used": ["f1", "f3", "f4", "f5"],
        "creative_assumptions": ["具体姐弟人物、外地机会和家庭责任冲突均为虚构"],
        "commercial_object_mode": "absent",
        "substitution_test": "商业对象退出后，人物在旧承诺和未来选择之间的因果仍完整，因此不进入故事",
        "story_world": {
            "actors": ["准备离开家乡的姐姐", "认为她必须留下的弟弟"],
            "trigger": "姐姐收到一份必须立刻答复的外地机会",
            "want": "姐姐想为自己的未来作一次选择又不愿被家人视为逃跑",
            "goal": "当天取得弟弟对她离开的明确支持",
            "initial_tactic": "姐姐先承诺继续承担家里所有旧责任来换取同意",
            "counterforce": "弟弟发现这个承诺根本无法兑现并拒绝接受安慰",
            "feedback": "越想什么都保留，姐弟之间越确认她没有真正作出选择",
            "strategy_change": "姐姐撤回无法兑现的承诺并说出自己必须放下的责任",
            "costly_choice": "在维持永远可靠的姐姐形象和获得真实离开之间选择后者",
            "cost": "她接受弟弟会在一段时间内失望，并失去永远可靠的自我形象",
            "relationship_before": "姐弟以她无限承担责任维持表面稳定",
            "relationship_after": "姐弟第一次以有限责任重新协商彼此边界",
            "state_change": "姐姐取得离开的现实空间，家庭责任被重新分配",
            "viewer_question": "她会继续用空头承诺保住体面，还是承认自己必须放下一部分",
            "causal_edges": [
                {"from": "trigger", "to": "initial_tactic", "because": "当天期限迫使她先争取支持"},
                {"from": "initial_tactic", "to": "feedback", "because": "全盘承担的承诺无法兑现"},
                {"from": "feedback", "to": "strategy_change", "because": "弟弟拒绝使安慰策略失效"},
                {"from": "strategy_change", "to": "costly_choice", "because": "撤回承诺暴露了真实取舍"},
                {"from": "costly_choice", "to": "state_change", "because": "承担失望才释放了离开的空间"},
            ],
        },
        "business_bridge": {
            "meaning_attributed_to_subject": "把能从具体劳动看见人类取舍的观察力归因给本人",
            "connection_to_objective": "故事外由稳定场景和本人表达连接长期影响力目标",
        },
        "logline": "当一份必须当天答复的外地机会逼近，想离开又怕被家人视为逃跑的姐姐先许诺继续承担所有责任，却被弟弟当场拆穿，最终她宁可失去永远可靠的形象，也撤回空头承诺并重新划定了姐弟之间的责任边界。",
    }


def test_all_frozen_briefs_are_valid_and_story_scoped() -> None:
    module = _load_module()
    suite = _suite()
    assert suite["schema_version"] == "ip-director-loop-scenario-suite-v1"
    assert suite["active_case_id"] == "DL1-fruit-grower-longterm"
    assert len(suite["cases"]) == 6
    for brief in suite["cases"]:
        assert module.validate_brief(brief) == []


def test_route_requires_parallel_near_mid_far_and_real_edge_mapping() -> None:
    module = _load_module()
    route = _valid_route()
    assert module.validate_route_result(route, _fruit_brief()) == []

    broken = copy.deepcopy(route)
    for direction in broken["directions"]:
        direction["semantic_distance"] = "far"
        direction["industry_role"] = "stage"
    broken["directions"][1]["structure_mapping"] = [
        {"source_edge": "同一句", "target_edge": "同一句"},
        {"source_edge": "同一句", "target_edge": "同一句"},
    ]
    codes = {issue["code"] for issue in module.validate_route_result(broken, _fruit_brief())}
    assert "route.distance_coverage" in codes
    assert "route.structure_edge_duplicate" in codes


def test_route_v2_keeps_exact_facts_and_reports_schema_drift_without_crashing() -> None:
    module = _load_module()
    route = _valid_route_v2()
    assert module.validate_route_result(route, _fruit_brief()) == []

    drifted = copy.deepcopy(route)
    drifted["schema_version"] = "ip-director-loop-route-result-v2"
    drifted["facts_used"][0]["statement"] = "本人一直经营果园十五年"
    drifted["semantic_kernel"]["literal_action"]["fact_refs"] = [{"id": "f1"}]
    codes = {issue["code"] for issue in module.validate_route_result(drifted, _fruit_brief())}
    assert "route_v2.schema" in codes
    assert "route_v2.fact_statement" in codes
    assert "route_v2.literal_fact_refs" in codes


def test_runner_defaults_to_agent_gateway_and_never_mixes_v1_contract_with_v2_method() -> None:
    runner = _load_runner()
    args = runner._parser().parse_args(
        [
            "--stage",
            "route",
            "--arm",
            "method",
            "--case-id",
            "DL1-fruit-grower-longterm",
            "--output",
            "unused.json",
        ]
    )
    assert args.transport == "gateway"
    contract, method = runner._prompt_paths(ASSET_ROOT, stage="route", arm="method")
    placebo_contract, placebo = runner._prompt_paths(ASSET_ROOT, stage="route", arm="placebo")
    assert contract.name == "director-route-output-contract-v2.md"
    assert placebo_contract == contract
    assert method.name == "director-route-method-v3.md"
    assert placebo.name == "director-route-placebo-v1.md"


def test_story_binds_frozen_route_and_requires_connected_distinct_causality() -> None:
    module = _load_module()
    route = _valid_route()
    story = _valid_story()
    assert module.validate_story_result(story, _fruit_brief(), route) == []

    broken = copy.deepcopy(story)
    broken["source_route_sha256"] = "0" * 64
    for field in module.STORY_TEXT_FIELDS:
        broken["story_world"][field] = "同一句废话"
    broken["story_world"]["causal_edges"] = []
    codes = {issue["code"] for issue in module.validate_story_result(broken, _fruit_brief(), route)}
    assert "story.route_sha" in codes
    assert "story.repetition" in codes
    assert "story.causal_edge_coverage" in codes


def test_absent_story_rejects_commercial_and_business_world_leaks() -> None:
    module = _load_module()
    story = _valid_story()
    story["logline"] += "，最后靠卖水果获得了大量订单"
    codes = {issue["code"] for issue in module.validate_story_result(story, _fruit_brief(), _valid_route())}
    assert "story.absent_object_leak" in codes
    assert "story.business_world_leak" in codes


def test_methods_and_contracts_are_sample_agnostic_and_stage_bounded() -> None:
    paths = [
        ASSET_ROOT / "director-route-output-contract-v1.md",
        ASSET_ROOT / "director-route-method-v1.md",
        ASSET_ROOT / "director-story-output-contract-v1.md",
        ASSET_ROOT / "director-story-method-v1.md",
        ASSET_ROOT / "director-route-output-contract-v2.md",
        ASSET_ROOT / "director-route-method-v2.md",
        ASSET_ROOT / "director-route-method-v3.md",
        ASSET_ROOT / "director-story-output-contract-v2.md",
        ASSET_ROOT / "director-story-method-v2.md",
    ]
    texts = [path.read_text(encoding="utf-8") for path in paths]
    for leaked_sample in (
        "黄金礼品",
        "黄金小礼品",
        "宝妈",
        "果农",
        "乡村龙太子",
        "一只大青蛙",
        "贵厨笔记",
        "领导送礼升职",
        "云沐荟",
    ):
        assert all(leaked_sample not in text for text in texts)
    assert "完成推荐后立即停止" in texts[1]
    assert "不重新发散" in texts[3]


def test_director_loop_stays_out_of_product_runtime() -> None:
    needles = (
        "ip_director_loop",
        "director-route-method-v1",
        "director-route-method-v2",
        "director-route-method-v3",
        "director-story-method-v1",
        "director-story-method-v2",
    )
    searched_roots = (ROOT / "backend", ROOT / "frontend", ROOT / "product" / "defaults")
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
            if any(needle in text for needle in needles):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def _gateway_test_root(tmp_path: Path, *, profile_enabled: bool) -> tuple[Path, Path]:
    root = tmp_path.resolve()
    state_dir = root / "backend" / ".deer-flow-ip-test"
    state_dir.mkdir(parents=True)
    (state_dir / ".ip-agent-test-mode.json").write_text(
        json.dumps(
            {
                "schema_version": "ip-agent-test-mode-v1",
                "root": str(root),
                "state_dir": str(state_dir),
                "profile": "evidence",
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "product-runtime-profile.yaml").write_text(
        f"schema_version: ip-agent-runtime-profile-v1\nenabled: {'true' if profile_enabled else 'false'}\n",
        encoding="utf-8",
    )
    return root, state_dir


def test_gateway_transport_refuses_enabled_product_runtime_pin(tmp_path: Path) -> None:
    runner = _load_runner()
    root, _ = _gateway_test_root(tmp_path, profile_enabled=True)

    with pytest.raises(RuntimeError, match="product runtime profile is enabled"):
        runner._validate_gateway_test_state(root)


def test_gateway_transport_requires_marked_state_and_disabled_profile(tmp_path: Path) -> None:
    runner = _load_runner()
    root, state_dir = _gateway_test_root(tmp_path, profile_enabled=False)

    assert runner._validate_gateway_test_state(root) == state_dir
    (state_dir / ".ip-agent-test-mode.json").unlink()
    with pytest.raises(RuntimeError, match="prepared, marked"):
        runner._validate_gateway_test_state(root)


def test_temporary_gateway_agent_is_zero_capability_and_removed(tmp_path: Path) -> None:
    runner = _load_runner()
    _, state_dir = _gateway_test_root(tmp_path, profile_enabled=False)
    agent_name = "ip-director-loop-test"
    agent_dir = state_dir / "users" / "default" / "agents" / agent_name

    with runner._temporary_gateway_agent(
        state_dir,
        agent_name=agent_name,
        model="paid-model-explicit",
        soul_text="contract plus method",
    ) as surface:
        config_path = agent_dir / "config.yaml"
        soul_path = agent_dir / "SOUL.md"
        config_text = config_path.read_text(encoding="utf-8")
        assert "model: paid-model-explicit" in config_text
        assert "skills: []" in config_text
        assert "tool_allowlist: []" in config_text
        assert "memory_enabled: false" in config_text
        assert soul_path.read_text(encoding="utf-8") == "contract plus method"
        assert stat.S_IMODE(agent_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
        assert len(surface["config_sha256"]) == 64

    assert not agent_dir.exists()


def test_gateway_run_body_sends_only_user_input_and_locks_identity() -> None:
    runner = _load_runner()
    body = runner._gateway_run_body(
        agent_name="ip-director-loop-test",
        model="paid-model-explicit",
        user_text="frozen brief only",
        thinking="enabled",
    )

    assert body["assistant_id"] == "ip-director-loop-test"
    assert body["context"]["agent_name"] == body["assistant_id"]
    assert body["context"]["model_name"] == "paid-model-explicit"
    assert body["input"] == {
        "messages": [{"role": "user", "content": "frozen brief only"}]
    }
    assert all(message["role"] == "user" for message in body["input"]["messages"])


def test_gateway_validation_requires_one_llm_and_zero_tools() -> None:
    runner = _load_runner()
    clean_summary = {
        "runtime_metadata": {
            "agent_name": "ip-director-loop-test",
            "model_name": "paid-model-explicit",
            "available_skills": [],
            "indexed_skill_names": [],
            "tool_allowlist": [],
            "assembled_tool_names": [],
            "memory_enabled": False,
            "thinking_enabled": True,
        },
        "llm_calls": [{"caller": "lead_agent"}],
        "tool_result_event_count": 0,
    }
    record = {
        "status": "success",
        "assistant_id": "ip-director-loop-test",
        "llm_call_count": 1,
    }
    assert runner._gateway_validation_issues(
        agent_name="ip-director-loop-test",
        model="paid-model-explicit",
        thinking="enabled",
        run_record=record,
        runtime_summary=clean_summary,
        tool_calls=[],
        tool_results=[],
        final_answer="{}",
    ) == []

    broken = copy.deepcopy(clean_summary)
    broken["llm_calls"].append({"caller": "lead_agent"})
    broken["tool_result_event_count"] = 1
    codes = {
        issue["code"]
        for issue in runner._gateway_validation_issues(
            agent_name="ip-director-loop-test",
            model="paid-model-explicit",
            thinking="enabled",
            run_record={**record, "llm_call_count": 2},
            runtime_summary=broken,
            tool_calls=[{"name": "unexpected"}],
            tool_results=[],
            final_answer="{}",
        )
    }
    assert codes == {"gateway.llm_count", "gateway.tool_call"}
