from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.account_diagnosis import (
    ACCOUNT_DIAGNOSIS_CONTRACT_VERSION,
    ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION,
    CONTENT_MECHANISM_LAYERS,
    FUNNEL_STAGES,
    PersonalIPAccountDiagnosticContextService,
    _coverage_declares_complete,
    _has_conversion_metric,
    _unique_record_count,
    compile_account_diagnosis,
)
from deerflow.skills.parser import parse_skill_file
from deerflow.skills.types import SkillCategory

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_DIAGNOSIS_SKILLS = {
    "diagnose-douyin-account",
    "diagnose-wechat-channels-account",
    "diagnose-wechat-official-account",
    "diagnose-xiaohongshu-account",
    "diagnose-x-account",
    "diagnose-instagram-account",
    "diagnose-youtube-account",
    "diagnose-tiktok-account",
}


def _context(
    *,
    ready: bool = True,
    commercial_outcomes: bool = True,
    intent_state: str = "fail",
    conversion_state: str = "fail",
    influence_state: str = "fail",
) -> dict:
    return {
        "contract_version": ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION,
        "context_digest": "context-digest",
        "generated_at": "2026-07-30T12:00:00Z",
        "account": {"id": "acct-1", "platform": "douyin"},
        "strategy": {
            "id": "strategy-1",
            "objective_system": {
                "asset_mechanism": "influence",
                "influence_goals": [{"goal": "形成正确识别"}],
                "behavioral_goals": [{"behavior": "产生有效意向"}],
                "economic_goals": [{"outcome": "形成真实转化"}],
                "priority_order": ["influence", "behavioral", "economic"],
            },
        },
        "sample": {"decision_ready": ready},
        "coverage": {"commercial_outcomes": commercial_outcomes},
        "observed_signal_states": {
            "intent": intent_state if commercial_outcomes else "unmeasured",
            "conversion": (conversion_state if commercial_outcomes else "unmeasured"),
        },
        "asset_signal_states": {
            "influence": influence_state,
            "behavioral": "fail" if commercial_outcomes else "unmeasured",
            "economic": "fail" if commercial_outcomes else "unmeasured",
        },
        "evidence_index": [
            {"kind": "metric_observation", "id": "metric-1"},
            {"kind": "platform_observation", "id": "platform-1"},
            {"kind": "platform_observation", "id": "platform-2"},
            {"kind": "strategy_version", "id": "strategy-1"},
        ],
        "platform_observations": [
            {
                "id": "platform-1",
                "dataset": "account_profile",
                "status": "observed",
                "observed_at": "2026-07-20T00:00:00Z",
                "summary": {
                    "recommendation_eligibility": "restricted",
                    "remediation_status": "pending",
                    "restriction_reason_id": "reason-1",
                },
            },
            {
                "id": "platform-2",
                "dataset": "account_profile",
                "status": "observed",
                "observed_at": "2026-07-30T00:00:00Z",
                "summary": {
                    "recommendation_eligibility": "restricted",
                    "remediation_status": "appeal_denied",
                    "restriction_reason_id": "reason-1",
                },
            },
        ],
    }


