from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from deerflow.config.paths import Paths
from deerflow.personal_ip.audience_provider import AudiencePreflightResult
from deerflow.personal_ip.browser_profiles import clear_browser_account_target
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins import (
    personal_ip_begin_publish_receipt_tool,
    personal_ip_finish_browser_publish_tool,
    personal_ip_prepare_browser_publish_tool,
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
    _personal_ip_finish_browser_publish,
    _personal_ip_prepare_browser_publish,
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
        personal_ip_prepare_browser_publish_tool,
        personal_ip_finish_browser_publish_tool,
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
        "personal_ip_finish_browser_publish",
        "personal_ip_promote_evidence",
        "personal_ip_prepare_browser_publish",
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
async def test_browser_publish_tools_bind_selected_profile_and_live_proof(tmp_path, monkeypatch) -> None:
    account = {
        "id": "acct-1",
        "platform": "youtube",
        "display_name": "频道一",
        "status": "active",
    }
    accounts = SimpleNamespace(get=AsyncMock(return_value=account))
    publish_receipts = SimpleNamespace(
        begin=AsyncMock(
            return_value={
                "id": "publish-browser-1",
                "account_id": "acct-1",
                "executor": "browser",
                "status": "planned",
                "attempts": [],
                "created_at": "2026-07-22T05:00:00+00:00",
            }
        ),
        record_attempt=AsyncMock(
            side_effect=[
                {
                    "id": "publish-browser-1",
                    "account_id": "acct-1",
                    "executor": "browser",
                    "status": "pending",
                    "attempts": [{"attempt_key": "browser-handoff-1"}],
                },
                {
                    "id": "publish-browser-1",
                    "account_id": "acct-1",
                    "executor": "browser",
                    "status": "published",
                    "external_post_id": "video-1",
                },
            ]
        ),
        get=AsyncMock(
            return_value={
                "id": "publish-browser-1",
                "account_id": "acct-1",
                "platform": "youtube",
                "executor": "browser",
                "status": "pending",
            }
        ),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            accounts=accounts,
            publish_receipts=publish_receipts,
        )
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_workflow_tools.get_paths",
        lambda: Paths(tmp_path),
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.personal_ip_workflow_tools._observe_selected_browser",
        AsyncMock(
            return_value={
                "url": "https://www.youtube.com/watch?v=video-1&utm_source=creator",
                "title": "刚刚发布的视频",
                "visible_text": "刚刚发布的视频 video-1",
            }
        ),
    )
    runtime = SimpleNamespace(context={"user_id": "user-1", "thread_id": "thread-1"})
    try:
        prepared = json.loads(
            await _personal_ip_prepare_browser_publish(
                runtime,
                operation_key="publish:video-1",
                idempotency_key="publish:video-1:youtube",
                pending_attempt_key="browser-handoff-1",
                account_id="acct-1",
                preflight_id="",
                request={"caption": "视频文案", "media_refs": ["artifact://video-1"]},
            )
        )
        finished = json.loads(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id="publish-browser-1",
                attempt_key="browser-result-1",
                status="published",
                evidence={"visible_confirmation": "发布成功"},
                occurred_at="2026-07-22T05:01:00Z",
                external_post_id="video-1",
                external_url="https://www.youtube.com/watch?v=video-1&utm_source=creator",
            )
        )
    finally:
        clear_browser_account_target(owner_user_id="user-1", thread_id="thread-1")

    assert prepared["receipt"]["status"] == "pending"
    assert prepared["browser_target"]["account_id"] == "acct-1"
    assert finished["status"] == "published"
    pending_kwargs = publish_receipts.record_attempt.await_args_list[0].kwargs
    assert pending_kwargs["status"] == "pending"
    assert pending_kwargs["occurred_at"].isoformat() == "2026-07-22T05:00:00+00:00"
    published_kwargs = publish_receipts.record_attempt.await_args_list[1].kwargs
    assert published_kwargs["status"] == "published"
    assert published_kwargs["result_payload"]["browser_proof"]["observed_url"] == "https://www.youtube.com/watch?v=video-1"
    assert "visible_text" not in published_kwargs["result_payload"]["browser_proof"]


