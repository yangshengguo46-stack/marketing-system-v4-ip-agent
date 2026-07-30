from __future__ import annotations

from copy import deepcopy

import pytest

from deerflow.personal_ip.differentiation import (
    DIFFERENTIATION_STATUSES,
    PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION,
    validate_differentiation_snapshot,
    validate_differentiation_transition,
)

EVIDENCE_REFS = [{"kind": "product_demo", "id": "demo-1"}]

DIFFERENTIATION_THESIS = {
    "primary_entity": {
        "entity_type": "product",
        "name": "IP Agent",
        "role": "让普通经营者持续形成可归因的公共影响力",
    },
    "supporting_entities": [
        {
            "entity_type": "person",
            "name": "创始人",
            "role": "用真实经营决策为产品提供可信证据",
        }
    ],
    "decision_context": {
        "category": "个人IP经营智能体",
        "target_publics": ["缺少内容团队的经营者"],
        "jobs_to_be_done": ["把专业能力变成持续被目标客户记住和选择的公共资产"],
        "alternatives": ["代运营团队", "通用内容生成工具", "经营者自己凭感觉发内容"],
        "points_of_parity": ["能产出选题和脚本", "支持多平台内容"],
        "desired_influence": ["当经营者要系统经营IP时优先想到并愿意验证IP Agent"],
        "desired_outcomes": ["adoption", "economic"],
        "time_horizon": "未来两个季度",
    },
    "contrast_field": {
        "competitor_territories": ["更快生成", "更多模板", "代替人工发稿"],
        "category_cliches": ["三秒钩子保证爆款", "一键复制头部账号"],
        "anti_benchmarks": ["只展示漂亮成片而不展示经营结果"],
        "distant_analogues": ["企业经营驾驶舱", "电影制片体系"],
        "cultural_tension": "创作者追求即时流量，经营者需要可积累且能产生选择的长期资产",
    },
    "proprietary_truth": {
        "evidence_refs": EVIDENCE_REFS,
        "rare_capabilities": ["把策略、制作、发布、数据和复盘放在一条不可变证据链"],
        "mechanisms": ["发布前盲预测与发布后同回执复盘"],
        "history": ["从真实本地智能体产品和经营工作流中形成"],
        "relationships_access": ["可接触真实经营者的一线决策与结果"],
        "rights_assets": ["自有产品代码和自有经营数据"],
    },
    "strategic_difference": {
        "value_created": "降低个人IP从判断到验证的系统性成本",
        "meaning_created": "让经营者凭真实证据建立影响力，而不是扮演流量人设",
        "reason_to_choose": "它管理的是从影响力到采用和交易的经营闭环，不只是生成内容",
        "reason_to_believe": ["所有判断都能追溯到版本、发布回执和真实结果"],
        "sacrifice": ["不承诺单条必爆", "不服务只求批量灌稿而拒绝复盘的工作方式"],
        "relevance_hypothesis": "目标经营者会因为判断可追溯、试错可复盘而更愿意持续采用",
        "copy_requirements": ["必须展示真实决策、限制、动作和结果"],
    },
    "dramatic_engine": {
        "protagonist": "正在用自己的产品验证个人IP经营方法的创始人",
        "public_desire": "证明一个普通经营者也能建立可积累的公共影响力",
        "counterforce": "资源有限、平台噪声和对速成爆款的诱惑",
        "recurring_choice": "选择公开真实失败并修正，还是只包装成功",
        "cost_and_state_change": "每次公开判断都承担声誉成本，并用结果改变下一版规则",
        "relationship_engine": "创始人、产品、真实用户和市场反馈互相施压",
        "world": "一个人用本地智能体经营八个平台的公开实验场",
        "event_generators": ["新用户冷启动", "账号诊断", "一次发布实验", "失败复盘", "产品能力升级"],
        "genre_emotional_promise": "经营纪录片式的真实、压力和阶段性兑现",
        "point_of_view": "只说当时知道什么、为何这样选、结果如何",
    },
    "distinctive_encoding": {
        "verbal_signals": ["先给判断，再给证据和下一步实验"],
        "visual_signals": ["真实工作台、版本差异和结果回执同框"],
        "sonic_signals": ["克制的人声和真实操作声"],
        "character_signals": ["承认未知、公开代价、愿意改判"],
        "spatial_ritual_signals": ["每次发布前冻结判断，发布后回到同一工作台复盘"],
        "behavioral_product_signals": ["让用户亲自选择方向并看到证据链"],
        "invariants": ["真实证据优先", "内容服务影响力与采用结果", "不把平台规则当核心论断"],
        "controlled_variables": ["题材", "节奏", "平台适配", "真人或非真人呈现"],
        "forbidden_combinations": ["套用竞品口号和视觉资产", "用伪科学名词替代可观察机制"],
        "attribution_targets": ["不出现名字时仍能被识别为IP Agent的经营实验"],
    },
    "operating_fit": {
        "capacity_constraints": ["创始人每天可投入两小时"],
        "evidence_supply": ["开发记录", "用户试用", "发布和转化结果"],
        "channel_constraints": ["八个平台做适配但共享同一核心论断"],
        "cost_risk": ["真实结果积累慢，早期不能靠大规模投流掩盖问题"],
        "extension_rules": ["任何新栏目都必须强化同一选择理由或产生新的验证证据"],
    },
    "validation": {
        "evidence_level": "owner_evidence",
        "observations": [],
        "inferences": ["目标用户可能重视可追溯判断"],
        "hypotheses": ["证据链表达会提升目标用户对产品可信度的具体追问"],
        "tests": [
            {
                "test_id": "pilot-1",
                "prediction": "目标经营者会提出关于证据、限制或适用条件的具体问题",
                "observation_window": "发布后14天",
                "success_signal": "出现可归因的产品试用或具体经营咨询",
                "failure_condition": "只有泛赞或播放，没有具体追问、试用或咨询",
            }
        ],
        "failure_conditions": ["连续三轮试播只有泛流量而没有识别、意向或采用信号"],
        "retirement_reason": "",
    },
}


