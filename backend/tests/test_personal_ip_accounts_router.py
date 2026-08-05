from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.gateway.routers import personal_ip_accounts as accounts_router


@pytest.mark.asyncio
async def test_logout_account_closes_session_erases_profile_and_resets_state(
    monkeypatch,
    tmp_path: Path,
):
    profile_dir = tmp_path / "acct-douyin"
    profile_dir.mkdir()
    (profile_dir / "Cookies").write_text("secret", encoding="utf-8")

    account = {
        "id": "acct-douyin",
        "owner_user_id": "user-1",
        "platform": "douyin",
        "display_name": "抖音账号",
        "metadata": {
            "browser_authenticated": True,
            "browser_authenticated_at": "2026-07-28T00:00:00Z",
            "connection_state": "actionable",
            "execution_ready": True,
        },
    }
    updated_account = {**account, "metadata": {}}
    repo = MagicMock()
    repo.get = AsyncMock(return_value=account)
    repo.update = AsyncMock(return_value=updated_account)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(personal_ip_account_repo=repo),
        ),
    )
    paths = MagicMock()
    paths.browser_profile_dir.return_value = profile_dir
    manager = MagicMock()
    manager.close_session = AsyncMock(return_value=True)

    monkeypatch.setattr(
        accounts_router,
        "_current_user_id",
        AsyncMock(return_value="user-1"),
    )
    monkeypatch.setattr(accounts_router, "get_paths", lambda: paths)
    monkeypatch.setattr(
        accounts_router,
        "get_browser_session_manager",
        lambda: manager,
    )

    result = await accounts_router.logout_personal_ip_account(
        "acct-douyin",
        request,
    )

    assert result == updated_account
    assert not profile_dir.exists()
    manager.close_session.assert_awaited_once_with(
        "account:user-1:acct-douyin",
    )
    updates = repo.update.await_args.kwargs["updates"]
    metadata = updates["metadata"]
    assert metadata["connection_state"] == "pending_login"
    assert metadata["browser_authenticated"] is False
    assert metadata["execution_ready"] is False
    assert "browser_authenticated_at" not in metadata
    assert "logged_out_at" in metadata


@pytest.mark.asyncio
async def test_delete_subject_rejects_immutable_content_lineage(monkeypatch) -> None:
    subject_repo = SimpleNamespace(
        get=AsyncMock(return_value={"id": "subject-1", "owner_user_id": "user-1"}),
        delete=AsyncMock(return_value=True),
    )
    account_repo = SimpleNamespace(list=AsyncMock(return_value=[]))
    content_repo = SimpleNamespace(has_subject_content=AsyncMock(return_value=True))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                personal_ip_subject_repo=subject_repo,
                personal_ip_account_repo=account_repo,
                personal_ip_content_repo=content_repo,
            )
        )
    )
    monkeypatch.setattr(
        accounts_router,
        "_current_user_id",
        AsyncMock(return_value="user-1"),
    )

    with pytest.raises(HTTPException) as error:
        await accounts_router.delete_personal_ip_subject("subject-1", request)

    assert error.value.status_code == 409
    assert "immutable content lineage" in error.value.detail
    content_repo.has_subject_content.assert_awaited_once_with(
        "subject-1",
        owner_user_id="user-1",
    )
    subject_repo.delete.assert_not_awaited()
