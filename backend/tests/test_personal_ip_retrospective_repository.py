from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_metrics import PersonalIPMetricRepository
from deerflow.persistence.personal_ip_preflights import PersonalIPPreflightRepository
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository
from deerflow.persistence.personal_ip_retrospectives import PersonalIPRetrospectiveRepository
from deerflow.personal_ip.audience_provider import AudiencePreflightRequest, AudiencePreflightResult
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter


def _preflight_contract() -> tuple[AudiencePreflightRequest, AudiencePreflightResult]:
    example = HLLMCreatorAdapter().build_example(
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
        target={"content_id": "draft-1", "title": "待发布", "description": "发布前预演"},
    )
    request = AudiencePreflightRequest(example=example, variant_count=1)
    result = AudiencePreflightResult(
        provider="hllm-lite",
        model_version="doubao-test",
        algorithm_version="lite-v0",
        request_digest=request.request_digest,
        audience_basis="aggregate_account_cohort",
        variants=[{"variant_id": "v1", "text": "候选文案", "match_score": None}],
    )
    return request, result


@pytest.mark.asyncio
async def test_retrospective_seals_prediction_publish_and_actual_evidence(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    preflights = PersonalIPPreflightRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    metrics = PersonalIPMetricRepository(sf)
    retrospectives = PersonalIPRetrospectiveRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="复盘账号")
    model_request, model_result = _preflight_contract()
    preflight = await preflights.seal(
        owner_user_id="user-1",
        operation_key="preflight:retro",
        subject_ids=[],
        target_account_ids=[account["id"]],
        request=model_request,
        result=model_result,
    )
    receipt = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:retro",
        idempotency_key="idem:retro",
        account_id=account["id"],
        preflight_id=preflight["id"],
        executor="platform_api",
        request_payload={"variant_id": "v1", "caption": "候选文案"},
    )
    await receipts.record_attempt(
        receipt["id"],
        owner_user_id="user-1",
        attempt_key="published",
        status="published",
        result_payload={"post_id": "post-1"},
        external_post_id="post-1",
        occurred_at=datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
    )
    observation = await metrics.record(
        owner_user_id="user-1",
        observation_key="post-1:t+1d",
        account_id=account["id"],
        receipt_id=receipt["id"],
        scope="post",
        metric_mode="snapshot",
        source="platform_api",
        status="partial",
        observed_at=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
        metrics={"views": 1200, "likes": 80},
        coverage={"missing_metrics": ["completion_rate"]},
    )

    kwargs = {
        "owner_user_id": "user-1",
        "review_key": "retro:post-1:t+1d",
        "publish_receipt_id": receipt["id"],
        "horizon": "t+1d",
        "metric_observation_ids": [observation["id"]],
    }
    created = await retrospectives.seal(**kwargs)
    replayed = await retrospectives.seal(**kwargs)

    assert replayed == created
    assert created["preflight_id"] == preflight["id"]
    assert created["account_id"] == account["id"]
    assert created["selected_variant_id"] == "v1"
    assert created["prediction"]["variant"]["text"] == "候选文案"
    assert created["outcome"]["latest_metrics"] == {"likes": 80, "views": 1200}
    assert created["status"] == "partial"
    assert created["comparison_state"] == "unscored"
    assert created["training_eligibility"]["status"] == "pending_human_review"
    assert len(created["evidence_digest"]) == 64
    assert await retrospectives.get(created["id"], owner_user_id="user-2") is None
    await close_engine()


@pytest.mark.asyncio
async def test_retrospective_rejects_unpublished_or_unrelated_evidence(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    preflights = PersonalIPPreflightRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    metrics = PersonalIPMetricRepository(sf)
    retrospectives = PersonalIPRetrospectiveRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="账号一")
    other = await accounts.create(owner_user_id="user-1", platform="xiaohongshu", display_name="账号二")
    model_request, model_result = _preflight_contract()
    preflight = await preflights.seal(
        owner_user_id="user-1",
        operation_key="preflight:reject",
        subject_ids=[],
        target_account_ids=[account["id"]],
        request=model_request,
        result=model_result,
    )
    receipt = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:reject",
        idempotency_key="idem:reject",
        account_id=account["id"],
        preflight_id=preflight["id"],
        executor="manual",
        request_payload={"variant_id": "v1"},
    )
    with pytest.raises(ValueError, match="must be published"):
        await retrospectives.seal(
            owner_user_id="user-1",
            review_key="retro:unpublished",
            publish_receipt_id=receipt["id"],
            horizon="t+1d",
            metric_observation_ids=[],
        )

    await receipts.record_attempt(
        receipt["id"],
        owner_user_id="user-1",
        attempt_key="published",
        status="published",
        result_payload={},
    )
    other_receipt = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:other",
        idempotency_key="idem:other",
        account_id=other["id"],
        preflight_id=None,
        executor="manual",
        request_payload={"caption": "其他内容"},
    )
    observation = await metrics.record(
        owner_user_id="user-1",
        observation_key="other:t+1d",
        account_id=other["id"],
        receipt_id=other_receipt["id"],
        scope="post",
        metric_mode="snapshot",
        source="manual",
        status="observed",
        observed_at=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
        metrics={"views": 10},
        coverage={},
    )
    with pytest.raises(ValueError, match="different publish receipt"):
        await retrospectives.seal(
            owner_user_id="user-1",
            review_key="retro:wrong-metric",
            publish_receipt_id=receipt["id"],
            horizon="t+1d",
            metric_observation_ids=[observation["id"]],
        )
    await close_engine()
