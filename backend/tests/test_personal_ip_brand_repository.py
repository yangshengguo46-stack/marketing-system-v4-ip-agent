from __future__ import annotations

from copy import deepcopy

import pytest
from test_personal_ip_differentiation import DIFFERENTIATION_THESIS, EVIDENCE_REFS

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_brand import PersonalIPBrandRepository
from deerflow.persistence.personal_ip_differentiation import PersonalIPDifferentiationRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.strategy_methodology import (
    PERSONAL_IP_STRATEGY_METHOD_VERSION,
    STRATEGY_STAGES,
    validate_strategy_snapshot,
)

PERSON_MODEL = {
    "basic_facts": {
        "age_context": "35岁",
        "gender_context": "男",
        "occupation": "AI产品创业者",
        "location_context": "中国大陆",
    },
    "history": ["做过企业营销与AI产品"],
    "expertise_evidence": ["有可运行产品"],
    "values_boundaries": ["只讲经过验证的东西"],
    "media_presence": {"photo_status": "reviewed_with_consent", "voice_status": "not_provided"},
    "capacity_constraints": ["每天可投入2小时"],
    "open_questions": [],
}

BUSINESS_MODEL = {
    "primary_goal": "用个人IP获取付费客户",
    "objective_system": {
        "asset_mechanism": "influence",
        "influence_goals": [
            {
                "goal": "让目标企业主把本产品与可验证的经营闭环联系起来",
                "target_public": "缺少内容团队的企业主",
                "success_signal": "目标企业主能正确复述产品解决的问题与差异",
            }
        ],
        "behavioral_goals": [
            {
                "behavior": "申请一次真实产品体验",
                "target_public": "正在评估智能体的潜在客户",
                "success_signal": "出现符合目标客户条件的体验申请",
            }
        ],
        "economic_goals": [
            {
                "outcome": "形成可持续的软件订阅与部署收入",
                "beneficiary": "产品经营主体",
                "success_signal": "出现完成付款并持续使用的目标客户",
            }
        ],
        "time_horizon": {
            "pilot_window": "首轮三个同平台样本发布后14天",
            "operating_horizon": "未来两个季度",
        },
        "priority_order": ["influence", "behavioral", "economic"],
        "guardrails": ["不以错误归因或夸大承诺换取短期转化"],
        "not_optimizing_now": ["泛人群播放量"],
    },
    "existing_assets": ["可演示的本地智能体"],
    "buyer_segments": ["缺少内容团队的企业主"],
    "paid_problems": ["不会持续经营个人IP"],
    "offer_options": ["软件订阅", "部署服务"],
    "proof": ["已有可运行产品"],
    "primary_monetization_path": {
        "buyer": "中小企业主",
        "paid_problem": "低成本持续经营个人IP",
        "offer": "软件订阅加部署服务",
        "conversion_path": "内容案例→体验→诊断→付费",
    },
    "reserved_paths": ["企业咨询"],
    "economics_constraints": ["先验证付费再扩大投流"],
    "open_questions": [],
}

BENCHMARK_RESEARCH = {
    "benchmarks": [
        {
            "benchmark_id": "bench-1",
            "platform": "douyin",
            "source_url": "https://example.com/1",
            "role": "business_model",
            "why_relevant": "同类服务",
            "observations": ["案例导向咨询"],
            "borrow": ["证据结构"],
            "avoid": ["收入承诺"],
        },
        {
            "benchmark_id": "bench-2",
            "platform": "xiaohongshu",
            "source_url": "https://example.com/2",
            "role": "content_system",
            "why_relevant": "持续选题",
            "observations": ["统一栏目"],
            "borrow": ["开发日志"],
            "avoid": ["工具清单"],
        },
        {
            "benchmark_id": "bench-3",
            "platform": "youtube",
            "source_url": "https://example.com/3",
            "role": "identity_expression",
            "why_relevant": "创业者表达",
            "observations": ["真人演示"],
            "borrow": ["观点加演示"],
            "avoid": ["过长铺垫"],
        },
    ]
}

POSITIONING_CANDIDATES = [
    {
        "candidate_id": "position-a",
        "working_title": "AI个人IP经营实战派",
        "buyer": "中小企业主",
        "problem": "无法稳定经营多平台",
        "promise": "把经营交给本地智能体",
        "proof": ["真实开发记录"],
        "difference": "公开经营结果",
        "monetization_path": "订阅加部署",
        "content_pillars": ["开发", "实验", "案例"],
        "risks": ["产品仍在验证"],
    },
    {
        "candidate_id": "position-b",
        "working_title": "一个人的智能体公司",
        "buyer": "个体创业者",
        "problem": "缺少内容团队",
        "promise": "用智能体跑通经营闭环",
        "proof": ["完整产品演示"],
        "difference": "以经营结果为中心",
        "monetization_path": "体验转付费",
        "content_pillars": ["一人公司", "实操", "复盘"],
        "risks": ["受众可能过宽"],
    },
]

