"""Read-only compatibility access to historical evidence-promotion rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_evidence_promotions.model import PersonalIPEvidencePromotionRow
from deerflow.persistence.personal_ip_retrospectives.model import PersonalIPRetrospectiveRow
from deerflow.utils.time import coerce_iso


def _utc(value: datetime | None = None) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


class PersonalIPEvidencePromotionRepository:
    """Read or export rows created before automatic promotion was retired."""

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
