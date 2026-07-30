from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.base import Base
from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_platform_connections import PersonalIPPlatformConnectionRepository
from deerflow.persistence.personal_ip_platform_connections.model import (
    PersonalIPPlatformConnectionRow,
    PersonalIPPlatformCredentialRow,
    PersonalIPPlatformOAuthStateRow,
)
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.personal_ip.data_lifecycle import (
    DELETE_CONFIRMATION_PHRASE,
    EXPORT_DATASET_NAMES,
    PERSONAL_IP_EXPORT_TABLES,
    PERSONAL_IP_SECRET_TABLES,
    PersonalIPDataLifecycleService,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class _FakeMineContext:
    def __init__(self) -> None:
        self.deleted_owners: list[str] = []

    def clear(self, owner_user_id: str, *, scope: str) -> dict:
        assert scope == "all"
        self.deleted_owners.append(owner_user_id)
        return {"scope": scope, "local_data_deleted": True}


def test_every_personal_ip_table_is_exported_or_explicitly_secret_deletion_only() -> None:
    actual = {table_name for table_name in Base.metadata.tables if table_name.startswith("personal_ip_")}
    assert actual == PERSONAL_IP_EXPORT_TABLES | PERSONAL_IP_SECRET_TABLES
    assert PERSONAL_IP_EXPORT_TABLES.isdisjoint(PERSONAL_IP_SECRET_TABLES)


async def _seed_owner(sf, owner_user_id: str) -> tuple[dict, dict, PersonalIPPlatformConnectionRepository]:
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    subject = await subjects.create(
        owner_user_id=owner_user_id,
        display_name=f"{owner_user_id}主体",
        metadata={"source": "lifecycle-test"},
    )
    account = await accounts.create(
        owner_user_id=owner_user_id,
        subject_id=subject["id"],
        platform="douyin",
        display_name=f"{owner_user_id}账号",
    )
    connections = PersonalIPPlatformConnectionRepository(
        sf,
        cipher=ChannelCredentialCipher.from_key("personal-ip-lifecycle-test-key"),
    )
    state = await connections.create_oauth_state(
        owner_user_id=owner_user_id,
        account_id=account["id"],
        platform="douyin",
        requested_scopes=["ma.video.bind"],
        expires_at=NOW + timedelta(minutes=10),
        now=NOW,
    )
    assert state["state"]
    await connections.store_grant(
        owner_user_id=owner_user_id,
        account_id=account["id"],
        platform="douyin",
        external_user_id=f"external-{owner_user_id}",
        oauth_open_id=f"open-{owner_user_id}",
        access_token=f"access-secret-{owner_user_id}",
        refresh_token=f"refresh-secret-{owner_user_id}",
        scopes=["ma.video.bind"],
        access_expires_at=NOW + timedelta(days=7),
        refresh_expires_at=NOW + timedelta(days=30),
        now=NOW,
    )
    return subject, account, connections


@pytest.mark.asyncio
async def test_export_is_complete_owner_scoped_credential_free_and_verified_restore(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    minecontext = _FakeMineContext()
    service = PersonalIPDataLifecycleService(sf, minecontext=minecontext)
    try:
        await _seed_owner(sf, "user-1")
        await _seed_owner(sf, "user-2")

        backup = await service.export_backup("user-1", now=NOW)
        assert backup["schema_version"] == "personal-ip-owner-backup-v1"
        assert backup["owner_user_id"] == "user-1"
        assert [dataset["name"] for dataset in backup["datasets"]] == list(EXPORT_DATASET_NAMES)
        assert backup["verification"]["data_digest"]
        assert backup["verification"]["manifest_digest"]

        serialized = json.dumps(backup, ensure_ascii=False)
        assert "access-secret-user-1" not in serialized
        assert "refresh-secret-user-1" not in serialized
        assert "encrypted_access_token" not in serialized
        assert "encrypted_refresh_token" not in serialized
        assert "state_hash" not in serialized
        connection_dataset = next(item for item in backup["datasets"] if item["name"] == "platform_connections")
        assert connection_dataset["records"][0]["status"] == "revoked"
        assert connection_dataset["records"][0]["credential_state"] == "omitted_reauthorization_required"

        tampered = copy.deepcopy(backup)
        tampered["datasets"][0]["records"][0]["display_name"] = "篡改"
        with pytest.raises(ValueError, match="digest"):
            await service.restore_backup("user-1", tampered)

        preview = await service.preview_delete("user-1", now=NOW)
        await service.delete_all(
            "user-1",
            {
                "schema_version": "personal-ip-destructive-delete-confirmation-v1",
                "owner_user_id": "user-1",
                "state_digest": preview["state_digest"],
                "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
                "backup_acknowledged": True,
                "delete_local_context": True,
            },
            now=NOW,
        )
        assert minecontext.deleted_owners == ["user-1"]

        restored = await service.restore_backup("user-1", backup)
        assert restored["schema_version"] == "personal-ip-owner-restore-receipt-v1"
        assert restored["verified"] is True
        assert restored["restored_data_digest"] == backup["verification"]["data_digest"]
        restored_backup = await service.export_backup("user-1", now=NOW)
        assert restored_backup["verification"]["data_digest"] == backup["verification"]["data_digest"]

        async with sf() as session:
            connection = (await session.execute(select(PersonalIPPlatformConnectionRow).where(PersonalIPPlatformConnectionRow.owner_user_id == "user-1"))).scalar_one()
            credential_count = (await session.execute(select(func.count()).select_from(PersonalIPPlatformCredentialRow).where(PersonalIPPlatformCredentialRow.connection_id == connection.id))).scalar_one()
        assert connection.status == "revoked"
        assert credential_count == 0
        assert await PersonalIPSubjectRepository(sf).list("user-2")
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_delete_requires_exact_fresh_confirmation_and_removes_secrets_without_cross_owner_loss(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    minecontext = _FakeMineContext()
    service = PersonalIPDataLifecycleService(sf, minecontext=minecontext)
    try:
        _, account, _ = await _seed_owner(sf, "user-1")
        await _seed_owner(sf, "user-2")
        preview = await service.preview_delete("user-1", now=NOW)

        bad = {
            "schema_version": "personal-ip-destructive-delete-confirmation-v1",
            "owner_user_id": "user-1",
            "state_digest": preview["state_digest"],
            "confirmation_phrase": "删除",
            "backup_acknowledged": True,
            "delete_local_context": True,
        }
        with pytest.raises(ValueError, match="confirmation phrase"):
            await service.delete_all("user-1", bad, now=NOW)

        await PersonalIPAccountRepository(sf).create(
            owner_user_id="user-1",
            subject_id=account["subject_id"],
            platform="youtube",
            display_name="数据变化",
        )
        stale = dict(bad)
        stale["confirmation_phrase"] = DELETE_CONFIRMATION_PHRASE
        with pytest.raises(ValueError, match="state changed"):
            await service.delete_all("user-1", stale, now=NOW)

        fresh = await service.preview_delete("user-1", now=NOW)
        receipt = await service.delete_all(
            "user-1",
            {
                "schema_version": "personal-ip-destructive-delete-confirmation-v1",
                "owner_user_id": "user-1",
                "state_digest": fresh["state_digest"],
                "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
                "backup_acknowledged": True,
                "delete_local_context": True,
            },
            now=NOW,
        )
        assert receipt["schema_version"] == "personal-ip-destructive-delete-receipt-v1"
        assert receipt["deleted_records"] == fresh["total_records"]
        assert receipt["local_context_deleted"] is True

        async with sf() as session:
            assert (await session.execute(select(func.count()).select_from(PersonalIPSubjectRow).where(PersonalIPSubjectRow.owner_user_id == "user-1"))).scalar_one() == 0
            assert (await session.execute(select(func.count()).select_from(PersonalIPPlatformCredentialRow))).scalar_one() == 1
            assert (await session.execute(select(func.count()).select_from(PersonalIPPlatformOAuthStateRow).where(PersonalIPPlatformOAuthStateRow.owner_user_id == "user-1"))).scalar_one() == 0
        assert await PersonalIPSubjectRepository(sf).list("user-2")
    finally:
        await close_engine()