LAUNCH_PACKAGE = {
    "selected_candidate_id": "position-a",
    "name_options": ["老杨的IP智能体", "杨老板AI实战", "一个人的智能体公司"],
    "handle_checks": [{"platform": "douyin", "name": "老杨的IP智能体", "status": "available"}],
    "avatar_direction": {"source": "creator_photo", "treatment": "本人半身照"},
    "bio_options": ["公开真实经营数据", "现场把个人IP做成生意"],
    "pinned_content": ["为什么做", "完整演示", "客户案例"],
    "pilot_experiments": [
        {
            "experiment_id": "pilot-1",
            "role": "reach",
            "target_audience": "缺少内容团队的企业主",
            "content_hypothesis": "真实展示一个人完成内容生产，会让目标企业主停下来判断是否适合自己",
            "evidence_level": "market_referenced",
            "evidence_refs": ["bench-2"],
            "mechanism_hypotheses": [
                {
                    "layer": "attention_prediction",
                    "claim": "一人完成原本需要团队的工作形成与既有经验相关的反差",
                    "predicted_signal": "目标人群的首段继续观看比例提高",
                    "failure_condition": "观众停留后仍无法复述视频要解决的问题",
                }
            ],
            "distribution_assumptions": ["平台把视频分发给创业和企业经营兴趣人群"],
            "observation_window": "发布后7天",
            "failure_rule": "没有获得目标人群停留或主页访问时，重做问题与首段表达",
            "uncertainty": "只有市场参照，还没有本账号发布证据",
        },
        {
            "experiment_id": "pilot-2",
            "role": "trust",
            "target_audience": "正在评估智能体能力的潜在客户",
            "content_hypothesis": "展示真实过程、限制和失败记录，比只展示结果更容易建立可信判断",
            "evidence_level": "market_referenced",
            "evidence_refs": ["bench-1", "bench-3"],
            "mechanism_hypotheses": [
                {
                    "layer": "emotion_identity",
                    "claim": "承认边界能减少潜在客户对夸大宣传的防御",
                    "predicted_signal": "评论和私信出现对过程、限制或适用条件的具体追问",
                    "failure_condition": "互动仍集中在泛泛称赞而没有具体判断",
                }
            ],
            "distribution_assumptions": ["视频获得足够的目标人群有效曝光"],
            "observation_window": "发布后7天",
            "failure_rule": "没有具体追问时，增加可验证过程和失败证据",
            "uncertainty": "市场样本支持表达方向，但本人可信度尚未验证",
        },
        {
            "experiment_id": "pilot-3",
            "role": "conversion",
            "target_audience": "愿意尝试个人IP智能体的中小企业主",
            "content_hypothesis": "给出低风险体验入口能把已建立的兴趣转成有效咨询",
            "evidence_level": "general_prior",
            "evidence_refs": [],
            "mechanism_hypotheses": [
                {
                    "layer": "behavior_conversion",
                    "claim": "明确下一步和适用条件能降低潜在客户采取行动的决策成本",
                    "predicted_signal": "出现符合目标客户条件的体验申请或咨询",
                    "failure_condition": "有主页访问但没有任何符合条件的下一步行动",
                }
            ],
            "distribution_assumptions": ["主页和体验入口可用且访问路径没有异常摩擦"],
            "observation_window": "发布后14天",
            "failure_rule": "有访问无行动时，检查承诺、资格说明和入口摩擦",
            "uncertainty": "尚无本账号转化基线，只能作为首轮可证伪假设",
        },
    ],
    "conversion_path": "内容→体验→诊断→付费",
    "success_metrics": ["有效咨询", "付费客户"],
    "adjustment_rules": ["有播放无咨询则重做付费问题"],
}


