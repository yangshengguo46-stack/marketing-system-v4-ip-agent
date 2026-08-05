from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.base import Base
from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_platform_connections import PersonalIPPlatformConnectionRepository
from deerflow.persistence.personal_ip_platform_connections.model import (
    PersonalIPPlatformConnectionRow,
    PersonalIPPlatformCredentialRow,
    PersonalIPPlatformOAuthStateRow,
)
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.persistence.personal_ip_video_productions import (
    PersonalIPVideoProductionRepository,
)
from deerflow.personal_ip.content_contracts import ContentWorkAppend, ContentWorkCreate
from deerflow.personal_ip.data_lifecycle import (
    DELETE_CONFIRMATION_PHRASE,
    EXPORT_DATASET_NAMES,
    PERSONAL_IP_DELETION_ONLY_TABLES,
    PERSONAL_IP_EXPORT_TABLES,
    PERSONAL_IP_SECRET_TABLES,
    PersonalIPDataLifecycleService,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def _canonical_digest(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _resign_backup(backup: dict) -> dict:
    for dataset in backup["datasets"]:
        dataset["count"] = len(dataset["records"])
        dataset["digest"] = _canonical_digest({"name": dataset["name"], "records": dataset["records"]})
    data_digest = _canonical_digest([{"name": dataset["name"], "records": dataset["records"]} for dataset in backup["datasets"]])
    backup["verification"]["data_digest"] = data_digest
    backup["verification"]["manifest_digest"] = _canonical_digest(
        {
            "schema_version": backup["schema_version"],
            "owner_user_id": backup["owner_user_id"],
            "exported_at": backup["exported_at"],
            "dataset_digests": [
                {
                    "name": dataset["name"],
                    "count": dataset["count"],
                    "digest": dataset["digest"],
                }
                for dataset in backup["datasets"]
            ],
            "data_digest": data_digest,
        }
    )
    return backup


def _dataset(backup: dict, name: str) -> dict:
    return next(dataset for dataset in backup["datasets"] if dataset["name"] == name)


def _legacy_backup(current: dict, schema_version: str) -> dict:
    legacy = copy.deepcopy(current)
    legacy["schema_version"] = schema_version
    for record in _dataset(legacy, "video_productions")["records"]:
        record.pop("content_work_id")
        record.pop("script_version_id")
    if schema_version == "personal-ip-owner-backup-v1":
        legacy["datasets"] = [
            dataset
            for dataset in legacy["datasets"]
            if dataset["name"]
            not in {
                "content_works",
                "breakdown_versions",
                "direction_versions",
                "script_versions",
            }
        ]
    return _resign_backup(legacy)


def _production_request_digest(record: dict) -> str:
    payload = {
        "budget": record["budget_json"],
        "delivery_spec": record["delivery_spec_json"],
        "provider_policy": record["provider_policy_json"],
        "source": record["source_json"],
        "source_kind": record["source_kind"],
        "subject_id": record["subject_id"],
        "target_account_ids": record["target_account_ids_json"],
        "thread_id": record["thread_id"],
        "title": record["title"],
    }
    if record["content_work_id"] is not None:
        payload.update(
            {
                "content_work_id": record["content_work_id"],
                "script_version_id": record["script_version_id"],
            }
        )
    return _canonical_digest(payload)


def _delete_confirmation(preview: dict, owner_user_id: str) -> dict:
    return {
        "schema_version": "personal-ip-destructive-delete-confirmation-v1",
        "owner_user_id": owner_user_id,
        "state_digest": preview["state_digest"],
        "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
        "backup_acknowledged": True,
        "delete_local_context": True,
    }


class _FakeMineContext:
    def __init__(self) -> None:
        self.deleted_owners: list[str] = []

    def clear(self, owner_user_id: str, *, scope: str) -> dict:
        assert scope == "all"
        self.deleted_owners.append(owner_user_id)
        return {"scope": scope, "local_data_deleted": True}


def test_every_personal_ip_table_is_exported_or_explicitly_secret_deletion_only() -> None:
    actual = {table_name for table_name in Base.metadata.tables if table_name.startswith("personal_ip_")}
    assert actual == PERSONAL_IP_EXPORT_TABLES | PERSONAL_IP_SECRET_TABLES | PERSONAL_IP_DELETION_ONLY_TABLES
    assert PERSONAL_IP_EXPORT_TABLES.isdisjoint(PERSONAL_IP_SECRET_TABLES)
    assert PERSONAL_IP_EXPORT_TABLES.isdisjoint(PERSONAL_IP_DELETION_ONLY_TABLES)
    assert PERSONAL_IP_SECRET_TABLES.isdisjoint(PERSONAL_IP_DELETION_ONLY_TABLES)


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
    content_request = ContentWorkCreate.model_validate(
        {
            "idempotency_key": f"{owner_user_id}:lifecycle-content",
            "subject_id": subject["id"],
            "title": "可备份内容",
            "entry_route": "zero_start",
            "objective": {"desired_change": "验证内容谱系可完整备份"},
            "direction": {
                "premise": "一次已经发生的验证",
                "audience_situation": "需要确认数据完整的人",
                "core_tension": "完整性不能靠口头声明",
                "content_promise": "展示一条可恢复的事实记录",
                "creative_route": "事实说明",
                "rationale": "只使用测试明确提供的事实。",
                "truth_mode": "factual",
                "claim_basis": [
                    {
                        "claim": "这是一条生命周期测试记录",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
            "script": {
                "title": "可备份内容",
                "story_mode": "factual",
                "script_text": "这是一条生命周期测试记录。",
                "claim_basis": [
                    {
                        "claim": "这是一条生命周期测试记录",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
        }
    )
    assert content_request.script is not None
    script_payload = json.dumps(
        content_request.script.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    await PersonalIPContentRepository(sf).create(
        owner_user_id=owner_user_id,
        request=content_request,
        verified_script_digests=frozenset({hashlib.sha256(script_payload).hexdigest()}),
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
        assert backup["schema_version"] == "personal-ip-owner-backup-v3"
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


@pytest.mark.parametrize(
    ("schema_version", "restores_content"),
    [
        ("personal-ip-owner-backup-v1", False),
        ("personal-ip-owner-backup-v2", True),
    ],
)
@pytest.mark.asyncio
async def test_restore_accepts_verified_legacy_backup_shapes(
    tmp_path,
    schema_version: str,
    restores_content: bool,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    service = PersonalIPDataLifecycleService(sf, minecontext=_FakeMineContext())
    try:
        subject, _, _ = await _seed_owner(sf, "user-1")
        production_repo = PersonalIPVideoProductionRepository(sf)
        production = await production_repo.begin(
            owner_user_id="user-1",
            operation_key="legacy-production",
            title="旧版可恢复制作",
            subject_id=subject["id"],
            target_account_ids=[],
            source_kind="idea",
            source={"idea": "旧版备份保留原始制作请求"},
            delivery_spec={"aspect_ratio": "9:16"},
            provider_policy={},
            budget={},
            thread_id="legacy-production-thread",
        )
        await production_repo.append_event(
            production["id"],
            owner_user_id="user-1",
            event_key="legacy-review-request",
            event_type="review_requested",
            status="awaiting_review",
            entity_type="production",
            entity_id=production["id"],
            payload={"review_kind": "general"},
            input_refs=[],
            output_refs=[],
            provider="deerflow",
            model=None,
            provider_task_id=None,
            cost={},
            occurred_at=NOW,
        )
        current = await service.export_backup("user-1", now=NOW)
        legacy = _legacy_backup(current, schema_version)

        preview = await service.preview_delete("user-1", now=NOW)
        await service.delete_all(
            "user-1",
            _delete_confirmation(preview, "user-1"),
            now=NOW,
        )
        receipt = await service.restore_backup("user-1", legacy)

        assert receipt["verified"] is True
        assert await PersonalIPSubjectRepository(sf).list("user-1")
        assert await PersonalIPAccountRepository(sf).list("user-1")
        content_works = await PersonalIPContentRepository(sf).list(
            "user-1",
            include_archived=True,
        )
        assert bool(content_works) is restores_content
        productions = await PersonalIPVideoProductionRepository(sf).list("user-1")
        assert len(productions) == 1
        assert productions[0]["content_work_id"] is None
        assert productions[0]["script_version_id"] is None
        restored_production = await PersonalIPVideoProductionRepository(sf).get(
            productions[0]["id"],
            owner_user_id="user-1",
        )
        assert restored_production is not None
        assert len(restored_production["events"]) == 1
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_restore_rejects_resigned_cross_owner_and_corrupt_content_graphs(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    service = PersonalIPDataLifecycleService(sf, minecontext=_FakeMineContext())
    try:
        await _seed_owner(sf, "user-1")
        await _seed_owner(sf, "user-2")
        content = PersonalIPContentRepository(sf)
        owner_work = (await content.list("user-1"))[0]
        await content.append(
            owner_work["id"],
            owner_user_id="user-1",
            request=ContentWorkAppend.model_validate(
                {
                    "idempotency_key": "user-1:owner-material",
                    "breakdown": {
                        "source_kind": "owner_material",
                        "source_identity": {"ref": "owner://note-1"},
                        "observations": [
                            {
                                "observation": "Owner 提供了一条明确素材",
                                "evidence_refs": ["owner://note-1#line-1"],
                            }
                        ],
                    },
                }
            ),
        )
        lineage = await content.get_lineage(
            owner_work["id"],
            owner_user_id="user-1",
        )
        assert lineage is not None
        owner_script = lineage["script_versions"][0]
        await PersonalIPVideoProductionRepository(sf).begin(
            owner_user_id="user-1",
            operation_key="linked-production",
            title="绑定不可变脚本的制作",
            subject_id=None,
            target_account_ids=[],
            source_kind="script",
            source={},
            delivery_spec={"aspect_ratio": "9:16"},
            provider_policy={},
            budget={},
            production_mode="faceless_material",
            thread_id="linked-production-thread",
            content_work_id=owner_work["id"],
            script_version_id=owner_script["id"],
        )
        backup = await service.export_backup("user-1", now=NOW)
        foreign_work_id = (await PersonalIPContentRepository(sf).list("user-2"))[0]["id"]

        cross_owner = copy.deepcopy(backup)
        _dataset(cross_owner, "direction_versions")["records"][0]["content_work_id"] = foreign_work_id
        _resign_backup(cross_owner)
        with pytest.raises(ValueError, match="does not belong to this Owner backup"):
            await service.restore_backup("user-1", cross_owner)

        bad_parent = copy.deepcopy(backup)
        direction = _dataset(bad_parent, "direction_versions")["records"][0]
        direction["parent_direction_version_id"] = "direction-missing"
        direction["direction_json"]["parent_direction_version_id"] = "direction-missing"
        _resign_backup(bad_parent)
        with pytest.raises(ValueError, match="DirectionVersion parent is invalid"):
            await service.restore_backup("user-1", bad_parent)

        bad_objective = copy.deepcopy(backup)
        _dataset(bad_objective, "direction_versions")["records"][0]["objective_snapshot_json"]["desired_change"] = "重算摘要也不能替换目标快照"
        _resign_backup(bad_objective)
        with pytest.raises(ValueError, match="objective snapshot does not match"):
            await service.restore_backup("user-1", bad_objective)

        forged_snapshot = copy.deepcopy(backup)
        _dataset(forged_snapshot, "breakdown_versions")["records"][0]["evidence_snapshot_json"] = {"forged": True}
        _resign_backup(forged_snapshot)
        with pytest.raises(ValueError, match="owner material cannot contain"):
            await service.restore_backup("user-1", forged_snapshot)

        foreign_production_link = copy.deepcopy(backup)
        production = _dataset(
            foreign_production_link,
            "video_productions",
        )["records"][0]
        production["content_work_id"] = foreign_work_id
        production["request_digest"] = _production_request_digest(production)
        _resign_backup(foreign_production_link)
        with pytest.raises(ValueError, match="linked video production"):
            await service.restore_backup("user-1", foreign_production_link)

        forged_source = copy.deepcopy(backup)
        production = _dataset(forged_source, "video_productions")["records"][0]
        production["source_json"]["script_text"] = "恶意替换后的脚本"
        source_payload = {key: value for key, value in production["source_json"].items() if key not in {"production_mode", "snapshot_sha256"}}
        production["source_json"]["snapshot_sha256"] = _canonical_digest(source_payload)
        production["request_digest"] = _production_request_digest(production)
        _resign_backup(forged_source)
        with pytest.raises(ValueError, match="source snapshot does not match"):
            await service.restore_backup("user-1", forged_source)
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
