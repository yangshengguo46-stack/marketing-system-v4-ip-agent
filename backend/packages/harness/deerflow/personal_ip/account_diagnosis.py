"""Owner-scoped account evidence reader for Personal-IP analysis.

This module intentionally contains no account verdict compiler.  It gathers
credential-free observations for one authenticated account and reports what is
present.  The agent may use its IP, story, platform and business methods to
form a recommendation, but the server does not turn sample counts or operating
metrics into a creative or strategic admission rule.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION = "personal-ip-account-evidence-context-v3"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _metric_view(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "receipt_id": item.get("receipt_id"),
        "scope": item.get("scope"),
        "metric_mode": item.get("metric_mode"),
        "status": item.get("status"),
        "observed_at": item.get("observed_at"),
        "window_start": item.get("window_start"),
        "window_end": item.get("window_end"),
        "metrics": _mapping(item.get("metrics")),
        "coverage": _mapping(item.get("coverage")),
    }


def _platform_observation_view(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "dataset": str(item.get("dataset") or ""),
        "status": item.get("status"),
        "source": item.get("source"),
        "source_url": item.get("source_url"),
        "observed_at": item.get("observed_at"),
        "records": _records(item.get("records")),
        "summary": _mapping(item.get("summary")),
        "coverage": _mapping(item.get("coverage")),
        "evidence": _mapping(item.get("evidence")),
    }


def _receipt_view(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "status": item.get("status"),
        "platform": item.get("platform"),
        "published_at": item.get("published_at"),
        "external_post_id": item.get("external_post_id"),
        "external_url": item.get("external_url"),
    }


def _retrospective_view(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "publish_receipt_id": item.get("publish_receipt_id"),
        "status": item.get("status"),
        "comparison_state": item.get("comparison_state"),
        "outcomes": _mapping(item.get("outcomes")),
        "created_at": item.get("created_at"),
    }


def _asset_observation_view(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "differentiation_version_id": item.get("differentiation_version_id"),
        "observation_type": item.get("observation_type"),
        "source": item.get("source"),
        "observed_at": item.get("observed_at"),
        "coverage_status": item.get("coverage_status"),
        "measures": _mapping(item.get("measures")),
        "evidence_refs": _records(item.get("evidence_refs")),
    }


class PersonalIPAccountDiagnosticContextService:
    """Read bounded account facts without producing or constraining a verdict."""

    def __init__(
        self,
        *,
        accounts: Any,
        metrics: Any,
        platform_observations: Any,
        publish_receipts: Any,
        retrospectives: Any,
        brand: Any | None = None,
        differentiation: Any | None = None,
    ) -> None:
        self._accounts = accounts
        self._metrics = metrics
        self._platform_observations = platform_observations
        self._publish_receipts = publish_receipts
        self._retrospectives = retrospectives
        self._brand = brand
        self._differentiation = differentiation

    async def build(self, *, owner_user_id: str, account_id: str) -> dict[str, Any]:
        account = await self._accounts.get(account_id, owner_user_id=owner_user_id)
        if account is None:
            raise ValueError("Personal-IP account not found")

        receipts = await self._publish_receipts.list(
            owner_user_id,
            account_id=account_id,
            limit=100,
        )
        metrics = await self._metrics.list(
            owner_user_id,
            account_id=account_id,
            limit=200,
        )
        observations = await self._platform_observations.list(
            owner_user_id,
            account_id=account_id,
            limit=200,
        )
        retrospectives = await self._retrospectives.list(
            owner_user_id,
            account_id=account_id,
            limit=100,
        )

        subject_id = str(account.get("subject_id") or "").strip() or None
        strategy: dict[str, Any] | None = None
        direction: dict[str, Any] | None = None
        asset_observations: list[dict[str, Any]] = []
        if subject_id and self._brand is not None:
            strategy = await self._brand.get_latest_strategy(
                subject_id,
                owner_user_id=owner_user_id,
            )
        if subject_id and self._differentiation is not None:
            direction_id = str(strategy.get("differentiation_version_id") or "").strip() if isinstance(strategy, Mapping) else ""
            if direction_id:
                direction = await self._differentiation.get_version(
                    direction_id,
                    owner_user_id=owner_user_id,
                )
            if direction is None:
                direction = await self._differentiation.get_latest(
                    subject_id,
                    owner_user_id=owner_user_id,
                )
            if hasattr(self._differentiation, "list_observations"):
                asset_observations = await self._differentiation.list_observations(
                    owner_user_id,
                    subject_id=subject_id,
                    limit=200,
                )

        metric_views = [_metric_view(item) for item in metrics if item.get("id")]
        observation_views = [_platform_observation_view(item) for item in observations if item.get("id")]
        receipt_views = [_receipt_view(item) for item in receipts if item.get("id")]
        retrospective_views = [_retrospective_view(item) for item in retrospectives if item.get("id")]
        asset_views = [_asset_observation_view(item) for item in asset_observations if item.get("id")]

        evidence_index = [
            *({"kind": "metric_observation", "id": item["id"]} for item in metric_views),
            *({"kind": "platform_observation", "id": item["id"]} for item in observation_views),
            *({"kind": "publish_receipt", "id": item["id"]} for item in receipt_views),
            *({"kind": "retrospective", "id": item["id"]} for item in retrospective_views),
            *({"kind": "ip_asset_observation", "id": item["id"]} for item in asset_views),
        ]
        if strategy and strategy.get("id"):
            evidence_index.append({"kind": "strategy_version", "id": str(strategy["id"])})
        if direction and direction.get("id"):
            evidence_index.append({"kind": "differentiation_version", "id": str(direction["id"])})

        context = {
            "contract_version": ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "account": {
                "id": str(account.get("id") or account_id),
                "subject_id": subject_id,
                "platform": str(account.get("platform") or ""),
                "display_name": str(account.get("display_name") or ""),
                "handle": account.get("handle"),
                "status": str(account.get("status") or ""),
            },
            "strategy": strategy,
            "direction": direction,
            "inventory": {
                "metric_observation_count": len(metric_views),
                "platform_observation_count": len(observation_views),
                "publish_receipt_count": len(receipt_views),
                "retrospective_count": len(retrospective_views),
                "asset_observation_count": len(asset_views),
            },
            "metric_observations": metric_views,
            "platform_observations": observation_views,
            "publish_receipts": receipt_views,
            "retrospectives": retrospective_views,
            "asset_observations": asset_views,
            "evidence_index": evidence_index,
        }
        context["context_digest"] = _digest(context)
        return context