def _assessment(
    *,
    decision: str = "adjust_and_retest",
    classification: str = "self_entertainment",
    primary_failure_domain: str = "content",
    structural_issue_codes: list[str] | None = None,
    structure_refs: list[dict] | None = None,
    recommendation_eligibility: str = "unknown",
) -> dict:
    mechanisms = []
    for index, layer in enumerate(CONTENT_MECHANISM_LAYERS):
        mechanisms.append(
            {
                "layer": layer,
                "state": "fail" if index == 0 else "unmeasured",
                "claim": "前三条样本没有建立稳定的继续观看行为。" if index == 0 else "当前证据没有测量这一层。",
                "evidence_refs": ([{"kind": "metric_observation", "id": "metric-1"}] if index == 0 else []),
            }
        )
    funnel = [
        {
            "stage": stage,
            "state": "fail",
            "claim": f"{stage} 在当前样本中未达到既定失败条件。",
            "evidence_refs": [{"kind": "metric_observation", "id": "metric-1"}],
        }
        for stage in FUNNEL_STAGES
    ]
    return {
        "platform_role": "constraint_and_amplifier",
        "mechanisms": mechanisms,
        "funnel": funnel,
        "account_structure": {
            "recommendation_eligibility": recommendation_eligibility,
            "audience_positioning_fit": "unknown",
            "identity_business_fit": "unknown",
            "structural_issue_codes": structural_issue_codes or [],
            "evidence_refs": structure_refs or [],
        },
        "primary_failure_domain": primary_failure_domain,
        "decision": decision,
        "classification": classification,
        "confidence": 0.72,
        "rationale": ["内容与商业漏斗都需要下一轮对照实验。"],
        "next_experiment": {
            "hypothesis": "缩小选题并提前给出具体利益点会改善有效意向。",
            "content_changes": ["只改开头承诺与案例证据"],
            "predicted_signals": ["有效咨询率高于当前样本"],
            "failure_condition": "连续三个样本仍没有有效意向。",
            "minimum_post_count": 3,
            "observation_window": "三个同平台、同受众、同转化入口的发布样本",
            "keep_platform_constant": True,
        },
    }


@pytest.mark.asyncio
async def test_diagnostic_context_is_owner_scoped_and_content_first() -> None:
    accounts = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "acct-1",
                "subject_id": "subject-1",
                "platform": "douyin",
                "display_name": "测试账号",
                "status": "active",
            }
        )
    )
    receipts = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": f"receipt-{index}",
                    "status": "published",
                    "published_at": f"2026-07-2{index}T00:00:00Z",
                }
                for index in range(1, 4)
            ]
        )
    )
    metrics = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": f"metric-{index}",
                    "receipt_id": f"receipt-{index}",
                    "scope": "post",
                    "metric_mode": "snapshot",
                    "status": "observed",
                    "observed_at": f"2026-07-2{index}T12:00:00Z",
                    "metrics": {
                        "views": 100 * index,
                        "qualified_leads": 0,
                        "orders": 0,
                    },
                    "coverage": {
                        "complete": True,
                        "scope_limit": "tracked_post_only",
                    },
                }
                for index in range(1, 4)
            ]
        )
    )
    observations = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": "platform-account",
                    "dataset": "account_profile",
                    "status": "observed",
                    "source": "browser",
                    "observed_at": "2026-07-30T01:00:00Z",
                    "records": [{}],
                    "summary": {"recommendation_eligibility": "eligible"},
                    "coverage": {"complete": True},
                },
                {
                    "id": "platform-content",
                    "dataset": "content_metrics",
                    "status": "partial",
                    "source": "browser",
                    "observed_at": "2026-07-30T01:00:00Z",
                    "records": [{"id": "post-1"}, {"id": "post-2"}, {"id": "post-3"}],
                    "summary": {},
                    "coverage": {"complete": False},
                },
            ]
        )
    )
    retrospectives = SimpleNamespace(list=AsyncMock(return_value=[]))
    brand = SimpleNamespace(
        get_latest_strategy=AsyncMock(
            return_value={
                "id": "strategy-1",
                "stage": "pilot_running",
                "mode": "monetization_first",
                "business_model": {
                    "objective_system": {
                        "asset_mechanism": "influence",
                        "influence_goals": [{"goal": "正确识别"}],
                        "behavioral_goals": [{"behavior": "有效咨询"}],
                        "economic_goals": [{"outcome": "真实收入"}],
                        "priority_order": [
                            "influence",
                            "behavioral",
                            "economic",
                        ],
                    }
                },
            }
        )
    )
    differentiation = SimpleNamespace(
        get_latest=AsyncMock(
            return_value={
                "id": "difference-1",
                "status": "pilot",
                "decision_context": {
                    "desired_influence": ["正确归因"],
                    "desired_outcomes": ["有效咨询"],
                },
                "strategic_difference": {
                    "reason_to_choose": "公开真实经营证据",
                    "sacrifice": ["不承诺必爆"],
                },
            }
        ),
        list_observations=AsyncMock(
            return_value=[
                {
                    "id": "asset-observation-1",
                    "differentiation_version_id": "difference-1",
                    "observation_type": "recognition",
                    "source": "audience_feedback",
                    "observed_at": "2026-07-30T02:00:00Z",
                    "coverage_status": "complete",
                    "measures": {"result": "supports"},
                }
            ]
        ),
    )

    context = await PersonalIPAccountDiagnosticContextService(
        accounts=accounts,
        brand=brand,
        differentiation=differentiation,
        metrics=metrics,
        platform_observations=observations,
        publish_receipts=receipts,
        retrospectives=retrospectives,
    ).build(owner_user_id="owner-1", account_id="acct-1")

    assert context["sample"]["decision_ready"] is True
    assert context["sample"]["evaluated_post_count"] == 3
    assert context["coverage"]["commercial_outcomes"] is True
    assert context["observed_signal_states"] == {
        "intent": "fail",
        "conversion": "fail",
    }
    assert context["asset_signal_states"] == {
        "influence": "pass",
        "behavioral": "unmeasured",
        "economic": "unmeasured",
    }
    assert context["strategy"]["objective_system"]["asset_mechanism"] == "influence"
    assert {"kind": "ip_asset_observation", "id": "asset-observation-1"} in context["evidence_index"]
    assert context["guardrails"]["content_is_primary"] is True
    assert context["guardrails"]["low_reach_alone_can_trigger_new_account"] is False
    accounts.get.assert_awaited_once_with("acct-1", owner_user_id="owner-1")
    receipts.list.assert_awaited_once_with(
        "owner-1",
        account_id="acct-1",
        limit=100,
    )
    brand.get_latest_strategy.assert_awaited_once_with(
        "subject-1",
        owner_user_id="owner-1",
    )


