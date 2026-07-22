"""Repository for immutable Personal-IP prediction-to-outcome evidence."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_metrics.model import PersonalIPMetricObservationRow
from deerflow.persistence.personal_ip_preflights.model import PersonalIPPreflightRow
from deerflow.persistence.personal_ip_publish_receipts.model import PersonalIPPublishReceiptRow
from deerflow.persistence.personal_ip_retrospectives.model import PersonalIPRetrospectiveRow
from deerflow.utils.time import coerce_iso


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _normalized_ids(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _clean_required(raw, field="metric_observation_ids", limit=64)
        if value not in seen:
            seen.add(value)
            result.append(value)
    if not result or len(result) > 100:
        raise ValueError("metric_observation_ids must contain 1 to 100 ids")
    return sorted(result)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _digest(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PersonalIPRetrospectiveRepository:
    """Seal facts for review without auto-promoting them into model training."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPRetrospectiveRow) -> dict[str, Any]:
        data = row.to_dict()
        data["metric_observation_ids"] = data.pop("metric_observation_ids_json") or []
        data["prediction"] = data.pop("prediction_json") or {}
        data["outcome"] = data.pop("outcome_json") or {}
        data["training_eligibility"] = data.pop("training_eligibility_json") or {}
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = coerce_iso(data["created_at"])
        return data

    @staticmethod
    def _same_evidence(
        row: PersonalIPRetrospectiveRow,
        *,
        publish_receipt_id: str,
        horizon: str,
        metric_observation_ids: list[str],
    ) -> bool:
        return row.publish_receipt_id == publish_receipt_id and row.horizon == horizon and row.metric_observation_ids_json == metric_observation_ids

    async def seal(
        self,
        *,
        owner_user_id: str,
        review_key: str,
        publish_receipt_id: str,
        horizon: str,
        metric_observation_ids: Sequence[str],
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        review = _clean_required(review_key, field="review_key", limit=256)
        publish_id = _clean_required(publish_receipt_id, field="publish_receipt_id", limit=64)
        horizon_key = _clean_required(horizon, field="horizon", limit=32)

        async with self._sf() as session:
            receipt = await session.get(PersonalIPPublishReceiptRow, publish_id)
            if receipt is None or receipt.owner_user_id != owner:
                raise ValueError("Personal-IP publish receipt not found")
            if receipt.status != "published":
                raise ValueError("publish receipt must be published before retrospective review")
            if receipt.preflight_id is None:
                raise ValueError("publish receipt has no preflight evidence")
            preflight = await session.get(PersonalIPPreflightRow, receipt.preflight_id)
            if preflight is None or preflight.owner_user_id != owner:
                raise ValueError("Personal-IP preflight not found")

            observation_ids = _normalized_ids(metric_observation_ids)
            existing_statement = select(PersonalIPRetrospectiveRow).where(
                PersonalIPRetrospectiveRow.owner_user_id == owner,
                or_(
                    PersonalIPRetrospectiveRow.review_key == review,
                    ((PersonalIPRetrospectiveRow.publish_receipt_id == publish_id) & (PersonalIPRetrospectiveRow.horizon == horizon_key)),
                ),
            )
            existing = (await session.execute(existing_statement)).scalars().first()
            if existing is not None:
                if self._same_evidence(
                    existing,
                    publish_receipt_id=publish_id,
                    horizon=horizon_key,
                    metric_observation_ids=observation_ids,
                ):
                    return self._to_dict(existing)
                raise ValueError("review key or publish horizon already seals different evidence")

            observations_statement = select(PersonalIPMetricObservationRow).where(
                PersonalIPMetricObservationRow.id.in_(observation_ids),
                PersonalIPMetricObservationRow.owner_user_id == owner,
            )
            observations = list((await session.execute(observations_statement)).scalars())
            if {row.id for row in observations} != set(observation_ids):
                raise ValueError("Personal-IP metric observation not found")
            for observation in observations:
                if observation.receipt_id != publish_id:
                    raise ValueError("metric observation belongs to a different publish receipt")
                if observation.account_id != receipt.account_id or observation.scope != "post":
                    raise ValueError("retrospective metrics must be post observations for the published account")

            selected_variant_id = str((receipt.request_json or {}).get("variant_id") or "").strip()
            if not selected_variant_id:
                raise ValueError("publish receipt does not identify the selected preflight variant")
            variants = list((preflight.provider_receipt_json or {}).get("variants") or [])
            selected_variant = next((variant for variant in variants if str(variant.get("variant_id")) == selected_variant_id), None)
            if selected_variant is None:
                raise ValueError("selected publish variant is absent from the preflight receipt")

            ordered_observations = sorted(observations, key=lambda row: (_utc(row.observed_at), row.id))
            latest_metrics: dict[str, int | float] = {}
            outcome_observations: list[dict[str, Any]] = []
            is_partial = False
            for observation in ordered_observations:
                metrics = dict(observation.metrics_json or {})
                latest_metrics.update(metrics)
                is_partial = is_partial or observation.status != "observed"
                outcome_observations.append(
                    {
                        "id": observation.id,
                        "metric_mode": observation.metric_mode,
                        "source": observation.source,
                        "status": observation.status,
                        "observed_at": coerce_iso(_utc(observation.observed_at)),
                        "metrics": metrics,
                        "coverage": dict(observation.coverage_json or {}),
                    }
                )
            prediction = {
                "provider": preflight.provider,
                "model_version": preflight.model_version,
                "algorithm_version": preflight.algorithm_version,
                "request_digest": preflight.request_digest,
                "variant": dict(selected_variant),
            }
            outcome = {
                "horizon": horizon_key,
                "latest_metrics": dict(sorted(latest_metrics.items())),
                "observations": outcome_observations,
            }
            comparison_state = "scored" if selected_variant.get("match_score") is not None else "unscored"
            status = "partial" if is_partial else "measured"
            reasons: list[str] = []
            if is_partial:
                reasons.append("partial_metric_coverage")
            if comparison_state == "unscored":
                reasons.append("prediction_has_no_calibrated_score")
            training_eligibility = {
                "status": "insufficient_evidence" if is_partial else "eligible_for_policy_evaluation",
                "reasons": reasons,
            }
            evidence = {
                "preflight_id": preflight.id,
                "publish_receipt_id": receipt.id,
                "account_id": receipt.account_id,
                "horizon": horizon_key,
                "prediction": prediction,
                "outcome": outcome,
            }
            row = PersonalIPRetrospectiveRow(
                id=f"retro-{uuid.uuid4().hex}",
                owner_user_id=owner,
                review_key=review,
                preflight_id=preflight.id,
                publish_receipt_id=receipt.id,
                account_id=receipt.account_id,
                subject_id=receipt.subject_id,
                platform=receipt.platform,
                horizon=horizon_key,
                selected_variant_id=selected_variant_id,
                provider=preflight.provider,
                model_version=preflight.model_version,
                algorithm_version=preflight.algorithm_version,
                metric_observation_ids_json=observation_ids,
                prediction_json=prediction,
                outcome_json=outcome,
                training_eligibility_json=training_eligibility,
                evidence_digest=_digest(evidence),
                status=status,
                comparison_state=comparison_state,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def get(self, retrospective_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPRetrospectiveRow, retrospective_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    async def list(
        self,
        owner_user_id: str,
        *,
        account_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPRetrospectiveRow).where(PersonalIPRetrospectiveRow.owner_user_id == owner_user_id)
        if account_id is not None:
            statement = statement.where(PersonalIPRetrospectiveRow.account_id == account_id)
        statement = statement.order_by(PersonalIPRetrospectiveRow.created_at.desc(), PersonalIPRetrospectiveRow.id.desc()).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._to_dict(row) for row in rows]
