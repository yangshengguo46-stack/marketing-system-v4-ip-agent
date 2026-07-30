from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from support.personal_ip_publish import (
    compliant_publish_request,
    compliant_publish_result,
)

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_preflights import PersonalIPPreflightRepository
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.audience_provider import AudiencePreflightRequest, AudiencePreflightResult
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter


def _variant(variant_id: str, text: str) -> dict:
    return {
        "variant_id": variant_id,
        "text": text,
        "evidence_level": "account_history_conditioned",
        "mechanism_hypotheses": [
            {
                "layer": "attention_prediction",
                "claim": "目标人群识别到相关问题后更可能继续观看",
                "predicted_signal": "首段继续观看比例提高",
                "failure_condition": "目标人群无法复述内容承诺",
            }
        ],
        "distribution_assumptions": ["平台分发给相关兴趣人群"],
        "uncertainty": "历史表现不能保证本次结果",
    }


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
        variants=[_variant("v1", "候选文案")],
    )
    return request, result


@pytest.mark.asyncio
async def test_publish_receipt_is_idempotent_and_keeps_append_only_attempts(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    preflights = PersonalIPPreflightRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    subject = await subjects.create(owner_user_id="user-1", display_name="老杨")
    account = await accounts.create(
        owner_user_id="user-1",
        subject_id=subject["id"],
        platform="douyin",
        display_name="老杨说 AI",
    )
    model_request, model_result = _preflight_contract()
    preflight = await preflights.seal(
        owner_user_id="user-1",
        operation_key="preflight:draft-1:v1",
        subject_ids=[subject["id"]],
        target_account_ids=[account["id"]],
        request=model_request,
        result=model_result,
    )

    created = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:draft-1:douyin",
        idempotency_key="idem-draft-1-douyin",
        account_id=account["id"],
        preflight_id=preflight["id"],
        executor="platform_api",
        request_payload=compliant_publish_request(
            "douyin",
            variant_id="v1",
            caption="候选文案",
        ),
    )
    replayed = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:draft-1:douyin",
        idempotency_key="idem-draft-1-douyin",
        account_id=account["id"],
        preflight_id=preflight["id"],
        executor="platform_api",
        request_payload=compliant_publish_request(
            "douyin",
            variant_id="v1",
            caption="候选文案",
        ),
    )

    assert replayed == created
    assert created["status"] == "planned"
    assert created["platform"] == "douyin"
    assert created["subject_id"] == subject["id"]
    assert created["attempts"] == []
    assert created["request"]["compliance_receipt"]["platform"] == "douyin"
    assert created["request"]["compliance_receipt"]["decision"] == "ready_for_publish"
    assert len(created["request"]["compliance_receipt"]["receipt_digest"]) == 64
    assert await receipts.get(created["id"], owner_user_id="user-2") is None

    pending = await receipts.record_attempt(
        created["id"],
        owner_user_id="user-1",
        attempt_key="attempt-1",
        status="pending",
        result_payload={"task_id": "task-123"},
        occurred_at=datetime(2026, 7, 21, 8, 0, tzinfo=UTC),
    )
    published = await receipts.record_attempt(
        created["id"],
        owner_user_id="user-1",
        attempt_key="attempt-2",
        status="published",
        result_payload=compliant_publish_result(
            created,
            post_id="post-456",
        ),
        external_post_id="post-456",
        external_url="https://www.douyin.com/video/post-456",
        occurred_at=datetime(2026, 7, 21, 8, 1, tzinfo=UTC),
    )
    duplicate = await receipts.record_attempt(
        created["id"],
        owner_user_id="user-1",
        attempt_key="attempt-2",
        status="published",
        result_payload=compliant_publish_result(
            created,
            post_id="post-456",
        ),
        external_post_id="post-456",
        external_url="https://www.douyin.com/video/post-456",
        occurred_at=datetime(2026, 7, 21, 8, 1, tzinfo=UTC),
    )

    assert pending is not None and pending["status"] == "pending"
    assert published is not None and published["status"] == "published"
    assert duplicate == published
    assert len(published["attempts"]) == 2
    assert published["external_post_id"] == "post-456"
    assert published["published_at"] == "2026-07-21T08:01:00+00:00"
    assert (await preflights.get(preflight["id"], owner_user_id="user-1"))["status"] == "published"

    with pytest.raises(ValueError, match="attempt_key already records a different result"):
        await receipts.record_attempt(
            created["id"],
            owner_user_id="user-1",
            attempt_key="attempt-2",
            status="failed",
            result_payload={"error": "late contradiction"},
        )
    with pytest.raises(ValueError, match="cannot transition"):
        await receipts.record_attempt(
            created["id"],
            owner_user_id="user-1",
            attempt_key="attempt-3",
            status="failed",
            result_payload={"error": "terminal downgrade"},
        )
    await close_engine()


