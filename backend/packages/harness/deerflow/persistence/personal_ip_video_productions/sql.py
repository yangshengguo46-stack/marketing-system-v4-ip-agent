"""Append-only repository for Personal-IP video production receipts."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_content.model import (
    PersonalIPContentWorkRow,
    PersonalIPScriptVersionRow,
)
from deerflow.persistence.personal_ip_platform_observations.sql import validate_credential_free_payload
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.persistence.personal_ip_video_productions.model import (
    PersonalIPVideoProductionEventRow,
    PersonalIPVideoProductionRow,
)
from deerflow.personal_ip.video_budget import (
    VIDEO_BUDGET_REJECTION_CONTRACT_VERSION,
    VIDEO_BUDGET_RELEASE_CONTRACT_VERSION,
    VIDEO_BUDGET_RESERVATION_CONTRACT_VERSION,
    VIDEO_BUDGET_SETTLEMENT_CONTRACT_VERSION,
    amount_to_micros,
    budget_limit,
    fold_video_budget,
    micros_to_amount,
    provider_requires_paid_admission,
    public_budget_state,
)
from deerflow.personal_ip.video_contracts import normalize_production_mode, validate_compiled_video_contract
from deerflow.utils.time import coerce_iso

VIDEO_PRODUCTION_CONTRACT_VERSION = "personal-ip-video-production-v1"
LINKED_VIDEO_PRODUCTION_CONTRACT_VERSION = "personal-ip-video-production-v2"
SCRIPT_SOURCE_SNAPSHOT_CONTRACT_VERSION = "personal-ip-script-source-snapshot-v1"

VIDEO_EVENT_STAGES: dict[str, str] = {
    "video_plan_compiled": "blueprint",
    "blueprint_sealed": "blueprint",
    "asset_registered": "assets",
    "asset_manifest_compiled": "assets",
    "material_inspection_compiled": "assets",
    "material_selection_compiled": "assets",
    "asset_generation_requested": "assets",
    "asset_generation_completed": "assets",
    "asset_generation_failed": "assets",
    "storyboard_sealed": "storyboard",
    "storyboard_compiled": "storyboard",
    "continuity_compiled": "consistency",
    "generated_shot_qa_compiled": "consistency",
    "shot_generation_requested": "generation",
    "shot_generation_completed": "generation",
    "shot_generation_failed": "generation",
    "consistency_checked": "consistency",
    "candidate_selected": "selection",
    "review_requested": "selection",
    "review_recorded": "selection",
    "voice_generated": "finishing",
    "narration_contract_compiled": "finishing",
    "narration_timing_compiled": "finishing",
    "voice_generation_requested": "finishing",
    "media_processing_requested": "finishing",
    "media_processing_completed": "finishing",
    "media_processing_failed": "finishing",
    "edit_completed": "finishing",
    "assembly_admitted": "finishing",
    "timeline_revision_compiled": "finishing",
    "final_edit_locked": "finishing",
    "delivery_qa_completed": "delivery",
    "delivery_completed": "delivery",
}
VIDEO_EVENT_STATUSES = {
    "planned",
    "running",
    "succeeded",
    "failed",
    "awaiting_review",
    "approved",
    "rejected",
}
VIDEO_EVENT_ALLOWED_STATUSES: dict[str, set[str]] = {
    "video_plan_compiled": {"succeeded"},
    "blueprint_sealed": {"succeeded"},
    "asset_registered": {"succeeded"},
    "asset_manifest_compiled": {"succeeded"},
    "material_inspection_compiled": {"succeeded"},
    "material_selection_compiled": {"succeeded"},
    "asset_generation_requested": {"running"},
    "asset_generation_completed": {"succeeded"},
    "asset_generation_failed": {"failed"},
    "storyboard_sealed": {"succeeded"},
    "storyboard_compiled": {"succeeded"},
    "continuity_compiled": {"succeeded"},
    "generated_shot_qa_compiled": {"succeeded", "failed"},
    "shot_generation_requested": {"planned", "running"},
    "shot_generation_completed": {"succeeded"},
    "shot_generation_failed": {"failed"},
    "consistency_checked": {"succeeded", "failed"},
    "candidate_selected": {"succeeded"},
    "review_requested": {"awaiting_review"},
    "review_recorded": {"approved", "rejected"},
    "voice_generated": {"succeeded", "failed"},
    "narration_contract_compiled": {"succeeded"},
    "narration_timing_compiled": {"succeeded"},
    "voice_generation_requested": {"running"},
    "media_processing_requested": {"running"},
    "media_processing_completed": {"succeeded"},
    "media_processing_failed": {"failed"},
    "edit_completed": {"succeeded", "failed"},
    "assembly_admitted": {"succeeded"},
    "timeline_revision_compiled": {"succeeded"},
    "final_edit_locked": {"succeeded"},
    "delivery_qa_completed": {"succeeded", "failed"},
    "delivery_completed": {"succeeded"},
}
VIDEO_ENTITY_TYPES = {
    "production",
    "character",
    "scene",
    "prop",
    "shot",
    "candidate",
    "audio",
    "timeline",
    "delivery",
    "asset",
}

COMPILED_VIDEO_EVENT_CONTRACTS: dict[str, tuple[str, str]] = {
    "video_plan_compiled": ("personal-ip-video-plan-v1", "production"),
    "asset_manifest_compiled": ("personal-ip-video-asset-manifest-v1", "production"),
    "material_inspection_compiled": ("personal-ip-video-material-inspection-v1", "asset"),
    "material_selection_compiled": ("personal-ip-video-material-selection-v1", "production"),
    "storyboard_compiled": ("personal-ip-video-storyboard-v1", "production"),
    "continuity_compiled": ("personal-ip-video-continuity-v1", "production"),
    "generated_shot_qa_compiled": ("personal-ip-generated-shot-qa-v1", "candidate"),
    "narration_contract_compiled": ("personal-ip-video-narration-v1", "production"),
    "narration_timing_compiled": ("personal-ip-video-narration-timing-v1", "production"),
    "assembly_admitted": ("personal-ip-approved-assembly-v1", "timeline"),
    "timeline_revision_compiled": ("personal-ip-video-timeline-revision-v1", "timeline"),
    "final_edit_locked": ("personal-ip-video-final-edit-lock-v1", "timeline"),
}


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _clean_optional(value: Any, *, field: str, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    if len(text) > limit:
        raise ValueError(f"{field} must contain at most {limit} characters")
    return text


def _json_snapshot(value: Any, *, field: str, expected: type, byte_limit: int = 2_000_000) -> Any:
    if not isinstance(value, expected):
        kind = "object" if expected is dict else "array"
        raise ValueError(f"{field} must be an {kind}")
    validate_credential_free_payload(value, field=field)
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(serialized.encode("utf-8")) > byte_limit:
        raise ValueError(f"{field} exceeds the snapshot limit")
    return json.loads(serialized)


def _normalized_ids(values: Sequence[str], *, field: str, limit: int, item_limit: int = 128) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean_required(raw, field=field, limit=item_limit)
        if value not in seen:
            seen.add(value)
            result.append(value)
    if len(result) > limit:
        raise ValueError(f"{field} may contain at most {limit} items")
    return result


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _digest(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PersonalIPVideoProductionRepository:
    """Persist an immutable request and append-only stage/provider receipts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _production_dict(row: PersonalIPVideoProductionRow) -> dict[str, Any]:
        data = row.to_dict()
        data["target_account_ids"] = data.pop("target_account_ids_json") or []
        data["source"] = data.pop("source_json") or {}
        data["production_mode"] = data["source"].get("production_mode")
        data["delivery_spec"] = data.pop("delivery_spec_json") or {}
        data["provider_policy"] = data.pop("provider_policy_json") or {}
        data["budget"] = data.pop("budget_json") or {}
        for field in ("created_at", "updated_at"):
            if isinstance(data.get(field), datetime):
                data[field] = coerce_iso(data[field])
        return data

    @staticmethod
    def _event_dict(row: PersonalIPVideoProductionEventRow) -> dict[str, Any]:
        data = row.to_dict()
        data["payload"] = data.pop("payload_json") or {}
        data["input_refs"] = data.pop("input_refs_json") or []
        data["output_refs"] = data.pop("output_refs_json") or []
        data["cost"] = data.pop("cost_json") or {}
        for field in ("occurred_at", "created_at"):
            if isinstance(data.get(field), datetime):
                data[field] = coerce_iso(data[field])
        return data

    @classmethod
    def _attach_budget_state(
        cls,
        production: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        try:
            state = fold_video_budget(production.get("budget") or {}, events)
        except ValueError:
            return
        production["budget_state"] = public_budget_state(state)

    @staticmethod
    async def _validate_targets(
        session: AsyncSession,
        *,
        owner_user_id: str,
        subject_id: str | None,
        target_account_ids: list[str],
    ) -> None:
        if subject_id is not None:
            subject = await session.get(PersonalIPSubjectRow, subject_id)
            if subject is None or subject.owner_user_id != owner_user_id or subject.status != "active":
                raise ValueError("Personal-IP video production subject not found")
        if target_account_ids:
            statement = select(PersonalIPAccountRow).where(
                PersonalIPAccountRow.id.in_(target_account_ids),
                PersonalIPAccountRow.owner_user_id == owner_user_id,
                PersonalIPAccountRow.status == "active",
            )
            accounts = list((await session.execute(statement)).scalars())
            if {account.id for account in accounts} != set(target_account_ids):
                raise ValueError("Personal-IP video production target account not found")
            if subject_id is not None and any(account.subject_id not in {None, subject_id} for account in accounts):
                raise ValueError("Personal-IP video production target account belongs to another subject")

    @staticmethod
    async def _linked_script_source(
        session: AsyncSession,
        *,
        owner_user_id: str,
        content_work_id: str,
        script_version_id: str,
    ) -> tuple[PersonalIPContentWorkRow, dict[str, Any]]:
        if session.get_bind().dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        work_statement = select(PersonalIPContentWorkRow).where(
            PersonalIPContentWorkRow.id == content_work_id,
            PersonalIPContentWorkRow.owner_user_id == owner_user_id,
        )
        if session.get_bind().dialect.name != "sqlite":
            work_statement = work_statement.with_for_update()
        work = (await session.execute(work_statement)).scalar_one_or_none()
        script = await session.get(PersonalIPScriptVersionRow, script_version_id)
        if work is None or script is None or work.owner_user_id != owner_user_id or script.owner_user_id != owner_user_id or script.content_work_id != work.id:
            raise ValueError("Personal-IP linked content script not found")
        payload = {
            "contract_version": SCRIPT_SOURCE_SNAPSHOT_CONTRACT_VERSION,
            "content_work_id": work.id,
            "objective_id": work.objective_id,
            "script_version_id": script.id,
            "direction_version_id": script.direction_version_id,
            "script_version_number": script.version_number,
            "title": script.title,
            "story_mode": script.story_mode,
            "script_text": script.script_text,
            "claim_basis": script.claim_basis_json or [],
            "creative_elements": script.creative_elements_json or [],
            "story_engine_seed": script.story_engine_seed_json,
            "locked_story": script.locked_story,
            "locked_story_sha256": script.locked_story_digest,
            "production_notes": script.production_notes_json or {},
        }
        snapshot = {**payload, "snapshot_sha256": _digest(payload)}
        return work, _json_snapshot(snapshot, field="linked_script_source", expected=dict)

    async def begin(
        self,
        *,
        owner_user_id: str,
        operation_key: str,
        title: str,
        subject_id: str | None,
        target_account_ids: Sequence[str],
        source_kind: str,
        source: dict[str, Any],
        delivery_spec: dict[str, Any],
        provider_policy: dict[str, Any],
        budget: dict[str, Any],
        production_mode: str | None = None,
        thread_id: str | None = None,
        content_work_id: str | None = None,
        script_version_id: str | None = None,
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread_key = _clean_optional(thread_id, field="thread_id", limit=64)
        operation = _clean_required(operation_key, field="operation_key", limit=256)
        title_key = _clean_required(title, field="title", limit=256)
        subject_key = _clean_optional(subject_id, field="subject_id", limit=64)
        content_work_key = _clean_optional(
            content_work_id,
            field="content_work_id",
            limit=64,
        )
        script_version_key = _clean_optional(
            script_version_id,
            field="script_version_id",
            limit=64,
        )
        if (content_work_key is None) != (script_version_key is None):
            raise ValueError("content_work_id and script_version_id must be provided together")
        linked_script = content_work_key is not None
        source_kind_key = str(source_kind or "").strip()
        if source_kind_key not in {"idea", "script"}:
            raise ValueError("source_kind must be idea or script")
        if linked_script and source_kind_key != "script":
            raise ValueError("linked ScriptVersion production requires source_kind=script")
        target_ids = _normalized_ids(target_account_ids, field="target_account_ids", limit=200)
        source_snapshot = _json_snapshot(source, field="source", expected=dict)
        if linked_script and source_snapshot:
            raise ValueError("linked ScriptVersion production source is server-derived and must be empty")
        if "production_mode" in source_snapshot:
            raise ValueError("source.production_mode is reserved; use the production_mode argument")
        normalized_mode = normalize_production_mode(production_mode) if production_mode is not None else None
        delivery_snapshot = _json_snapshot(delivery_spec, field="delivery_spec", expected=dict)
        provider_snapshot = _json_snapshot(provider_policy, field="provider_policy", expected=dict)
        budget_snapshot = _json_snapshot(budget, field="budget", expected=dict)
        caller_attempted_to_disable_approval = "paid_calls_require_explicit_approval" in budget_snapshot and budget_snapshot["paid_calls_require_explicit_approval"] is not True
        if budget_snapshot and not caller_attempted_to_disable_approval:
            budget_snapshot["paid_calls_require_explicit_approval"] = True
        async with self._sf() as session:
            linked_work: PersonalIPContentWorkRow | None = None
            if linked_script:
                assert content_work_key is not None and script_version_key is not None
                linked_work, source_snapshot = await self._linked_script_source(
                    session,
                    owner_user_id=owner,
                    content_work_id=content_work_key,
                    script_version_id=script_version_key,
                )
                if linked_work.subject_id is not None:
                    if subject_key is not None and subject_key != linked_work.subject_id:
                        raise ValueError("Personal-IP linked content subject does not match the production subject")
                    subject_key = linked_work.subject_id
            if normalized_mode is not None:
                source_snapshot["production_mode"] = normalized_mode
            request_payload = {
                "budget": budget_snapshot,
                "delivery_spec": delivery_snapshot,
                "provider_policy": provider_snapshot,
                "source": source_snapshot,
                "source_kind": source_kind_key,
                "subject_id": subject_key,
                "target_account_ids": target_ids,
                "thread_id": thread_key,
                "title": title_key,
            }
            if linked_script:
                request_payload.update(
                    {
                        "content_work_id": content_work_key,
                        "script_version_id": script_version_key,
                    }
                )
            request_digest = _digest(request_payload)
            statement = select(PersonalIPVideoProductionRow).where(
                PersonalIPVideoProductionRow.owner_user_id == owner,
                PersonalIPVideoProductionRow.operation_key == operation,
            )
            existing = (await session.execute(statement)).scalar_one_or_none()
            if existing is not None:
                if existing.request_digest != request_digest:
                    if caller_attempted_to_disable_approval:
                        raise ValueError("video paid-call approval is server-controlled and cannot be disabled")
                    raise ValueError("operation_key already records a different video production")
                result = self._production_dict(existing)
                result["events"] = await self._events(session, existing.id)
                self._attach_budget_state(result, result["events"])
                return result
            if linked_work is not None and linked_work.status != "active":
                raise ValueError("Personal-IP linked content work is archived")
            if caller_attempted_to_disable_approval:
                raise ValueError("video paid-call approval is server-controlled and cannot be disabled")
            await self._validate_targets(
                session,
                owner_user_id=owner,
                subject_id=subject_key,
                target_account_ids=target_ids,
            )
            now = datetime.now(UTC)
            row = PersonalIPVideoProductionRow(
                id=f"video-production-{uuid.uuid4().hex}",
                owner_user_id=owner,
                thread_id=thread_key,
                operation_key=operation,
                contract_version=(LINKED_VIDEO_PRODUCTION_CONTRACT_VERSION if linked_script else VIDEO_PRODUCTION_CONTRACT_VERSION),
                title=title_key,
                content_work_id=content_work_key,
                script_version_id=script_version_key,
                subject_id=subject_key,
                target_account_ids_json=target_ids,
                source_kind=source_kind_key,
                source_json=source_snapshot,
                delivery_spec_json=delivery_snapshot,
                provider_policy_json=provider_snapshot,
                budget_json=budget_snapshot,
                request_digest=request_digest,
                status="draft",
                current_stage="intake",
                event_count=0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            result = self._production_dict(row)
            result["events"] = []
            self._attach_budget_state(result, [])
            return result

    async def _events(self, session: AsyncSession, production_id: str) -> list[dict[str, Any]]:
        statement = select(PersonalIPVideoProductionEventRow).where(PersonalIPVideoProductionEventRow.production_id == production_id).order_by(PersonalIPVideoProductionEventRow.sequence.asc())
        rows = (await session.execute(statement)).scalars()
        return [self._event_dict(row) for row in rows]

    async def get(self, production_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPVideoProductionRow, production_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            result = self._production_dict(row)
            result["events"] = await self._events(session, row.id)
            self._attach_budget_state(result, result["events"])
            return result

    async def list(
        self,
        owner_user_id: str,
        *,
        status: str | None = None,
        thread_id: str | None = None,
        content_work_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPVideoProductionRow).where(PersonalIPVideoProductionRow.owner_user_id == owner_user_id)
        if status is not None:
            statement = statement.where(PersonalIPVideoProductionRow.status == status)
        if thread_id is not None:
            statement = statement.where(PersonalIPVideoProductionRow.thread_id == _clean_required(thread_id, field="thread_id", limit=64))
        if content_work_id is not None:
            statement = statement.where(
                PersonalIPVideoProductionRow.content_work_id
                == _clean_required(
                    content_work_id,
                    field="content_work_id",
                    limit=64,
                )
            )
        statement = statement.order_by(
            PersonalIPVideoProductionRow.updated_at.desc(),
            PersonalIPVideoProductionRow.id.desc(),
        ).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._production_dict(row) for row in rows]

    async def bind_thread(
        self,
        production_id: str,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> dict[str, Any] | None:
        """Bind a legacy production to its one customer-visible task thread."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        thread_key = _clean_required(thread_id, field="thread_id", limit=64)
        async with self._sf() as session:
            row = await session.get(PersonalIPVideoProductionRow, production_id)
            if row is None or row.owner_user_id != owner:
                return None
            if row.thread_id not in {None, thread_key}:
                raise ValueError("Video production is already bound to another task")
            conflict = (
                await session.execute(
                    select(PersonalIPVideoProductionRow).where(
                        PersonalIPVideoProductionRow.owner_user_id == owner,
                        PersonalIPVideoProductionRow.thread_id == thread_key,
                        PersonalIPVideoProductionRow.id != row.id,
                    )
                )
            ).scalar_one_or_none()
            if conflict is not None:
                raise ValueError("Task already owns another video production")
            if row.thread_id is None:
                row.thread_id = thread_key
                row.updated_at = datetime.now(UTC)
                await session.commit()
                await session.refresh(row)
            result = self._production_dict(row)
            result["events"] = await self._events(session, row.id)
            self._attach_budget_state(result, result["events"])
            return result

    @staticmethod
    async def _lock_budget_production(
        session: AsyncSession,
        *,
        production_id: str,
        owner_user_id: str,
    ) -> PersonalIPVideoProductionRow | None:
        """Serialize admission on SQLite and row-lock it on other databases."""

        if session.get_bind().dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        statement = select(PersonalIPVideoProductionRow).where(
            PersonalIPVideoProductionRow.id == production_id,
            PersonalIPVideoProductionRow.owner_user_id == owner_user_id,
        )
        if session.get_bind().dialect.name != "sqlite":
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    def _budget_event(
        production: PersonalIPVideoProductionRow,
        *,
        owner_user_id: str,
        event_key: str,
        event_type: str,
        status: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        input_refs: list[str],
        output_refs: list[str],
        cost: dict[str, Any],
    ) -> PersonalIPVideoProductionEventRow:
        occurred_at = datetime.now(UTC)
        event_payload = {
            "cost": cost,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "event_type": event_type,
            "input_refs": input_refs,
            "model": None,
            "occurred_at": coerce_iso(occurred_at),
            "output_refs": output_refs,
            "payload": payload,
            "provider": "deerflow_budget_guard",
            "provider_task_id": None,
            "stage": production.current_stage,
            "status": status,
        }
        sequence = production.event_count + 1
        event = PersonalIPVideoProductionEventRow(
            id=f"video-event-{uuid.uuid4().hex}",
            owner_user_id=owner_user_id,
            production_id=production.id,
            event_key=event_key,
            event_digest=_digest(event_payload),
            sequence=sequence,
            event_type=event_type,
            stage=production.current_stage,
            status=status,
            entity_type=entity_type,
            entity_id=entity_id,
            provider="deerflow_budget_guard",
            model=None,
            provider_task_id=None,
            payload_json=payload,
            input_refs_json=input_refs,
            output_refs_json=output_refs,
            cost_json=cost,
            occurred_at=occurred_at,
            created_at=occurred_at,
        )
        production.event_count = sequence
        production.updated_at = occurred_at
        return event

    async def _budget_result(
        self,
        session: AsyncSession,
        production: PersonalIPVideoProductionRow,
        *,
        operation: dict[str, Any],
    ) -> dict[str, Any]:
        result = self._production_dict(production)
        result["events"] = await self._events(session, production.id)
        self._attach_budget_state(result, result["events"])
        result["budget_operation"] = operation
        return result

    @staticmethod
    def _validate_paid_approval(
        *,
        events: list[dict[str, Any]],
        approval_event_key: str | None,
        expected_request: dict[str, Any],
    ) -> None:
        if not approval_event_key:
            raise ValueError("video budget reservation requires an approved paid-provider review")
        approval = next(
            (event for event in events if event.get("event_key") == approval_event_key),
            None,
        )
        approval_payload = approval.get("payload") if isinstance(approval, dict) else {}
        if not isinstance(approval_payload, dict):
            approval_payload = {}
        if approval is None or approval.get("event_type") != "review_recorded" or approval.get("status") != "approved" or approval_payload.get("review_kind") != "paid_provider_call":
            raise ValueError("video budget reservation requires an approved paid-provider review")
        request_event_key = str(approval_payload.get("request_event_key") or "").strip()
        request = next(
            (event for event in events if event.get("event_key") == request_event_key),
            None,
        )
        request_payload = request.get("payload") if isinstance(request, dict) else {}
        if not isinstance(request_payload, dict):
            request_payload = {}
        if request is None or request.get("event_type") != "review_requested" or request_payload.get("review_kind") != "paid_provider_call" or request_payload.get("budget_request") != expected_request:
            raise ValueError("approved paid-provider review does not match this budget reservation")

    @staticmethod
    def _validate_provider_request_budget(
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        provider: str,
        payload: dict[str, Any],
        cost: dict[str, Any],
        events: list[dict[str, Any]],
    ) -> None:
        capability_by_event = {
            "asset_generation_requested": "image_generation",
            "shot_generation_requested": "video_generation",
            "voice_generation_requested": "speech_generation",
            "media_processing_requested": "media_processing",
        }
        capability = capability_by_event.get(event_type)
        if capability is None:
            return
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        billing_mode = str(payload.get("billing_mode") or parameters.get("billing_mode") or "").strip()
        if billing_mode not in {"free", "paid"}:
            raise ValueError(f"{event_type} payload.billing_mode must be free or paid")
        cost_status = str(cost.get("status") or "").strip()
        cost_currency = str(cost.get("currency") or "").strip().upper()
        if billing_mode == "free":
            if provider_requires_paid_admission(provider, capability):
                raise ValueError("server classifies this provider call as paid; a budget reservation is required")
            if (
                cost_status != "known"
                or amount_to_micros(
                    cost.get("amount"),
                    field="free provider request cost.amount",
                )
                != 0
            ):
                raise ValueError("free provider requests require a known zero cost receipt")
            return

        reservation_id = str(payload.get("budget_reservation_id") or parameters.get("budget_reservation_id") or "").strip()
        if not reservation_id:
            raise ValueError("paid provider requests require budget_reservation_id")
        if cost_status != "estimated":
            raise ValueError("paid provider requests require an estimated cost before submission")
        estimated_micros = amount_to_micros(
            cost.get("amount"),
            field="paid provider request cost.amount",
            allow_zero=False,
        )
        reservation = next(
            (event for event in events if event.get("event_type") == "budget_reserved" and (event.get("payload") or {}).get("reservation_id") == reservation_id),
            None,
        )
        if reservation is None:
            raise ValueError("paid provider budget reservation not found")
        if any(event.get("event_type") in {"budget_settled", "budget_released"} and (event.get("payload") or {}).get("reservation_id") == reservation_id for event in events):
            raise ValueError("paid provider budget reservation is no longer active")
        request = (reservation.get("payload") or {}).get("request")
        if not isinstance(request, dict):
            raise ValueError("paid provider budget reservation is invalid")
        PersonalIPVideoProductionRepository._validate_paid_approval(
            events=events,
            approval_event_key=(reservation.get("payload") or {}).get("approval_event_key"),
            expected_request=request,
        )
        if request.get("capability") != capability or request.get("provider") != provider or request.get("entity_type") != entity_type or request.get("entity_id") != entity_id:
            raise ValueError("paid provider request does not match its budget reservation")
        maximum_micros = amount_to_micros(
            request.get("maximum_amount"),
            field="budget reservation maximum_amount",
            allow_zero=False,
        )
        if estimated_micros > maximum_micros:
            raise ValueError("paid provider estimate exceeds the reserved maximum")
        if cost_currency != request.get("currency"):
            raise ValueError("paid provider request currency does not match its reservation")

        def _event_reservation_id(event: dict[str, Any]) -> str:
            event_payload = event.get("payload")
            if not isinstance(event_payload, dict):
                return ""
            event_parameters = event_payload.get("parameters")
            if not isinstance(event_parameters, dict):
                event_parameters = {}
            return str(event_payload.get("budget_reservation_id") or event_parameters.get("budget_reservation_id") or "").strip()

        if any(event.get("event_type") in capability_by_event and _event_reservation_id(event) == reservation_id for event in events):
            raise ValueError("budget reservation already admitted another provider request")

    async def reserve_budget(
        self,
        production_id: str,
        *,
        owner_user_id: str,
        reservation_key: str,
        capability: str,
        provider: str,
        entity_type: str,
        entity_id: str,
        maximum_amount: Any,
        currency: str,
        approval_event_key: str | None,
        request_ref: str,
    ) -> dict[str, Any] | None:
        """Atomically reserve a paid-call maximum before provider submission."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        reservation_key_value = _clean_required(
            reservation_key,
            field="reservation_key",
            limit=220,
        )
        capability_value = _clean_required(
            capability,
            field="capability",
            limit=80,
        )
        provider_value = _clean_required(provider, field="provider", limit=80)
        if entity_type not in VIDEO_ENTITY_TYPES:
            raise ValueError("unsupported video budget entity_type")
        entity_id_value = _clean_required(entity_id, field="entity_id", limit=128)
        maximum_micros = amount_to_micros(
            maximum_amount,
            field="maximum_amount",
            allow_zero=False,
        )
        currency_value = _clean_required(
            currency,
            field="currency",
            limit=8,
        ).upper()
        request_ref_value = _clean_required(
            request_ref,
            field="request_ref",
            limit=2_048,
        )
        validate_credential_free_payload(request_ref_value, field="request_ref")
        approval_key = _clean_optional(
            approval_event_key,
            field="approval_event_key",
            limit=256,
        )
        request = {
            "reservation_key": reservation_key_value,
            "provider": provider_value,
            "capability": capability_value,
            "maximum_amount": micros_to_amount(maximum_micros),
            "currency": currency_value,
            "entity_type": entity_type,
            "entity_id": entity_id_value,
        }
        event_key = f"budget-reserve:{reservation_key_value}"
        rejection_event_key = f"budget-reject:{reservation_key_value}"

        async with self._sf() as session:
            production = await self._lock_budget_production(
                session,
                production_id=production_id,
                owner_user_id=owner,
            )
            if production is None:
                return None
            if production.status in {"completed", "cancelled"}:
                raise ValueError("terminal video production cannot reserve provider budget")
            events = await self._events(session, production.id)
            existing = next(
                (event for event in events if event.get("event_key") == event_key),
                None,
            )
            if existing is not None:
                payload = existing.get("payload") or {}
                if payload.get("request") != request:
                    raise ValueError("reservation_key already records a different budget request")
                self._validate_paid_approval(
                    events=events,
                    approval_event_key=payload.get("approval_event_key"),
                    expected_request=request,
                )
                operation = {
                    "contract_version": VIDEO_BUDGET_RESERVATION_CONTRACT_VERSION,
                    "operation": "reserved",
                    "reservation_id": payload["reservation_id"],
                    "reservation_event_key": event_key,
                    **request,
                }
                return await self._budget_result(
                    session,
                    production,
                    operation=operation,
                )
            existing_rejection = next(
                (event for event in events if event.get("event_key") == rejection_event_key),
                None,
            )
            if existing_rejection is not None:
                payload = existing_rejection.get("payload") or {}
                if payload.get("request") != request:
                    raise ValueError("reservation_key already records a different budget request")
                raise ValueError("budget reservation exceeds the remaining video budget")

            budget_currency, _ = budget_limit(production.budget_json or {})
            if currency_value != budget_currency:
                raise ValueError("budget reservation currency does not match the video budget")
            self._validate_paid_approval(
                events=events,
                approval_event_key=approval_key,
                expected_request=request,
            )
            state = fold_video_budget(production.budget_json or {}, events)
            if maximum_micros > state["_available_micros"]:
                payload = {
                    "contract_version": VIDEO_BUDGET_REJECTION_CONTRACT_VERSION,
                    "request": request,
                    "available_amount": micros_to_amount(state["_available_micros"]),
                    "currency": currency_value,
                    "decision": "rejected",
                    "reason_code": "hard_limit_exceeded",
                }
                event = self._budget_event(
                    production,
                    owner_user_id=owner,
                    event_key=rejection_event_key,
                    event_type="budget_reservation_rejected",
                    status="rejected",
                    entity_type=entity_type,
                    entity_id=entity_id_value,
                    payload=payload,
                    input_refs=[],
                    output_refs=[],
                    cost={
                        "status": "estimated",
                        "amount": request["maximum_amount"],
                        "currency": currency_value,
                        "basis": "rejected hard budget admission",
                    },
                )
                session.add(event)
                await session.commit()
                raise ValueError("budget reservation exceeds the remaining video budget")

            reservation_id = f"video-budget-reservation-{uuid.uuid4().hex}"
            payload = {
                "contract_version": VIDEO_BUDGET_RESERVATION_CONTRACT_VERSION,
                "reservation_id": reservation_id,
                "request": request,
                "maximum_amount": request["maximum_amount"],
                "currency": currency_value,
                "approval_event_key": approval_key,
                "request_ref": request_ref_value,
                "decision": "reserved",
            }
            cost = {
                "status": "estimated",
                "amount": request["maximum_amount"],
                "currency": currency_value,
                "basis": "hard budget reservation",
            }
            event = self._budget_event(
                production,
                owner_user_id=owner,
                event_key=event_key,
                event_type="budget_reserved",
                status="running",
                entity_type=entity_type,
                entity_id=entity_id_value,
                payload=payload,
                input_refs=[request_ref_value],
                output_refs=[f"budget-reservation://{reservation_id}"],
                cost=cost,
            )
            session.add(event)
            await session.commit()
            await session.refresh(production)
            operation = {
                "contract_version": VIDEO_BUDGET_RESERVATION_CONTRACT_VERSION,
                "operation": "reserved",
                "reservation_id": reservation_id,
                "reservation_event_key": event_key,
                **request,
            }
            return await self._budget_result(
                session,
                production,
                operation=operation,
            )

    async def settle_budget(
        self,
        production_id: str,
        *,
        owner_user_id: str,
        reservation_id: str,
        settlement_key: str,
        actual_amount: Any,
        currency: str,
        provider_receipt_ref: str,
    ) -> dict[str, Any] | None:
        """Convert one active maximum reservation into accumulated actual cost."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        reservation_id_value = _clean_required(
            reservation_id,
            field="reservation_id",
            limit=96,
        )
        settlement_key_value = _clean_required(
            settlement_key,
            field="settlement_key",
            limit=220,
        )
        actual_micros = amount_to_micros(
            actual_amount,
            field="actual_amount",
        )
        currency_value = _clean_required(
            currency,
            field="currency",
            limit=8,
        ).upper()
        receipt_ref = _clean_required(
            provider_receipt_ref,
            field="provider_receipt_ref",
            limit=2_048,
        )
        validate_credential_free_payload(
            receipt_ref,
            field="provider_receipt_ref",
        )
        event_key = f"budget-settle:{settlement_key_value}"

        async with self._sf() as session:
            production = await self._lock_budget_production(
                session,
                production_id=production_id,
                owner_user_id=owner,
            )
            if production is None:
                return None
            events = await self._events(session, production.id)
            reservation = next(
                (event for event in events if event.get("event_type") == "budget_reserved" and (event.get("payload") or {}).get("reservation_id") == reservation_id_value),
                None,
            )
            if reservation is None:
                raise ValueError("video budget reservation not found")
            reservation_payload = reservation.get("payload") or {}
            maximum_micros = amount_to_micros(
                reservation_payload.get("maximum_amount"),
                field="reserved maximum_amount",
                allow_zero=False,
            )
            if actual_micros > maximum_micros:
                raise ValueError("actual cost exceeds the reserved maximum")
            if currency_value != reservation_payload.get("currency"):
                raise ValueError("budget settlement currency does not match the reservation")
            operation_payload = {
                "contract_version": VIDEO_BUDGET_SETTLEMENT_CONTRACT_VERSION,
                "reservation_id": reservation_id_value,
                "reservation_event_key": reservation["event_key"],
                "actual_amount": micros_to_amount(actual_micros),
                "currency": currency_value,
                "provider_receipt_ref": receipt_ref,
                "decision": "settled",
            }
            existing = next(
                (event for event in events if event.get("event_key") == event_key),
                None,
            )
            if existing is not None:
                if existing.get("payload") != operation_payload:
                    raise ValueError("settlement_key already records a different budget settlement")
                return await self._budget_result(
                    session,
                    production,
                    operation={
                        **operation_payload,
                        "operation": "settled",
                        "settlement_event_key": event_key,
                    },
                )
            terminal = next(
                (event for event in events if event.get("event_type") in {"budget_settled", "budget_released"} and (event.get("payload") or {}).get("reservation_id") == reservation_id_value),
                None,
            )
            if terminal is not None:
                terminal_word = "released" if terminal.get("event_type") == "budget_released" else "settled"
                raise ValueError(f"video budget reservation is already {terminal_word}")
            cost = {
                "status": "known",
                "amount": operation_payload["actual_amount"],
                "currency": currency_value,
                "basis": "provider receipt settlement",
            }
            event = self._budget_event(
                production,
                owner_user_id=owner,
                event_key=event_key,
                event_type="budget_settled",
                status="succeeded",
                entity_type=reservation["entity_type"],
                entity_id=reservation["entity_id"],
                payload=operation_payload,
                input_refs=[
                    f"event://{reservation['event_key']}",
                    receipt_ref,
                ],
                output_refs=[f"budget-settlement://{reservation_id_value}"],
                cost=cost,
            )
            session.add(event)
            await session.commit()
            await session.refresh(production)
            return await self._budget_result(
                session,
                production,
                operation={
                    **operation_payload,
                    "operation": "settled",
                    "settlement_event_key": event_key,
                },
            )

    async def release_budget(
        self,
        production_id: str,
        *,
        owner_user_id: str,
        reservation_id: str,
        release_key: str,
        reason: str,
    ) -> dict[str, Any] | None:
        """Release an active reservation only when the provider was not called."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        reservation_id_value = _clean_required(
            reservation_id,
            field="reservation_id",
            limit=96,
        )
        release_key_value = _clean_required(
            release_key,
            field="release_key",
            limit=220,
        )
        reason_value = _clean_required(reason, field="reason", limit=1_000)
        event_key = f"budget-release:{release_key_value}"

        async with self._sf() as session:
            production = await self._lock_budget_production(
                session,
                production_id=production_id,
                owner_user_id=owner,
            )
            if production is None:
                return None
            events = await self._events(session, production.id)
            reservation = next(
                (event for event in events if event.get("event_type") == "budget_reserved" and (event.get("payload") or {}).get("reservation_id") == reservation_id_value),
                None,
            )
            if reservation is None:
                raise ValueError("video budget reservation not found")
            operation_payload = {
                "contract_version": VIDEO_BUDGET_RELEASE_CONTRACT_VERSION,
                "reservation_id": reservation_id_value,
                "reservation_event_key": reservation["event_key"],
                "reason": reason_value,
                "decision": "released",
            }
            existing = next(
                (event for event in events if event.get("event_key") == event_key),
                None,
            )
            if existing is not None:
                if existing.get("payload") != operation_payload:
                    raise ValueError("release_key already records a different budget release")
                return await self._budget_result(
                    session,
                    production,
                    operation={
                        **operation_payload,
                        "operation": "released",
                        "release_event_key": event_key,
                    },
                )
            terminal = next(
                (event for event in events if event.get("event_type") in {"budget_settled", "budget_released"} and (event.get("payload") or {}).get("reservation_id") == reservation_id_value),
                None,
            )
            if terminal is not None:
                terminal_word = "released" if terminal.get("event_type") == "budget_released" else "settled"
                raise ValueError(f"video budget reservation is already {terminal_word}")
            if any(
                event.get("event_type")
                in {
                    "asset_generation_requested",
                    "shot_generation_requested",
                    "voice_generation_requested",
                    "media_processing_requested",
                }
                and (
                    (event.get("payload") or {}).get("budget_reservation_id")
                    or (
                        (event.get("payload") or {}).get("parameters")
                        if isinstance(
                            (event.get("payload") or {}).get("parameters"),
                            dict,
                        )
                        else {}
                    ).get("budget_reservation_id")
                )
                == reservation_id_value
                for event in events
            ):
                raise ValueError("provider request was admitted; settle the reservation instead")
            currency, _ = budget_limit(production.budget_json or {})
            event = self._budget_event(
                production,
                owner_user_id=owner,
                event_key=event_key,
                event_type="budget_released",
                status="succeeded",
                entity_type=reservation["entity_type"],
                entity_id=reservation["entity_id"],
                payload=operation_payload,
                input_refs=[f"event://{reservation['event_key']}"],
                output_refs=[f"budget-release://{reservation_id_value}"],
                cost={
                    "status": "known",
                    "amount": 0.0,
                    "currency": currency,
                    "basis": "provider not called; reservation released",
                },
            )
            session.add(event)
            await session.commit()
            await session.refresh(production)
            return await self._budget_result(
                session,
                production,
                operation={
                    **operation_payload,
                    "operation": "released",
                    "release_event_key": event_key,
                },
            )

    async def append_event(
        self,
        production_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        event_type: str,
        status: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any],
        input_refs: Sequence[str],
        output_refs: Sequence[str],
        provider: str,
        model: str | None,
        provider_task_id: str | None,
        cost: dict[str, Any],
        occurred_at: datetime | None = None,
        trusted_human_confirmation: bool = False,
    ) -> dict[str, Any] | None:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        event_key_value = _clean_required(event_key, field="event_key", limit=256)
        event_type_key = str(event_type or "").strip()
        stage = VIDEO_EVENT_STAGES.get(event_type_key)
        if stage is None:
            raise ValueError("unsupported video production event_type")
        status_key = str(status or "").strip()
        if status_key not in VIDEO_EVENT_STATUSES:
            raise ValueError("unsupported video production event status")
        if status_key not in VIDEO_EVENT_ALLOWED_STATUSES[event_type_key]:
            allowed = ", ".join(sorted(VIDEO_EVENT_ALLOWED_STATUSES[event_type_key]))
            raise ValueError(f"{event_type_key} status must be one of: {allowed}")
        entity_type_key = str(entity_type or "").strip()
        if entity_type_key not in VIDEO_ENTITY_TYPES:
            raise ValueError("unsupported video production entity_type")
        entity_id_key = _clean_required(entity_id, field="entity_id", limit=128)
        provider_key = _clean_required(provider, field="provider", limit=80)
        model_key = _clean_optional(model, field="model", limit=160)
        provider_task_key = _clean_optional(provider_task_id, field="provider_task_id", limit=256)
        payload_snapshot = _json_snapshot(payload, field="payload", expected=dict)
        if event_type_key == "review_recorded" and payload_snapshot.get("review_kind") in {"candidate_selection", "paid_provider_call", "real_publish"} and trusted_human_confirmation is not True:
            raise ValueError("meaningful review decisions require a trusted human confirmation")
        input_snapshot = _normalized_ids(input_refs, field="input_refs", limit=500, item_limit=2_048)
        output_snapshot = _normalized_ids(output_refs, field="output_refs", limit=500, item_limit=2_048)
        cost_snapshot = _json_snapshot(cost, field="cost", expected=dict, byte_limit=256_000)
        if event_type_key == "delivery_qa_completed":
            if payload_snapshot.get("contract_version") != "personal-ip-delivery-qa-v1":
                raise ValueError("delivery QA payload must use personal-ip-delivery-qa-v1")
            if payload_snapshot.get("passed") is not (status_key == "succeeded"):
                raise ValueError("delivery QA payload passed flag must match event status")
            if not output_snapshot:
                raise ValueError("delivery QA must reference at least one output")
        if event_type_key == "delivery_completed" and not output_snapshot:
            raise ValueError("delivery_completed must reference at least one output")
        compiled_contract = COMPILED_VIDEO_EVENT_CONTRACTS.get(event_type_key)
        if compiled_contract is not None:
            compiled_contract_version, compiled_entity_type = compiled_contract
            validate_compiled_video_contract(
                payload_snapshot,
                contract_version=compiled_contract_version,
                production_id=production_id,
            )
            if entity_type_key != compiled_entity_type:
                raise ValueError(f"{event_type_key} must target a {compiled_entity_type} entity")
            if compiled_entity_type == "production" and entity_id_key != production_id:
                raise ValueError("compiled video contracts must target their production entity")
            if not output_snapshot:
                raise ValueError("compiled video contracts must reference their sealed output")
            if event_type_key == "generated_shot_qa_compiled":
                if payload_snapshot.get("candidate_id") != entity_id_key:
                    raise ValueError("generated shot QA candidate_id must match its event entity")
                if payload_snapshot.get("automated_gate_passed") is not (status_key == "succeeded"):
                    raise ValueError("generated shot QA gate must match event status")
            if event_type_key == "material_inspection_compiled" and payload_snapshot.get("asset_id") != entity_id_key:
                raise ValueError("material inspection asset_id must match its event entity")

        async with self._sf() as session:
            if event_type_key in {
                "asset_generation_requested",
                "shot_generation_requested",
                "voice_generation_requested",
                "media_processing_requested",
            }:
                production = await self._lock_budget_production(
                    session,
                    production_id=production_id,
                    owner_user_id=owner,
                )
            else:
                production_statement = (
                    select(PersonalIPVideoProductionRow)
                    .where(
                        PersonalIPVideoProductionRow.id == production_id,
                        PersonalIPVideoProductionRow.owner_user_id == owner,
                    )
                    .with_for_update()
                )
                production = (await session.execute(production_statement)).scalar_one_or_none()
            if production is None or production.owner_user_id != owner:
                return None
            if compiled_contract is not None:
                production_mode = (production.source_json or {}).get("production_mode")
                validation_kwargs: dict[str, Any] = {
                    "contract_version": compiled_contract_version,
                    "production_id": production.id,
                }
                if production_mode is not None:
                    validation_kwargs["production_mode"] = production_mode
                validate_compiled_video_contract(payload_snapshot, **validation_kwargs)
            existing_statement = select(PersonalIPVideoProductionEventRow).where(
                PersonalIPVideoProductionEventRow.production_id == production.id,
                PersonalIPVideoProductionEventRow.event_key == event_key_value,
            )
            existing = (await session.execute(existing_statement)).scalar_one_or_none()
            event_time = _utc(occurred_at if occurred_at is not None else (existing.occurred_at if existing else None))
            event_payload = {
                "cost": cost_snapshot,
                "entity_id": entity_id_key,
                "entity_type": entity_type_key,
                "event_type": event_type_key,
                "input_refs": input_snapshot,
                "model": model_key,
                "occurred_at": coerce_iso(event_time),
                "output_refs": output_snapshot,
                "payload": payload_snapshot,
                "provider": provider_key,
                "provider_task_id": provider_task_key,
                "stage": stage,
                "status": status_key,
            }
            event_digest = _digest(event_payload)
            if existing is not None:
                if existing.event_digest != event_digest:
                    raise ValueError("event_key already records a different video production event")
                result = self._production_dict(production)
                result["events"] = await self._events(session, production.id)
                self._attach_budget_state(result, result["events"])
                return result
            if production.status in {"completed", "cancelled"}:
                raise ValueError("terminal video production cannot accept new events")
            events = await self._events(session, production.id)
            self._validate_provider_request_budget(
                event_type=event_type_key,
                entity_type=entity_type_key,
                entity_id=entity_id_key,
                provider=provider_key,
                payload=payload_snapshot,
                cost=cost_snapshot,
                events=events,
            )
            latest_lock: PersonalIPVideoProductionEventRow | None = None
            if event_type_key in {"delivery_qa_completed", "delivery_completed"}:
                latest_revision_statement = (
                    select(PersonalIPVideoProductionEventRow)
                    .where(
                        PersonalIPVideoProductionEventRow.production_id == production.id,
                        PersonalIPVideoProductionEventRow.event_type == "timeline_revision_compiled",
                        PersonalIPVideoProductionEventRow.status == "succeeded",
                    )
                    .order_by(PersonalIPVideoProductionEventRow.sequence.desc())
                    .limit(1)
                )
                latest_revision = (await session.execute(latest_revision_statement)).scalar_one_or_none()
                if latest_revision is not None:
                    latest_lock_statement = (
                        select(PersonalIPVideoProductionEventRow)
                        .where(
                            PersonalIPVideoProductionEventRow.production_id == production.id,
                            PersonalIPVideoProductionEventRow.event_type == "final_edit_locked",
                            PersonalIPVideoProductionEventRow.status == "succeeded",
                        )
                        .order_by(PersonalIPVideoProductionEventRow.sequence.desc())
                        .limit(1)
                    )
                    latest_lock = (await session.execute(latest_lock_statement)).scalar_one_or_none()
                    if latest_lock is None:
                        raise ValueError("delivery QA requires final_edit_locked after a timeline revision")
                    if (latest_lock.payload_json or {}).get("source_timeline_sha256") != (latest_revision.payload_json or {}).get("sha256"):
                        raise ValueError("delivery QA requires a lock for the latest timeline revision")
            if event_type_key == "delivery_completed":
                qa_statement = (
                    select(PersonalIPVideoProductionEventRow)
                    .where(
                        PersonalIPVideoProductionEventRow.production_id == production.id,
                        PersonalIPVideoProductionEventRow.event_type == "delivery_qa_completed",
                        PersonalIPVideoProductionEventRow.status == "succeeded",
                    )
                    .order_by(PersonalIPVideoProductionEventRow.sequence.desc())
                )
                qa_events = list((await session.execute(qa_statement)).scalars())
                if latest_lock is not None:
                    qa_events = [event for event in qa_events if event.sequence > latest_lock.sequence]
                passed_qa = [event for event in qa_events if (event.payload_json or {}).get("passed") is True]
                if not passed_qa:
                    raise ValueError("delivery_completed requires a successful delivery QA event")
                if not any(set(event.output_refs_json or []) == set(output_snapshot) for event in passed_qa):
                    raise ValueError("delivery_completed requires QA for the exact delivery outputs")

            sequence = production.event_count + 1
            event = PersonalIPVideoProductionEventRow(
                id=f"video-event-{uuid.uuid4().hex}",
                owner_user_id=owner,
                production_id=production.id,
                event_key=event_key_value,
                event_digest=event_digest,
                sequence=sequence,
                event_type=event_type_key,
                stage=stage,
                status=status_key,
                entity_type=entity_type_key,
                entity_id=entity_id_key,
                provider=provider_key,
                model=model_key,
                provider_task_id=provider_task_key,
                payload_json=payload_snapshot,
                input_refs_json=input_snapshot,
                output_refs_json=output_snapshot,
                cost_json=cost_snapshot,
                occurred_at=event_time,
                created_at=datetime.now(UTC),
            )
            session.add(event)
            production.event_count = sequence
            production.current_stage = stage
            if event_type_key == "delivery_completed":
                production.status = "completed"
            elif status_key in {"failed", "rejected"}:
                production.status = "blocked"
            elif status_key == "awaiting_review":
                production.status = "awaiting_review"
            else:
                production.status = "running"
            production.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(production)
            result = self._production_dict(production)
            result["events"] = await self._events(session, production.id)
            self._attach_budget_state(result, result["events"])
            return result