@pytest.mark.asyncio
async def test_diagnostic_context_does_not_treat_stale_content_as_current_evidence() -> None:
    accounts = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "acct-1",
                "platform": "douyin",
                "display_name": "旧账号",
                "status": "active",
            }
        )
    )
    receipts = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": f"receipt-{index}",
                    "status": "published",
                    "published_at": f"2020-07-0{index}T00:00:00Z",
                }
                for index in range(1, 4)
            ]
        )
    )
    metrics = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": f"metric-{index}",
                    "receipt_id": f"receipt-{index}",
                    "scope": "account",
                    "metric_mode": "window_total",
                    "status": "observed",
                    "observed_at": f"2020-07-0{index}T12:00:00Z",
                    "metrics": {
                        "qualified_leads": 0,
                        "orders": 0,
                    },
                    "coverage": {"complete": True},
                }
                for index in range(1, 4)
            ]
        )
    )
    observations = SimpleNamespace(
        list=AsyncMock(
            return_value=[
                {
                    "id": "old-content",
                    "dataset": "content_metrics",
                    "status": "observed",
                    "source": "browser",
                    "observed_at": "2020-07-03T12:00:00Z",
                    "records": [
                        {"id": "post-1"},
                        {"id": "post-2"},
                        {"id": "post-3"},
                    ],
                    "summary": {},
                    "coverage": {"complete": True},
                },
                {
                    "id": "old-conversions",
                    "dataset": "conversions",
                    "status": "observed",
                    "source": "browser",
                    "observed_at": "2020-07-03T12:00:00Z",
                    "records": [],
                    "summary": {
                        "intent_state": "fail",
                        "conversion_state": "fail",
                    },
                    "coverage": {"complete": True},
                },
            ]
        )
    )

    context = await PersonalIPAccountDiagnosticContextService(
        accounts=accounts,
        metrics=metrics,
        platform_observations=observations,
        publish_receipts=receipts,
        retrospectives=SimpleNamespace(list=AsyncMock(return_value=[])),
    ).build(owner_user_id="owner-1", account_id="acct-1")

    assert context["sample"]["known_post_count"] == 3
    assert context["sample"]["evaluated_post_count"] == 0
    assert context["sample"]["decision_ready"] is False
    assert context["coverage"]["content_performance"] is False
    assert context["coverage"]["commercial_outcomes"] is False
    assert context["observed_signal_states"] == {
        "intent": "unmeasured",
        "conversion": "unmeasured",
    }
    assert context["guardrails"]["content_evidence_max_age_days"] == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("metric_scope", ["post", "account"])
