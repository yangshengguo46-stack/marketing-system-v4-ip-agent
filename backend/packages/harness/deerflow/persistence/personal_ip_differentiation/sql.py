"""Immutable differentiation-thesis and IP-asset observation persistence."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_differentiation.model import (
    PersonalIPAssetObservationRow,
    PersonalIPDifferentiationVersionRow,
)
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.personal_ip.differentiation import (
    DIFFERENTIATION_OBSERVATION_SOURCES,
    DIFFERENTIATION_OBSERVATION_TYPES,
    PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION,
    downstream_observation_types,
    validate_differentiation_snapshot,
    validate_differentiation_transition,
)
from deerflow.personal_ip.strategy_methodology import normalize_evidence_refs
from deerflow.utils.time import coerce_iso

_VERSION_DOCUMENTS = (
    "primary_entity",
    "supporting_entities",
    "decision_context",
    "contrast_field",
    "proprietary_truth",
    "strategic_difference",
    "dramatic_engine",
    "distinctive_encoding",
    "operating_fit",
    "validation",
)
_COVERAGE_STATUSES = {"complete", "partial", "unavailable"}
_OBSERVATION_RESULTS = {"supports", "contradicts", "mixed", "inconclusive"}
_SENSITIVE_KEY_FRAGMENTS = (
    "access_token",
    "refresh_token",
    "password",
    "credential",
    "cookie",
    "authorization",
    "secret",
)


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _digest(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _json_copy(value: Any, *, field: str) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must contain JSON values") from exc


def _reject_sensitive(value: Any, *, path: str = "measures") -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).strip().lower().replace("-", "_")
            if any(fragment in key for fragment in _SENSITIVE_KEY_FRAGMENTS):
                raise ValueError(f"{path} must not contain credential material")
            _reject_sensitive(nested, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _reject_sensitive(nested, path=f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if lowered.startswith("bearer ") or lowered.startswith("eyj"):
            raise ValueError(f"{path} must not contain credential material")


class PersonalIPDifferentiationRepository:
    """Append-only differentiation truth and observed IP-asset effects."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _version_to_dict(row: PersonalIPDifferentiationVersionRow) -> dict[str, Any]:
        data = row.to_dict()
        for field in _VERSION_DOCUMENTS:
            data[field] = data.pop(f"{field}_json")
        data["evidence_refs"] = data.pop("evidence_refs_json") or []
        data["validation_summary"] = data.pop("validation_summary_json") or {}
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = coerce_iso(data["created_at"])
        return data

    @staticmethod
    def _observation_to_dict(row: PersonalIPAssetObservationRow) -> dict[str, Any]:
        data = row.to_dict()
        data["measures"] = data.pop("measures_json") or {}
        data["evidence_refs"] = data.pop("evidence_refs_json") or []
        for field in ("observed_at", "created_at"):
            if isinstance(data.get(field), datetime):
                data[field] = coerce_iso(data[field])
        return data

    @staticmethod
    async def _require_subject(
        session: AsyncSession,
        *,
        subject_id: str,
        owner_user_id: str,
    ) -> PersonalIPSubjectRow:
        subject = await session.get(PersonalIPSubjectRow, subject_id)
        if subject is None or subject.owner_user_id != owner_user_id or subject.status != "active":
            raise ValueError("Personal-IP subject not found")
        return subject

    @staticmethod
    def _user_payload(data: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "subject_id": data["subject_id"],
            "thesis_key": data["thesis_key"],
            "status": data["status"],
            **{field: data[field] for field in _VERSION_DOCUMENTS},
            "evidence_refs": data["evidence_refs"],
        }

    async def _validation_summary(
        self,
        session: AsyncSession,
        *,
        owner_user_id: str,
        subject_id: str,
        thesis_key: str,
    ) -> dict[str, Any]:
        rows = (
            await session.execute(
                select(PersonalIPAssetObservationRow)
                .where(
                    PersonalIPAssetObservationRow.owner_user_id == owner_user_id,
                    PersonalIPAssetObservationRow.subject_id == subject_id,
                    PersonalIPAssetObservationRow.thesis_key == thesis_key,
                )
                .order_by(
                    PersonalIPAssetObservationRow.observed_at.asc(),
                    PersonalIPAssetObservationRow.id.asc(),
                )
            )
        ).scalars()
        complete = [row for row in rows if row.coverage_status == "complete"]
        supportive = [row for row in complete if isinstance(row.measures_json, Mapping) and row.measures_json.get("result") == "supports"]
        contradictory = [row for row in complete if isinstance(row.measures_json, Mapping) and row.measures_json.get("result") == "contradicts"]
        types = sorted({row.observation_type for row in supportive})
        latest = max((row.observed_at for row in complete), default=None)
        return {
            "complete_observation_count": len(complete),
            "supportive_observation_count": len(supportive),
            "contradictory_observation_count": len(contradictory),
            "supportive_observation_types": types,
            "has_downstream_outcome": bool(set(types) & downstream_observation_types()),
            "latest_observed_at": coerce_iso(latest) if latest is not None else None,
        }

    @staticmethod
    def _enforce_observation_gate(*, status: str, summary: Mapping[str, Any]) -> None:
        count = int(summary.get("supportive_observation_count") or 0)
        types = {str(item) for item in summary.get("supportive_observation_types") or []}
        if status == "provisionally_adopted" and count < 1:
            raise ValueError("provisionally_adopted requires at least one complete supportive observation")
        if status == "validated":
            if count < 3:
                raise ValueError("validated requires at least three complete supportive observations")
            if len(types) < 2:
                raise ValueError("validated requires at least two distinct observation types")
            if not bool(summary.get("has_downstream_outcome")):
                raise ValueError("validated requires an intent, adoption, conversion or economic observation")

    async def create_version(
        self,
        *,
        owner_user_id: str,
        operation_key: str,
        subject_id: str,
        thesis_key: str,
        status: str,
        primary_entity: Mapping[str, Any] | None = None,
        supporting_entities: Sequence[Mapping[str, Any]] | None = None,
        decision_context: Mapping[str, Any] | None = None,
        contrast_field: Mapping[str, Any] | None = None,
        proprietary_truth: Mapping[str, Any] | None = None,
        strategic_difference: Mapping[str, Any] | None = None,
        dramatic_engine: Mapping[str, Any] | None = None,
        distinctive_encoding: Mapping[str, Any] | None = None,
        operating_fit: Mapping[str, Any] | None = None,
        validation: Mapping[str, Any] | None = None,
        evidence_refs: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        operation = _clean_required(operation_key, field="operation_key", limit=256)
        subject_key = _clean_required(subject_id, field="subject_id", limit=64)
        lineage = _clean_required(thesis_key, field="thesis_key", limit=128)
        status_key = str(status or "").strip()

        async with self._sf() as session:
            existing = (
                await session.execute(
                    select(PersonalIPDifferentiationVersionRow).where(
                        PersonalIPDifferentiationVersionRow.owner_user_id == owner,
                        PersonalIPDifferentiationVersionRow.operation_key == operation,
                    )
                )
            ).scalar_one_or_none()

            await self._require_subject(session, subject_id=subject_key, owner_user_id=owner)
            if existing is not None:
                existing_data = self._version_to_dict(existing)
                replay_payload = {
                    "subject_id": subject_key,
                    "thesis_key": lineage,
                    "status": status_key,
                }
                for field in _VERSION_DOCUMENTS:
                    requested = locals()[field]
                    replay_payload[field] = _json_copy(
                        requested if requested is not None else existing_data[field],
                        field=field,
                    )
                replay_payload["evidence_refs"] = normalize_evidence_refs(
                    evidence_refs if evidence_refs is not None else existing_data["evidence_refs"],
                    required=True,
                )
                validate_differentiation_snapshot(
                    status=status_key,
                    evidence_refs=replay_payload["evidence_refs"],
                    **{field: replay_payload[field] for field in _VERSION_DOCUMENTS},
                )
                if self._user_payload(existing_data) != replay_payload:
                    raise ValueError("operation_key already records a different differentiation version")
                return existing_data

            latest = (
                await session.execute(
                    select(PersonalIPDifferentiationVersionRow)
                    .where(
                        PersonalIPDifferentiationVersionRow.owner_user_id == owner,
                        PersonalIPDifferentiationVersionRow.subject_id == subject_key,
                    )
                    .order_by(PersonalIPDifferentiationVersionRow.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            latest_data = self._version_to_dict(latest) if latest is not None else {}
            same_lineage = latest is not None and latest.thesis_key == lineage
            if latest is not None and not same_lineage and status_key != "candidate":
                raise ValueError("a new thesis_key must restart as candidate")
            target_status = validate_differentiation_transition(latest.status if same_lineage else None, status_key)

            merged: dict[str, Any] = {}
            for field in _VERSION_DOCUMENTS:
                requested = locals()[field]
                if requested is not None:
                    merged[field] = _json_copy(requested, field=field)
                elif same_lineage:
                    merged[field] = _json_copy(latest_data.get(field), field=field)
                else:
                    merged[field] = [] if field == "supporting_entities" else {}
            merged_evidence = normalize_evidence_refs(
                evidence_refs if evidence_refs is not None else (latest_data.get("evidence_refs") if same_lineage else []),
                required=True,
            )
            validate_differentiation_snapshot(
                status=target_status,
                evidence_refs=merged_evidence,
                **merged,
            )
            summary = await self._validation_summary(
                session,
                owner_user_id=owner,
                subject_id=subject_key,
                thesis_key=lineage,
            )
            self._enforce_observation_gate(status=target_status, summary=summary)
            user_payload = {
                "subject_id": subject_key,
                "thesis_key": lineage,
                "status": target_status,
                **merged,
                "evidence_refs": merged_evidence,
            }

            sealed_payload = {
                "method_version": PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION,
                **user_payload,
                "validation_summary": summary,
            }
            row = PersonalIPDifferentiationVersionRow(
                id=f"difference-{uuid.uuid4().hex}",
                owner_user_id=owner,
                operation_key=operation,
                subject_id=subject_key,
                version=(latest.version + 1) if latest is not None else 1,
                thesis_key=lineage,
                status=target_status,
                method_version=PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION,
                primary_entity_json=merged["primary_entity"],
                supporting_entities_json=merged["supporting_entities"],
                decision_context_json=merged["decision_context"],
                contrast_field_json=merged["contrast_field"],
                proprietary_truth_json=merged["proprietary_truth"],
                strategic_difference_json=merged["strategic_difference"],
                dramatic_engine_json=merged["dramatic_engine"],
                distinctive_encoding_json=merged["distinctive_encoding"],
                operating_fit_json=merged["operating_fit"],
                validation_json=merged["validation"],
                evidence_refs_json=merged_evidence,
                validation_summary_json=summary,
                content_digest=_digest(sealed_payload),
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._version_to_dict(row)

    async def record_observation(
        self,
        *,
        owner_user_id: str,
        operation_key: str,
        subject_id: str,
        differentiation_version_id: str,
        observation_type: str,
        source: str,
        observed_at: datetime,
        coverage_status: str,
        measures: Mapping[str, Any],
        evidence_refs: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        operation = _clean_required(operation_key, field="operation_key", limit=256)
        subject_key = _clean_required(subject_id, field="subject_id", limit=64)
        version_key = _clean_required(
            differentiation_version_id,
            field="differentiation_version_id",
            limit=64,
        )
        type_key = str(observation_type or "").strip()
        source_key = str(source or "").strip()
        coverage_key = str(coverage_status or "").strip()
        if type_key not in DIFFERENTIATION_OBSERVATION_TYPES:
            raise ValueError("unsupported differentiation observation_type")
        if source_key not in DIFFERENTIATION_OBSERVATION_SOURCES:
            raise ValueError("unsupported differentiation observation source")
        if coverage_key not in _COVERAGE_STATUSES:
            raise ValueError("coverage_status must be complete, partial or unavailable")
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            raise ValueError("observed_at must be a timezone-aware datetime")
        normalized_measures = _json_copy(dict(measures), field="measures")
        _reject_sensitive(normalized_measures)
        result_key = str(normalized_measures.get("result") or "").strip()
        if result_key not in _OBSERVATION_RESULTS:
            raise ValueError("measures.result must be supports, contradicts, mixed or inconclusive")
        normalized_measures["result"] = result_key
        normalized_evidence = normalize_evidence_refs(evidence_refs, required=True)

        async with self._sf() as session:
            existing = (
                await session.execute(
                    select(PersonalIPAssetObservationRow).where(
                        PersonalIPAssetObservationRow.owner_user_id == owner,
                        PersonalIPAssetObservationRow.operation_key == operation,
                    )
                )
            ).scalar_one_or_none()
            version = await session.get(PersonalIPDifferentiationVersionRow, version_key)
            if version is None or version.owner_user_id != owner or version.subject_id != subject_key:
                raise ValueError("Personal-IP differentiation version not found")
            payload = {
                "subject_id": subject_key,
                "differentiation_version_id": version_key,
                "thesis_key": version.thesis_key,
                "observation_type": type_key,
                "source": source_key,
                "observed_at": coerce_iso(observed_at),
                "coverage_status": coverage_key,
                "measures": normalized_measures,
                "evidence_refs": normalized_evidence,
            }
            evidence_digest = _digest(payload)
            if existing is not None:
                existing_data = self._observation_to_dict(existing)
                if existing.evidence_digest != evidence_digest:
                    raise ValueError("operation_key already records a different IP-asset observation")
                return existing_data
            row = PersonalIPAssetObservationRow(
                id=f"ip-observation-{uuid.uuid4().hex}",
                owner_user_id=owner,
                operation_key=operation,
                subject_id=subject_key,
                differentiation_version_id=version_key,
                thesis_key=version.thesis_key,
                observation_type=type_key,
                source=source_key,
                observed_at=observed_at.astimezone(UTC),
                coverage_status=coverage_key,
                measures_json=normalized_measures,
                evidence_refs_json=normalized_evidence,
                evidence_digest=evidence_digest,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._observation_to_dict(row)

    async def get_latest(
        self,
        subject_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        statement = (
            select(PersonalIPDifferentiationVersionRow)
            .where(
                PersonalIPDifferentiationVersionRow.owner_user_id == owner_user_id,
                PersonalIPDifferentiationVersionRow.subject_id == subject_id,
            )
            .order_by(PersonalIPDifferentiationVersionRow.version.desc())
            .limit(1)
        )
        async with self._sf() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
            return self._version_to_dict(row) if row is not None else None

    async def get_version(
        self,
        version_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPDifferentiationVersionRow, version_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._version_to_dict(row)

    async def list_versions(
        self,
        owner_user_id: str,
        *,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPDifferentiationVersionRow).where(PersonalIPDifferentiationVersionRow.owner_user_id == owner_user_id)
        if subject_id is not None:
            statement = statement.where(PersonalIPDifferentiationVersionRow.subject_id == subject_id)
        statement = statement.order_by(
            PersonalIPDifferentiationVersionRow.created_at.desc(),
            PersonalIPDifferentiationVersionRow.id.desc(),
        ).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._version_to_dict(row) for row in rows]

    async def list_observations(
        self,
        owner_user_id: str,
        *,
        subject_id: str | None = None,
        thesis_key: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPAssetObservationRow).where(PersonalIPAssetObservationRow.owner_user_id == owner_user_id)
        if subject_id is not None:
            statement = statement.where(PersonalIPAssetObservationRow.subject_id == subject_id)
        if thesis_key is not None:
            statement = statement.where(PersonalIPAssetObservationRow.thesis_key == thesis_key)
        statement = statement.order_by(
            PersonalIPAssetObservationRow.observed_at.desc(),
            PersonalIPAssetObservationRow.id.desc(),
        ).limit(max(1, min(int(limit), 1000)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._observation_to_dict(row) for row in rows]
