"""Credential-safe backup, verified restore and destructive deletion for Personal-IP.

The service deliberately uses the existing owner-scoped tables as its source of
truth.  It does not create a second mutable state store.  Platform credentials
and one-use OAuth state are deletion-only data: exports contain a revoked
connection shell so a restore always requires a fresh platform authorization.
One-shot paid-call scopes/events are also deletion-only, but unlike connection
shells they are omitted entirely so restore can never revive an approval,
reservation, or consumed admission.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.ip_agent.evidence_contracts import ReferenceVideoEvidence
from deerflow.persistence.base import Base
from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_content.model import (
    PersonalIPBreakdownVersionRow,
    PersonalIPContentWorkRow,
    PersonalIPDirectionVersionRow,
    PersonalIPScriptVersionRow,
)
from deerflow.persistence.personal_ip_metrics.model import PersonalIPMetricObservationRow
from deerflow.persistence.personal_ip_paid_calls.model import (
    PersonalIPPaidCallEventRow,
    PersonalIPPaidCallScopeRow,
)
from deerflow.persistence.personal_ip_platform_connections.model import (
    PersonalIPPlatformConnectionRow,
    PersonalIPPlatformCredentialRow,
    PersonalIPPlatformOAuthStateRow,
)
from deerflow.persistence.personal_ip_platform_observations.model import PersonalIPPlatformObservationRow
from deerflow.persistence.personal_ip_publish_receipts.model import PersonalIPPublishReceiptRow
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.persistence.personal_ip_video_productions.model import (
    PersonalIPVideoProductionEventRow,
    PersonalIPVideoProductionRow,
)
from deerflow.persistence.personal_ip_video_productions.sql import (
    LINKED_VIDEO_PRODUCTION_CONTRACT_VERSION,
    SCRIPT_SOURCE_SNAPSHOT_CONTRACT_VERSION,
    VIDEO_PRODUCTION_CONTRACT_VERSION,
)
from deerflow.personal_ip.content_contracts import (
    BreakdownDraft,
    ContentObjective,
    DirectionDraft,
    ScriptDraft,
)
from deerflow.personal_ip.evidence_binding import reference_evidence_refs
from deerflow.personal_ip.video_contracts import VIDEO_PRODUCTION_MODES

LEGACY_BACKUP_SCHEMA_VERSION = "personal-ip-owner-backup-v1"
CONTENT_BACKUP_SCHEMA_VERSION = "personal-ip-owner-backup-v2"
BACKUP_SCHEMA_VERSION = "personal-ip-owner-backup-v3"
RESTORE_RECEIPT_VERSION = "personal-ip-owner-restore-receipt-v1"
DELETE_PREVIEW_VERSION = "personal-ip-destructive-delete-preview-v1"
DELETE_CONFIRMATION_VERSION = "personal-ip-destructive-delete-confirmation-v1"
DELETE_RECEIPT_VERSION = "personal-ip-destructive-delete-receipt-v1"
DELETE_CONFIRMATION_PHRASE = "永久删除我的全部个人IP数据"

_FORBIDDEN_EXPORT_KEYS = {
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "cookies",
    "password",
    "secret",
    "state_hash",
    "encrypted_access_token",
    "encrypted_refresh_token",
}


@dataclass(frozen=True)
class _Dataset:
    name: str
    model: type[Base]


# Restore order is dependency order; deletion uses the reverse.
_DATASETS: tuple[_Dataset, ...] = (
    _Dataset("subjects", PersonalIPSubjectRow),
    _Dataset("content_works", PersonalIPContentWorkRow),
    _Dataset("breakdown_versions", PersonalIPBreakdownVersionRow),
    _Dataset("direction_versions", PersonalIPDirectionVersionRow),
    _Dataset("script_versions", PersonalIPScriptVersionRow),
    _Dataset("accounts", PersonalIPAccountRow),
    _Dataset("publish_receipts", PersonalIPPublishReceiptRow),
    _Dataset("metric_observations", PersonalIPMetricObservationRow),
    _Dataset("platform_observations", PersonalIPPlatformObservationRow),
    _Dataset("platform_connections", PersonalIPPlatformConnectionRow),
    _Dataset("video_productions", PersonalIPVideoProductionRow),
    _Dataset("video_production_events", PersonalIPVideoProductionEventRow),
)
_LEGACY_DATASETS: tuple[_Dataset, ...] = tuple(
    item
    for item in _DATASETS
    if item.name
    not in {
        "content_works",
        "breakdown_versions",
        "direction_versions",
        "script_versions",
    }
)
_LEGACY_VIDEO_PRODUCTION_COLUMNS = frozenset({"content_work_id", "script_version_id"})
EXPORT_DATASET_NAMES: tuple[str, ...] = tuple(item.name for item in _DATASETS)
PERSONAL_IP_EXPORT_TABLES: frozenset[str] = frozenset(item.model.__tablename__ for item in _DATASETS)
PERSONAL_IP_SECRET_TABLES: frozenset[str] = frozenset(
    {
        PersonalIPPlatformCredentialRow.__tablename__,
        PersonalIPPlatformOAuthStateRow.__tablename__,
    }
)
_DELETION_ONLY_DATASETS: tuple[_Dataset, ...] = (
    _Dataset("paid_call_scopes", PersonalIPPaidCallScopeRow),
    _Dataset("paid_call_events", PersonalIPPaidCallEventRow),
)
PERSONAL_IP_DELETION_ONLY_TABLES: frozenset[str] = frozenset(item.model.__tablename__ for item in _DELETION_ONLY_DATASETS)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _assert_credential_free(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_EXPORT_KEYS:
                raise ValueError(f"credential-bearing field is not exportable: {path}.{key}")
            _assert_credential_free(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_credential_free(item, path=f"{path}[{index}]")


def _primary_key(model: type[Base], record: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(record[column.name]) for column in model.__table__.primary_key.columns)


def _safe_connection_record(record: dict[str, Any]) -> dict[str, Any]:
    """Turn authorization metadata into a credential-free reconnect shell."""

    record.update(
        {
            "status": "revoked",
            "oauth_open_id": None,
            "scopes_json": [],
            "access_expires_at": None,
            "refresh_expires_at": None,
            "last_refreshed_at": None,
            "last_error_code": "restore_reauthorization_required",
            "credential_state": "omitted_reauthorization_required",
        }
    )
    return record


def _dataset_digest(name: str, records: Sequence[Mapping[str, Any]]) -> str:
    return _digest({"name": name, "records": records})


def _record_index(
    dataset_name: str,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for record in records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"backup dataset {dataset_name} contains an invalid id")
        if record_id in indexed:
            raise ValueError(f"backup dataset {dataset_name} contains a duplicate id")
        indexed[record_id] = record
    return indexed


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"backup content lineage has an invalid {field}")
    return value


def _validate_content_restore_datasets(
    datasets: Sequence[Mapping[str, Any]],
) -> None:
    """Validate the complete content graph before any backup row is restored."""

    records_by_name = {str(dataset["name"]): dataset["records"] for dataset in datasets}
    subject_ids = set(_record_index("subjects", records_by_name["subjects"]))
    works = _record_index("content_works", records_by_name["content_works"])
    breakdowns = _record_index(
        "breakdown_versions",
        records_by_name["breakdown_versions"],
    )
    directions = _record_index(
        "direction_versions",
        records_by_name["direction_versions"],
    )
    scripts = _record_index("script_versions", records_by_name["script_versions"])

    objective_ids: set[str] = set()
    for work in works.values():
        subject_id = work.get("subject_id")
        if subject_id is not None and subject_id not in subject_ids:
            raise ValueError("backup content work subject does not belong to this Owner backup")
        objective_id = work.get("objective_id")
        if not isinstance(objective_id, str) or not objective_id:
            raise ValueError("backup content work objective_id is required")
        if objective_id in objective_ids:
            raise ValueError("backup content work objective_id must be unique")
        objective_ids.add(objective_id)
        thread_id = work.get("thread_id")
        if thread_id is not None and (not isinstance(thread_id, str) or not thread_id.strip() or len(thread_id) > 128):
            raise ValueError("backup content work thread_id is invalid")
        if work.get("entry_route") not in {"zero_start", "benchmark"}:
            raise ValueError("backup content work entry_route is invalid")
        if work.get("status") not in {"active", "archived"}:
            raise ValueError("backup content work status is invalid")
        _require_sha256(work.get("operation_digest"), field="operation_digest")
        try:
            objective = ContentObjective.model_validate(work.get("objective_json"))
        except ValueError as exc:
            raise ValueError("backup content work objective is invalid") from exc
        if objective.model_dump(mode="json") != work.get("objective_json"):
            raise ValueError("backup content work objective is not canonical")

    version_numbers: dict[tuple[str, str], set[int]] = {}
    commit_digests: dict[tuple[str, str], str] = {}

    def validate_version_base(
        dataset_name: str,
        record: Mapping[str, Any],
    ) -> str:
        work_id = record.get("content_work_id")
        if not isinstance(work_id, str) or work_id not in works:
            raise ValueError(f"backup {dataset_name} content work does not belong to this Owner backup")
        version_number = record.get("version_number")
        if not isinstance(version_number, int) or isinstance(version_number, bool) or version_number < 1:
            raise ValueError(f"backup {dataset_name} version number is invalid")
        numbers = version_numbers.setdefault((dataset_name, work_id), set())
        if version_number in numbers:
            raise ValueError(f"backup {dataset_name} contains a duplicate version number")
        numbers.add(version_number)
        commit_key = record.get("commit_key")
        if not isinstance(commit_key, str) or not commit_key:
            raise ValueError(f"backup {dataset_name} commit key is invalid")
        commit_digest = _require_sha256(
            record.get("commit_digest"),
            field=f"{dataset_name} commit_digest",
        )
        digest_key = (work_id, commit_key)
        existing_digest = commit_digests.setdefault(digest_key, commit_digest)
        if existing_digest != commit_digest:
            raise ValueError("backup content commit has inconsistent digests")
        return work_id

    breakdown_models: dict[str, BreakdownDraft] = {}
    breakdown_refs: dict[str, set[str]] = {}
    for breakdown_id, record in breakdowns.items():
        work_id = validate_version_base("breakdown_versions", record)
        try:
            breakdown = BreakdownDraft.model_validate(
                {
                    "source_kind": record.get("source_kind"),
                    "source_identity": record.get("source_identity_json"),
                    "source_digest": record.get("source_digest"),
                    "evidence_request_id": record.get("evidence_request_id"),
                    "evidence_item_index": record.get("evidence_item_index"),
                    "evidence_contract_version": record.get("evidence_contract_version"),
                    "evidence_payload_digest": record.get("evidence_payload_digest"),
                    "observations": record.get("observations_json"),
                    "interpretations": record.get("interpretations_json"),
                    "limitations": record.get("limitations_json"),
                }
            )
        except ValueError as exc:
            raise ValueError("backup BreakdownVersion contract is invalid") from exc
        breakdown_models[breakdown_id] = breakdown

        if breakdown.source_kind == "owner_material":
            if record.get("evidence_snapshot_json") is not None:
                raise ValueError("owner material cannot contain an Evidence MCP snapshot")
            breakdown_refs[breakdown_id] = {ref for observation in breakdown.observations for ref in observation.evidence_refs}
            continue

        snapshot = record.get("evidence_snapshot_json")
        if not isinstance(snapshot, Mapping):
            raise ValueError("external BreakdownVersion requires an evidence snapshot")
        try:
            evidence = ReferenceVideoEvidence.model_validate(snapshot)
        except ValueError as exc:
            raise ValueError("backup BreakdownVersion evidence snapshot is invalid") from exc
        canonical_snapshot = evidence.model_dump(mode="json", exclude_none=True)
        if canonical_snapshot != snapshot:
            raise ValueError("backup BreakdownVersion evidence snapshot is not canonical")
        request_id = str(breakdown.evidence_request_id or "")
        item_index = breakdown.evidence_item_index
        if evidence.metadata.request_id != request_id:
            raise ValueError("backup BreakdownVersion evidence request id does not match")
        if evidence.contract_version != breakdown.evidence_contract_version:
            raise ValueError("backup BreakdownVersion evidence contract does not match")
        if _digest(canonical_snapshot) != breakdown.evidence_payload_digest:
            raise ValueError("backup BreakdownVersion evidence digest does not match")
        if item_index is None or item_index >= len(canonical_snapshot["items"]):
            raise ValueError("backup BreakdownVersion evidence item is out of range")
        item = canonical_snapshot["items"][item_index]
        if item.get("status") == "failed":
            raise ValueError("failed evidence cannot be restored as a BreakdownVersion")
        source = item.get("source")
        if not isinstance(source, Mapping):
            raise ValueError("backup BreakdownVersion evidence source is invalid")
        source_digest = _require_sha256(
            source.get("content_sha256"),
            field="evidence source digest",
        )
        if breakdown.source_digest != source_digest:
            raise ValueError("backup BreakdownVersion source digest does not match evidence")
        source_ref = str(source.get("ref") or "").strip()
        expected_source_kind = "uploaded_file" if source_ref.startswith("/mnt/user-data/uploads/") else "platform_content"
        if breakdown.source_kind != expected_source_kind:
            raise ValueError("backup BreakdownVersion source kind does not match evidence")
        expected_identity = {
            "ref": source_ref,
            "observed_at": source.get("observed_at"),
            "trust": source.get("trust"),
            "evidence_request_id": request_id,
            "evidence_item_index": item_index,
            "analysis_receipt_sha256": _digest(item.get("analysis_receipt") or {}),
        }
        if breakdown.source_identity != expected_identity:
            raise ValueError("backup BreakdownVersion source identity does not match evidence")
        allowed_refs = reference_evidence_refs(
            request_id=request_id,
            item_index=item_index,
            item=item,
        )
        if any(ref not in allowed_refs for observation in breakdown.observations for ref in observation.evidence_refs):
            raise ValueError("backup BreakdownVersion contains an unknown evidence ref")
        breakdown_refs[breakdown_id] = allowed_refs

        if works[work_id].get("entry_route") == "zero_start":
            # Zero-start may acquire evidence later; the route does not weaken
            # any binding checks, so this remains valid lineage.
            continue

    direction_models: dict[str, DirectionDraft] = {}
    direction_allowed_refs: dict[str, set[str]] = {}
    for direction_id, record in directions.items():
        work_id = validate_version_base("direction_versions", record)
        try:
            objective_snapshot = ContentObjective.model_validate(record.get("objective_snapshot_json"))
            direction = DirectionDraft.model_validate(record.get("direction_json"))
        except ValueError as exc:
            raise ValueError("backup DirectionVersion contract is invalid") from exc
        if objective_snapshot.model_dump(mode="json") != works[work_id].get("objective_json"):
            raise ValueError("backup DirectionVersion objective snapshot does not match its work")
        breakdown_ids = record.get("breakdown_version_ids_json")
        if not isinstance(breakdown_ids, list) or len(breakdown_ids) != len(set(breakdown_ids)):
            raise ValueError("backup DirectionVersion breakdown references are invalid")
        if direction.breakdown_version_ids != breakdown_ids:
            raise ValueError("backup DirectionVersion breakdown snapshot does not match")
        allowed_refs: set[str] = set()
        for breakdown_id in breakdown_ids:
            breakdown_record = breakdowns.get(breakdown_id)
            if breakdown_record is None or breakdown_record.get("content_work_id") != work_id:
                raise ValueError("backup DirectionVersion breakdown does not belong to the same work")
            allowed_refs.update(breakdown_refs[breakdown_id])
        parent_id = record.get("parent_direction_version_id")
        if direction.parent_direction_version_id != parent_id:
            raise ValueError("backup DirectionVersion parent snapshot does not match")
        if parent_id is not None:
            parent = directions.get(parent_id)
            if parent is None or parent.get("content_work_id") != work_id or parent.get("version_number", 0) >= record.get("version_number", 0):
                raise ValueError("backup DirectionVersion parent is invalid")
        for claim in direction.claim_basis:
            if claim.state == "source_observed" and any(ref not in allowed_refs for ref in claim.evidence_refs):
                raise ValueError("backup DirectionVersion claim evidence is not in its breakdowns")
        direction_models[direction_id] = direction
        direction_allowed_refs[direction_id] = allowed_refs

    for _script_id, record in scripts.items():
        work_id = validate_version_base("script_versions", record)
        direction_id = record.get("direction_version_id")
        direction_record = directions.get(direction_id)
        if direction_record is None or direction_record.get("content_work_id") != work_id:
            raise ValueError("backup ScriptVersion direction does not belong to the same work")
        try:
            script = ScriptDraft.model_validate(
                {
                    "title": record.get("title"),
                    "story_mode": record.get("story_mode"),
                    "script_text": record.get("script_text"),
                    "claim_basis": record.get("claim_basis_json"),
                    "creative_elements": record.get("creative_elements_json"),
                    "story_engine_seed": record.get("story_engine_seed_json"),
                    "locked_story": record.get("locked_story"),
                    "production_notes": record.get("production_notes_json"),
                    "direction_version_id": direction_id,
                    "parent_script_version_id": record.get("parent_script_version_id"),
                }
            )
        except ValueError as exc:
            raise ValueError("backup ScriptVersion contract is invalid") from exc
        direction = direction_models[direction_id]
        if script.story_mode != direction.truth_mode:
            raise ValueError("backup ScriptVersion truth mode does not match its direction")
        direction_claims = {_canonical(claim.model_dump(mode="json")) for claim in direction.claim_basis}
        if any(_canonical(claim.model_dump(mode="json")) not in direction_claims for claim in script.claim_basis):
            raise ValueError("backup ScriptVersion claim basis is absent from its direction")
        for claim in script.claim_basis:
            if claim.state == "source_observed" and any(ref not in direction_allowed_refs[direction_id] for ref in claim.evidence_refs):
                raise ValueError("backup ScriptVersion claim evidence is not in its direction")
        parent_id = record.get("parent_script_version_id")
        if parent_id is not None:
            parent = scripts.get(parent_id)
            if parent is None or parent.get("content_work_id") != work_id or parent.get("version_number", 0) >= record.get("version_number", 0):
                raise ValueError("backup ScriptVersion parent is invalid")
        locked_story = record.get("locked_story")
        locked_digest = record.get("locked_story_digest")
        if not locked_story:
            if locked_digest is not None:
                raise ValueError("backup ScriptVersion has a digest without a locked story")
        elif hashlib.sha256(str(locked_story).encode("utf-8")).hexdigest() != locked_digest:
            raise ValueError("backup ScriptVersion locked story digest does not match")

    for (dataset_name, work_id), numbers in version_numbers.items():
        if sorted(numbers) != list(range(1, len(numbers) + 1)):
            raise ValueError(f"backup {dataset_name} versions for work {work_id} are not contiguous")


def _event_digest_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("backup video production event occurred_at is invalid")
    try:
        occurred_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("backup video production event occurred_at is invalid") from exc
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    return occurred_at.astimezone(UTC).isoformat()


def _validate_production_restore_datasets(
    datasets: Sequence[Mapping[str, Any]],
) -> None:
    """Validate production links and server-derived source snapshots."""

    records_by_name = {str(dataset["name"]): dataset["records"] for dataset in datasets}
    subjects = _record_index("subjects", records_by_name["subjects"])
    accounts = _record_index("accounts", records_by_name["accounts"])
    works = _record_index("content_works", records_by_name["content_works"])
    scripts = _record_index(
        "script_versions",
        records_by_name["script_versions"],
    )
    productions = _record_index(
        "video_productions",
        records_by_name["video_productions"],
    )
    events = _record_index(
        "video_production_events",
        records_by_name["video_production_events"],
    )

    operation_keys: set[str] = set()
    thread_ids: set[str] = set()
    for production_id, record in productions.items():
        operation_key = record.get("operation_key")
        if not isinstance(operation_key, str) or not operation_key:
            raise ValueError("backup video production operation_key is invalid")
        if operation_key in operation_keys:
            raise ValueError("backup video production operation_key must be unique")
        operation_keys.add(operation_key)
        thread_id = record.get("thread_id")
        if thread_id is not None:
            if not isinstance(thread_id, str) or not thread_id or len(thread_id) > 64:
                raise ValueError("backup video production thread_id is invalid")
            if thread_id in thread_ids:
                raise ValueError("backup video production thread_id must be unique")
            thread_ids.add(thread_id)

        subject_id = record.get("subject_id")
        if subject_id is not None and subject_id not in subjects:
            raise ValueError("backup video production subject does not belong to this Owner backup")
        target_account_ids = record.get("target_account_ids_json")
        if not isinstance(target_account_ids, list) or any(not isinstance(account_id, str) or not account_id for account_id in target_account_ids) or len(target_account_ids) != len(set(target_account_ids)):
            raise ValueError("backup video production target accounts are invalid")
        for account_id in target_account_ids:
            account = accounts.get(account_id)
            if account is None:
                raise ValueError("backup video production target account does not belong to this Owner backup")
            if subject_id is not None and account.get("subject_id") not in {
                None,
                subject_id,
            }:
                raise ValueError("backup video production target account belongs to another subject")

        source_kind = record.get("source_kind")
        if source_kind not in {"idea", "script"}:
            raise ValueError("backup video production source_kind is invalid")
        source = record.get("source_json")
        delivery_spec = record.get("delivery_spec_json")
        provider_policy = record.get("provider_policy_json")
        budget = record.get("budget_json")
        if not all(isinstance(value, Mapping) for value in (source, delivery_spec, provider_policy, budget)):
            raise ValueError("backup video production request snapshots are invalid")
        production_mode = source.get("production_mode")
        if production_mode is not None and production_mode not in (VIDEO_PRODUCTION_MODES):
            raise ValueError("backup video production production_mode is invalid")
        if not isinstance(record.get("title"), str) or not record.get("title"):
            raise ValueError("backup video production title is invalid")

        content_work_id = record.get("content_work_id")
        script_version_id = record.get("script_version_id")
        if (content_work_id is None) != (script_version_id is None):
            raise ValueError("backup video production content and script links must be paired")
        linked = content_work_id is not None
        if linked:
            if record.get("contract_version") != (LINKED_VIDEO_PRODUCTION_CONTRACT_VERSION):
                raise ValueError("backup linked video production contract version is invalid")
            if source_kind != "script":
                raise ValueError("backup linked video production must use a script source")
            work = works.get(str(content_work_id))
            script = scripts.get(str(script_version_id))
            if work is None or script is None:
                raise ValueError("backup linked video production does not belong to this Owner backup")
            if script.get("content_work_id") != content_work_id:
                raise ValueError("backup linked video production script does not belong to its work")
            work_subject_id = work.get("subject_id")
            if work_subject_id is not None and subject_id != work_subject_id:
                raise ValueError("backup linked video production subject does not match its work")

            expected_source = {
                "contract_version": SCRIPT_SOURCE_SNAPSHOT_CONTRACT_VERSION,
                "content_work_id": content_work_id,
                "objective_id": work.get("objective_id"),
                "script_version_id": script_version_id,
                "direction_version_id": script.get("direction_version_id"),
                "script_version_number": script.get("version_number"),
                "title": script.get("title"),
                "story_mode": script.get("story_mode"),
                "script_text": script.get("script_text"),
                "claim_basis": script.get("claim_basis_json") or [],
                "creative_elements": script.get("creative_elements_json") or [],
                "story_engine_seed": script.get("story_engine_seed_json"),
                "locked_story": script.get("locked_story"),
                "locked_story_sha256": script.get("locked_story_digest"),
                "production_notes": script.get("production_notes_json") or {},
            }
            source_payload = {key: value for key, value in source.items() if key not in {"production_mode", "snapshot_sha256"}}
            if source_payload != expected_source:
                raise ValueError("backup linked video production source snapshot does not match its ScriptVersion")
            if source.get("snapshot_sha256") != _digest(expected_source):
                raise ValueError("backup linked video production source snapshot digest does not match")
        elif record.get("contract_version") != VIDEO_PRODUCTION_CONTRACT_VERSION:
            raise ValueError("backup unlinked video production contract version is invalid")

        request_payload: dict[str, Any] = {
            "budget": dict(budget),
            "delivery_spec": dict(delivery_spec),
            "provider_policy": dict(provider_policy),
            "source": dict(source),
            "source_kind": source_kind,
            "subject_id": subject_id,
            "target_account_ids": target_account_ids,
            "thread_id": thread_id,
            "title": record.get("title"),
        }
        if linked:
            request_payload.update(
                {
                    "content_work_id": content_work_id,
                    "script_version_id": script_version_id,
                }
            )
        request_digest = _require_sha256(
            record.get("request_digest"),
            field="video production request_digest",
        )
        if request_digest != _digest(request_payload):
            raise ValueError("backup video production request digest does not match its snapshots")

        event_count = record.get("event_count")
        if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 0:
            raise ValueError("backup video production event_count is invalid")

    events_by_production: dict[str, list[Mapping[str, Any]]] = {}
    event_keys: dict[str, set[str]] = {}
    for event in events.values():
        production_id = event.get("production_id")
        if not isinstance(production_id, str) or production_id not in productions:
            raise ValueError("backup video production event does not belong to this Owner backup")
        sequence = event.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ValueError("backup video production event sequence is invalid")
        event_key = event.get("event_key")
        if not isinstance(event_key, str) or not event_key:
            raise ValueError("backup video production event_key is invalid")
        keys = event_keys.setdefault(production_id, set())
        if event_key in keys:
            raise ValueError("backup video production event_key must be unique")
        keys.add(event_key)
        event_payload = {
            "cost": event.get("cost_json"),
            "entity_id": event.get("entity_id"),
            "entity_type": event.get("entity_type"),
            "event_type": event.get("event_type"),
            "input_refs": event.get("input_refs_json"),
            "model": event.get("model"),
            "occurred_at": _event_digest_timestamp(event.get("occurred_at")),
            "output_refs": event.get("output_refs_json"),
            "payload": event.get("payload_json"),
            "provider": event.get("provider"),
            "provider_task_id": event.get("provider_task_id"),
            "stage": event.get("stage"),
            "status": event.get("status"),
        }
        event_digest = _require_sha256(
            event.get("event_digest"),
            field="video production event_digest",
        )
        if event_digest != _digest(event_payload):
            raise ValueError("backup video production event digest does not match its snapshot")
        events_by_production.setdefault(production_id, []).append(event)

    for production_id, production in productions.items():
        production_events = events_by_production.get(production_id, [])
        sequences = sorted(int(event["sequence"]) for event in production_events)
        if sequences != list(range(1, len(sequences) + 1)):
            raise ValueError("backup video production event sequences are not contiguous")
        if production.get("event_count") != len(production_events):
            raise ValueError("backup video production event_count does not match its events")


class PersonalIPDataLifecycleService:
    """Owner-scoped lifecycle service over every Personal-IP persistence table."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        minecontext: Any | None,
    ) -> None:
        self._sf = session_factory
        self._minecontext = minecontext

    @staticmethod
    async def _lock_owner(session: AsyncSession, owner_user_id: str) -> None:
        bind = session.get_bind()
        dialect = bind.dialect.name
        if dialect == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        else:
            await session.begin()
            if dialect == "postgresql":
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": f"personal-ip-data-lifecycle:{owner_user_id}"},
                )

    @staticmethod
    async def _export_datasets(
        session: AsyncSession,
        owner_user_id: str,
    ) -> list[dict[str, Any]]:
        exported: list[dict[str, Any]] = []
        for dataset in _DATASETS:
            rows = (await session.execute(select(dataset.model).where(dataset.model.owner_user_id == owner_user_id))).scalars().all()
            records = [_json_value(row.to_dict()) for row in rows]
            if dataset.name == "platform_connections":
                records = [_safe_connection_record(record) for record in records]
            records.sort(key=lambda record, model=dataset.model: _primary_key(model, record))
            _assert_credential_free(records, path=f"$.datasets.{dataset.name}")
            exported.append(
                {
                    "name": dataset.name,
                    "count": len(records),
                    "digest": _dataset_digest(dataset.name, records),
                    "records": records,
                }
            )
        return exported

    @staticmethod
    async def _secret_counts(
        session: AsyncSession,
        owner_user_id: str,
    ) -> dict[str, int]:
        connection_ids = select(PersonalIPPlatformConnectionRow.id).where(PersonalIPPlatformConnectionRow.owner_user_id == owner_user_id)
        credentials = (await session.execute(select(func.count()).select_from(PersonalIPPlatformCredentialRow).where(PersonalIPPlatformCredentialRow.connection_id.in_(connection_ids)))).scalar_one()
        oauth_states = (await session.execute(select(func.count()).select_from(PersonalIPPlatformOAuthStateRow).where(PersonalIPPlatformOAuthStateRow.owner_user_id == owner_user_id))).scalar_one()
        return {
            "platform_credentials": int(credentials),
            "platform_oauth_states": int(oauth_states),
        }

    @staticmethod
    async def _deletion_only_counts(
        session: AsyncSession,
        owner_user_id: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for dataset in _DELETION_ONLY_DATASETS:
            count = (await session.execute(select(func.count()).select_from(dataset.model).where(dataset.model.owner_user_id == owner_user_id))).scalar_one()
            counts[dataset.name] = int(count)
        return counts

    @staticmethod
    def _data_digest(datasets: Sequence[Mapping[str, Any]]) -> str:
        return _digest([{"name": dataset["name"], "records": dataset["records"]} for dataset in datasets])

    @staticmethod
    def _manifest_digest(
        *,
        owner_user_id: str,
        exported_at: str,
        datasets: Sequence[Mapping[str, Any]],
        data_digest: str,
        schema_version: str = BACKUP_SCHEMA_VERSION,
    ) -> str:
        return _digest(
            {
                "schema_version": schema_version,
                "owner_user_id": owner_user_id,
                "exported_at": exported_at,
                "dataset_digests": [{"name": item["name"], "count": item["count"], "digest": item["digest"]} for item in datasets],
                "data_digest": data_digest,
            }
        )

    async def export_backup(
        self,
        owner_user_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not owner_user_id:
            raise ValueError("owner_user_id is required")
        exported_at = _iso(now or datetime.now(UTC))
        async with self._sf() as session:
            datasets = await self._export_datasets(session, owner_user_id)
        data_digest = self._data_digest(datasets)
        manifest_digest = self._manifest_digest(
            owner_user_id=owner_user_id,
            exported_at=exported_at,
            datasets=datasets,
            data_digest=data_digest,
        )
        backup = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "owner_user_id": owner_user_id,
            "exported_at": exported_at,
            "credential_policy": {
                "credentials_included": False,
                "oauth_states_included": False,
                "paid_call_admissions_included": False,
                "platform_reauthorization_required_after_restore": True,
                "paid_call_reapproval_required_after_restore": True,
            },
            "datasets": datasets,
            "verification": {
                "algorithm": "sha256-canonical-json-v1",
                "data_digest": data_digest,
                "manifest_digest": manifest_digest,
            },
        }
        _assert_credential_free(backup)
        return backup

    @staticmethod
    def _verify_backup(owner_user_id: str, backup: Mapping[str, Any]) -> list[dict[str, Any]]:
        schema_version = backup.get("schema_version")
        if schema_version not in {
            BACKUP_SCHEMA_VERSION,
            CONTENT_BACKUP_SCHEMA_VERSION,
            LEGACY_BACKUP_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported Personal-IP backup schema version")
        if backup.get("owner_user_id") != owner_user_id:
            raise ValueError("backup owner does not match the authenticated owner")
        datasets = backup.get("datasets")
        if not isinstance(datasets, list):
            raise ValueError("backup datasets are required")
        specifications = _LEGACY_DATASETS if schema_version == LEGACY_BACKUP_SCHEMA_VERSION else _DATASETS
        expected_names = [item.name for item in specifications]
        if [item.get("name") for item in datasets if isinstance(item, Mapping)] != expected_names:
            raise ValueError("backup dataset inventory is incomplete or out of order")
        normalized: list[dict[str, Any]] = []
        for specification, raw_dataset in zip(specifications, datasets, strict=True):
            if not isinstance(raw_dataset, Mapping):
                raise ValueError("backup dataset must be an object")
            records = raw_dataset.get("records")
            if not isinstance(records, list):
                raise ValueError(f"backup dataset {specification.name} records are required")
            if raw_dataset.get("count") != len(records):
                raise ValueError(f"backup dataset {specification.name} count mismatch")
            if raw_dataset.get("digest") != _dataset_digest(specification.name, records):
                raise ValueError(f"backup dataset {specification.name} digest mismatch")
            expected_columns = {column.name for column in specification.model.__table__.columns}
            allowed_columns = set(expected_columns)
            if (
                schema_version
                in {
                    LEGACY_BACKUP_SCHEMA_VERSION,
                    CONTENT_BACKUP_SCHEMA_VERSION,
                }
                and specification.name == "video_productions"
            ):
                allowed_columns.difference_update(_LEGACY_VIDEO_PRODUCTION_COLUMNS)
            if specification.name == "platform_connections":
                allowed_columns.add("credential_state")
            normalized_records: list[dict[str, Any]] = []
            for record in records:
                if not isinstance(record, Mapping) or set(record) != allowed_columns:
                    raise ValueError(f"backup dataset {specification.name} record shape mismatch")
                if record.get("owner_user_id") != owner_user_id:
                    raise ValueError("backup contains a record for a different owner")
                if specification.name == "platform_connections" and (record.get("status") != "revoked" or record.get("credential_state") != "omitted_reauthorization_required"):
                    raise ValueError("restored platform connections must require reauthorization")
                normalized_records.append(dict(record))
            normalized.append(
                {
                    **dict(raw_dataset),
                    "records": normalized_records,
                }
            )
        _assert_credential_free(normalized)
        verification = backup.get("verification")
        if not isinstance(verification, Mapping):
            raise ValueError("backup verification receipt is required")
        data_digest = PersonalIPDataLifecycleService._data_digest(normalized)
        if verification.get("data_digest") != data_digest:
            raise ValueError("backup data digest mismatch")
        exported_at = backup.get("exported_at")
        if not isinstance(exported_at, str):
            raise ValueError("backup exported_at is required")
        manifest_digest = PersonalIPDataLifecycleService._manifest_digest(
            owner_user_id=owner_user_id,
            exported_at=exported_at,
            datasets=normalized,
            data_digest=data_digest,
            schema_version=str(schema_version),
        )
        if verification.get("manifest_digest") != manifest_digest:
            raise ValueError("backup manifest digest mismatch")
        if schema_version == BACKUP_SCHEMA_VERSION:
            promoted = normalized
        else:
            # V1 predates content lineage; both V1 and V2 predate the
            # ScriptVersion-to-production columns.  Verify their original
            # inventory, shapes and hashes above, then upgrade only the
            # in-memory restore representation.
            legacy_by_name = {item["name"]: item for item in normalized}
            promoted = []
            for specification in _DATASETS:
                existing = legacy_by_name.get(specification.name)
                records = [dict(record) for record in existing["records"]] if existing is not None else []
                if specification.name == "video_productions":
                    for record in records:
                        record["content_work_id"] = None
                        record["script_version_id"] = None
                promoted.append(
                    {
                        "name": specification.name,
                        "count": len(records),
                        "digest": _dataset_digest(specification.name, records),
                        "records": records,
                    }
                )
        _validate_content_restore_datasets(promoted)
        _validate_production_restore_datasets(promoted)
        return promoted

    @staticmethod
    def _restore_values(dataset: _Dataset, record: Mapping[str, Any]) -> dict[str, Any]:
        values = dict(record)
        values.pop("credential_state", None)
        for column in dataset.model.__table__.columns:
            value = values.get(column.name)
            if value is not None and isinstance(column.type, DateTime):
                if not isinstance(value, str):
                    raise ValueError(f"backup datetime {dataset.name}.{column.name} must be an ISO string")
                values[column.name] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return values

    async def restore_backup(
        self,
        owner_user_id: str,
        backup: Mapping[str, Any],
    ) -> dict[str, Any]:
        datasets = self._verify_backup(owner_user_id, backup)
        async with self._sf() as session:
            try:
                await self._lock_owner(session, owner_user_id)
                existing = await self._export_datasets(session, owner_user_id)
                secret_counts = await self._secret_counts(session, owner_user_id)
                deletion_only_counts = await self._deletion_only_counts(session, owner_user_id)
                if any(item["count"] for item in existing) or any(secret_counts.values()) or any(deletion_only_counts.values()):
                    raise ValueError("Personal-IP restore requires an empty owner scope; delete existing data first")
                for specification, dataset in zip(_DATASETS, datasets, strict=True):
                    for record in dataset["records"]:
                        session.add(specification.model(**self._restore_values(specification, record)))
                    # These mappings intentionally do not declare ORM
                    # relationships. Flush each dependency tier explicitly so
                    # SQLAlchemy cannot reorder a child before its parent.
                    await session.flush()
                restored = await self._export_datasets(session, owner_user_id)
                restored_digest = self._data_digest(restored)
                expected_digest = self._data_digest(datasets)
                if restored_digest != expected_digest:
                    raise ValueError("restored data digest does not match the backup")
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return {
            "schema_version": RESTORE_RECEIPT_VERSION,
            "owner_user_id": owner_user_id,
            "verified": True,
            "restored_data_digest": restored_digest,
            "restored_records": sum(item["count"] for item in datasets),
            "credentials_restored": False,
            "paid_call_admissions_restored": False,
            "platform_reauthorization_required": True,
            "paid_call_reapproval_required": True,
            "restored_at": _iso(datetime.now(UTC)),
        }

    async def preview_delete(
        self,
        owner_user_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        async with self._sf() as session:
            datasets = await self._export_datasets(session, owner_user_id)
            secret_counts = await self._secret_counts(session, owner_user_id)
            deletion_only_counts = await self._deletion_only_counts(session, owner_user_id)
        counts = {item["name"]: int(item["count"]) for item in datasets}
        counts.update(secret_counts)
        counts.update(deletion_only_counts)
        data_digest = self._data_digest(datasets)
        state_digest = _digest(
            {
                "owner_user_id": owner_user_id,
                "data_digest": data_digest,
                "record_counts": counts,
            }
        )
        return {
            "schema_version": DELETE_PREVIEW_VERSION,
            "owner_user_id": owner_user_id,
            "prepared_at": _iso(now or datetime.now(UTC)),
            "record_counts": counts,
            "total_records": sum(counts.values()),
            "state_digest": state_digest,
            "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
            "requires_backup_acknowledgement": True,
            "includes_local_context": True,
            "irreversible": True,
        }

    @staticmethod
    def _validate_delete_confirmation(
        owner_user_id: str,
        confirmation: Mapping[str, Any],
    ) -> None:
        if confirmation.get("schema_version") != DELETE_CONFIRMATION_VERSION:
            raise ValueError("invalid destructive-delete confirmation schema")
        if confirmation.get("owner_user_id") != owner_user_id:
            raise ValueError("destructive-delete confirmation owner mismatch")
        if confirmation.get("confirmation_phrase") != DELETE_CONFIRMATION_PHRASE:
            raise ValueError("exact destructive-delete confirmation phrase is required")
        if confirmation.get("backup_acknowledged") is not True:
            raise ValueError("backup acknowledgement is required")
        if confirmation.get("delete_local_context") is not True:
            raise ValueError("whole Personal-IP deletion must include local context")

    async def delete_all(
        self,
        owner_user_id: str,
        confirmation: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self._validate_delete_confirmation(owner_user_id, confirmation)
        async with self._sf() as session:
            try:
                await self._lock_owner(session, owner_user_id)
                datasets = await self._export_datasets(session, owner_user_id)
                secret_counts = await self._secret_counts(session, owner_user_id)
                deletion_only_counts = await self._deletion_only_counts(session, owner_user_id)
                counts = {item["name"]: int(item["count"]) for item in datasets}
                counts.update(secret_counts)
                counts.update(deletion_only_counts)
                current_state_digest = _digest(
                    {
                        "owner_user_id": owner_user_id,
                        "data_digest": self._data_digest(datasets),
                        "record_counts": counts,
                    }
                )
                if confirmation.get("state_digest") != current_state_digest:
                    raise ValueError("Personal-IP state changed after the delete preview; prepare a fresh confirmation")
                if self._minecontext is None:
                    raise RuntimeError("MineContext lifecycle service is unavailable")
                local_receipt = await asyncio.to_thread(
                    self._minecontext.clear,
                    owner_user_id,
                    scope="all",
                )
                if not local_receipt.get("local_data_deleted"):
                    raise RuntimeError("MineContext local data deletion was not verified")

                connection_ids = select(PersonalIPPlatformConnectionRow.id).where(PersonalIPPlatformConnectionRow.owner_user_id == owner_user_id)
                await session.execute(delete(PersonalIPPlatformCredentialRow).where(PersonalIPPlatformCredentialRow.connection_id.in_(connection_ids)))
                await session.execute(delete(PersonalIPPlatformOAuthStateRow).where(PersonalIPPlatformOAuthStateRow.owner_user_id == owner_user_id))
                for dataset in reversed(_DELETION_ONLY_DATASETS):
                    await session.execute(delete(dataset.model).where(dataset.model.owner_user_id == owner_user_id))
                for dataset in reversed(_DATASETS):
                    await session.execute(delete(dataset.model).where(dataset.model.owner_user_id == owner_user_id))
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return {
            "schema_version": DELETE_RECEIPT_VERSION,
            "owner_user_id": owner_user_id,
            "deleted_records": sum(counts.values()),
            "record_counts": counts,
            "state_digest": current_state_digest,
            "local_context_deleted": True,
            "credentials_deleted": True,
            "oauth_states_deleted": True,
            "paid_call_admissions_deleted": True,
            "deleted_at": _iso(now or datetime.now(UTC)),
        }


__all__ = [
    "BACKUP_SCHEMA_VERSION",
    "DELETE_CONFIRMATION_PHRASE",
    "EXPORT_DATASET_NAMES",
    "PERSONAL_IP_DELETION_ONLY_TABLES",
    "PERSONAL_IP_EXPORT_TABLES",
    "PERSONAL_IP_SECRET_TABLES",
    "PersonalIPDataLifecycleService",
]