async def test_only_published_post_metrics_contribute_to_sample_count(
    metric_scope: str,
) -> None:
    context = await PersonalIPAccountDiagnosticContextService(
        accounts=SimpleNamespace(
            get=AsyncMock(
                return_value={
                    "id": "acct-1",
                    "platform": "douyin",
                    "display_name": "测试账号",
                    "status": "active",
                }
            )
        ),
        metrics=SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": f"metric-{index}",
                        "receipt_id": f"never-published-{index}",
                        "scope": metric_scope,
                        "metric_mode": ("snapshot" if metric_scope == "post" else "window_total"),
                        "status": "observed",
                        "observed_at": "2026-07-30T01:00:00Z",
                        "metrics": {
                            "views": 100,
                            "qualified_leads": 0,
                            "orders": 0,
                        },
                        "coverage": {"complete": True},
                    }
                    for index in range(1, 4)
                ]
            )
        ),
        platform_observations=SimpleNamespace(list=AsyncMock(return_value=[])),
        publish_receipts=SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": f"receipt-{index}",
                        "status": "published",
                        "published_at": "2026-07-30T00:00:00Z",
                    }
                    for index in range(1, 4)
                ]
            )
        ),
        retrospectives=SimpleNamespace(list=AsyncMock(return_value=[])),
    ).build(owner_user_id="owner-1", account_id="acct-1")

    assert context["sample"]["metric_linked_post_count"] == 0
    assert context["sample"]["evaluated_post_count"] == 0
    assert context["sample"]["decision_ready"] is False
    if metric_scope == "post":
        assert context["metric_observations"] == []
        assert not any(ref["kind"] == "metric_observation" for ref in context["evidence_index"])
    else:
        assert len(context["metric_observations"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metric_variant",
    [
        "partial_account_window",
        "split_account_windows",
        "incomplete_post_rows",
    ],
)
async def test_incomplete_metrics_do_not_prove_commercial_outcomes(
    metric_variant: str,
) -> None:
    if metric_variant == "partial_account_window":
        metric_rows = [
            {
                "id": "metric-partial",
                "scope": "account",
                "metric_mode": "window_total",
                "status": "partial",
                "observed_at": "2026-07-30T01:00:00Z",
                "metrics": {
                    "qualified_leads": 0,
                    "orders": 0,
                },
                "coverage": {
                    "complete": False,
                    "scope_limit": "one_surface_only",
                },
            }
        ]
        published_receipts = []
    elif metric_variant == "split_account_windows":
        metric_rows = [
            {
                "id": "metric-intent-window",
                "scope": "account",
                "metric_mode": "window_total",
                "status": "observed",
                "observed_at": "2026-07-30T01:00:00Z",
                "metrics": {"qualified_leads": 0},
                "coverage": {"complete": True},
            },
            {
                "id": "metric-conversion-window",
                "scope": "account",
                "metric_mode": "window_total",
                "status": "observed",
                "observed_at": "2026-07-30T01:00:00Z",
                "metrics": {"orders": 0},
                "coverage": {"complete": True},
            },
        ]
        published_receipts = []
    else:
        metric_rows = [
            {
                "id": f"metric-{index}",
                "receipt_id": f"receipt-{index}",
                "scope": "post",
                "metric_mode": "snapshot",
                "status": "observed",
                "observed_at": "2026-07-30T01:00:00Z",
                "metrics": {
                    "qualified_leads": 0,
                    "orders": 0,
                },
                "coverage": {
                    "complete": False,
                    "scope_limit": "comments_only",
                },
            }
            for index in range(1, 4)
        ]
        published_receipts = [
            {
                "id": f"receipt-{index}",
                "status": "published",
                "published_at": "2026-07-30T00:00:00Z",
            }
            for index in range(1, 4)
        ]

    context = await PersonalIPAccountDiagnosticContextService(
        accounts=SimpleNamespace(
            get=AsyncMock(
                return_value={
                    "id": "acct-1",
                    "platform": "douyin",
                    "display_name": "测试账号",
                    "status": "active",
                }
            )
        ),
        metrics=SimpleNamespace(list=AsyncMock(return_value=metric_rows)),
        platform_observations=SimpleNamespace(
            list=AsyncMock(
                return_value=[
                    {
                        "id": "platform-content",
                        "dataset": "content_metrics",
                        "status": "observed",
                        "source": "browser",
                        "observed_at": "2026-07-30T01:00:00Z",
                        "records": [
                            {"id": "post-1"},
                            {"id": "post-2"},
                            {"id": "post-3"},
                        ],
                        "summary": {},
                        "coverage": {"complete": True},
                    }
                ]
            )
        ),
        publish_receipts=SimpleNamespace(list=AsyncMock(return_value=published_receipts)),
        retrospectives=SimpleNamespace(list=AsyncMock(return_value=[])),
    ).build(owner_user_id="owner-1", account_id="acct-1")

    assert context["sample"]["decision_ready"] is True
    assert context["coverage"]["commercial_outcomes"] is False
    assert context["observed_signal_states"] == {
        "intent": "unmeasured",
        "conversion": "unmeasured",
    }


def test_compile_accepts_evidence_bound_adjust_and_self_entertainment() -> None:
    result = compile_account_diagnosis(
        context=_context(),
        assessment=_assessment(),
    )

    assert result["contract_version"] == ACCOUNT_DIAGNOSIS_CONTRACT_VERSION
    assert result["assessment"]["decision"] == "adjust_and_retest"
    assert result["assessment"]["classification"] == "self_entertainment"
    assert result["diagnosis_digest"]


def test_brand_recognition_success_is_operating_content_despite_no_conversion() -> None:
    result = compile_account_diagnosis(
        context=_context(influence_state="pass"),
        assessment=_assessment(classification="operating_content"),
    )

    assert result["assessment"]["classification"] == "operating_content"
    assert result["outcome_states"] == {
        "influence": "pass",
        "behavioral": "fail",
        "economic": "fail",
    }


def test_low_reach_alone_cannot_trigger_a_new_account() -> None:
    with pytest.raises(
        ValueError,
        match="low reach or weak content alone cannot justify a new account",
    ):
        compile_account_diagnosis(
            context=_context(),
            assessment=_assessment(
                decision="start_new_account",
                classification="unproven",
            ),
        )


def test_new_account_requires_platform_observed_structural_evidence() -> None:
    result = compile_account_diagnosis(
        context=_context(),
        assessment=_assessment(
            decision="start_new_account",
            classification="self_entertainment",
            primary_failure_domain="account_structure",
            structural_issue_codes=["persistent_recommendation_ineligibility"],
            structure_refs=[
                {"kind": "platform_observation", "id": "platform-1"},
                {"kind": "platform_observation", "id": "platform-2"},
            ],
            recommendation_eligibility="restricted",
        ),
    )

    assert result["assessment"]["decision"] == "start_new_account"
    assert result["assessment"]["primary_failure_domain"] == "account_structure"


def test_one_current_restriction_does_not_prove_persistent_ineligibility() -> None:
    with pytest.raises(
        ValueError,
        match="at least two collection times",
    ):
        compile_account_diagnosis(
            context=_context(),
            assessment=_assessment(
                decision="start_new_account",
                classification="unproven",
                primary_failure_domain="account_structure",
                structural_issue_codes=["persistent_recommendation_ineligibility"],
                structure_refs=[{"kind": "platform_observation", "id": "platform-1"}],
                recommendation_eligibility="restricted",
            ),
        )


def test_persistent_restriction_normalizes_time_and_requires_latest_failed_repair() -> None:
    assessment = _assessment(
        decision="start_new_account",
        classification="self_entertainment",
        primary_failure_domain="account_structure",
        structural_issue_codes=["persistent_recommendation_ineligibility"],
        structure_refs=[
            {"kind": "platform_observation", "id": "platform-1"},
            {"kind": "platform_observation", "id": "platform-2"},
        ],
        recommendation_eligibility="restricted",
    )
    same_instant = deepcopy(_context())
    same_instant["platform_observations"][1]["observed_at"] = "2026-07-20T08:00:00+08:00"
    with pytest.raises(ValueError, match="at least two collection times"):
        compile_account_diagnosis(
            context=same_instant,
            assessment=assessment,
        )

    one_second_apart = deepcopy(_context())
    one_second_apart["platform_observations"][1]["observed_at"] = "2026-07-20T00:00:01Z"
    with pytest.raises(ValueError, match="at least seven days"):
        compile_account_diagnosis(
            context=one_second_apart,
            assessment=assessment,
        )

    latest_recovered = deepcopy(_context())
    latest_recovered["platform_observations"].append(
        {
            "id": "platform-3",
            "dataset": "account_profile",
            "status": "observed",
            "observed_at": "2026-07-30T11:00:00Z",
            "summary": {
                "recommendation_eligibility": "eligible",
                "restriction_reason_id": "reason-1",
                "remediation_status": "succeeded",
            },
        }
    )
    with pytest.raises(ValueError, match="latest account status must still show"):
        compile_account_diagnosis(
            context=latest_recovered,
            assessment=assessment,
        )

    stale_evidence = deepcopy(_context())
    stale_evidence["generated_at"] = "2026-08-02T00:00:00Z"
    with pytest.raises(ValueError, match="within the last 24 hours"):
        compile_account_diagnosis(
            context=stale_evidence,
            assessment=assessment,
        )

    unavailable_remediation = deepcopy(_context())
    unavailable_remediation["platform_observations"][1]["summary"]["remediation_status"] = "unavailable"
    with pytest.raises(ValueError, match="repair or appeal was exhausted"):
        compile_account_diagnosis(
            context=unavailable_remediation,
            assessment=assessment,
        )

    mismatched_reason = deepcopy(_context())
    mismatched_reason["platform_observations"][1]["summary"]["restriction_reason_id"] = "reason-2"
    with pytest.raises(ValueError, match="one stable restriction reason"):
        compile_account_diagnosis(
            context=mismatched_reason,
            assessment=assessment,
        )


def test_repairable_platform_restriction_has_an_adjust_and_retest_exit() -> None:
    assessment = _assessment(
        decision="adjust_and_retest",
        classification="operating_content",
        primary_failure_domain="platform_constraint",
        structure_refs=[{"kind": "platform_observation", "id": "platform-1"}],
        recommendation_eligibility="restricted",
    )
    for item in assessment["mechanisms"]:
        item["state"] = "pass"
        item["evidence_refs"] = [{"kind": "metric_observation", "id": "metric-1"}]
    for item in assessment["funnel"]:
        item["state"] = "pass"

    result = compile_account_diagnosis(
        context=_context(intent_state="pass", conversion_state="pass"),
        assessment=assessment,
    )

    assert result["assessment"]["decision"] == "adjust_and_retest"
    assert result["assessment"]["primary_failure_domain"] == "platform_constraint"


def test_measured_failure_cannot_be_softened_to_continue_unchanged() -> None:
    assessment = _assessment(
        decision="continue_current_account",
        classification="operating_content",
    )
    trust = next(item for item in assessment["funnel"] if item["stage"] == "trust")
    trust["state"] = "pass"
    with pytest.raises(
        ValueError,
        match="requires adjustment and retest",
    ):
        compile_account_diagnosis(
            context=_context(),
            assessment=assessment,
        )


def test_proven_self_entertainment_cannot_be_softened_to_unproven() -> None:
    with pytest.raises(
        ValueError,
        match="must not be softened",
    ):
        compile_account_diagnosis(
            context=_context(),
            assessment=_assessment(classification="unproven"),
        )


def test_observed_zero_intent_and_conversion_cannot_be_relabeled_unmeasured() -> None:
    assessment = _assessment(classification="unproven")
    for item in assessment["funnel"]:
        if item["stage"] in {"intent", "conversion"}:
            item["state"] = "unmeasured"
            item["evidence_refs"] = []

    with pytest.raises(
        ValueError,
        match="must match the server-observed signal state",
    ):
        compile_account_diagnosis(
            context=_context(),
            assessment=assessment,
        )


@pytest.mark.parametrize(
    "claim,error",
    [
        (
            "Eligibility guarantees distribution to non-followers.",
            "not a guarantee of distribution",
        ),
        (
            "Recommendation eligibility is a guarantee of distribution.",
            "not a guarantee of distribution",
        ),
        (
            "Eligible accounts are guaranteed distribution.",
            "not a guarantee of distribution",
        ),
        (
            "有推荐资格就会获得稳定分发。",
            "not a guarantee of distribution",
        ),
        (
            "你就是自嗨，作品高级只是自我感觉。",
            "without insulting",
        ),
        (
            "你拍这些不过是在孤芳自赏，所谓高级只是自我陶醉。",
            "without insulting",
        ),
    ],
)
def test_diagnosis_rejects_platform_certainty_and_hostile_language(
    claim: str,
    error: str,
) -> None:
    assessment = _assessment()
    assessment["rationale"] = [claim]

    with pytest.raises(ValueError, match=error):
        compile_account_diagnosis(
            context=_context(),
            assessment=assessment,
        )


def test_self_entertainment_requires_commercial_outcome_coverage() -> None:
    with pytest.raises(
        ValueError,
        match="requires measured influence, behavioral and economic outcomes",
    ):
        compile_account_diagnosis(
            context=_context(commercial_outcomes=False),
            assessment=_assessment(),
        )


def test_clicks_and_messages_do_not_count_as_completed_commercial_outcomes() -> None:
    assert _has_conversion_metric({"link_clicks": 10, "direct_messages": 2}) is False
    assert _has_conversion_metric({"qualified_leads": 0, "orders": 0}) is True
    assert _coverage_declares_complete({"complete": False}) is False
    assert _coverage_declares_complete({"coverage_status": "complete"}) is True
    assert (
        _unique_record_count(
            [
                {"post_id": "same-post", "views": 1},
                {"video_id": "same-post", "views": 2},
                {"id": "same-post", "views": 3},
            ]
        )
        == 1
    )
    assert (
        _unique_record_count(
            [
                {"url": "https://www.douyin.com/video/123"},
                {"url": ("https://www.douyin.com/video/123?from=creator&utm_source=test")},
                {"url": ("https://www.douyin.com/video/123/#comments")},
            ]
        )
        == 1
    )
    assert (
        _unique_record_count(
            [
                {"url": "https://www.youtube.com/watch?v=video-1"},
                {"url": "https://www.youtube.com/watch?v=video-2"},
            ]
        )
        == 2
    )


def test_insufficient_sample_forces_unproven_evidence_collection() -> None:
    assessment = _assessment(
        decision="insufficient_evidence",
        classification="unproven",
        primary_failure_domain="insufficient_evidence",
    )
    result = compile_account_diagnosis(
        context=_context(ready=False, commercial_outcomes=False),
        assessment=assessment,
    )

    assert result["assessment"]["decision"] == "insufficient_evidence"


def test_next_content_experiment_must_hold_the_platform_constant() -> None:
    assessment = _assessment()
    assessment["next_experiment"]["keep_platform_constant"] = False

    with pytest.raises(ValueError, match="Input should be True"):
        compile_account_diagnosis(
            context=_context(),
            assessment=assessment,
        )


def test_all_eight_platform_diagnosis_skills_share_the_compiler_and_dated_sources() -> None:
    public_root = REPO_ROOT / "skills" / "public"

    for skill_name in PLATFORM_DIAGNOSIS_SKILLS:
        skill_path = public_root / skill_name / "SKILL.md"
        parsed = parse_skill_file(skill_path, category=SkillCategory.PUBLIC)
        reference = (public_root / skill_name / "references" / "platform-evidence.md").read_text(encoding="utf-8")
        instructions = skill_path.read_text(encoding="utf-8")

        assert parsed is not None
        assert parsed.name == skill_name
        assert "personal_ip_account_diagnostic_context" in instructions
        assert "personal_ip_compile_account_diagnosis" in instructions
        assert "Last reviewed: 2026-07-30" in reference
        assert "https://" in reference

    operator = (public_root / "personal-ip-operator" / "SKILL.md").read_text(encoding="utf-8")
    default_config = (REPO_ROOT / "product" / "defaults" / "agents" / "ip-agent" / "config.yaml").read_text(encoding="utf-8")
    for skill_name in PLATFORM_DIAGNOSIS_SKILLS:
        assert skill_name in operator
        assert f"- {skill_name}" in default_config
