"""Whole-portfolio read model for the Personal-IP operating loop."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime
from typing import Any

OPERATING_COCKPIT_CONTRACT_VERSION = "personal-ip-operating-cockpit-v7"
STARTUP_CONTEXT_CONTRACT_VERSION = "personal-ip-startup-context-v1"
_HISTORY_LIMIT = 500
_RECENT_LIMIT = 20
_ALERT_DETAIL_LIMIT = 50
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


def _project(items: list[dict[str, Any]], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{field: item.get(field) for field in fields if field in item} for item in items[:_RECENT_LIMIT]]


def _alert(
    *,
    alert_id: str,
    category: str,
    severity: str,
    code: str,
    source_type: str,
    source_id: str,
    title: str,
    action: str,
    occurred_at: str | None = None,
    production_id: str | None = None,
    thread_id: str | None = None,
    provider: str | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    item = {
        "alert_id": alert_id,
        "category": category,
        "severity": severity,
        "code": code,
        "source_type": source_type,
        "source_id": source_id,
        "title": title,
        "action": action,
    }
    optional = {
        "occurred_at": occurred_at,
        "production_id": production_id,
        "thread_id": thread_id,
        "provider": provider,
        "stage": stage,
    }
    item.update({key: value for key, value in optional.items() if value})
    return item


def _build_operational_alerts(
    *,
    receipts: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    platform_observations: list[dict[str, Any]],
    video_details: list[dict[str, Any]],
    video_detail_failures: list[str],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for receipt in receipts:
        status = str(receipt.get("status") or "")
        if status not in {"failed", "unknown"}:
            continue
        receipt_id = str(receipt.get("id") or "")
        items.append(
            _alert(
                alert_id=f"publish:{receipt_id}:{status}",
                category="loop",
                severity="blocking" if status == "failed" else "warning",
                code="publish_failed" if status == "failed" else "publish_state_unknown",
                source_type="publish_receipt",
                source_id=receipt_id,
                title="发布执行失败" if status == "failed" else "发布结果尚未确认",
                action="检查该作品的发布回执，修复后重新准备发布。",
                occurred_at=receipt.get("updated_at") or receipt.get("published_at"),
            )
        )

    for source_type, observations, key_fields in (
        (
            "metric_observation",
            metrics,
            ("receipt_id", "scope", "metric_mode"),
        ),
        (
            "platform_observation",
            platform_observations,
            ("account_id", "platform", "dataset"),
        ),
    ):
        latest_by_series: dict[tuple[str, ...], dict[str, Any]] = {}
        for observation in sorted(
            observations,
            key=lambda item: str(item.get("observed_at") or ""),
            reverse=True,
        ):
            series = tuple(str(observation.get(field) or "") for field in key_fields)
            latest_by_series.setdefault(series, observation)
        for observation in latest_by_series.values():
            if observation.get("status") != "unavailable":
                continue
            observation_id = str(observation.get("id") or "")
            items.append(
                _alert(
                    alert_id=f"{source_type}:{observation_id}:unavailable",
                    category="loop",
                    severity="warning",
                    code="collection_unavailable",
                    source_type=source_type,
                    source_id=observation_id,
                    title="经营数据采集不可用",
                    action="重新登录对应平台账号并再次采集；缺失数据不会按零计算。",
                    occurred_at=observation.get("observed_at"),
                )
            )

    for production_id in video_detail_failures:
        items.append(
            _alert(
                alert_id=f"video:{production_id}:detail-unavailable",
                category="loop",
                severity="warning",
                code="video_state_unavailable",
                source_type="video_production",
                source_id=production_id,
                production_id=production_id,
                title="视频任务状态读取失败",
                action="刷新工作台；若持续失败，检查 Gateway 和数据库健康状态。",
            )
        )

    for production in video_details:
        production_id = str(production.get("id") or "")
        thread_id = str(production.get("thread_id") or "") or None
        actionable_event_found = False
        events = production.get("events") or []
        for index, event in enumerate(events):
            status = str(event.get("status") or "")
            if status not in {"failed", "rejected"}:
                continue
            event_id = str(event.get("id") or event.get("event_key") or "")
            event_type = str(event.get("event_type") or "")
            provider = str(event.get("provider") or "")
            common = {
                "source_type": "video_event",
                "source_id": event_id,
                "occurred_at": event.get("occurred_at"),
                "production_id": production_id,
                "thread_id": thread_id,
                "stage": event.get("stage"),
            }
            later_events = events[index + 1 :]
            if event_type == "budget_reservation_rejected" and provider == "deerflow_budget_guard":
                if any(later.get("event_type") == "budget_reserved" and later.get("entity_type") == event.get("entity_type") and later.get("entity_id") == event.get("entity_id") for later in later_events):
                    continue
                actionable_event_found = True
                items.append(
                    _alert(
                        alert_id=f"cost:{event_id}",
                        category="cost",
                        severity="blocking",
                        code="budget_reservation_rejected",
                        title="付费调用被预算守卫拒绝",
                        action="检查剩余预算和未结算预留；调整方案后用新的尝试键重试。",
                        provider=provider or None,
                        **common,
                    )
                )
            elif provider not in {"", "deerflow_budget_guard", "human-workbench"}:
                if any(later.get("status") == "succeeded" and later.get("provider") == provider and later.get("entity_type") == event.get("entity_type") and later.get("entity_id") == event.get("entity_id") for later in later_events):
                    continue
                actionable_event_found = True
                items.append(
                    _alert(
                        alert_id=f"provider:{event_id}",
                        category="provider",
                        severity="blocking",
                        code="provider_execution_failed",
                        title="视频供应商执行失败",
                        action="检查供应商可用性和回执，修复后从失败镜头继续。",
                        provider=provider,
                        **common,
                    )
                )

        budget = production.get("budget_state")
        if isinstance(budget, dict) and production.get("status") not in {"completed", "cancelled"} and budget.get("available") == 0:
            items.append(
                _alert(
                    alert_id=f"cost:{production_id}:exhausted",
                    category="cost",
                    severity="warning",
                    code="budget_exhausted",
                    source_type="video_production",
                    source_id=production_id,
                    production_id=production_id,
                    thread_id=thread_id,
                    title="视频预算已全部使用或占用",
                    action="先结算或释放未完成预留；当前不会继续发起付费调用。",
                    occurred_at=production.get("updated_at"),
                    stage=production.get("current_stage"),
                )
            )
        if production.get("status") == "blocked" and not actionable_event_found:
            items.append(
                _alert(
                    alert_id=f"video:{production_id}:blocked",
                    category="loop",
                    severity="blocking",
                    code="video_production_blocked",
                    source_type="video_production",
                    source_id=production_id,
                    production_id=production_id,
                    thread_id=thread_id,
                    title="视频生产流程被阻塞",
                    action="打开该视频任务，处理当前阶段失败后继续。",
                    occurred_at=production.get("updated_at"),
                    stage=production.get("current_stage"),
                )
            )

    items.sort(
        key=lambda item: (
            item.get("occurred_at") or "",
            item["alert_id"],
        ),
        reverse=True,
    )
    category_counts = Counter(item["category"] for item in items)
    return {
        "summary": {
            "total": len(items),
            "blocking": sum(item["severity"] == "blocking" for item in items),
            "warning": sum(item["severity"] == "warning" for item in items),
            "by_category": {
                "loop": category_counts["loop"],
                "provider": category_counts["provider"],
                "cost": category_counts["cost"],
            },
        },
        "items": items[:_RECENT_LIMIT],
    }


class PersonalIPStartupContextService:
    """Distinguish a true cold start without scanning workflow ledgers."""

    def __init__(self, *, subjects, accounts) -> None:
        self._subjects = subjects
        self._accounts = accounts

    async def build(self, *, owner_user_id: str) -> dict[str, Any]:
        owner = str(owner_user_id or "").strip()
        if not owner:
            raise ValueError("owner_user_id is required")
        subjects, accounts = await asyncio.gather(
            self._subjects.list(owner, include_archived=False),
            self._accounts.list(owner, include_archived=False),
        )
        is_new_owner = not subjects and not accounts
        return {
            "contract_version": STARTUP_CONTEXT_CONTRACT_VERSION,
            "experience": "new_owner" if is_new_owner else "returning_owner",
            "portfolio": {
                "subject_count": len(subjects),
                "account_count": len(accounts),
            },
            "should_read_operating_cockpit": not is_new_owner,
            "next_step": "respond_to_current_request" if is_new_owner else "resume_operating_state",
        }


class PersonalIPOperatingCockpitService:
    """Join immutable workflow ledgers into one customer-facing cockpit."""

    def __init__(
        self,
        *,
        subjects,
        accounts,
        brand,
        differentiation,
        preflights,
        publish_receipts,
        metrics,
        platform_observations,
        retrospectives,
        video_productions,
    ) -> None:
        self._subjects = subjects
        self._accounts = accounts
        self._brand = brand
        self._differentiation = differentiation
        self._preflights = preflights
        self._publish_receipts = publish_receipts
        self._metrics = metrics
        self._platform_observations = platform_observations
        self._retrospectives = retrospectives
        self._video_productions = video_productions

    async def build(self, *, owner_user_id: str) -> dict[str, Any]:
        owner = str(owner_user_id or "").strip()
        if not owner:
            raise ValueError("owner_user_id is required")
        (
            subjects,
            accounts,
            strategies,
            differentiation_versions,
            asset_observations,
            preflights,
            receipts,
            metrics,
            platform_observations,
            retrospectives,
            video_productions,
        ) = await asyncio.gather(
            self._subjects.list(owner, include_archived=False),
            self._accounts.list(owner, include_archived=False),
            self._brand.list_strategies(owner, limit=_HISTORY_LIMIT),
            self._differentiation.list_versions(owner, limit=_HISTORY_LIMIT),
            self._differentiation.list_observations(owner, limit=_HISTORY_LIMIT),
            self._preflights.list(owner, limit=_HISTORY_LIMIT),
            self._publish_receipts.list(owner, limit=_HISTORY_LIMIT),
            self._metrics.list(owner, limit=_HISTORY_LIMIT),
            self._platform_observations.list(owner, limit=_HISTORY_LIMIT),
            self._retrospectives.list(owner, limit=_HISTORY_LIMIT),
            self._video_productions.list(owner, limit=_HISTORY_LIMIT),
        )
        active_video_productions = [production for production in video_productions if production.get("status") in {"draft", "running", "awaiting_review", "blocked"}][:_ALERT_DETAIL_LIMIT]
        video_detail_results = await asyncio.gather(
            *(
                self._video_productions.get(
                    str(production["id"]),
                    owner_user_id=owner,
                )
                for production in active_video_productions
            ),
            return_exceptions=True,
        )
        video_details: list[dict[str, Any]] = []
        video_detail_failures: list[str] = []
        for production, result in zip(
            active_video_productions,
            video_detail_results,
            strict=True,
        ):
            if isinstance(result, Exception) or result is None:
                video_detail_failures.append(str(production["id"]))
            else:
                video_details.append(result)

        latest_strategy_by_subject: dict[str, dict[str, Any]] = {}
        for strategy in strategies:
            key = str(strategy.get("subject_id") or "")
            if key and key not in latest_strategy_by_subject:
                latest_strategy_by_subject[key] = strategy
        latest_differentiation_by_subject: dict[str, dict[str, Any]] = {}
        for version in differentiation_versions:
            key = str(version.get("subject_id") or "")
            if key and key not in latest_differentiation_by_subject:
                latest_differentiation_by_subject[key] = version
        receipt_preflight_ids = {str(receipt.get("preflight_id")) for receipt in receipts if receipt.get("preflight_id")}
        preflights_awaiting_publish = sorted(preflight["id"] for preflight in preflights if preflight.get("status") == "sealed" and preflight.get("id") not in receipt_preflight_ids)
        published_receipts = [receipt for receipt in receipts if receipt.get("status") == "published"]
        metric_receipt_ids = {str(metric.get("receipt_id")) for metric in metrics if metric.get("receipt_id")}
        retrospective_receipt_ids = {str(retrospective.get("publish_receipt_id")) for retrospective in retrospectives if retrospective.get("publish_receipt_id")}
        published_awaiting_metrics = sorted(receipt["id"] for receipt in published_receipts if receipt.get("id") not in metric_receipt_ids)
        published_awaiting_retrospective = sorted(receipt["id"] for receipt in published_receipts if receipt.get("id") not in retrospective_receipt_ids)
        receipt_statuses = Counter(str(receipt.get("status") or "unknown") for receipt in receipts)
        video_statuses = Counter(str(production.get("status") or "unknown") for production in video_productions)
        video_stages = Counter(str(production.get("current_stage") or "intake") for production in video_productions)
        pending_publish_count = sum(receipt_statuses[status] for status in ("planned", "pending", "failed", "unknown"))
        platforms = sorted({str(account.get("platform")) for account in accounts if account.get("platform")})

        histories = {
            "strategies": strategies,
            "differentiation_versions": differentiation_versions,
            "asset_observations": asset_observations,
            "preflights": preflights,
            "publish_receipts": receipts,
            "metrics": metrics,
            "platform_observations": platform_observations,
            "retrospectives": retrospectives,
            "video_productions": video_productions,
        }
        preflight_summaries = [
            {
                **preflight,
                "variant_count": len((preflight.get("provider_receipt") or {}).get("variants") or []),
            }
            for preflight in preflights
        ]
        receipt_summaries = [{**receipt, "attempt_count": len(receipt.get("attempts") or [])} for receipt in receipts]
        alerts = _build_operational_alerts(
            receipts=receipts,
            metrics=metrics,
            platform_observations=platform_observations,
            video_details=video_details,
            video_detail_failures=video_detail_failures,
        )
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
                    total=len(subjects),
                    pending=0,
                    subjects_with_notes=len(set(latest_strategy_by_subject) | set(latest_differentiation_by_subject)),
                    subjects_with_strategy=len(latest_strategy_by_subject),
                    strategy_versions=len(strategies),
                    differentiation_versions=len(differentiation_versions),
                    subjects_with_direction=len(latest_differentiation_by_subject),
                    asset_observations=len(asset_observations),
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
                    measured=sum(retrospective.get("status") == "measured" for retrospective in retrospectives),
                    partial=sum(retrospective.get("status") == "partial" for retrospective in retrospectives),
                ),
            },
            "queues": {
                "preflights_awaiting_publish": preflights_awaiting_publish,
                "published_receipts_awaiting_metrics": published_awaiting_metrics,
                "published_receipts_awaiting_retrospective": published_awaiting_retrospective,
            },
            "alerts": alerts,
            "recent": {
                "strategies": _project(
                    strategies,
                    (
                        "id",
                        "subject_id",
                        "version",
                        "stage",
                        "method_version",
                        "person_model",
                        "business_model",
                        "benchmark_research",
                        "positioning_candidates",
                        "launch_package",
                        "validation",
                        "content_digest",
                        "created_at",
                    ),
                ),
                "differentiation": _project(
                    differentiation_versions,
                    (
                        "id",
                        "subject_id",
                        "version",
                        "thesis_key",
                        "status",
                        "method_version",
                        "primary_entity",
                        "decision_context",
                        "strategic_difference",
                        "dramatic_engine",
                        "distinctive_encoding",
                        "validation_summary",
                        "content_digest",
                        "created_at",
                    ),
                ),
                "asset_observations": _project(
                    asset_observations,
                    (
                        "id",
                        "subject_id",
                        "differentiation_version_id",
                        "thesis_key",
                        "observation_type",
                        "source",
                        "observed_at",
                        "coverage_status",
                        "measures",
                        "evidence_digest",
                    ),
                ),
                "preflights": _project(
                    preflight_summaries,
                    (
                        "id",
                        "status",
                        "target_account_ids",
                        "provider",
                        "model_version",
                        "variant_count",
                        "created_at",
                    ),
                ),
                "publish_receipts": _project(
                    receipt_summaries,
                    (
                        "id",
                        "preflight_id",
                        "account_id",
                        "platform",
                        "executor",
                        "status",
                        "attempt_count",
                        "published_at",
                        "updated_at",
                    ),
                ),
                "metrics": _project(
                    metrics,
                    (
                        "id",
                        "receipt_id",
                        "account_id",
                        "platform",
                        "scope",
                        "metric_mode",
                        "status",
                        "observed_at",
                        "metrics",
                        "coverage",
                    ),
                ),
                "platform_observations": _project(
                    platform_observations,
                    ("id", "account_id", "platform", "dataset", "status", "observed_at", "summary", "coverage"),
                ),
                "retrospectives": _project(
                    retrospectives,
                    ("id", "publish_receipt_id", "account_id", "platform", "horizon", "status", "comparison_state", "created_at"),
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
                "video_alert_detail_limit": _ALERT_DETAIL_LIMIT,
                "possibly_truncated": sorted(name for name, items in histories.items() if len(items) >= _HISTORY_LIMIT),
            },
        }
