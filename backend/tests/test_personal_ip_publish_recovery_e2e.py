from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from support.personal_ip_publish import (
    compliant_publish_request,
    compliant_publish_result,
)

from deerflow.config.database_config import DatabaseConfig
from deerflow.config.paths import Paths
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository
from deerflow.personal_ip.browser_profiles import (
    clear_browser_account_target,
    get_browser_account_target,
    select_browser_account_target,
)
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins.personal_ip_workflow_tools import (
    _personal_ip_finish_browser_publish,
    _personal_ip_prepare_browser_publish,
)

_PLATFORM_CASES = [
    ("douyin", "https://www.douyin.com/video/712345", "712345"),
    ("wechat_channels", "https://channels.weixin.qq.com/web/pages/feed?feedId=feed-1", "feed-1"),
    ("wechat_official", "https://mp.weixin.qq.com/s/article-1", "article-1"),
    ("xiaohongshu", "https://www.xiaohongshu.com/explore/note-1", "note-1"),
    ("x", "https://x.com/creator/status/1001", "1001"),
    ("instagram", "https://www.instagram.com/reel/reel-1/", "reel-1"),
    ("youtube", "https://www.youtube.com/watch?v=video-1", "video-1"),
    ("tiktok", "https://www.tiktok.com/@creator/video/2001", "2001"),
]


def _decoded(value: str) -> dict:
    return json.loads(value)


