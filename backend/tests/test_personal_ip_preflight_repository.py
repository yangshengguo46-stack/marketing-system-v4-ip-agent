from __future__ import annotations

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_preflights import PersonalIPPreflightRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.audience_provider import AudiencePreflightRequest, AudiencePreflightResult
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter


def _model_request(*, title: str = "待发布内容") -> AudiencePreflightRequest:
    example = HLLMCreatorAdapter().build_example(
        history=[
            {
                "content_id": "published-1",
                "published_at": "2026-07-20T08:00:00Z",
                "platform": "douyin",
                "title": "历史内容",
                "content_type": "short_video",
                "metrics": {"views": 1000, "likes": 80},
            }
        ],
        audience_profile={"cohort_label": "关注智能体的创作者"},
        creator_profile={"voice": ["直接"]},
        target={"content_id": "draft-1", "title": title, "description": "发布前预演"},
    )
    return AudiencePreflightRequest(example=example, variant_count=2)


def _model_result(request: AudiencePreflightRequest) -> AudiencePreflightResult:
    return AudiencePreflightResult(
        provider="hllm-lite",
        model_version="doubao-test",
        algorithm_version="doubao-profile-conditioned-v0",
        request_digest=request.request_digest,
        audience_basis="aggregate_account_cohort",
        variants=[
            {"variant_id": "v1", "text": "候选一"},
            {"variant_id": "v2", "text": "候选二"},
        ],
        warnings=["no learned score"],
    )


@pytest.mark.asyncio
async def test_preflight_snapshot_is_owner_scoped_immutable_and_idempotent(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    preflights = PersonalIPPreflightRepository(sf)
    subject = await subjects.create(owner_user_id="user-1", display_name="老杨")
    account = await accounts.create(
        owner_user_id="user-1",
        subject_id=subject["id"],
        platform="douyin",
        display_name="老杨说 AI",
    )
    request = _model_request()
    result = _model_result(request)

    created = await preflights.seal(
        owner_user_id="user-1",
        operation_key="preflight:draft-1:v1",
        subject_ids=[subject["id"]],
        target_account_ids=[account["id"]],
        request=request,
        result=result,
    )
    replayed = await preflights.seal(
        owner_user_id="user-1",
        operation_key="preflight:draft-1:v1",
        subject_ids=[subject["id"]],
        target_account_ids=[account["id"]],
        request=request,
        result=result,
    )

    assert created["id"].startswith("preflight-")
    assert replayed == created
    assert created["status"] == "sealed"
    assert created["request_digest"] == request.request_digest
    assert created["target_account_ids"] == [account["id"]]
    assert created["provider_receipt"]["variants"][0]["text"] == "候选一"
    assert await preflights.get(created["id"], owner_user_id="user-2") is None
    assert await preflights.list("user-2") == []

    with pytest.raises(ValueError, match="operation_key already seals a different preflight"):
        changed_request = _model_request(title="另一份内容")
        await preflights.seal(
            owner_user_id="user-1",
            operation_key="preflight:draft-1:v1",
            subject_ids=[subject["id"]],
            target_account_ids=[account["id"]],
            request=changed_request,
            result=_model_result(changed_request),
        )
    await close_engine()


@pytest.mark.asyncio
async def test_preflight_rejects_foreign_operation_targets_and_receipts(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    preflights = PersonalIPPreflightRepository(sf)
    foreign_subject = await subjects.create(owner_user_id="user-2", display_name="其他主体")
    foreign_account = await accounts.create(
        owner_user_id="user-2",
        subject_id=foreign_subject["id"],
        platform="xiaohongshu",
        display_name="其他账号",
    )
    request = _model_request()

    with pytest.raises(ValueError, match="target account not found"):
        await preflights.seal(
            owner_user_id="user-1",
            operation_key="preflight:foreign",
            subject_ids=[],
            target_account_ids=[foreign_account["id"]],
            request=request,
            result=_model_result(request),
        )

    wrong_result = _model_result(request).model_copy(update={"request_digest": "0" * 64})
    with pytest.raises(ValueError, match="receipt does not match"):
        await preflights.seal(
            owner_user_id="user-1",
            operation_key="preflight:wrong-receipt",
            subject_ids=[],
            target_account_ids=[],
            request=request,
            result=wrong_result,
        )
    await close_engine()
