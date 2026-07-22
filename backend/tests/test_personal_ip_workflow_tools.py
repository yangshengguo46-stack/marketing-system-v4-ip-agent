from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.audience_provider import AudiencePreflightResult
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins import (
    personal_ip_begin_publish_receipt_tool,
    personal_ip_promote_evidence_tool,
    personal_ip_read_evidence_promotion_tool,
    personal_ip_read_preflight_tool,
    personal_ip_read_publish_receipt_tool,
    personal_ip_read_retrospective_tool,
    personal_ip_record_publish_attempt_tool,
    personal_ip_run_preflight_tool,
    personal_ip_seal_retrospective_tool,
)
from deerflow.tools.builtins.personal_ip_workflow_tools import (
    _personal_ip_begin_publish_receipt,
    _personal_ip_promote_evidence,
    _personal_ip_read_evidence_promotion,
    _personal_ip_read_preflight,
    _personal_ip_read_publish_receipt,
    _personal_ip_read_retrospective,
    _personal_ip_record_publish_attempt,
    _personal_ip_run_preflight,
    _personal_ip_seal_retrospective,
)
from deerflow.tools.tools import BUILTIN_TOOLS


def test_personal_ip_workflow_tools_are_native_with_policy_promotion() -> None:
    tools = [
        personal_ip_run_preflight_tool,
        personal_ip_read_preflight_tool,
        personal_ip_begin_publish_receipt_tool,
        personal_ip_record_publish_attempt_tool,
        personal_ip_read_publish_receipt_tool,
        personal_ip_seal_retrospective_tool,
        personal_ip_read_retrospective_tool,
        personal_ip_promote_evidence_tool,
        personal_ip_read_evidence_promotion_tool,
    ]
    assert all(item in BUILTIN_TOOLS for item in tools)
    names = {item.name for item in tools}
    assert names == {
        "personal_ip_begin_publish_receipt",
        "personal_ip_promote_evidence",
        "personal_ip_read_evidence_promotion",
        "personal_ip_read_preflight",
        "personal_ip_read_publish_receipt",
        "personal_ip_read_retrospective",
        "personal_ip_record_publish_attempt",
        "personal_ip_run_preflight",
        "personal_ip_seal_retrospective",
    }
    assert not any("decide_evidence" in tool.name for tool in BUILTIN_TOOLS)


@pytest.mark.asyncio
async def test_run_preflight_keeps_local_identity_out_of_provider_request(monkeypatch) -> None:
    preflights = SimpleNamespace(
        seal=AsyncMock(
            return_value={
                "id": "preflight-1",
                "status": "sealed",
                "provider": "hllm-lite",
            }
        )
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            preflights=preflights,
        )
    )

    async def preflight(request):
        payload = request.to_payload()
        assert "acct-1" not in json.dumps(payload)
        assert "subject-1" not in json.dumps(payload)
        return AudiencePreflightResult(
            provider="hllm-lite",
            model_version="doubao-test",
            algorithm_version="lite-v0",
            request_digest=request.request_digest,
            audience_basis="aggregate_account_cohort",
            variants=[{"variant_id": "variant-1", "text": "候选文案"}],
        )

    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_workflow_tools._audience_preflight_provider",
        lambda: SimpleNamespace(preflight=preflight),
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    result = json.loads(
        await _personal_ip_run_preflight(
            runtime,
            operation_key="preflight:draft-1",
            subject_ids=["subject-1"],
            target_account_ids=["acct-1"],
            history=[
                {
                    "content_id": "published-1",
                    "published_at": "2026-07-20T08:00:00Z",
                    "platform": "douyin",
                    "title": "历史内容",
                    "content_type": "short_video",
                    "metrics": {"views": 1000, "likes": 90},
                }
            ],
            audience_profile={"cohort_label": "智能体创作者"},
            creator_profile={"voice": ["直接"]},
            target={
                "content_id": "draft-1",
                "title": "待发布",
                "description": "发布前预演",
            },
            variant_count=3,
        )
    )

    assert result["id"] == "preflight-1"
    kwargs = preflights.seal.await_args.kwargs
    assert kwargs["owner_user_id"] == "user-1"
    assert kwargs["subject_ids"] == ["subject-1"]
    assert kwargs["target_account_ids"] == ["acct-1"]
    assert kwargs["result"].variants[0].variant_id == "variant-1"


