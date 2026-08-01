from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.config.paths import Paths
from deerflow.personal_ip.browser_profiles import clear_browser_account_target
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, configure_personal_ip_runtime
from deerflow.tools.builtins import (
    personal_ip_begin_publish_receipt_tool,
    personal_ip_finish_browser_publish_tool,
    personal_ip_prepare_browser_publish_tool,
    personal_ip_read_publish_receipt_tool,
    personal_ip_record_publish_attempt_tool,
)
from deerflow.tools.builtins.personal_ip_workflow_tools import (
    _personal_ip_begin_publish_receipt,
    _personal_ip_finish_browser_publish,
    _personal_ip_prepare_browser_publish,
    _personal_ip_read_publish_receipt,
    _personal_ip_record_publish_attempt,
)
from deerflow.tools.tools import BUILTIN_TOOLS


def test_personal_ip_workflow_tools_keep_publish_tools() -> None:
    tools = [
        personal_ip_begin_publish_receipt_tool,
        personal_ip_prepare_browser_publish_tool,
        personal_ip_finish_browser_publish_tool,
        personal_ip_record_publish_attempt_tool,
        personal_ip_read_publish_receipt_tool,
    ]
    assert all(item in BUILTIN_TOOLS for item in tools)
    names = {item.name for item in tools}
    assert names == {
        "personal_ip_begin_publish_receipt",
        "personal_ip_finish_browser_publish",
        "personal_ip_prepare_browser_publish",
        "personal_ip_read_publish_receipt",
        "personal_ip_record_publish_attempt",
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
async def test_native_publish_tools_preserve_owner_scope_and_append_only_sequence() -> None:
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
            executor="platform_api",
            request={"caption": "候选文案"},
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
    detail = json.loads(await _personal_ip_read_publish_receipt(runtime, "publish-1"))

    assert created["id"] == "publish-1"
    assert attempted["status"] == "published"
    assert detail["id"] == "publish-1"
    assert publish_receipts.begin.await_args.kwargs["owner_user_id"] == "user-1"
    assert "semantic_dependency" not in publish_receipts.begin.await_args.kwargs
    assert publish_receipts.record_attempt.await_args.kwargs["occurred_at"].isoformat() == "2026-07-22T05:00:00+00:00"


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
