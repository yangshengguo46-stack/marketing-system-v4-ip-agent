"""Whole-portfolio read model for the Personal-IP operating loop."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime
from typing import Any

OPERATING_COCKPIT_CONTRACT_VERSION = "personal-ip-operating-cockpit-v1"
_HISTORY_LIMIT = 500
_RECENT_LIMIT = 20
VIDEO_PRODUCTION_STAGES = (
    "intake",
    "blueprint",
    "assets",
    "storyboard",
    "generation",
    "consistency",
    "selection",
    "finishing",
    "delivery",
)


def _stage(*, total: int, pending: int, **details: int) -> dict[str, Any]:
    if total == 0:
        state = "empty"
    elif pending:
        state = "needs_attention"
    else:
        state = "ready"
    return {"state": state, "total": total, "pending": pending, **details}


def _model_ready(account: dict[str, Any]) -> bool:
    return all(
        (
            str(account.get("primary_audience") or "").strip(),
            str(account.get("promise_to_audience") or "").strip(),
            account.get("content_pillars") or [],
            str(account.get("business_goal") or "").strip(),
        )
    )


def _project(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{field: item.get(field) for field in fields if field in item} for item in items[:_RECENT_LIMIT]]


class PersonalIPOperatingCockpitService:
    """Join immutable workflow ledgers into one customer-facing cockpit."""

    def __init__(
        self,
        *,
        subjects,
        accounts,
        preflights,
        publish_receipts,
        metrics,
        platform_observations,
        retrospectives,
        evidence_promotions,
        video_productions,
    ) -> None:
        self._subjects = subjects
        self._accounts = accounts
        self._preflights = preflights
        self._publish_receipts = publish_receipts
        self._metrics = metrics
        self._platform_observations = platform_observations
        self._retrospectives = retrospectives
        self._evidence_promotions = evidence_promotions
        self._video_productions = video_productions

    async def build(self, *, owner_user_id: str) -> dict[str, Any]:
        owner = str(owner_user_id or "").strip()
        if not owner:
            raise ValueError("owner_user_id is required")
        (
            subjects,
            accounts,
            preflights,
            receipts,
            metrics,
            platform_observations,
            retrospectives,
            promotions,
            video_productions,
        ) = await asyncio.gather(
            self._subjects.list(owner, include_archived=False),
            self._accounts.list(owner, include_archived=False),
            self._preflights.list(owner, limit=_HISTORY_LIMIT),
            self._publish_receipts.list(owner, limit=_HISTORY_LIMIT),
            self._metrics.list(owner, limit=_HISTORY_LIMIT),
            self._platform_observations.list(owner, limit=_HISTORY_LIMIT),
            self._retrospectives.list(owner, limit=_HISTORY_LIMIT),
            self._evidence_promotions.list(owner, limit=_HISTORY_LIMIT),
            self._video_productions.list(owner, limit=_HISTORY_LIMIT),
        )

        accounts_needing_model_input = sorted(account["id"] for account in accounts if not _model_ready(account))
        receipt_preflight_ids = {str(receipt.get("preflight_id")) for receipt in receipts if receipt.get("preflight_id")}
        preflights_awaiting_publish = sorted(preflight["id"] for preflight in preflights if preflight.get("status") == "sealed" and preflight.get("id") not in receipt_preflight_ids)
        published_receipts = [receipt for receipt in receipts if receipt.get("status") == "published"]
        metric_receipt_ids = {str(metric.get("receipt_id")) for metric in metrics if metric.get("receipt_id")}
        retrospective_receipt_ids = {str(retrospective.get("publish_receipt_id")) for retrospective in retrospectives if retrospective.get("publish_receipt_id")}
        published_awaiting_metrics = sorted(receipt["id"] for receipt in published_receipts if receipt.get("id") not in metric_receipt_ids)
        published_awaiting_retrospective = sorted(receipt["id"] for receipt in published_receipts if receipt.get("id") not in retrospective_receipt_ids)
        evidence_awaiting_decision = sorted(promotion["id"] for promotion in promotions if promotion.get("status") == "proposed")
        receipt_statuses = Counter(str(receipt.get("status") or "unknown") for receipt in receipts)
        video_statuses = Counter(str(production.get("status") or "unknown") for production in video_productions)
        video_stages = Counter(str(production.get("current_stage") or "intake") for production in video_productions)
        pending_publish_count = sum(receipt_statuses[status] for status in ("planned", "pending", "failed", "unknown"))
        platforms = sorted({str(account.get("platform")) for account in accounts if account.get("platform")})

        histories = {
            "preflights": preflights,
            "publish_receipts": receipts,
            "metrics": metrics,
            "platform_observations": platform_observations,
            "retrospectives": retrospectives,
            "evidence_promotions": promotions,
            "video_productions": video_productions,
        }
        return {
            "contract_version": OPERATING_COCKPIT_CONTRACT_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "portfolio": {
                "subject_count": len(subjects),
                "account_count": len(accounts),
                "platform_count": len(platforms),
                "platforms": platforms,
            },
            "stages": {
                "modeling": _stage(
                    total=len(accounts),
                    pending=len(accounts_needing_model_input),
                    ready=len(accounts) - len(accounts_needing_model_input),
                ),
                "preflight": _stage(
                    total=len(preflights),
                    pending=len(preflights_awaiting_publish),
                    sealed=sum(preflight.get("status") == "sealed" for preflight in preflights),
                ),
                "publishing": _stage(
                    total=len(receipts),
                    pending=pending_publish_count,
                    published=receipt_statuses["published"],
                    failed=receipt_statuses["failed"],
                ),
                "performance": _stage(
                    total=len(metrics) + len(platform_observations),
                    pending=len(published_awaiting_metrics),
                    metric_observations=len(metrics),
                    platform_observations=len(platform_observations),
                ),
                "retrospective": _stage(
                    total=len(retrospectives),
                    pending=len(published_awaiting_retrospective),
                    pending_human_review=sum(retrospective.get("status") == "pending_human_review" for retrospective in retrospectives),
                ),
                "evidence": _stage(
                    total=len(promotions),
                    pending=len(evidence_awaiting_decision),
                    approved=sum(promotion.get("status") == "approved" for promotion in promotions),
                ),
            },
            "queues": {
                "accounts_needing_model_input": accounts_needing_model_input,
                "preflights_awaiting_publish": preflights_awaiting_publish,
                "published_receipts_awaiting_metrics": published_awaiting_metrics,
                "published_receipts_awaiting_retrospective": published_awaiting_retrospective,
                "evidence_awaiting_decision": evidence_awaiting_decision,
            },
            "recent": {
                "preflights": _project(
                    preflights,
                    ("id", "status", "target_account_ids", "provider", "model_version", "created_at"),
                ),
                "publish_receipts": _project(
                    receipts,
                    ("id", "preflight_id", "account_id", "platform", "executor", "status", "published_at", "updated_at"),
                ),
                "metrics": _project(
                    metrics,
                    ("id", "receipt_id", "account_id", "platform", "scope", "status", "observed_at", "coverage"),
                ),
                "platform_observations": _project(
                    platform_observations,
                    ("id", "account_id", "platform", "dataset", "status", "observed_at", "summary", "coverage"),
                ),
                "retrospectives": _project(
                    retrospectives,
                    ("id", "publish_receipt_id", "account_id", "platform", "horizon", "status", "comparison_state", "created_at"),
                ),
                "evidence_promotions": _project(
                    promotions,
                    ("id", "evidence_type", "claim", "status", "minimum_support", "created_at", "updated_at"),
                ),
            },
            "video": {
                "contract_version": "personal-ip-video-production-v1",
                "production_count": len(video_productions),
                "active_count": sum(video_statuses[status] for status in ("draft", "running", "awaiting_review", "blocked")),
                "completed_count": video_statuses["completed"],
                "blocked_production_ids": sorted(production["id"] for production in video_productions if production.get("status") == "blocked"),
                "awaiting_review_production_ids": sorted(production["id"] for production in video_productions if production.get("status") == "awaiting_review"),
                "stages": {stage: video_stages[stage] for stage in VIDEO_PRODUCTION_STAGES},
                "recent": _project(
                    video_productions,
                    ("id", "title", "status", "current_stage", "event_count", "subject_id", "updated_at"),
                ),
            },
            "coverage": {
                "history_limit": _HISTORY_LIMIT,
                "possibly_truncated": sorted(name for name, items in histories.items() if len(items) >= _HISTORY_LIMIT),
            },
        }
