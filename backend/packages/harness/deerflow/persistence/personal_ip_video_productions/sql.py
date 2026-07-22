"""Append-only repository for Personal-IP video production receipts."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_platform_observations.sql import validate_credential_free_payload
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.persistence.personal_ip_video_productions.model import (
    PersonalIPVideoProductionEventRow,
    PersonalIPVideoProductionRow,
)
from deerflow.utils.time import coerce_iso

VIDEO_PRODUCTION_CONTRACT_VERSION = "personal-ip-video-production-v1"

VIDEO_EVENT_STAGES: dict[str, str] = {
    "blueprint_sealed": "blueprint",
    "asset_registered": "assets",
    "asset_generation_requested": "assets",
    "asset_generation_completed": "assets",
    "asset_generation_failed": "assets",
    "storyboard_sealed": "storyboard",
    "shot_generation_requested": "generation",
    "shot_generation_completed": "generation",
    "shot_generation_failed": "generation",
    "consistency_checked": "consistency",
    "candidate_selected": "selection",
    "review_requested": "selection",
    "review_recorded": "selection",
    "voice_generated": "finishing",
    "voice_generation_requested": "finishing",
    "media_processing_requested": "finishing",
    "media_processing_completed": "finishing",
    "media_processing_failed": "finishing",
    "edit_completed": "finishing",
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
    "blueprint_sealed": {"succeeded"},
    "asset_registered": {"succeeded"},
    "asset_generation_requested": {"running"},
    "asset_generation_completed": {"succeeded"},
    "asset_generation_failed": {"failed"},
    "storyboard_sealed": {"succeeded"},
    "shot_generation_requested": {"planned", "running"},
    "shot_generation_completed": {"succeeded"},
    "shot_generation_failed": {"failed"},
    "consistency_checked": {"succeeded", "failed"},
    "candidate_selected": {"succeeded"},
    "review_requested": {"awaiting_review"},
    "review_recorded": {"approved", "rejected"},
    "voice_generated": {"succeeded", "failed"},
    "voice_generation_requested": {"running"},
    "media_processing_requested": {"running"},
    "media_processing_completed": {"succeeded"},
    "media_processing_failed": {"failed"},
    "edit_completed": {"succeeded", "failed"},
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
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        operation = _clean_required(operation_key, field="operation_key", limit=256)
        title_key = _clean_required(title, field="title", limit=256)
        subject_key = _clean_optional(subject_id, field="subject_id", limit=64)
        source_kind_key = str(source_kind or "").strip()
        if source_kind_key not in {"idea", "script"}:
            raise ValueError("source_kind must be idea or script")
        target_ids = _normalized_ids(target_account_ids, field="target_account_ids", limit=200)
        source_snapshot = _json_snapshot(source, field="source", expected=dict)
        delivery_snapshot = _json_snapshot(delivery_spec, field="delivery_spec", expected=dict)
        provider_snapshot = _json_snapshot(provider_policy, field="provider_policy", expected=dict)
        budget_snapshot = _json_snapshot(budget, field="budget", expected=dict)
        request_payload = {
            "budget": budget_snapshot,
            "delivery_spec": delivery_snapshot,
            "provider_policy": provider_snapshot,
            "source": source_snapshot,
            "source_kind": source_kind_key,
            "subject_id": subject_key,
            "target_account_ids": target_ids,
            "title": title_key,
        }
        request_digest = _digest(request_payload)

        async with self._sf() as session:
            statement = select(PersonalIPVideoProductionRow).where(
                PersonalIPVideoProductionRow.owner_user_id == owner,
                PersonalIPVideoProductionRow.operation_key == operation,
            )
            existing = (await session.execute(statement)).scalar_one_or_none()
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise ValueError("operation_key already records a different video production")
                result = self._production_dict(existing)
                result["events"] = await self._events(session, existing.id)
                return result
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
                operation_key=operation,
                contract_version=VIDEO_PRODUCTION_CONTRACT_VERSION,
                title=title_key,
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
            return result

    async def list(self, owner_user_id: str, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        statement = select(PersonalIPVideoProductionRow).where(PersonalIPVideoProductionRow.owner_user_id == owner_user_id)
        if status is not None:
            statement = statement.where(PersonalIPVideoProductionRow.status == status)
        statement = statement.order_by(
            PersonalIPVideoProductionRow.updated_at.desc(),
            PersonalIPVideoProductionRow.id.desc(),
        ).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._production_dict(row) for row in rows]

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
        input_snapshot = _normalized_ids(input_refs, field="input_refs", limit=500, item_limit=2_048)
        output_snapshot = _normalized_ids(output_refs, field="output_refs", limit=500, item_limit=2_048)
        cost_snapshot = _json_snapshot(cost, field="cost", expected=dict, byte_limit=256_000)

        async with self._sf() as session:
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
                return result
            if production.status in {"completed", "cancelled"}:
                raise ValueError("terminal video production cannot accept new events")

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
            return result