@pytest.mark.asyncio
async def test_run_preflight_uses_strategy_without_local_ids(monkeypatch) -> None:
    preflights = SimpleNamespace(
        seal=AsyncMock(
            return_value={
                "id": "preflight-1",
                "status": "sealed",
                "provider": "hllm-lite",
            }
        )
    )
    brand = SimpleNamespace(
        get_latest_strategy=AsyncMock(
            return_value={
                "stage": "launch_package_ready",
                "mode": "monetization_first",
                "person_model": {"values_boundaries": ["不夸大"]},
                "business_model": {"primary_goal": "获取付费客户"},
                "positioning_candidates": [{"candidate_id": "a", "promise": "经营结果"}],
                "launch_package": {"selected_candidate_id": "a", "bio_options": ["真实经营"]},
            }
        ),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            preflights=preflights,
            brand=brand,
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
async def test_run_preflight_requires_both_local_evidence_purposes(monkeypatch) -> None:
    preflights = SimpleNamespace(seal=AsyncMock(return_value={"id": "preflight-local", "status": "sealed"}))
    evidence = {
        "schema_version": "personal-ip-local-context-evidence-v1",
        "evidence_id": "mctx_1",
        "source": {"source_kind": "projects", "context_type": "activity", "observed_at": "2026-07-22T05:00:00+00:00"},
        "summary": {"title": "路线图", "text": "下周交付", "keywords": ["交付"]},
        "digest": "a" * 64,
    }
    minecontext = SimpleNamespace(read_evidence=MagicMock(return_value=[evidence]))
    brand = SimpleNamespace(
        get_latest_strategy=AsyncMock(
            return_value={
                "stage": "launch_package_ready",
                "mode": "monetization_first",
                "person_model": {"values_boundaries": ["不夸大"]},
                "business_model": {"primary_goal": "获取付费客户"},
                "positioning_candidates": [{"candidate_id": "a", "promise": "经营结果"}],
                "launch_package": {"selected_candidate_id": "a", "bio_options": ["真实经营"]},
            }
        ),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=SimpleNamespace(),
            preflights=preflights,
            brand=brand,
            minecontext=minecontext,
        )
    )

    async def preflight(request):
        profile = json.loads(request.to_payload()["example"]["user_profile"])
        assert profile["local_context_evidence"]["items"][0]["evidence_id"] == "mctx_1"
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
    result = json.loads(
        await _personal_ip_run_preflight(
            SimpleNamespace(context={"user_id": "user-1"}),
            operation_key="preflight:local",
            subject_ids=["subject-1"],
            target_account_ids=[],
            history=[
                {
                    "content_id": "published-1",
                    "published_at": "2026-07-20T08:00:00Z",
                    "platform": "douyin",
                    "title": "历史内容",
                    "content_type": "short_video",
                    "metrics": {"views": 1000},
                }
            ],
            target={"content_id": "draft-1", "title": "待发布", "description": "预演"},
            local_context_evidence_ids=["mctx_1"],
        )
    )

    assert result["id"] == "preflight-local"
    assert [call.kwargs["purpose"] for call in minecontext.read_evidence.call_args_list] == ["preflight", "hllm_user_profile"]


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
            executor="platform_api",
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


@pytest.mark.asyncio
async def test_generic_publish_tools_reject_browser_receipt_bypass() -> None:
    publish_receipts = SimpleNamespace(
        begin=AsyncMock(),
        get=AsyncMock(return_value={"id": "publish-1", "executor": "browser"}),
        record_attempt=AsyncMock(),
    )
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            publish_receipts=publish_receipts,
        )
    )
    runtime = SimpleNamespace(context={"user_id": "user-1"})

    created = json.loads(
        await _personal_ip_begin_publish_receipt(
            runtime,
            operation_key="publish:draft-1",
            idempotency_key="idem:draft-1",
            account_id="acct-1",
            preflight_id="",
            executor="browser",
            request={"caption": "候选文案"},
        )
    )
    attempted = json.loads(
        await _personal_ip_record_publish_attempt(
            runtime,
            receipt_id="publish-1",
            attempt_key="attempt-1",
            status="published",
            result={"confirmation": "未经 live proof"},
            occurred_at="",
            external_post_id="post-1",
            external_url="",
        )
    )

    assert "must use personal_ip_prepare_browser_publish" in created["message"]
    assert "must use personal_ip_finish_browser_publish" in attempted["message"]
    publish_receipts.begin.assert_not_awaited()
    publish_receipts.record_attempt.assert_not_awaited()