@pytest.mark.asyncio
async def test_strategy_is_immutable_owner_scoped_storage_without_stage_gates(tmp_path) -> None:
    assert STRATEGY_STAGES[-2:] == ("commercial_signal_observed", "scaling")
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    try:
        sf = get_session_factory()
        assert sf is not None
        subjects = PersonalIPSubjectRepository(sf)
        strategies = PersonalIPBrandRepository(sf)
        differentiation = PersonalIPDifferentiationRepository(sf)
        subject = await subjects.create(owner_user_id="user-1", display_name="老杨")
        difference_candidate = await differentiation.create_version(
            owner_user_id="user-1",
            operation_key="difference:candidate",
            subject_id=subject["id"],
            thesis_key="ip-agent-core",
            status="candidate",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        difference_pilot = await differentiation.create_version(
            owner_user_id="user-1",
            operation_key="difference:pilot",
            subject_id=subject["id"],
            thesis_key="ip-agent-core",
            status="pilot",
            evidence_refs=EVIDENCE_REFS,
            **DIFFERENTIATION_THESIS,
        )
        assert difference_candidate["version"] == 1

        evidence_refs = [{"kind": "user_interview", "id": "interview-1"}]
        first = await strategies.create_strategy_version(
            owner_user_id="user-1",
            operation_key="strategy:evidence",
            subject_id=subject["id"],
            stage="evidence_collecting",
            person_model={"basic_facts": {"occupation": "AI产品创业者"}},
            evidence_refs=evidence_refs,
        )
        assert first["method_version"] == PERSONAL_IP_STRATEGY_METHOD_VERSION

        writes = [
            ("person_model_draft", {"person_model": PERSON_MODEL}),
            ("business_model_draft", {"business_model": BUSINESS_MODEL}),
            ("benchmark_researching", {"benchmark_research": BENCHMARK_RESEARCH}),
            ("positioning_candidates", {"positioning_candidates": POSITIONING_CANDIDATES}),
            ("launch_package_ready", {"launch_package": LAUNCH_PACKAGE}),
            (
                "pilot_running",
                {
                    "validation": {
                        "pilot_started_at": "2026-07-29T00:00:00+00:00",
                        "experiment_ids": ["pilot-1", "pilot-2", "pilot-3"],
                    }
                },
            ),
        ]
        for index, (stage, payload) in enumerate(writes, start=2):
            if STRATEGY_STAGES.index(stage) >= STRATEGY_STAGES.index("positioning_candidates"):
                payload["differentiation_version_id"] = difference_pilot["id"]
            await strategies.create_strategy_version(
                owner_user_id="user-1",
                operation_key=f"strategy:{stage}",
                subject_id=subject["id"],
                stage=stage,
                evidence_refs=[{"kind": "user_interview", "id": f"evidence-{index}"}],
                **payload,
            )

        validation = {
            "pilot_started_at": "2026-07-29T00:00:00+00:00",
            "experiment_ids": ["pilot-1", "pilot-2", "pilot-3"],
            "commercial_signals": [{"kind": "qualified_lead", "count": 3}],
            "validation_decision": {
                "selected_candidate_id": "position-a",
                "decision": "continue_and_scale",
                "supporting_evidence": ["metric-1"],
            },
        }
        observed = await strategies.create_strategy_version(
            owner_user_id="user-1",
            operation_key="strategy:observed",
            subject_id=subject["id"],
            stage="commercial_signal_observed",
            validation=validation,
            evidence_refs=[{"kind": "metric_observation", "id": "metric-1"}],
        )
        assert observed["validation"]["validation_decision"]["decision"] == "continue_and_scale"

        scaled = await strategies.create_strategy_version(
            owner_user_id="user-1",
            operation_key="strategy:scaling",
            subject_id=subject["id"],
            stage="scaling",
            evidence_refs=[{"kind": "metric_observation", "id": "metric-1"}],
        )
        latest = await strategies.get_latest_strategy(subject["id"], owner_user_id="user-1")
        assert latest == scaled
        assert latest["stage"] == "scaling"
        assert latest["differentiation_version_id"] == difference_pilot["id"]
        assert len(await strategies.list_strategies("user-1", subject_id=subject["id"])) == len(STRATEGY_STAGES)
        assert await strategies.get_latest_strategy(subject["id"], owner_user_id="user-2") is None
    finally:
        await close_engine()


def test_strategy_storage_does_not_grade_creative_language() -> None:
    for claim in (
        "美食特写会释放多巴胺并提高完播",
        "这个反差开头一定会火",
    ):
        launch_package = deepcopy(LAUNCH_PACKAGE)
        launch_package["pilot_experiments"][0]["mechanism_hypotheses"][0]["claim"] = claim

        validate_strategy_snapshot(
            stage="launch_package_ready",
            mode="monetization_first",
            person_model=PERSON_MODEL,
            business_model=BUSINESS_MODEL,
            benchmark_research=BENCHMARK_RESEARCH,
            positioning_candidates=POSITIONING_CANDIDATES,
            launch_package=launch_package,
            validation={},
            evidence_refs=[{"kind": "user_interview", "id": "interview-1"}],
        )


def test_product_strategy_uses_product_evidence_instead_of_person_demographics() -> None:
    product_model = {
        "entity_type": "product",
        "basic_facts": {
            "category": "个人IP经营智能体",
            "lifecycle_stage": "公开试用",
            "operating_context": "本地部署并由经营者持续使用",
        },
        "history": ["从真实个人IP运营工作流中形成"],
        "capability_evidence": ["已有可运行产品和不可变经营账本"],
        "values_boundaries": ["不承诺必爆", "不伪造经营结果"],
        "public_interfaces": ["产品工作台", "创始人公开实验", "用户案例"],
        "capacity_constraints": ["创始人每天可投入两小时"],
        "stakeholders": ["试用经营者", "付费客户", "内容观众"],
        "open_questions": [],
    }

    validate_strategy_snapshot(
        stage="business_model_draft",
        mode="monetization_first",
        person_model=product_model,
        business_model={},
        benchmark_research={},
        positioning_candidates=[],
        launch_package={},
        validation={},
        evidence_refs=[{"kind": "product_demo", "id": "demo-1"}],
        subject_type="product",
    )


def test_partial_business_strategy_can_be_stored_for_later_reasoning() -> None:
    business_model = deepcopy(BUSINESS_MODEL)
    business_model["objective_system"].pop("behavioral_goals")

    validate_strategy_snapshot(
        stage="benchmark_researching",
        mode="monetization_first",
        person_model=PERSON_MODEL,
        business_model=business_model,
        benchmark_research={},
        positioning_candidates=[],
        launch_package={},
        validation={},
        evidence_refs=[],
    )