def test_complete_pilot_thesis_is_valid_and_versioned() -> None:
    assert PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION == "ip-differentiation-thesis-v1"
    assert DIFFERENTIATION_STATUSES == (
        "candidate",
        "pilot",
        "provisionally_adopted",
        "validated",
        "retired",
    )
    validate_differentiation_snapshot(
        status="pilot",
        evidence_refs=EVIDENCE_REFS,
        **DIFFERENTIATION_THESIS,
    )


def test_candidate_requires_a_choice_reason_belief_and_sacrifice() -> None:
    for field in ("reason_to_choose", "reason_to_believe", "sacrifice"):
        thesis = deepcopy(DIFFERENTIATION_THESIS)
        thesis["strategic_difference"][field] = [] if field != "reason_to_choose" else ""
        with pytest.raises(ValueError, match=field):
            validate_differentiation_snapshot(
                status="candidate",
                evidence_refs=EVIDENCE_REFS,
                **thesis,
            )


def test_pilot_rejects_viral_guarantees_and_neuroscience_shortcuts() -> None:
    for claim, expected in (
        ("这个表达一定会火", "cannot guarantee"),
        ("这个画面触发多巴胺，所以用户不会划走", "observable"),
    ):
        thesis = deepcopy(DIFFERENTIATION_THESIS)
        thesis["validation"]["hypotheses"] = [claim]
        with pytest.raises(ValueError, match=expected):
            validate_differentiation_snapshot(
                status="pilot",
                evidence_refs=EVIDENCE_REFS,
                **thesis,
            )


def test_transition_is_deliberate_and_retirement_requires_reason() -> None:
    assert validate_differentiation_transition(None, "candidate") == "candidate"
    assert validate_differentiation_transition("candidate", "pilot") == "pilot"
    with pytest.raises(ValueError, match="next differentiation status"):
        validate_differentiation_transition("candidate", "validated")

    thesis = deepcopy(DIFFERENTIATION_THESIS)
    with pytest.raises(ValueError, match="retirement_reason"):
        validate_differentiation_snapshot(
            status="retired",
            evidence_refs=EVIDENCE_REFS,
            **thesis,
        )
