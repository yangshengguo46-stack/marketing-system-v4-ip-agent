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
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository


@pytest.mark.asyncio
async def test_publish_receipt_is_idempotent_and_keeps_append_only_attempts(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    subject = await subjects.create(owner_user_id="user-1", display_name="老杨")
    account = await accounts.create(
        owner_user_id="user-1",
        subject_id=subject["id"],
        platform="douyin",
        display_name="老杨说 AI",
    )
    created = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:draft-1:douyin",
        idempotency_key="idem-draft-1-douyin",
        account_id=account["id"],
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
async def test_publish_receipt_rejects_foreign_account(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    foreign = await accounts.create(
        owner_user_id="user-2",
        platform="xiaohongshu",
        display_name="他人账号",
    )

    with pytest.raises(ValueError, match="target account not found"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:foreign",
            idempotency_key="idem-foreign",
            account_id=foreign["id"],
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
            executor="browser",
            request_payload={"caption": "未声明"},
        )
    with pytest.raises(ValueError, match="credential"):
        await receipts.begin(
            owner_user_id="user-1",
            operation_key="publish:credential",
            idempotency_key="idem-credential",
            account_id=account["id"],
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
