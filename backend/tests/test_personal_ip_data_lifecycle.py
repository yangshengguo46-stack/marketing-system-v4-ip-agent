from __future__ import annotations

import copy
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.gateway.routers import personal_ip_artifacts, personal_ip_data_lifecycle
from deerflow.config.database_config import DatabaseConfig
from deerflow.config.paths import Paths
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
from deerflow.personal_ip.video_contracts import (
    compile_final_edit_lock,
    compile_timeline_revision,
)

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
BACKUP_SIGNING_KEY = "personal-ip-lifecycle-backup-test-key-v1"


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
    manifest = {
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
    if backup["schema_version"] == "personal-ip-owner-backup-v4":
        manifest.update(
            {
                "credential_policy": backup["credential_policy"],
                "artifact_policy": backup["artifact_policy"],
                "verification_algorithm": backup["verification"]["algorithm"],
                "signing_key_id": backup["verification"]["key_id"],
            }
        )
        derived_key = hashlib.sha256(b"personal-ip-owner-backup-signing-v1\0" + BACKUP_SIGNING_KEY.encode("utf-8")).digest()
        backup["verification"]["manifest_digest"] = hmac.new(
            derived_key,
            b"personal-ip-owner-backup-v4\0"
            + json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    else:
        backup["verification"]["manifest_digest"] = _canonical_digest(manifest)
    return backup


def _dataset(backup: dict, name: str) -> dict:
    return next(dataset for dataset in backup["datasets"] if dataset["name"] == name)


def _legacy_backup(current: dict, schema_version: str) -> dict:
    legacy = copy.deepcopy(current)
    legacy["schema_version"] = schema_version
    legacy["verification"]["algorithm"] = "sha256-canonical-json-v1"
    legacy["verification"].pop("key_id", None)
    legacy["datasets"] = [dataset for dataset in legacy["datasets"] if dataset["name"] != "artifacts"]
    if schema_version in {
        "personal-ip-owner-backup-v1",
        "personal-ip-owner-backup-v2",
    }:
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


def _production_event_digest(record: dict) -> str:
    occurred_at = datetime.fromisoformat(record["occurred_at"].replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return _canonical_digest(
        {
            "cost": record["cost_json"],
            "entity_id": record["entity_id"],
            "entity_type": record["entity_type"],
            "event_type": record["event_type"],
            "input_refs": record["input_refs_json"],
            "model": record["model"],
            "occurred_at": occurred_at.astimezone(UTC).isoformat(),
            "output_refs": record["output_refs_json"],
            "payload": record["payload_json"],
            "provider": record["provider"],
            "provider_task_id": record["provider_task_id"],
            "stage": record["stage"],
            "status": record["status"],
        }
    )


def _delete_confirmation(preview: dict, owner_user_id: str) -> dict:
    return {
        "schema_version": "personal-ip-destructive-delete-confirmation-v1",
        "owner_user_id": owner_user_id,
        "state_digest": preview["state_digest"],
        "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
        "backup_acknowledged": True,
        "artifact_files_acknowledged": True,
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


async def _seed_final_artifact(sf, paths: Paths, owner_user_id: str) -> tuple[dict, object]:
    content = PersonalIPContentRepository(sf)
    productions = PersonalIPVideoProductionRepository(sf)
    work = (await content.list(owner_user_id))[0]
    lineage = await content.get_lineage(work["id"], owner_user_id=owner_user_id)
    assert lineage is not None
    script = lineage["script_versions"][0]
    production = await productions.begin(
        owner_user_id=owner_user_id,
        operation_key=f"{owner_user_id}:lifecycle-final-artifact",
        title="生命周期正式成片",
        subject_id=work["subject_id"],
        target_account_ids=[],
        source_kind="script",
        source={},
        delivery_spec={"aspect_ratio": "9:16"},
        provider_policy={},
        budget={},
        production_mode="faceless_material",
        thread_id=f"{owner_user_id}-final-artifact",
        content_work_id=work["id"],
        script_version_id=script["id"],
    )
    revision = compile_timeline_revision(
        production_id=production["id"],
        production_mode="faceless_material",
        revision_id="lifecycle-timeline-r1",
        base_revision_id=None,
        author_kind="human",
        intent="确认生命周期测试成片",
        fps=25,
        tracks=[
            {
                "id": "video",
                "type": "video",
                "clips": [
                    {
                        "id": "clip-1",
                        "start_sec": 0,
                        "duration_sec": 2,
                        "source_in_sec": 0,
                    }
                ],
            }
        ],
        operations=[
            {
                "id": "edit-1",
                "type": "trim",
                "clip_id": "clip-1",
                "source_in_sec": 0,
                "duration_sec": 2,
            }
        ],
        strategy_confirmed=True,
    )
    await productions.append_event(
        production["id"],
        owner_user_id=owner_user_id,
        event_key="lifecycle:timeline:r1",
        event_type="timeline_revision_compiled",
        status="succeeded",
        entity_type="timeline",
        entity_id="lifecycle-timeline-r1",
        payload=revision,
        input_refs=[f"video-production://{production['id']}/assembly"],
        output_refs=[f"contract://timeline/{revision['sha256']}"],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    final_lock = compile_final_edit_lock(
        production_id=production["id"],
        production_mode="faceless_material",
        lock_id="lifecycle-final-lock-1",
        timeline_revision=revision,
        locked_by="human",
        note="确认进入交付 QA",
    )
    await productions.append_event(
        production["id"],
        owner_user_id=owner_user_id,
        event_key="lifecycle:final-lock:1",
        event_type="final_edit_locked",
        status="succeeded",
        entity_type="timeline",
        entity_id="lifecycle-final-lock-1",
        payload=final_lock,
        input_refs=["timeline-revision://lifecycle-timeline-r1"],
        output_refs=[f"contract://final-lock/{final_lock['sha256']}"],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )

    storage_key = "video-deliveries/lifecycle/final.mp4"
    artifact_file = paths.user_dir(owner_user_id) / storage_key
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_bytes(b"lifecycle-final-artifact")
    source_ref = artifact_file.as_uri()
    content_sha256 = hashlib.sha256(artifact_file.read_bytes()).hexdigest()
    size_bytes = artifact_file.stat().st_size
    mime_type = "video/mp4"
    execution_payload = {
        "contract_version": "personal-ip-media-execution-v1",
        "capability": "media_processing",
        "provider": "project-ffmpeg",
        "executor": "lifecycle-test",
        "model": None,
        "status": "succeeded",
        "task_id": None,
        "request_id": "lifecycle-render-1",
        "started_at": "2026-08-05T01:00:00+00:00",
        "completed_at": "2026-08-05T01:00:01+00:00",
        "parameters": {"job_kind": "locked_timeline_delivery"},
        "inputs": [],
        "outputs": [
            {
                "ref": source_ref,
                "sha256": content_sha256,
                "size_bytes": size_bytes,
                "mime_type": mime_type,
            }
        ],
        "cost": {"status": "known", "amount": 0, "currency": "CNY"},
        "failure": None,
    }
    await productions.append_event(
        production["id"],
        owner_user_id=owner_user_id,
        event_key="lifecycle:render:final",
        event_type="media_processing_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="lifecycle-final-lock-1",
        payload=execution_payload,
        input_refs=["contract://final-lock/lifecycle"],
        output_refs=[source_ref],
        provider="project-ffmpeg",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    qa_payload = {
        "contract_version": "personal-ip-delivery-qa-v1",
        "passed": True,
        "artifact": execution_payload["outputs"][0],
        "delivery_spec": {"aspect_ratio": "9:16"},
        "checks": [{"name": "decode", "passed": True}],
        "probe": {"video_codec": "h264", "width": 1080, "height": 1920},
        "executors": {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"},
    }
    await productions.append_event(
        production["id"],
        owner_user_id=owner_user_id,
        event_key="lifecycle:qa:final",
        event_type="delivery_qa_completed",
        status="succeeded",
        entity_type="delivery",
        entity_id="lifecycle-final-lock-1",
        payload=qa_payload,
        input_refs=[source_ref],
        output_refs=[source_ref],
        provider="project-ffmpeg-ffprobe",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
        trusted_delivery_qa=True,
    )
    completed = await productions.complete_delivery_and_seal_artifact(
        production["id"],
        owner_user_id=owner_user_id,
        event_key="lifecycle:delivery:final",
        qa_event_key="lifecycle:qa:final",
        source_execution_event_keys=["lifecycle:render:final"],
        source_ref=source_ref,
        storage_key=storage_key,
        sha256=content_sha256,
        size_bytes=size_bytes,
        mime_type=mime_type,
        metadata={"source_revision_id": "lifecycle-timeline-r1"},
        provider="project-ffmpeg",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
        occurred_at=NOW,
    )
    assert completed is not None
    return completed, artifact_file


@pytest.mark.asyncio
async def test_export_is_complete_owner_scoped_credential_free_and_verified_restore(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    minecontext = _FakeMineContext()
    service = PersonalIPDataLifecycleService(
        sf,
        minecontext=minecontext,
        backup_signing_key=BACKUP_SIGNING_KEY,
    )
    try:
        await _seed_owner(sf, "user-1")
        await _seed_owner(sf, "user-2")

        backup = await service.export_backup("user-1", now=NOW)
        assert backup["schema_version"] == "personal-ip-owner-backup-v4"
        assert backup["owner_user_id"] == "user-1"
        assert [dataset["name"] for dataset in backup["datasets"]] == list(EXPORT_DATASET_NAMES)
        assert backup["verification"]["data_digest"]
        assert backup["verification"]["manifest_digest"]

        wrong_key_service = PersonalIPDataLifecycleService(
            sf,
            minecontext=minecontext,
            backup_signing_key="wrong-personal-ip-backup-signing-key-v1",
        )
        with pytest.raises(ValueError, match="signing key"):
            await wrong_key_service.restore_backup("user-1", backup)
        bad_mac = copy.deepcopy(backup)
        manifest_digest = bad_mac["verification"]["manifest_digest"]
        bad_mac["verification"]["manifest_digest"] = manifest_digest[:-1] + ("0" if manifest_digest[-1] != "0" else "1")
        with pytest.raises(ValueError, match="manifest digest"):
            await service.restore_backup("user-1", bad_mac)

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
                "artifact_files_acknowledged": True,
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
async def test_final_artifact_backup_restore_and_binary_deletion_are_fail_closed(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path / "database")))
    sf = get_session_factory()
    assert sf is not None
    paths = Paths(tmp_path / "state")
    service = PersonalIPDataLifecycleService(
        sf,
        minecontext=_FakeMineContext(),
        backup_signing_key=BACKUP_SIGNING_KEY,
        paths=paths,
    )
    try:
        await _seed_owner(sf, "user-1")
        completed, artifact_file = await _seed_final_artifact(
            sf,
            paths,
            "user-1",
        )
        assert artifact_file.is_file()
        backup = await service.export_backup("user-1", now=NOW)
        assert backup["artifact_policy"] == {
            "metadata_included": True,
            "binary_files_included": False,
            "content_must_be_downloaded_separately": True,
        }
        artifact_dataset = _dataset(backup, "artifacts")
        assert artifact_dataset["count"] == 1
        assert artifact_dataset["records"][0]["id"] == completed["final_artifact"]["id"]

        misleading_policy = copy.deepcopy(backup)
        misleading_policy["artifact_policy"]["binary_files_included"] = True
        with pytest.raises(ValueError, match="Artifact policy"):
            await service.restore_backup("user-1", misleading_policy)
        wrong_algorithm = copy.deepcopy(backup)
        wrong_algorithm["verification"]["algorithm"] = "sha256-pretend-v1"
        with pytest.raises(ValueError, match="algorithm"):
            await service.restore_backup("user-1", wrong_algorithm)

        erased_formal_artifact = copy.deepcopy(backup)
        _dataset(erased_formal_artifact, "artifacts")["records"] = []
        delivery_event = next(
            event
            for event in _dataset(
                erased_formal_artifact,
                "video_production_events",
            )["records"]
            if event["event_type"] == "delivery_completed"
        )
        delivery_event["entity_type"] = "delivery"
        delivery_event["entity_id"] = "legacy-looking-delivery"
        delivery_event["event_digest"] = _production_event_digest(delivery_event)
        _resign_backup(erased_formal_artifact)
        with pytest.raises(ValueError, match="requires a formal final Artifact"):
            await service.restore_backup("user-1", erased_formal_artifact)

        resigned_tamper = copy.deepcopy(backup)
        _dataset(resigned_tamper, "artifacts")["records"][0]["sha256"] = "b" * 64
        _resign_backup(resigned_tamper)
        with pytest.raises(ValueError, match="does not match|digest"):
            await service.restore_backup("user-1", resigned_tamper)

        unsafe_path = copy.deepcopy(backup)
        _dataset(unsafe_path, "artifacts")["records"][0]["storage_key"] = "../outside.mp4"
        _resign_backup(unsafe_path)
        with pytest.raises(ValueError, match="storage key"):
            await service.restore_backup("user-1", unsafe_path)

        noncanonical_mime = copy.deepcopy(backup)
        _dataset(noncanonical_mime, "artifacts")["records"][0]["mime_type"] = "Video/mp4"
        _resign_backup(noncanonical_mime)
        with pytest.raises(ValueError, match="MIME type"):
            await service.restore_backup("user-1", noncanonical_mime)

        stale_source = copy.deepcopy(backup)
        production_record = _dataset(stale_source, "video_productions")["records"][0]
        event_records = _dataset(stale_source, "video_production_events")["records"]
        delivery_event = next(event for event in event_records if event["event_type"] == "delivery_completed")
        source_event = next(event for event in event_records if event["event_key"] == "lifecycle:render:final")
        newer_source_event = copy.deepcopy(source_event)
        newer_source_event.update(
            {
                "id": "lifecycle-render-newer-after-qa",
                "event_key": "lifecycle:render:newer-after-qa",
                "sequence": delivery_event["sequence"],
            }
        )
        newer_source_event["event_digest"] = _production_event_digest(newer_source_event)
        delivery_event["sequence"] += 1
        production_record["event_count"] += 1
        event_records.append(newer_source_event)
        _resign_backup(stale_source)
        with pytest.raises(ValueError, match="source execution is stale"):
            await service.restore_backup("user-1", stale_source)

        preview = await service.preview_delete("user-1", now=NOW)
        assert preview["includes_artifact_files"] is True
        receipt = await service.delete_all(
            "user-1",
            _delete_confirmation(preview, "user-1"),
            now=NOW,
        )
        assert receipt["artifact_files_deleted"] is True
        assert receipt["deleted_artifact_files"] == 1
        assert not artifact_file.exists()

        restored = await service.restore_backup("user-1", backup)
        assert restored["verified"] is True
        assert restored["ledger_verified"] is True
        assert restored["artifact_contents_restored"] is False
        assert restored["artifact_contents_requiring_reattach"] == 1
        restored_production = await PersonalIPVideoProductionRepository(sf).get(
            completed["id"],
            owner_user_id="user-1",
        )
        assert restored_production is not None
        assert restored_production["final_artifact"] == {
            **completed["final_artifact"],
            "content_available": False,
        }
        assert not artifact_file.exists()

        second_preview = await service.preview_delete("user-1", now=NOW)
        second_receipt = await service.delete_all(
            "user-1",
            _delete_confirmation(second_preview, "user-1"),
            now=NOW,
        )
        assert second_receipt["artifact_files_deleted"] is True
        assert second_receipt["deleted_artifact_files"] == 0
    finally:
        await close_engine()


@pytest.mark.parametrize(
    ("schema_version", "restores_content", "restores_links"),
    [
        ("personal-ip-owner-backup-v1", False, False),
        ("personal-ip-owner-backup-v2", True, False),
        ("personal-ip-owner-backup-v3", True, True),
    ],
)
@pytest.mark.asyncio
async def test_restore_accepts_verified_legacy_backup_shapes(
    tmp_path,
    schema_version: str,
    restores_content: bool,
    restores_links: bool,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    service = PersonalIPDataLifecycleService(
        sf,
        minecontext=_FakeMineContext(),
        backup_signing_key=BACKUP_SIGNING_KEY,
    )
    try:
        subject, _, _ = await _seed_owner(sf, "user-1")
        production_repo = PersonalIPVideoProductionRepository(sf)
        if restores_links:
            content_repo = PersonalIPContentRepository(sf)
            work = (await content_repo.list("user-1"))[0]
            lineage = await content_repo.get_lineage(
                work["id"],
                owner_user_id="user-1",
            )
            assert lineage is not None
            script = lineage["script_versions"][0]
            production = await production_repo.begin(
                owner_user_id="user-1",
                operation_key="legacy-production",
                title="旧版可恢复绑定制作",
                subject_id=subject["id"],
                target_account_ids=[],
                source_kind="script",
                source={},
                delivery_spec={"aspect_ratio": "9:16"},
                provider_policy={},
                budget={},
                production_mode="faceless_material",
                thread_id="legacy-production-thread",
                content_work_id=work["id"],
                script_version_id=script["id"],
            )
        else:
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
        if restores_links:
            legacy_production = _dataset(legacy, "video_productions")["records"][0]
            legacy_production["status"] = "completed"
            legacy_production["current_stage"] = "delivery"
            legacy_event = _dataset(legacy, "video_production_events")["records"][0]
            legacy_event.update(
                {
                    "event_type": "delivery_completed",
                    "stage": "delivery",
                    "status": "succeeded",
                    "entity_type": "delivery",
                    "entity_id": "legacy-delivery-v1",
                    "payload_json": {"accepted": True},
                    "input_refs_json": ["legacy://qa"],
                    "output_refs_json": ["legacy://final.mp4"],
                    "provider": "legacy-finisher",
                }
            )
            legacy_event["event_digest"] = _production_event_digest(legacy_event)
            _resign_backup(legacy)

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
        assert (productions[0]["content_work_id"] is not None) is restores_links
        assert (productions[0]["script_version_id"] is not None) is restores_links
        restored_production = await PersonalIPVideoProductionRepository(sf).get(
            productions[0]["id"],
            owner_user_id="user-1",
        )
        assert restored_production is not None
        assert len(restored_production["events"]) == 1
        assert restored_production["final_artifact"] is None
        if restores_links:
            assert restored_production["status"] == "completed"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_restore_rejects_resigned_cross_owner_and_corrupt_content_graphs(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    service = PersonalIPDataLifecycleService(
        sf,
        minecontext=_FakeMineContext(),
        backup_signing_key=BACKUP_SIGNING_KEY,
    )
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
    service = PersonalIPDataLifecycleService(
        sf,
        minecontext=minecontext,
        backup_signing_key=BACKUP_SIGNING_KEY,
    )
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
            "artifact_files_acknowledged": True,
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
                "artifact_files_acknowledged": True,
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


@pytest.mark.asyncio
async def test_gateway_sqlite_final_artifact_backup_delete_restore_and_reattach_roundtrip(
    monkeypatch,
    tmp_path,
) -> None:
    owner_user_id = "user-1"
    payload = b"lifecycle-final-artifact"
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path / "database")))
    sf = get_session_factory()
    assert sf is not None
    paths = Paths(tmp_path / "state")
    repository = PersonalIPVideoProductionRepository(sf)
    service = PersonalIPDataLifecycleService(
        sf,
        minecontext=_FakeMineContext(),
        backup_signing_key=BACKUP_SIGNING_KEY,
        paths=paths,
    )

    async def current_user(_request):
        return SimpleNamespace(id=owner_user_id)

    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.state.personal_ip_data_lifecycle_service = service
    app.include_router(personal_ip_artifacts.router)
    app.include_router(personal_ip_data_lifecycle.router)
    monkeypatch.setattr(
        personal_ip_artifacts,
        "get_current_user_from_request",
        current_user,
    )
    monkeypatch.setattr(
        personal_ip_data_lifecycle,
        "get_current_user_from_request",
        current_user,
    )
    monkeypatch.setattr(personal_ip_artifacts, "get_paths", lambda: paths)

    try:
        await _seed_owner(sf, owner_user_id)
        completed, artifact_file = await _seed_final_artifact(
            sf,
            paths,
            owner_user_id,
        )
        artifact = completed["final_artifact"]
        assert artifact["content_available"] is True
        assert artifact_file.read_bytes() == payload

        async with httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.ASGITransport(app=app),
        ) as client:
            metadata = await client.get(f"/api/personal-ip/artifacts/{artifact['id']}")
            initial_range = await client.get(
                f"/api/personal-ip/artifacts/{artifact['id']}/content",
                headers={"Range": "bytes=2-10"},
            )
            exported = await client.get("/api/personal-ip/data/export")

            assert metadata.status_code == 200
            assert metadata.json()["content_available"] is True
            assert metadata.json()["content_sha256"] == hashlib.sha256(payload).hexdigest()
            assert "storage_key" not in metadata.json()
            assert initial_range.status_code == 206
            assert initial_range.content == payload[2:11]

            backup = exported.json()
            assert exported.status_code == 200
            assert backup["schema_version"] == "personal-ip-owner-backup-v4"
            assert backup["verification"]["algorithm"] == ("hmac-sha256-canonical-json-v1")
            assert backup["verification"]["key_id"]
            assert backup["artifact_policy"]["binary_files_included"] is False

            preview = await client.get("/api/personal-ip/data/delete-preview")
            assert preview.status_code == 200
            deletion = await client.post(
                "/api/personal-ip/data/delete",
                json={
                    "schema_version": ("personal-ip-destructive-delete-confirmation-v1"),
                    "owner_user_id": owner_user_id,
                    "state_digest": preview.json()["state_digest"],
                    "confirmation_phrase": preview.json()["confirmation_phrase"],
                    "backup_acknowledged": True,
                    "artifact_files_acknowledged": True,
                    "delete_local_context": True,
                },
            )
            assert deletion.status_code == 200
            assert deletion.json()["artifact_files_deleted"] is True
            assert deletion.json()["deleted_artifact_files"] == 1
            assert not artifact_file.exists()

            restored = await client.post(
                "/api/personal-ip/data/restore",
                json={"backup": backup},
            )
            assert restored.status_code == 200
            assert restored.json()["verified"] is True
            assert restored.json()["artifact_contents_requiring_reattach"] == 1

            restored_metadata = await client.get(f"/api/personal-ip/artifacts/{artifact['id']}")
            missing_content = await client.get(f"/api/personal-ip/artifacts/{artifact['id']}/content")
            assert restored_metadata.status_code == 200
            assert restored_metadata.json()["content_available"] is False
            assert missing_content.status_code == 404

            reattached = await client.put(
                f"/api/personal-ip/artifacts/{artifact['id']}/content",
                content=payload,
                headers={"Content-Type": artifact["mime_type"]},
            )
            assert reattached.status_code == 200
            assert reattached.json()["content_available"] is True
            assert reattached.json()["artifact_digest"] == artifact["artifact_digest"]

            downloaded = await client.get(f"/api/personal-ip/artifacts/{artifact['id']}/content")
            restored_range = await client.get(
                f"/api/personal-ip/artifacts/{artifact['id']}/content",
                headers={"Range": "bytes=2-10"},
            )
            assert downloaded.status_code == 200
            assert downloaded.content == payload
            assert hashlib.sha256(downloaded.content).hexdigest() == artifact["content_sha256"]
            assert restored_range.status_code == 206
            assert restored_range.content == payload[2:11]
            assert restored_range.headers["etag"] == (f'"{artifact["content_sha256"]}"')
    finally:
        await close_engine()
