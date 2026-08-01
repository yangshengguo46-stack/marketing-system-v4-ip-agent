"""Persistence for immutable subject-level Personal-IP operating strategies."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_brand.model import PersonalIPStrategyVersionRow
from deerflow.persistence.personal_ip_differentiation.model import PersonalIPDifferentiationVersionRow
from deerflow.persistence.personal_ip_subjects.model import PersonalIPSubjectRow
from deerflow.personal_ip.strategy_methodology import (
    PERSONAL_IP_STRATEGY_METHOD_VERSION,
    normalize_evidence_refs,
    validate_strategy_snapshot,
    validate_strategy_transition,
)
from deerflow.utils.time import coerce_iso


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _digest(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PersonalIPBrandRepository:
    """Append and read the one subject-level operating-strategy ledger."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _strategy_to_dict(row: PersonalIPStrategyVersionRow) -> dict[str, Any]:
        data = row.to_dict()
        data["person_model"] = data.pop("person_model_json") or {}
        data["business_model"] = data.pop("business_model_json") or {}
        data["benchmark_research"] = data.pop("benchmark_research_json") or {}
        data["positioning_candidates"] = data.pop("positioning_candidates_json") or []
        data["launch_package"] = data.pop("launch_package_json") or {}
        data["validation"] = data.pop("validation_json") or {}
        data["evidence_refs"] = data.pop("evidence_refs_json") or []
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = coerce_iso(data["created_at"])
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

    async def create_strategy_version(
        self,
        *,
        owner_user_id: str,
        operation_key: str,
        subject_id: str,
        stage: str,
        mode: str = "monetization_first",
        person_model: dict[str, Any] | None = None,
        business_model: dict[str, Any] | None = None,
        benchmark_research: dict[str, Any] | None = None,
        positioning_candidates: list[dict[str, Any]] | None = None,
        launch_package: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
        evidence_refs: list[dict[str, Any]] | None = None,
        differentiation_version_id: str | None = None,
    ) -> dict[str, Any]:
        """Append one immutable strategy snapshot, merging omitted documents."""

        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        operation = _clean_required(operation_key, field="operation_key", limit=256)
        subject_key = _clean_required(subject_id, field="subject_id", limit=64)
        mode_key = str(mode or "").strip()

        async with self._sf() as session:
            existing = (
                await session.execute(
                    select(PersonalIPStrategyVersionRow).where(
                        PersonalIPStrategyVersionRow.owner_user_id == owner,
                        PersonalIPStrategyVersionRow.operation_key == operation,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing_data = self._strategy_to_dict(existing)
                requested = {
                    "person_model": person_model,
                    "business_model": business_model,
                    "benchmark_research": benchmark_research,
                    "positioning_candidates": positioning_candidates,
                    "launch_package": launch_package,
                    "validation": validation,
                }
                requested_differentiation_id = (
                    _clean_required(
                        differentiation_version_id,
                        field="differentiation_version_id",
                        limit=64,
                    )
                    if differentiation_version_id is not None
                    else existing_data.get("differentiation_version_id")
                )
                normalized_evidence = normalize_evidence_refs(evidence_refs) if evidence_refs is not None else existing_data["evidence_refs"]
                if (
                    existing.stage != str(stage or "").strip()
                    or existing.mode != mode_key
                    or any(value is not None and existing_data[field] != value for field, value in requested.items())
                    or existing_data.get("differentiation_version_id") != requested_differentiation_id
                    or existing_data["evidence_refs"] != normalized_evidence
                ):
                    raise ValueError("operation_key already records a different Personal-IP strategy version")
                return existing_data

            subject = await self._require_subject(
                session,
                subject_id=subject_key,
                owner_user_id=owner,
            )
            latest = (
                await session.execute(
                    select(PersonalIPStrategyVersionRow)
                    .where(
                        PersonalIPStrategyVersionRow.owner_user_id == owner,
                        PersonalIPStrategyVersionRow.subject_id == subject_key,
                    )
                    .order_by(PersonalIPStrategyVersionRow.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            target_stage = validate_strategy_transition(latest.stage if latest else None, stage)
            latest_data = self._strategy_to_dict(latest) if latest is not None else {}
            merged_person = dict(person_model) if person_model is not None else dict(latest_data.get("person_model") or {})
            merged_business = dict(business_model) if business_model is not None else dict(latest_data.get("business_model") or {})
            merged_benchmarks = dict(benchmark_research) if benchmark_research is not None else dict(latest_data.get("benchmark_research") or {})
            merged_candidates = list(positioning_candidates) if positioning_candidates is not None else list(latest_data.get("positioning_candidates") or [])
            merged_launch = dict(launch_package) if launch_package is not None else dict(latest_data.get("launch_package") or {})
            merged_validation = dict(validation) if validation is not None else dict(latest_data.get("validation") or {})
            merged_evidence = normalize_evidence_refs(
                evidence_refs if evidence_refs is not None else list(latest_data.get("evidence_refs") or []),
            )
            merged_differentiation_id = (
                _clean_required(
                    differentiation_version_id,
                    field="differentiation_version_id",
                    limit=64,
                )
                if differentiation_version_id is not None
                else latest_data.get("differentiation_version_id")
            )
            if merged_differentiation_id:
                differentiation = await session.get(
                    PersonalIPDifferentiationVersionRow,
                    merged_differentiation_id,
                )
                if differentiation is None or differentiation.owner_user_id != owner or differentiation.subject_id != subject_key:
                    raise ValueError("Personal-IP differentiation version not found")
            validate_strategy_snapshot(
                stage=target_stage,
                mode=mode_key,
                person_model=merged_person,
                business_model=merged_business,
                benchmark_research=merged_benchmarks,
                positioning_candidates=merged_candidates,
                launch_package=merged_launch,
                validation=merged_validation,
                evidence_refs=merged_evidence,
                subject_type=subject.subject_type,
            )
            snapshot = {
                "method_version": PERSONAL_IP_STRATEGY_METHOD_VERSION,
                "subject_id": subject_key,
                "stage": target_stage,
                "mode": mode_key,
                "person_model": merged_person,
                "business_model": merged_business,
                "benchmark_research": merged_benchmarks,
                "positioning_candidates": merged_candidates,
                "launch_package": merged_launch,
                "validation": merged_validation,
                "evidence_refs": merged_evidence,
                "differentiation_version_id": merged_differentiation_id,
            }
            row = PersonalIPStrategyVersionRow(
                id=f"strategy-{uuid.uuid4().hex}",
                owner_user_id=owner,
                operation_key=operation,
                subject_id=subject_key,
                version=(latest.version + 1) if latest is not None else 1,
                stage=target_stage,
                mode=mode_key,
                method_version=PERSONAL_IP_STRATEGY_METHOD_VERSION,
                differentiation_version_id=merged_differentiation_id,
                person_model_json=merged_person,
                business_model_json=merged_business,
                benchmark_research_json=merged_benchmarks,
                positioning_candidates_json=merged_candidates,
                launch_package_json=merged_launch,
                validation_json=merged_validation,
                evidence_refs_json=merged_evidence,
                content_digest=_digest(snapshot),
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._strategy_to_dict(row)

    async def get_latest_strategy(
        self,
        subject_id: str,
        *,
        owner_user_id: str,
    ) -> dict[str, Any] | None:
        statement = (
            select(PersonalIPStrategyVersionRow)
            .where(
                PersonalIPStrategyVersionRow.owner_user_id == owner_user_id,
                PersonalIPStrategyVersionRow.subject_id == subject_id,
            )
            .order_by(PersonalIPStrategyVersionRow.version.desc())
            .limit(1)
        )
        async with self._sf() as session:
            row = (await session.execute(statement)).scalar_one_or_none()
            return self._strategy_to_dict(row) if row is not None else None

    async def list_strategies(
        self,
        owner_user_id: str,
        *,
        subject_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPStrategyVersionRow).where(PersonalIPStrategyVersionRow.owner_user_id == owner_user_id)
        if subject_id is not None:
            statement = statement.where(PersonalIPStrategyVersionRow.subject_id == subject_id)
        statement = statement.order_by(
            PersonalIPStrategyVersionRow.created_at.desc(),
            PersonalIPStrategyVersionRow.id.desc(),
        ).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._strategy_to_dict(row) for row in rows]
