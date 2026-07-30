from __future__ import annotations

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_brand import PersonalIPBrandRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.strategy_methodology import (
    PERSONAL_IP_STRATEGY_METHOD_VERSION,
    STRATEGY_STAGES,
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
        {"experiment_id": "pilot-1", "role": "reach"},
        {"experiment_id": "pilot-2", "role": "trust"},
        {"experiment_id": "pilot-3", "role": "conversion"},
    ],
    "conversion_path": "内容→体验→诊断→付费",
    "success_metrics": ["有效咨询", "付费客户"],
    "adjustment_rules": ["有播放无咨询则重做付费问题"],
}


@pytest.mark.asyncio
async def test_strategy_is_the_only_subject_model_and_requires_observed_validation(tmp_path) -> None:
    assert STRATEGY_STAGES[-2:] == ("commercial_signal_observed", "scaling")
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    try:
        sf = get_session_factory()
        assert sf is not None
        subjects = PersonalIPSubjectRepository(sf)
        strategies = PersonalIPBrandRepository(sf)
        subject = await subjects.create(owner_user_id="user-1", display_name="老杨")

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

        with pytest.raises(ValueError, match="next strategy stage"):
            await strategies.create_strategy_version(
                owner_user_id="user-1",
                operation_key="strategy:jump",
                subject_id=subject["id"],
                stage="positioning_candidates",
                evidence_refs=evidence_refs,
            )

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
        assert len(await strategies.list_strategies("user-1", subject_id=subject["id"])) == len(STRATEGY_STAGES)
        assert await strategies.get_latest_strategy(subject["id"], owner_user_id="user-2") is None
    finally:
        await close_engine()
