"""Policy-gated cross-sample evidence promotion and export."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_evidence_promotions.model import PersonalIPEvidencePromotionRow
from deerflow.persistence.personal_ip_retrospectives.model import PersonalIPRetrospectiveRow
from deerflow.utils.time import coerce_iso

_EVIDENCE_TYPES = {"audience_pattern", "content_pattern", "platform_pattern", "training_cohort"}


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _normalized_ids(values: Sequence[str], *, minimum: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean_required(raw, field="retrospective_ids", limit=64)
        if value not in seen:
            seen.add(value)
            result.append(value)
    if len(result) < minimum or len(result) > 100:
        raise ValueError(f"retrospective_ids must contain {minimum} to 100 unique ids")
    return sorted(result)


def _utc(value: datetime | None = None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _digest(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PersonalIPEvidencePromotionRepository:
    """Automatically promote claims backed by independent measured samples."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPEvidencePromotionRow) -> dict[str, Any]:
        data = row.to_dict()
        data["retrospective_ids"] = data.pop("retrospective_ids_json") or []
        data["evidence_summary"] = data.pop("evidence_summary_json") or {}
        data["decisions"] = data.pop("decisions_json") or []
        for field in ("decided_at", "created_at", "updated_at"):
            if isinstance(data.get(field), datetime):
                data[field] = coerce_iso(data[field])
        return data

    @staticmethod
    def _same_proposal(
        row: PersonalIPEvidencePromotionRow,
        *,
        evidence_type: str,
        claim: str,
        retrospective_ids: list[str],
        minimum_support: int,
    ) -> bool:
        return row.evidence_type == evidence_type and row.claim == claim and row.retrospective_ids_json == retrospective_ids and row.minimum_support == minimum_support

    async def propose(
        self,
        *,
        owner_user_id: str,
        proposal_key: str,
        evidence_type: str,
        claim: str,
        retrospective_ids: Sequence[str],
        minimum_support: int = 3,
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        proposal = _clean_required(proposal_key, field="proposal_key", limit=256)
        type_key = str(evidence_type or "").strip()
        if type_key not in _EVIDENCE_TYPES:
            raise ValueError("unsupported evidence promotion type")
        claim_text = _clean_required(claim, field="claim", limit=2000)
        support_threshold = int(minimum_support)
        if support_threshold < 3 or support_threshold > 100:
            raise ValueError("minimum_support must be between 3 and 100")
        evidence_ids = _normalized_ids(retrospective_ids, minimum=support_threshold)

        async with self._sf() as session:
            existing_statement = select(PersonalIPEvidencePromotionRow).where(
                PersonalIPEvidencePromotionRow.owner_user_id == owner,
                PersonalIPEvidencePromotionRow.proposal_key == proposal,
            )
            existing = (await session.execute(existing_statement)).scalar_one_or_none()
            if existing is not None:
                if self._same_proposal(
                    existing,
                    evidence_type=type_key,
                    claim=claim_text,
                    retrospective_ids=evidence_ids,
                    minimum_support=support_threshold,
                ):
                    return self._to_dict(existing)
                raise ValueError("proposal_key already records different promotion evidence")

            statement = select(PersonalIPRetrospectiveRow).where(
                PersonalIPRetrospectiveRow.id.in_(evidence_ids),
                PersonalIPRetrospectiveRow.owner_user_id == owner,
            )
            retrospectives = list((await session.execute(statement)).scalars())
            if {row.id for row in retrospectives} != set(evidence_ids):
                raise ValueError("Personal-IP retrospective not found")
            measured_publish_ids = {row.publish_receipt_id for row in retrospectives if row.status == "measured"}
            if len(measured_publish_ids) < support_threshold:
                raise ValueError(f"promotion requires at least {support_threshold} independent measured retrospectives")
            if any(row.status != "measured" for row in retrospectives):
                raise ValueError("promotion evidence must contain only completely measured retrospectives")

            summary = {
                "retrospective_count": len(retrospectives),
                "independent_publish_count": len({row.publish_receipt_id for row in retrospectives}),
                "independent_measured_support": len(measured_publish_ids),
                "measured_count": sum(row.status == "measured" for row in retrospectives),
                "partial_count": sum(row.status == "partial" for row in retrospectives),
                "account_count": len({row.account_id for row in retrospectives}),
                "platforms": sorted({row.platform for row in retrospectives}),
                "horizons": sorted({row.horizon for row in retrospectives}),
                "model_versions": sorted({row.model_version for row in retrospectives}),
                "algorithm_versions": sorted({row.algorithm_version for row in retrospectives}),
                "unscored_count": sum(row.comparison_state == "unscored" for row in retrospectives),
            }
            evidence_snapshot = {
                "evidence_type": type_key,
                "claim": claim_text,
                "minimum_support": support_threshold,
                "sources": [
                    {
                        "retrospective_id": row.id,
                        "publish_receipt_id": row.publish_receipt_id,
                        "evidence_digest": row.evidence_digest,
                    }
                    for row in sorted(retrospectives, key=lambda item: item.id)
                ],
                "summary": summary,
            }
            evidence_digest = _digest(evidence_snapshot)
            now = datetime.now(UTC)
            policy_decision = {
                "decision_key": f"evidence-policy:{evidence_digest}",
                "decision": "approved",
                "reviewer_source": "cross_sample_evidence_policy",
                "rationale": (f"Automatically promoted after {len(measured_publish_ids)} independent measured publications satisfied the minimum support of {support_threshold}."),
                "occurred_at": coerce_iso(now),
            }
            row = PersonalIPEvidencePromotionRow(
                id=f"promotion-{uuid.uuid4().hex}",
                owner_user_id=owner,
                proposal_key=proposal,
                evidence_type=type_key,
                claim=claim_text,
                retrospective_ids_json=evidence_ids,
                evidence_summary_json=summary,
                evidence_digest=evidence_digest,
                minimum_support=support_threshold,
                status="approved",
                decisions_json=[policy_decision],
                decided_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def get(self, promotion_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPEvidencePromotionRow, promotion_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    async def list(
        self,
        owner_user_id: str,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPEvidencePromotionRow).where(PersonalIPEvidencePromotionRow.owner_user_id == owner_user_id)
        if status is not None:
            statement = statement.where(PersonalIPEvidencePromotionRow.status == status)
        statement = statement.order_by(PersonalIPEvidencePromotionRow.updated_at.desc(), PersonalIPEvidencePromotionRow.id.desc()).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._to_dict(row) for row in rows]

    async def export_approved(self, promotion_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPEvidencePromotionRow, promotion_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            if row.status != "approved":
                raise ValueError("only approved evidence promotions can be exported")
            statement = select(PersonalIPRetrospectiveRow).where(
                PersonalIPRetrospectiveRow.id.in_(row.retrospective_ids_json or []),
                PersonalIPRetrospectiveRow.owner_user_id == owner_user_id,
            )
            retrospectives = list((await session.execute(statement)).scalars())
            source_examples = [
                {
                    "retrospective_id": retrospective.id,
                    "evidence_digest": retrospective.evidence_digest,
                    "preflight_id": retrospective.preflight_id,
                    "publish_receipt_id": retrospective.publish_receipt_id,
                    "account_id": retrospective.account_id,
                    "platform": retrospective.platform,
                    "horizon": retrospective.horizon,
                    "status": retrospective.status,
                    "comparison_state": retrospective.comparison_state,
                    "prediction": retrospective.prediction_json,
                    "outcome": retrospective.outcome_json,
                    "training_eligibility": retrospective.training_eligibility_json,
                }
                for retrospective in sorted(retrospectives, key=lambda item: item.id)
            ]
            return {
                "contract_version": "personal-ip-approved-evidence-v1",
                "promotion": {
                    "id": row.id,
                    "evidence_type": row.evidence_type,
                    "claim": row.claim,
                    "evidence_digest": row.evidence_digest,
                    "minimum_support": row.minimum_support,
                    "approved_at": coerce_iso(_utc(row.decided_at)),
                },
                "source_examples": source_examples,
            }