@pytest.mark.asyncio
async def test_publish_receipt_rejects_foreign_or_out_of_preflight_accounts(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    preflights = PersonalIPPreflightRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    subject = await subjects.create(owner_user_id="user-1", display_name="主体")
    allowed = await accounts.create(
        owner_user_id="user-1",
        subject_id=subject["id"],
        platform="douyin",
        display_name="允许账号",
    )
    outside = await accounts.create(
        owner_user_id="user-1",
        subject_id=subject["id"],
        platform="xiaohongshu",
        display_name="未预演账号",
    )
    foreign = await accounts.create(
        owner_user_id="user-2",
        platform="xiaohongshu",
        display_name="他人账号",
    )
    model_request, model_result = _preflight_contract()
    preflight = await preflights.seal(
        owner_user_id="user-1",
        operation_key="preflight:limited",
        subject_ids=[subject["id"]],
        target_account_ids=[allowed["id"]],
        request=model_request,
        result=model_result,
    )

    with pytest.raises(ValueError, match="outside the sealed preflight targets"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:outside",
            idempotency_key="idem-outside",
            account_id=outside["id"],
            preflight_id=preflight["id"],
            executor="ui_tars",
            request_payload=compliant_publish_request(
                "xiaohongshu",
                caption="测试",
            ),
        )
    with pytest.raises(ValueError, match="selected preflight variant"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:missing-variant",
            idempotency_key="idem-missing-variant",
            account_id=allowed["id"],
            preflight_id=preflight["id"],
            executor="browser",
            request_payload=compliant_publish_request(
                "douyin",
                caption="测试",
            ),
        )
    with pytest.raises(ValueError, match="outside the sealed preflight receipt"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:foreign-variant",
            idempotency_key="idem-foreign-variant",
            account_id=allowed["id"],
            preflight_id=preflight["id"],
            executor="browser",
            request_payload=compliant_publish_request(
                "douyin",
                variant_id="not-sealed",
                caption="测试",
            ),
        )
    with pytest.raises(ValueError, match="target account not found"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:foreign",
            idempotency_key="idem-foreign",
            account_id=foreign["id"],
            preflight_id=None,
            executor="browser",
            request_payload=compliant_publish_request(
                "xiaohongshu",
                caption="测试",
            ),
        )
    await close_engine()


@pytest.mark.asyncio
async def test_publish_receipt_rejects_credentials_and_sanitizes_external_url(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    account = await accounts.create(
        owner_user_id="user-1",
        platform="douyin",
        display_name="凭据边界账号",
    )
    with pytest.raises(ValueError, match="compliance declaration is required"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:no-compliance",
            idempotency_key="idem-no-compliance",
            account_id=account["id"],
            preflight_id=None,
            executor="browser",
            request_payload={"caption": "未声明"},
        )
    with pytest.raises(ValueError, match="credential"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:credential",
            idempotency_key="idem-credential",
            account_id=account["id"],
            preflight_id=None,
            executor="browser",
            request_payload=compliant_publish_request(
                "douyin",
                cookie="session=secret",
            ),
        )
    created = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:safe",
        idempotency_key="idem-safe",
        account_id=account["id"],
        preflight_id=None,
        executor="browser",
        request_payload=compliant_publish_request(
            "douyin",
            caption="测试",
        ),
    )
    with pytest.raises(ValueError, match="compliance_evidence"):
        await receipts.record_attempt(
            created["id"],
            owner_user_id="user-1",
            attempt_key="attempt-missing-compliance-evidence",
            status="published",
            result_payload={"confirmation": "页面显示发布成功"},
            external_post_id="post-1",
        )
    published = await receipts.record_attempt(
        created["id"],
        owner_user_id="user-1",
        attempt_key="attempt-safe",
        status="published",
        result_payload=compliant_publish_result(
            created,
            confirmation="页面显示发布成功",
        ),
        external_post_id="post-1",
        external_url="https://www.douyin.com/video/post-1?share_token=secret#fragment",
    )
    assert published is not None
    assert published["external_url"] == "https://www.douyin.com/video/post-1"
    with pytest.raises(ValueError, match="publish platform"):
        await receipts.record_attempt(
            created["id"],
            owner_user_id="user-1",
            attempt_key="attempt-cross-platform",
            status="published",
            result_payload=compliant_publish_result(
                created,
                confirmation="伪造跨平台地址",
            ),
            external_post_id="post-1",
            external_url="https://example.com/post/1",
        )
    with pytest.raises(ValueError, match="credential"):
        await receipts.record_attempt(
            created["id"],
            owner_user_id="user-1",
            attempt_key="attempt-leak",
            status="published",
            result_payload=compliant_publish_result(
                created,
                access_token="secret",
            ),
        )
    await close_engine()


@pytest.mark.asyncio
async def test_concurrent_publish_begin_converges_on_one_idempotent_receipt(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    account = await accounts.create(
        owner_user_id="user-1",
        platform="douyin",
        display_name="并发测试账号",
    )

    async def begin_once() -> dict:
        return await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:concurrent",
            idempotency_key="idem-concurrent",
            account_id=account["id"],
            preflight_id=None,
            executor="platform_api",
            request_payload=compliant_publish_request(
                "douyin",
                caption="同一请求",
            ),
        )

    results = await asyncio.gather(begin_once(), begin_once())

    assert results[0]["id"] == results[1]["id"]
    assert len(await receipts.list("user-1")) == 1
    await close_engine()