@pytest.mark.asyncio
@pytest.mark.parametrize(("platform", "public_url", "post_id"), _PLATFORM_CASES)
@pytest.mark.parametrize("recovery_status", ["unknown", "failed"])
async def test_eight_platform_browser_publish_recovery_matrix(
    tmp_path,
    monkeypatch,
    platform: str,
    public_url: str,
    post_id: str,
    recovery_status: str,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path / "db")))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform=platform, display_name=f"{platform} 主账号")
    wrong_account = await accounts.create(owner_user_id="user-1", platform=platform, display_name=f"{platform} 错误账号")
    configure_personal_ip_runtime(
        PersonalIPRuntimeServices(
            connections=SimpleNamespace(),
            metrics=SimpleNamespace(),
            accounts=accounts,
            publish_receipts=receipts,
        )
    )
    paths = Paths(tmp_path / "paths")
    monkeypatch.setattr("deerflow.tools.builtins.personal_ip_workflow_tools.get_paths", lambda: paths)
    observe = AsyncMock()
    monkeypatch.setattr("deerflow.tools.builtins.personal_ip_workflow_tools._observe_selected_browser", observe)
    runtime = SimpleNamespace(context={"user_id": "user-1", "thread_id": f"thread-{platform}"})
    operation_key = f"publish:{platform}:draft-1"
    idempotency_key = f"idem:{platform}:draft-1"

    try:
        prepared = _decoded(
            await _personal_ip_prepare_browser_publish(
                runtime,
                operation_key=operation_key,
                idempotency_key=idempotency_key,
                pending_attempt_key="handoff-1",
                account_id=account["id"],
                request=compliant_publish_request(
                    platform,
                    caption="已批准发布",
                    media_refs=["artifact://video-1"],
                ),
            )
        )
        receipt_id = prepared["receipt"]["id"]
        assert prepared["receipt"]["status"] == "pending"
        assert runtime.context == {"user_id": "user-1", "thread_id": f"thread-{platform}"}

        conflicting_target = _decoded(
            await _personal_ip_prepare_browser_publish(
                runtime,
                operation_key=operation_key,
                idempotency_key=idempotency_key,
                pending_attempt_key="handoff-wrong-account",
                account_id=wrong_account["id"],
                request=compliant_publish_request(
                    platform,
                    caption="已批准发布",
                    media_refs=["artifact://video-1"],
                ),
            )
        )
        assert conflicting_target["category"] == "invalid_request"
        selected = get_browser_account_target(owner_user_id="user-1", thread_id=runtime.context["thread_id"])
        assert selected is not None and selected.account_id == account["id"]

        observe.return_value = {
            "url": prepared["browser_target"]["start_url"],
            "title": "创作者后台",
            "visible_text": f"列表里出现了 {post_id}",
        }
        page_not_changed = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="result-before-navigation",
                status="published",
                evidence=compliant_publish_result(
                    prepared["receipt"],
                    confirmation="点击已返回",
                ),
                occurred_at="2026-07-22T05:01:00Z",
                external_post_id=post_id,
                external_url="",
            )
        )
        assert page_not_changed["category"] == "invalid_request"

        safe_user_id = paths.prepare_user_dir_for_raw_id("user-1")
        select_browser_account_target(
            owner_user_id="user-1",
            thread_id=runtime.context["thread_id"],
            account_id=wrong_account["id"],
            platform=platform,
            display_name=wrong_account["display_name"],
            user_data_dir=paths.ensure_browser_profile_dir(wrong_account["id"], user_id=safe_user_id),
        )
        wrong_target = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="result-wrong-account",
                status="failed",
                evidence={"reason": "wrong account"},
                occurred_at="2026-07-22T05:02:00Z",
                external_post_id="",
                external_url="",
            )
        )
        assert "account does not match" in wrong_target["message"]

        replayed_prepare = _decoded(
            await _personal_ip_prepare_browser_publish(
                runtime,
                operation_key=operation_key,
                idempotency_key=idempotency_key,
                pending_attempt_key="handoff-1",
                account_id=account["id"],
                request=compliant_publish_request(
                    platform,
                    caption="已批准发布",
                    media_refs=["artifact://video-1"],
                ),
            )
        )
        assert len(replayed_prepare["receipt"]["attempts"]) == 1

        mismatched_platform = "youtube" if platform != "youtube" else "x"
        select_browser_account_target(
            owner_user_id="user-1",
            thread_id=runtime.context["thread_id"],
            account_id=account["id"],
            platform=mismatched_platform,
            display_name=account["display_name"],
            user_data_dir=paths.ensure_browser_profile_dir(account["id"], user_id=safe_user_id),
        )
        wrong_selected_platform = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="result-wrong-selected-platform",
                status="failed",
                evidence={"reason": "wrong selected platform"},
                occurred_at="2026-07-22T05:02:30Z",
                external_post_id="",
                external_url="",
            )
        )
        assert "platform does not match" in wrong_selected_platform["message"]

        replayed_prepare = _decoded(
            await _personal_ip_prepare_browser_publish(
                runtime,
                operation_key=operation_key,
                idempotency_key=idempotency_key,
                pending_attempt_key="handoff-1",
                account_id=account["id"],
                request=compliant_publish_request(
                    platform,
                    caption="已批准发布",
                    media_refs=["artifact://video-1"],
                ),
            )
        )
        assert len(replayed_prepare["receipt"]["attempts"]) == 1

        other_url = "https://www.youtube.com/watch?v=wrong-platform" if platform != "youtube" else "https://x.com/creator/status/999"
        observe.return_value = {"url": other_url, "title": "错误平台", "visible_text": "wrong-platform"}
        wrong_platform = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="result-wrong-platform",
                status="published",
                evidence=compliant_publish_result(
                    prepared["receipt"],
                    confirmation="错误页面",
                ),
                occurred_at="2026-07-22T05:03:00Z",
                external_post_id="wrong-platform",
                external_url="",
            )
        )
        assert "selected platform" in wrong_platform["message"]

        recoverable_failure = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key=f"result-{recovery_status}",
                status=recovery_status,
                evidence={"reason": "submit outcome unavailable"},
                occurred_at="2026-07-22T05:04:00Z",
                external_post_id="",
                external_url="",
            )
        )
        assert recoverable_failure["status"] == recovery_status

        retried = _decoded(
            await _personal_ip_prepare_browser_publish(
                runtime,
                operation_key=operation_key,
                idempotency_key=idempotency_key,
                pending_attempt_key="handoff-2",
                account_id=account["id"],
                request=compliant_publish_request(
                    platform,
                    caption="已批准发布",
                    media_refs=["artifact://video-1"],
                ),
            )
        )
        assert retried["receipt"]["status"] == "pending"

        observe.return_value = {"url": public_url, "title": "公开帖子", "visible_text": f"公开帖子 {post_id}"}
        published = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="result-published",
                status="published",
                evidence=compliant_publish_result(
                    prepared["receipt"],
                    confirmation="public page visible",
                ),
                occurred_at="2026-07-22T05:05:00Z",
                external_post_id=post_id,
                external_url=public_url,
            )
        )
        assert published["status"] == "published"

        clear_browser_account_target(owner_user_id="user-1", thread_id=runtime.context["thread_id"])
        observe.side_effect = AssertionError("idempotent callback must not need the browser again")
        duplicate = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="result-published",
                status="published",
                evidence=compliant_publish_result(
                    prepared["receipt"],
                    confirmation="public page visible",
                ),
                occurred_at="2026-07-22T05:05:00Z",
                external_post_id=post_id,
                external_url=public_url,
            )
        )
        assert duplicate == published

        conflicting_duplicate = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="result-published",
                status="failed",
                evidence={"reason": "contradictory duplicate"},
                occurred_at="2026-07-22T05:05:00Z",
                external_post_id="",
                external_url="",
            )
        )
        assert conflicting_duplicate["category"] == "invalid_request"
        assert "already records a different browser result" in conflicting_duplicate["message"]

        replay_after_success = _decoded(
            await _personal_ip_prepare_browser_publish(
                runtime,
                operation_key=operation_key,
                idempotency_key=idempotency_key,
                pending_attempt_key="handoff-1",
                account_id=account["id"],
                request=compliant_publish_request(
                    platform,
                    caption="已批准发布",
                    media_refs=["artifact://video-1"],
                ),
            )
        )
        assert replay_after_success["receipt"]["status"] == "published"

        downgraded = _decoded(
            await _personal_ip_finish_browser_publish(
                runtime,
                receipt_id=receipt_id,
                attempt_key="late-failure",
                status="failed",
                evidence={"reason": "late contradictory callback"},
                occurred_at="2026-07-22T05:06:00Z",
                external_post_id="",
                external_url="",
            )
        )
        assert downgraded["category"] == "invalid_request"
        assert "cannot transition" in downgraded["message"]
        persisted = await receipts.get(receipt_id, owner_user_id="user-1")
        assert persisted is not None and persisted["status"] == "published"
        assert [attempt["status"] for attempt in persisted["attempts"]] == ["pending", recovery_status, "pending", "published"]
    finally:
        clear_browser_account_target(owner_user_id="user-1", thread_id=runtime.context["thread_id"])
        configure_personal_ip_runtime(None)
        await close_engine()
