from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_platform_connections import PersonalIPPlatformConnectionRepository
from deerflow.persistence.personal_ip_platform_connections.model import (
    PersonalIPPlatformCredentialRow,
    PersonalIPPlatformOAuthStateRow,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_platform_connection_encrypts_grant_and_consumes_state_once(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音账号")
    repository = PersonalIPPlatformConnectionRepository(
        sf,
        cipher=ChannelCredentialCipher.from_key("test-only-credential-key"),
    )

    state = await repository.create_oauth_state(
        owner_user_id="user-1",
        account_id=account["id"],
        platform="douyin",
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert state["state"]
    async with sf() as session:
        state_rows = (await session.execute(select(PersonalIPPlatformOAuthStateRow))).scalars().all()
    assert len(state_rows) == 1
    assert state_rows[0].state_hash != state["state"]
    assert state["state"] not in state_rows[0].state_hash

    consumed = await repository.consume_oauth_state(
        state=state["state"],
        owner_user_id="user-1",
        now=NOW + timedelta(minutes=1),
    )
    assert consumed == {
        "account_id": account["id"],
        "owner_user_id": "user-1",
        "platform": "douyin",
        "requested_scopes": ["ma.video.bind"],
    }
    assert (
        await repository.consume_oauth_state(
            state=state["state"],
            owner_user_id="user-1",
            now=NOW + timedelta(minutes=1),
        )
        is None
    )

    connection = await repository.store_grant(
        owner_user_id="user-1",
        account_id=account["id"],
        platform="douyin",
        external_user_id="mini-open-id",
        oauth_open_id="oauth-open-id",
        access_token="act.super-secret",
        refresh_token="rft.super-secret",
        scopes=["ma.video.bind"],
        access_expires_at=NOW + timedelta(days=15),
        refresh_expires_at=NOW + timedelta(days=30),
        now=NOW,
    )
    assert connection["status"] == "connected"
    assert connection["external_user_id"] == "mini-open-id"
    assert "access_token" not in connection
    assert "refresh_token" not in connection
    assert not any(key.startswith("encrypted_") for key in connection)

    credentials = await repository.get_credentials(
        connection["id"],
        owner_user_id="user-1",
    )
    assert credentials is not None
    assert credentials["access_token"] == "act.super-secret"
    assert credentials["refresh_token"] == "rft.super-secret"

    async with sf() as session:
        credential = (await session.execute(select(PersonalIPPlatformCredentialRow))).scalar_one()
    assert credential.encrypted_access_token != "act.super-secret"
    assert credential.encrypted_refresh_token != "rft.super-secret"
    assert "super-secret" not in credential.encrypted_access_token
    assert "super-secret" not in credential.encrypted_refresh_token
    await close_engine()


@pytest.mark.asyncio
async def test_platform_connection_rejects_foreign_or_expired_state_and_wipes_revoked_tokens(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音账号")
    repository = PersonalIPPlatformConnectionRepository(sf, cipher=ChannelCredentialCipher.from_key("test-key"))

    state = await repository.create_oauth_state(
        owner_user_id="user-1",
        account_id=account["id"],
        platform="douyin",
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert await repository.consume_oauth_state(state=state["state"], owner_user_id="user-2", now=NOW) is None
    assert (
        await repository.consume_oauth_state(
            state=state["state"],
            owner_user_id="user-1",
            now=NOW + timedelta(minutes=11),
        )
        is None
    )

    connection = await repository.store_grant(
        owner_user_id="user-1",
        account_id=account["id"],
        platform="douyin",
        external_user_id="mini-open-id",
        oauth_open_id="oauth-open-id",
        access_token="access-token",
        refresh_token="refresh-token",
        scopes=["ma.video.bind"],
        access_expires_at=NOW + timedelta(days=15),
        refresh_expires_at=NOW + timedelta(days=30),
        now=NOW,
    )
    assert await repository.get(connection["id"], owner_user_id="user-2") is None
    assert await repository.revoke(connection["id"], owner_user_id="user-1", now=NOW) is True
    assert await repository.get_credentials(connection["id"], owner_user_id="user-1") is None
    revoked = await repository.get(connection["id"], owner_user_id="user-1")
    assert revoked is not None
    assert revoked["status"] == "revoked"

    async with sf() as session:
        credential = (await session.execute(select(PersonalIPPlatformCredentialRow))).scalar_one_or_none()
    assert credential is None
    await close_engine()


@pytest.mark.asyncio
async def test_platform_connection_requires_owned_active_matching_platform_account(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="xiaohongshu", display_name="小红书账号")
    repository = PersonalIPPlatformConnectionRepository(sf, cipher=ChannelCredentialCipher.from_key("test-key"))

    with pytest.raises(ValueError, match="account not found"):
        await repository.create_oauth_state(
            owner_user_id="user-2",
            account_id=account["id"],
            platform="xiaohongshu",
            expires_at=NOW + timedelta(minutes=10),
            now=NOW,
        )
    with pytest.raises(ValueError, match="platform does not match"):
        await repository.create_oauth_state(
            owner_user_id="user-1",
            account_id=account["id"],
            platform="douyin",
            expires_at=NOW + timedelta(minutes=10),
            now=NOW,
        )
    await close_engine()