@pytest.mark.asyncio
async def test_native_workflow_tools_preserve_owner_scope_and_append_only_sequence() -> None:
    publish_receipts = SimpleNamespace(
        begin=AsyncMock(return_value={"id": "publish-1", "status": "planned"}),
        record_attempt=AsyncMock(
            return_value={
                "id": "publish-1",
                "status": "published",
                "attempts": [{"attempt_key": "attempt-1"}],
            }
        ),
        get=AsyncMock(return_value={"id": "publish-1", "attempts": []}),
    )
    preflights = SimpleNamespace(get=AsyncMock(return_value={"id": "preflight-1"}))
    retrospectives = SimpleNamespace(
        seal=AsyncMock(return_value={"id": "retro-1", "status": "measured"}),
        get=AsyncMock(return_value={"id": "retro-1", "prediction": {}, "outcome": {}}),
    )
    promotions = SimpleNamespace(
        propose=AsyncMock(return_value={"id": "promotion-1", "status": "approved"}),
        get=AsyncMock(return_value={"id": "promotion-1", "status": "approved"}),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=publish_receipts,
            preflights=preflights,
            retrospectives=retrospectives,
            evidence_promotions=promotions,
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    created = json.loads(
        await _personal_ip_begin_publish_receipt(
            runtime,
            operation_key="publish:draft-1",
            idempotency_key="idem:draft-1",
            account_id="acct-1",
            preflight_id="preflight-1",
            executor="browser",
            request={"variant_id": "variant-1", "caption": "候选文案"},
        )
    )
    attempted = json.loads(
        await _personal_ip_record_publish_attempt(
            runtime,
            receipt_id="publish-1",
            attempt_key="attempt-1",
            status="published",
            result={"confirmation": "发布成功"},
            occurred_at="2026-07-22T05:00:00Z",
            external_post_id="post-1",
            external_url="https://example.com/post-1",
        )
    )
    publish_detail = json.loads(await _personal_ip_read_publish_receipt(runtime, "publish-1"))
    preflight_detail = json.loads(await _personal_ip_read_preflight(runtime, "preflight-1"))
    retrospective = json.loads(
        await _personal_ip_seal_retrospective(
            runtime,
            review_key="retro:post-1:t3d",
            publish_receipt_id="publish-1",
            horizon="T+3d",
            metric_observation_ids=["metric-1"],
        )
    )
    retrospective_detail = json.loads(await _personal_ip_read_retrospective(runtime, "retro-1"))
    promotion = json.loads(
        await _personal_ip_promote_evidence(
            runtime,
            proposal_key="pattern:hook-1",
            evidence_type="content_pattern",
            claim="开头直给结果提高完播",
            retrospective_ids=["retro-1", "retro-2", "retro-3"],
            minimum_support=3,
        )
    )
    promotion_detail = json.loads(await _personal_ip_read_evidence_promotion(runtime, "promotion-1"))

    assert created["id"] == "publish-1"
    assert attempted["status"] == "published"
    assert publish_detail["id"] == "publish-1"
    assert preflight_detail["id"] == "preflight-1"
    assert retrospective["id"] == "retro-1"
    assert retrospective_detail["id"] == "retro-1"
    assert promotion["id"] == "promotion-1"
    assert promotion_detail["id"] == "promotion-1"
    assert publish_receipts.begin.await_args.kwargs["owner_user_id"] == "user-1"
    assert publish_receipts.record_attempt.await_args.kwargs["occurred_at"].isoformat() == "2026-07-22T05:00:00+00:00"
    retrospectives.seal.assert_awaited_once_with(
        owner_user_id="user-1",
        review_key="retro:post-1:t3d",
        publish_receipt_id="publish-1",
        horizon="T+3d",
        metric_observation_ids=["metric-1"],
    )
    promotions.propose.assert_awaited_once_with(
        owner_user_id="user-1",
        proposal_key="pattern:hook-1",
        evidence_type="content_pattern",
        claim="开头直给结果提高完播",
        retrospective_ids=["retro-1", "retro-2", "retro-3"],
        minimum_support=3,
    )
