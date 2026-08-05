"""Owner-scoped repository for immutable Personal-IP content versions."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_content.model import (
    PersonalIPBreakdownVersionRow,
    PersonalIPContentWorkRow,
    PersonalIPDirectionVersionRow,
    PersonalIPScriptVersionRow,
)
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.personal_ip.content_contracts import ContentWorkAppend, ContentWorkCreate
from deerflow.personal_ip.evidence_binding import reference_evidence_refs
from deerflow.utils.time import coerce_iso


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _version_payload(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude_none=False)


class PersonalIPContentRepository:
    """Append-only content lineage with Owner and work consistency checks."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _iso_dict(row: Any) -> dict[str, Any]:
        data = row.to_dict()
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = coerce_iso(value)
        return data

    @classmethod
    def _work_dict(cls, row: PersonalIPContentWorkRow) -> dict[str, Any]:
        data = cls._iso_dict(row)
        data["objective"] = data.pop("objective_json")
        data.pop("operation_digest", None)
        return data

    @classmethod
    def _breakdown_dict(cls, row: PersonalIPBreakdownVersionRow) -> dict[str, Any]:
        data = cls._iso_dict(row)
        data["source_identity"] = data.pop("source_identity_json")
        data["evidence_snapshot"] = data.pop("evidence_snapshot_json")
        data["observations"] = data.pop("observations_json")
        data["interpretations"] = data.pop("interpretations_json")
        data["limitations"] = data.pop("limitations_json")
        data.pop("commit_digest", None)
        return data

    @classmethod
    def _direction_dict(cls, row: PersonalIPDirectionVersionRow) -> dict[str, Any]:
        data = cls._iso_dict(row)
        data["breakdown_version_ids"] = data.pop("breakdown_version_ids_json")
        data["objective_snapshot"] = data.pop("objective_snapshot_json")
        data["direction"] = data.pop("direction_json")
        data.pop("commit_digest", None)
        return data

    @classmethod
    def _script_dict(cls, row: PersonalIPScriptVersionRow) -> dict[str, Any]:
        data = cls._iso_dict(row)
        data["claim_basis"] = data.pop("claim_basis_json")
        data["creative_elements"] = data.pop("creative_elements_json")
        data["story_engine_seed"] = data.pop("story_engine_seed_json")
        data["production_notes"] = data.pop("production_notes_json")
        data.pop("commit_digest", None)
        return data

    @staticmethod
    async def _owned_subject(
        session: AsyncSession,
        subject_id: str | None,
        owner_user_id: str,
    ) -> None:
        if subject_id is None:
            return
        subject = await session.get(PersonalIPSubjectRow, subject_id)
        if subject is None or subject.owner_user_id != owner_user_id:
            raise ValueError("Personal-IP subject not found")

    @staticmethod
    async def _owned_work(
        session: AsyncSession,
        content_work_id: str,
        owner_user_id: str,
        *,
        lock: bool = False,
    ) -> PersonalIPContentWorkRow | None:
        if lock and session.get_bind().dialect.name == "sqlite":
            await session.execute(text("BEGIN IMMEDIATE"))
        statement = select(PersonalIPContentWorkRow).where(
            PersonalIPContentWorkRow.id == content_work_id,
            PersonalIPContentWorkRow.owner_user_id == owner_user_id,
        )
        if lock and session.get_bind().dialect.name != "sqlite":
            statement = statement.with_for_update()
        return (await session.execute(statement)).scalar_one_or_none()

    @staticmethod
    async def _next_version(session: AsyncSession, model: Any, content_work_id: str) -> int:
        current = (await session.execute(select(func.max(model.version_number)).where(model.content_work_id == content_work_id))).scalar_one()
        return int(current or 0) + 1

    @staticmethod
    async def _require_breakdowns(
        session: AsyncSession,
        *,
        owner_user_id: str,
        content_work_id: str,
        version_ids: list[str],
    ) -> list[PersonalIPBreakdownVersionRow]:
        if not version_ids:
            return []
        rows = (
            (
                await session.execute(
                    select(PersonalIPBreakdownVersionRow).where(
                        PersonalIPBreakdownVersionRow.id.in_(version_ids),
                        PersonalIPBreakdownVersionRow.owner_user_id == owner_user_id,
                        PersonalIPBreakdownVersionRow.content_work_id == content_work_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if {row.id for row in rows} != set(version_ids):
            raise ValueError("breakdown version does not belong to this Owner and content work")
        return list(rows)

    @staticmethod
    def _breakdown_claim_refs(row: PersonalIPBreakdownVersionRow) -> set[str]:
        """Rebuild claimable refs from one sealed BreakdownVersion."""
        if row.source_kind == "owner_material":
            observations = row.observations_json
            if not isinstance(observations, list):
                raise ValueError("owner-material BreakdownVersion observations are invalid")
            refs: set[str] = set()
            for observation in observations:
                if not isinstance(observation, Mapping):
                    raise ValueError("owner-material BreakdownVersion observation is invalid")
                evidence_refs = observation.get("evidence_refs")
                if not isinstance(evidence_refs, list) or any(not isinstance(ref, str) for ref in evidence_refs):
                    raise ValueError("owner-material BreakdownVersion evidence refs are invalid")
                refs.update(evidence_refs)
            return refs

        snapshot = row.evidence_snapshot_json
        request_id = str(row.evidence_request_id or "")
        item_index = row.evidence_item_index
        if not isinstance(snapshot, Mapping):
            raise ValueError("external BreakdownVersion evidence snapshot is unavailable")
        metadata = snapshot.get("metadata")
        items = snapshot.get("items")
        if (
            not isinstance(metadata, Mapping)
            or metadata.get("request_id") != request_id
            or snapshot.get("contract_version") != row.evidence_contract_version
            or _digest(snapshot) != row.evidence_payload_digest
            or not isinstance(items, list)
            or not isinstance(item_index, int)
            or item_index < 0
            or item_index >= len(items)
            or not isinstance(items[item_index], Mapping)
        ):
            raise ValueError("external BreakdownVersion evidence snapshot is invalid")
        return reference_evidence_refs(
            request_id=request_id,
            item_index=item_index,
            item=items[item_index],
        )

    @staticmethod
    async def _require_direction(
        session: AsyncSession,
        *,
        owner_user_id: str,
        content_work_id: str,
        direction_version_id: str,
    ) -> PersonalIPDirectionVersionRow:
        row = await session.get(PersonalIPDirectionVersionRow, direction_version_id)
        if row is None or row.owner_user_id != owner_user_id or row.content_work_id != content_work_id:
            raise ValueError("direction version does not belong to this Owner and content work")
        return row

    @staticmethod
    async def _require_parent_direction(
        session: AsyncSession,
        *,
        owner_user_id: str,
        content_work_id: str,
        parent_id: str | None,
    ) -> None:
        if parent_id is not None:
            await PersonalIPContentRepository._require_direction(
                session,
                owner_user_id=owner_user_id,
                content_work_id=content_work_id,
                direction_version_id=parent_id,
            )

    @staticmethod
    async def _require_parent_script(
        session: AsyncSession,
        *,
        owner_user_id: str,
        content_work_id: str,
        parent_id: str | None,
    ) -> None:
        if parent_id is None:
            return
        row = await session.get(PersonalIPScriptVersionRow, parent_id)
        if row is None or row.owner_user_id != owner_user_id or row.content_work_id != content_work_id:
            raise ValueError("parent script version does not belong to this Owner and content work")

    @staticmethod
    async def _existing_commit_rows(
        session: AsyncSession,
        *,
        content_work_id: str,
        commit_key: str,
        include_breakdown: bool,
        include_direction: bool,
        include_script: bool,
    ) -> tuple[
        PersonalIPBreakdownVersionRow | None,
        PersonalIPDirectionVersionRow | None,
        PersonalIPScriptVersionRow | None,
    ]:
        breakdown = None
        direction = None
        script = None
        if include_breakdown:
            breakdown = (
                await session.execute(
                    select(PersonalIPBreakdownVersionRow).where(
                        PersonalIPBreakdownVersionRow.content_work_id == content_work_id,
                        PersonalIPBreakdownVersionRow.commit_key == commit_key,
                    )
                )
            ).scalar_one_or_none()
        if include_direction:
            direction = (
                await session.execute(
                    select(PersonalIPDirectionVersionRow).where(
                        PersonalIPDirectionVersionRow.content_work_id == content_work_id,
                        PersonalIPDirectionVersionRow.commit_key == commit_key,
                    )
                )
            ).scalar_one_or_none()
        if include_script:
            script = (
                await session.execute(
                    select(PersonalIPScriptVersionRow).where(
                        PersonalIPScriptVersionRow.content_work_id == content_work_id,
                        PersonalIPScriptVersionRow.commit_key == commit_key,
                    )
                )
            ).scalar_one_or_none()
        return breakdown, direction, script

    async def _append_in_session(
        self,
        session: AsyncSession,
        *,
        work: PersonalIPContentWorkRow,
        owner_user_id: str,
        commit: ContentWorkAppend,
        commit_digest: str,
        created_by_run_id: str | None,
        verified_evidence_snapshots: Mapping[str, dict[str, Any]],
        verified_script_digests: frozenset[str],
    ) -> dict[str, Any]:
        supplied = (commit.breakdown is not None, commit.direction is not None, commit.script is not None)
        existing = await self._existing_commit_rows(
            session,
            content_work_id=work.id,
            commit_key=commit.idempotency_key,
            include_breakdown=True,
            include_direction=True,
            include_script=True,
        )
        presence = tuple(row is not None for row in existing)
        if any(presence):
            if presence != supplied:
                raise RuntimeError("content commit is partially present; manual integrity review is required")
            if any(row is not None and row.commit_digest != commit_digest for row in existing):
                raise ValueError("idempotency_key already records a different content commit")
            return {
                "replayed": True,
                "breakdown_version": self._breakdown_dict(existing[0]) if existing[0] else None,
                "direction_version": self._direction_dict(existing[1]) if existing[1] else None,
                "script_version": self._script_dict(existing[2]) if existing[2] else None,
            }

        if work.status != "active":
            raise ValueError("archived Personal-IP content work cannot accept new versions")

        now = datetime.now(UTC)
        breakdown_row: PersonalIPBreakdownVersionRow | None = None
        direction_row: PersonalIPDirectionVersionRow | None = None
        script_row: PersonalIPScriptVersionRow | None = None

        if commit.breakdown is not None:
            if commit.breakdown.source_kind in {"platform_content", "uploaded_file"}:
                request_id = str(commit.breakdown.evidence_request_id or "")
                evidence_snapshot = verified_evidence_snapshots.get(request_id)
                if evidence_snapshot is None:
                    raise ValueError("external breakdown requires a verified Evidence MCP result from this task")
                if commit.breakdown.source_digest is None or commit.breakdown.evidence_contract_version is None or commit.breakdown.evidence_payload_digest is None:
                    raise ValueError("external breakdown Evidence MCP binding is incomplete")
                metadata = evidence_snapshot.get("metadata")
                if (
                    not isinstance(metadata, dict)
                    or metadata.get("request_id") != request_id
                    or evidence_snapshot.get("contract_version") != commit.breakdown.evidence_contract_version
                    or _digest(evidence_snapshot) != commit.breakdown.evidence_payload_digest
                ):
                    raise ValueError("external breakdown Evidence MCP snapshot does not match its binding")
            else:
                evidence_snapshot = None
            breakdown_row = PersonalIPBreakdownVersionRow(
                id=_id("breakdown"),
                owner_user_id=owner_user_id,
                content_work_id=work.id,
                version_number=await self._next_version(session, PersonalIPBreakdownVersionRow, work.id),
                commit_key=commit.idempotency_key,
                commit_digest=commit_digest,
                source_kind=commit.breakdown.source_kind,
                source_identity_json=dict(commit.breakdown.source_identity),
                source_digest=commit.breakdown.source_digest,
                evidence_request_id=commit.breakdown.evidence_request_id,
                evidence_item_index=commit.breakdown.evidence_item_index,
                evidence_contract_version=commit.breakdown.evidence_contract_version,
                evidence_payload_digest=commit.breakdown.evidence_payload_digest,
                evidence_snapshot_json=evidence_snapshot,
                observations_json=[item.model_dump(mode="json") for item in commit.breakdown.observations],
                interpretations_json=[item.model_dump(mode="json") for item in commit.breakdown.interpretations],
                limitations_json=list(commit.breakdown.limitations),
                created_by_run_id=created_by_run_id,
                created_at=now,
            )
            session.add(breakdown_row)
            await session.flush()

        if commit.direction is not None:
            await self._require_parent_direction(
                session,
                owner_user_id=owner_user_id,
                content_work_id=work.id,
                parent_id=commit.direction.parent_direction_version_id,
            )
            breakdown_ids = list(dict.fromkeys(commit.direction.breakdown_version_ids))
            if breakdown_row is not None and breakdown_row.id not in breakdown_ids:
                breakdown_ids.append(breakdown_row.id)
            breakdown_rows = await self._require_breakdowns(
                session,
                owner_user_id=owner_user_id,
                content_work_id=work.id,
                version_ids=breakdown_ids,
            )
            allowed_claim_refs = {ref for selected_breakdown in breakdown_rows for ref in self._breakdown_claim_refs(selected_breakdown)}
            if any(ref not in allowed_claim_refs for claim in commit.direction.claim_basis if claim.state == "source_observed" for ref in claim.evidence_refs):
                raise ValueError("source_observed claim evidence is not present in the selected BreakdownVersions")
            direction_payload = _version_payload(commit.direction)
            direction_payload["breakdown_version_ids"] = breakdown_ids
            direction_row = PersonalIPDirectionVersionRow(
                id=_id("direction"),
                owner_user_id=owner_user_id,
                content_work_id=work.id,
                version_number=await self._next_version(session, PersonalIPDirectionVersionRow, work.id),
                commit_key=commit.idempotency_key,
                commit_digest=commit_digest,
                parent_direction_version_id=commit.direction.parent_direction_version_id,
                breakdown_version_ids_json=breakdown_ids,
                objective_snapshot_json=dict(work.objective_json),
                direction_json=direction_payload,
                created_by_run_id=created_by_run_id,
                created_at=now,
            )
            session.add(direction_row)
            await session.flush()

        if commit.script is not None:
            script_digest = _digest(_version_payload(commit.script))
            if script_digest not in verified_script_digests:
                raise ValueError("ScriptVersion requires a verified writer-brain truth-boundary receipt")
            await self._require_parent_script(
                session,
                owner_user_id=owner_user_id,
                content_work_id=work.id,
                parent_id=commit.script.parent_script_version_id,
            )
            if direction_row is not None:
                if commit.script.direction_version_id not in {None, direction_row.id}:
                    raise ValueError("a script in the same commit must use the new direction version")
                script_direction = direction_row
            else:
                if not commit.script.direction_version_id:
                    raise ValueError("script direction_version_id is required")
                script_direction = await self._require_direction(
                    session,
                    owner_user_id=owner_user_id,
                    content_work_id=work.id,
                    direction_version_id=commit.script.direction_version_id,
                )
            direction_truth_mode = str((script_direction.direction_json or {}).get("truth_mode") or "")
            if direction_truth_mode != commit.script.story_mode:
                raise ValueError("script story_mode must match its direction truth_mode")
            script_row = PersonalIPScriptVersionRow(
                id=_id("script"),
                owner_user_id=owner_user_id,
                content_work_id=work.id,
                direction_version_id=script_direction.id,
                version_number=await self._next_version(session, PersonalIPScriptVersionRow, work.id),
                commit_key=commit.idempotency_key,
                commit_digest=commit_digest,
                parent_script_version_id=commit.script.parent_script_version_id,
                title=commit.script.title,
                story_mode=commit.script.story_mode,
                script_text=commit.script.script_text,
                claim_basis_json=[item.model_dump(mode="json") for item in commit.script.claim_basis],
                creative_elements_json=[item.model_dump(mode="json") for item in commit.script.creative_elements],
                story_engine_seed_json=(commit.script.story_engine_seed.model_dump(mode="json") if commit.script.story_engine_seed is not None else None),
                locked_story=commit.script.locked_story,
                locked_story_digest=(hashlib.sha256(commit.script.locked_story.encode("utf-8")).hexdigest() if commit.script.locked_story else None),
                production_notes_json=dict(commit.script.production_notes),
                created_by_run_id=created_by_run_id,
                created_at=now,
            )
            session.add(script_row)
            await session.flush()

        work.updated_at = now
        return {
            "replayed": False,
            "breakdown_version": self._breakdown_dict(breakdown_row) if breakdown_row else None,
            "direction_version": self._direction_dict(direction_row) if direction_row else None,
            "script_version": self._script_dict(script_row) if script_row else None,
        }

    async def create(
        self,
        *,
        owner_user_id: str,
        request: ContentWorkCreate,
        created_by_run_id: str | None = None,
        thread_id: str | None = None,
        operation_digest_override: str | None = None,
        verified_evidence_snapshots: Mapping[str, dict[str, Any]] | None = None,
        verified_script_digests: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        payload = request.model_dump(mode="json", exclude={"idempotency_key"})
        operation_digest = operation_digest_override or _digest(payload)
        normalized_thread_id = str(thread_id or "").strip() or None
        if normalized_thread_id is not None and len(normalized_thread_id) > 128:
            raise ValueError("thread_id exceeds the content work identity limit")
        try:
            async with self._sf() as session, session.begin():
                existing = (
                    await session.execute(
                        select(PersonalIPContentWorkRow).where(
                            PersonalIPContentWorkRow.owner_user_id == owner_user_id,
                            PersonalIPContentWorkRow.operation_key == request.idempotency_key,
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if existing.operation_digest != operation_digest:
                        raise ValueError("idempotency_key already records a different content work")
                    if normalized_thread_id is not None and existing.thread_id != normalized_thread_id:
                        raise ValueError("idempotency_key already belongs to a different task")
                    lineage = await self._lineage_in_session(session, existing)
                    lineage["replayed"] = True
                    return lineage
                await self._owned_subject(session, request.subject_id, owner_user_id)
                now = datetime.now(UTC)
                work = PersonalIPContentWorkRow(
                    id=_id("content-work"),
                    owner_user_id=owner_user_id,
                    objective_id=_id("objective"),
                    thread_id=normalized_thread_id,
                    subject_id=request.subject_id,
                    operation_key=request.idempotency_key,
                    operation_digest=operation_digest,
                    title=request.title,
                    entry_route=request.entry_route,
                    objective_json=request.objective.model_dump(mode="json"),
                    status="active",
                    created_by_run_id=created_by_run_id,
                    created_at=now,
                    updated_at=now,
                )
                session.add(work)
                await session.flush()
                if request.breakdown is not None or request.direction is not None or request.script is not None:
                    commit = ContentWorkAppend(
                        idempotency_key=request.idempotency_key,
                        breakdown=request.breakdown,
                        direction=request.direction,
                        script=request.script,
                    )
                    await self._append_in_session(
                        session,
                        work=work,
                        owner_user_id=owner_user_id,
                        commit=commit,
                        commit_digest=operation_digest,
                        created_by_run_id=created_by_run_id,
                        verified_evidence_snapshots=verified_evidence_snapshots or {},
                        verified_script_digests=verified_script_digests,
                    )
                lineage = await self._lineage_in_session(session, work)
                lineage["replayed"] = False
                return lineage
        except IntegrityError:
            async with self._sf() as replay_session:
                existing = (
                    await replay_session.execute(
                        select(PersonalIPContentWorkRow).where(
                            PersonalIPContentWorkRow.owner_user_id == owner_user_id,
                            PersonalIPContentWorkRow.operation_key == request.idempotency_key,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None or existing.operation_digest != operation_digest:
                    raise
                if normalized_thread_id is not None and existing.thread_id != normalized_thread_id:
                    raise ValueError("idempotency_key already belongs to a different task")
                lineage = await self._lineage_in_session(replay_session, existing)
                lineage["replayed"] = True
                return lineage

    async def append(
        self,
        content_work_id: str,
        *,
        owner_user_id: str,
        request: ContentWorkAppend,
        created_by_run_id: str | None = None,
        commit_digest_override: str | None = None,
        verified_evidence_snapshots: Mapping[str, dict[str, Any]] | None = None,
        verified_script_digests: frozenset[str] = frozenset(),
    ) -> dict[str, Any] | None:
        commit_digest = commit_digest_override or _digest(request.model_dump(mode="json", exclude={"idempotency_key"}))
        async with self._sf() as session, session.begin():
            work = await self._owned_work(session, content_work_id, owner_user_id, lock=True)
            if work is None:
                return None
            result = await self._append_in_session(
                session,
                work=work,
                owner_user_id=owner_user_id,
                commit=request,
                commit_digest=commit_digest,
                created_by_run_id=created_by_run_id,
                verified_evidence_snapshots=verified_evidence_snapshots or {},
                verified_script_digests=verified_script_digests,
            )
            return {"content_work_id": work.id, **result}

    async def replay_commit(
        self,
        *,
        owner_user_id: str,
        content_work_id: str | None,
        idempotency_key: str,
        expected_digest: str,
    ) -> dict[str, Any] | None:
        """Return a prior exact commit without repeating model/provider work."""
        async with self._sf() as session:
            if content_work_id is None:
                work = (
                    await session.execute(
                        select(PersonalIPContentWorkRow).where(
                            PersonalIPContentWorkRow.owner_user_id == owner_user_id,
                            PersonalIPContentWorkRow.operation_key == idempotency_key,
                        )
                    )
                ).scalar_one_or_none()
                if work is None:
                    return None
                if work.operation_digest != expected_digest:
                    raise ValueError("idempotency_key already records a different content work")
                lineage = await self._lineage_in_session(session, work)
                lineage["replayed"] = True
                return lineage

            work = await self._owned_work(session, content_work_id, owner_user_id)
            if work is None:
                return None
            breakdown, direction, script = await self._existing_commit_rows(
                session,
                content_work_id=content_work_id,
                commit_key=idempotency_key,
                include_breakdown=True,
                include_direction=True,
                include_script=True,
            )
            rows = [row for row in (breakdown, direction, script) if row is not None]
            if not rows:
                return None
            if any(row.commit_digest != expected_digest for row in rows):
                raise ValueError("idempotency_key already records a different content commit")
            return {
                "content_work_id": content_work_id,
                "replayed": True,
                "breakdown_version": self._breakdown_dict(breakdown) if breakdown else None,
                "direction_version": self._direction_dict(direction) if direction else None,
                "script_version": self._script_dict(script) if script else None,
            }

    async def list(
        self,
        owner_user_id: str,
        *,
        include_archived: bool = False,
        subject_id: str | None = None,
        thread_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPContentWorkRow).where(PersonalIPContentWorkRow.owner_user_id == owner_user_id)
        if not include_archived:
            statement = statement.where(PersonalIPContentWorkRow.status == "active")
        if subject_id is not None:
            statement = statement.where(PersonalIPContentWorkRow.subject_id == subject_id)
        if thread_id is not None:
            statement = statement.where(PersonalIPContentWorkRow.thread_id == thread_id)
        statement = statement.order_by(
            PersonalIPContentWorkRow.updated_at.desc(),
            PersonalIPContentWorkRow.id.desc(),
        ).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars().all()
            return [self._work_dict(row) for row in rows]

    async def has_subject_content(
        self,
        subject_id: str,
        *,
        owner_user_id: str,
    ) -> bool:
        """Return whether an Owner's subject is referenced by any content work."""

        async with self._sf() as session:
            content_work_id = (
                await session.execute(
                    select(PersonalIPContentWorkRow.id)
                    .where(
                        PersonalIPContentWorkRow.owner_user_id == owner_user_id,
                        PersonalIPContentWorkRow.subject_id == subject_id,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            return content_work_id is not None

    async def _lineage_in_session(
        self,
        session: AsyncSession,
        work: PersonalIPContentWorkRow,
    ) -> dict[str, Any]:
        breakdowns = (await session.execute(select(PersonalIPBreakdownVersionRow).where(PersonalIPBreakdownVersionRow.content_work_id == work.id).order_by(PersonalIPBreakdownVersionRow.version_number.asc()))).scalars().all()
        directions = (await session.execute(select(PersonalIPDirectionVersionRow).where(PersonalIPDirectionVersionRow.content_work_id == work.id).order_by(PersonalIPDirectionVersionRow.version_number.asc()))).scalars().all()
        scripts = (await session.execute(select(PersonalIPScriptVersionRow).where(PersonalIPScriptVersionRow.content_work_id == work.id).order_by(PersonalIPScriptVersionRow.version_number.asc()))).scalars().all()
        return {
            "content_work": self._work_dict(work),
            "breakdown_versions": [self._breakdown_dict(row) for row in breakdowns],
            "direction_versions": [self._direction_dict(row) for row in directions],
            "script_versions": [self._script_dict(row) for row in scripts],
        }

    async def get_lineage(
        self,
        content_work_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            work = await self._owned_work(session, content_work_id, owner_user_id)
            if work is None:
                return None
            return await self._lineage_in_session(session, work)

    async def archive(
        self,
        content_work_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        async with self._sf() as session, session.begin():
            work = await self._owned_work(session, content_work_id, owner_user_id, lock=True)
            if work is None:
                return None
            work.status = "archived"
            work.updated_at = datetime.now(UTC)
            await session.flush()
            return self._work_dict(work)


__all__ = ["PersonalIPContentRepository"]
