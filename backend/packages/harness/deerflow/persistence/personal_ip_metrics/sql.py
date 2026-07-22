"""SQL repository and conservative aggregation for Personal-IP metrics."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_metrics.model import PersonalIPMetricObservationRow
from deerflow.persistence.personal_ip_publish_receipts.model import PersonalIPPublishReceiptRow
from deerflow.utils.time import coerce_iso

_SCOPES = {"account", "post"}
_METRIC_MODES = {"window_total", "delta", "snapshot"}
_SOURCES = {"platform_api", "ui_tars", "browser", "manual"}
_STATUSES = {"observed", "partial", "unavailable"}
_ADDITIVE_METRICS = {
    "clicks",
    "comments",
    "followers_delta",
    "impressions",
    "likes",
    "profile_visits",
    "saves",
    "shares",
    "views",
    "watch_time_seconds",
}
_METRIC_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _utc_datetime(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field} must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _json_object(value: Any, *, field: str, byte_limit: int = 256_000) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(serialized.encode("utf-8")) > byte_limit:
        raise ValueError(f"{field} exceeds the snapshot limit")
    return json.loads(serialized)


def _normalize_metrics(value: Any, *, status: str) -> dict[str, int | float]:
    snapshot = _json_object(value, field="metrics")
    if len(snapshot) > 100:
        raise ValueError("metrics may contain at most 100 fields")
    normalized: dict[str, int | float] = {}
    for raw_key, raw_value in snapshot.items():
        key = str(raw_key).strip().lower()
        if not _METRIC_NAME.fullmatch(key):
            raise ValueError(f"invalid metric name: {raw_key}")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)) or not math.isfinite(raw_value):
            raise ValueError(f"metric {key} must be a finite number")
        if raw_value < 0 and not key.endswith("_delta"):
            raise ValueError(f"metric {key} cannot be negative")
        normalized[key] = raw_value
    if status in {"observed", "partial"} and not normalized:
        raise ValueError(f"{status} observations require metrics")
    return normalized


class PersonalIPMetricRepository:
    """Persist immutable observations and aggregate only compatible windows."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _to_dict(row: PersonalIPMetricObservationRow) -> dict[str, Any]:
        data = row.to_dict()
        data["metrics"] = data.pop("metrics_json") or {}
        data["coverage"] = data.pop("coverage_json") or {}
        for field in ("window_started_at", "window_ended_at", "observed_at", "created_at"):
            if isinstance(data.get(field), datetime):
                data[field] = coerce_iso(data[field])
        return data

    @staticmethod
    def _same_observation(
        row: PersonalIPMetricObservationRow,
        *,
        series_key: str,
        account_id: str,
        receipt_id: str | None,
        scope: str,
        metric_mode: str,
        source: str,
        status: str,
        window_started_at: datetime | None,
        window_ended_at: datetime | None,
        observed_at: datetime,
        metrics: dict[str, int | float],
        coverage: dict[str, Any],
    ) -> bool:
        row_started = _utc_datetime(row.window_started_at, field="window_started_at") if row.window_started_at is not None else None
        row_ended = _utc_datetime(row.window_ended_at, field="window_ended_at") if row.window_ended_at is not None else None
        row_observed = _utc_datetime(row.observed_at, field="observed_at")
        return (
            row.series_key == series_key
            and row.account_id == account_id
            and row.receipt_id == receipt_id
            and row.scope == scope
            and row.metric_mode == metric_mode
            and row.source == source
            and row.status == status
            and row_started == window_started_at
            and row_ended == window_ended_at
            and row_observed == observed_at
            and row.metrics_json == metrics
            and row.coverage_json == coverage
        )

    async def record(
        self,
        *,
        owner_user_id: str,
        observation_key: str,
        account_id: str,
        receipt_id: str | None,
        scope: str,
        metric_mode: str,
        source: str,
        status: str,
        observed_at: datetime,
        metrics: dict[str, Any],
        coverage: dict[str, Any],
        window_started_at: datetime | None = None,
        window_ended_at: datetime | None = None,
        series_key: str | None = None,
    ) -> dict[str, Any]:
        owner = _clean_required(owner_user_id, field="owner_user_id", limit=64)
        observation = _clean_required(observation_key, field="observation_key", limit=256)
        account_key = _clean_required(account_id, field="account_id", limit=64)
        receipt_key = str(receipt_id or "").strip() or None
        scope_key = str(scope or "").strip()
        mode_key = str(metric_mode or "").strip()
        source_key = str(source or "").strip()
        status_key = str(status or "").strip()
        if scope_key not in _SCOPES:
            raise ValueError("unsupported metric scope")
        if mode_key not in _METRIC_MODES:
            raise ValueError("unsupported metric mode")
        if source_key not in _SOURCES:
            raise ValueError("unsupported metric source")
        if status_key not in _STATUSES:
            raise ValueError("unsupported metric observation status")
        observed = _utc_datetime(observed_at, field="observed_at")
        started = _utc_datetime(window_started_at, field="window_started_at") if window_started_at is not None else None
        ended = _utc_datetime(window_ended_at, field="window_ended_at") if window_ended_at is not None else None
        if mode_key in {"window_total", "delta"}:
            if started is None or ended is None or started >= ended:
                raise ValueError("window metrics require a valid started and ended interval")
        elif started is not None or ended is not None:
            if started is None or ended is None or started >= ended:
                raise ValueError("snapshot window must be omitted or valid")
        metric_snapshot = _normalize_metrics(metrics, status=status_key)
        coverage_snapshot = _json_object(coverage, field="coverage")

        async with self._sf() as session:
            account = await session.get(PersonalIPAccountRow, account_key)
            if account is None or account.owner_user_id != owner or account.status != "active":
                raise ValueError("Personal-IP metric account not found")
            if receipt_key is not None:
                receipt = await session.get(PersonalIPPublishReceiptRow, receipt_key)
                if receipt is None or receipt.owner_user_id != owner:
                    raise ValueError("Personal-IP publish receipt not found")
                if receipt.account_id != account_key:
                    raise ValueError("receipt belongs to a different account")
            if scope_key == "post" and receipt_key is None:
                raise ValueError("post metric observations require a publish receipt")
            derived_series = f"receipt:{receipt_key}" if receipt_key else f"account:{account_key}:{scope_key}"
            final_series = _clean_required(series_key or derived_series, field="series_key", limit=256)

            statement = select(PersonalIPMetricObservationRow).where(
                PersonalIPMetricObservationRow.owner_user_id == owner,
                PersonalIPMetricObservationRow.observation_key == observation,
            )
            existing = (await session.execute(statement)).scalars().first()
            if existing is not None:
                if self._same_observation(
                    existing,
                    series_key=final_series,
                    account_id=account_key,
                    receipt_id=receipt_key,
                    scope=scope_key,
                    metric_mode=mode_key,
                    source=source_key,
                    status=status_key,
                    window_started_at=started,
                    window_ended_at=ended,
                    observed_at=observed,
                    metrics=metric_snapshot,
                    coverage=coverage_snapshot,
                ):
                    return self._to_dict(existing)
                raise ValueError("observation_key already records a different observation")

            row = PersonalIPMetricObservationRow(
                id=f"metric-{uuid.uuid4().hex}",
                owner_user_id=owner,
                observation_key=observation,
                series_key=final_series,
                account_id=account.id,
                subject_id=account.subject_id,
                platform=account.platform,
                receipt_id=receipt_key,
                scope=scope_key,
                metric_mode=mode_key,
                source=source_key,
                status=status_key,
                window_started_at=started,
                window_ended_at=ended,
                observed_at=observed,
                metrics_json=metric_snapshot,
                coverage_json=coverage_snapshot,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._to_dict(row)

    async def get(self, observation_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPMetricObservationRow, observation_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_dict(row)

    async def list(
        self,
        owner_user_id: str,
        *,
        account_id: str | None = None,
        receipt_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        statement = select(PersonalIPMetricObservationRow).where(PersonalIPMetricObservationRow.owner_user_id == owner_user_id)
        if account_id is not None:
            statement = statement.where(PersonalIPMetricObservationRow.account_id == account_id)
        if receipt_id is not None:
            statement = statement.where(PersonalIPMetricObservationRow.receipt_id == receipt_id)
        statement = statement.order_by(PersonalIPMetricObservationRow.observed_at.desc(), PersonalIPMetricObservationRow.id.desc()).limit(max(1, min(int(limit), 500)))
        async with self._sf() as session:
            rows = (await session.execute(statement)).scalars()
            return [self._to_dict(row) for row in rows]

    async def aggregate(
        self,
        *,
        owner_user_id: str,
        window_started_at: datetime,
        window_ended_at: datetime,
    ) -> dict[str, Any]:
        started = _utc_datetime(window_started_at, field="window_started_at")
        ended = _utc_datetime(window_ended_at, field="window_ended_at")
        if started >= ended:
            raise ValueError("aggregate window must end after it starts")

        async with self._sf() as session:
            accounts = list(
                (
                    await session.execute(
                        select(PersonalIPAccountRow).where(
                            PersonalIPAccountRow.owner_user_id == owner_user_id,
                            PersonalIPAccountRow.status == "active",
                        )
                    )
                ).scalars()
            )
            rows = list(
                (
                    await session.execute(
                        select(PersonalIPMetricObservationRow).where(
                            PersonalIPMetricObservationRow.owner_user_id == owner_user_id,
                        )
                    )
                ).scalars()
            )

        active_ids = {account.id for account in accounts}
        window_rows = [
            row
            for row in rows
            if row.account_id in active_ids
            and row.metric_mode in {"window_total", "delta"}
            and row.window_started_at is not None
            and row.window_ended_at is not None
            and _utc_datetime(row.window_started_at, field="window_started_at") >= started
            and _utc_datetime(row.window_ended_at, field="window_ended_at") <= ended
        ]
        snapshot_rows = [row for row in rows if row.account_id in active_ids and row.metric_mode == "snapshot" and _utc_datetime(row.observed_at, field="observed_at") >= started]
        latest: dict[tuple[Any, ...], PersonalIPMetricObservationRow] = {}
        for row in window_rows:
            row_started = _utc_datetime(row.window_started_at, field="window_started_at")
            row_ended = _utc_datetime(row.window_ended_at, field="window_ended_at")
            row_observed = _utc_datetime(row.observed_at, field="observed_at")
            row_created = _utc_datetime(row.created_at, field="created_at")
            # A window total is a replacement reading for one series/window
            # start, so a later cutoff must not be added to an earlier poll.
            # Deltas remain independently additive by their exact interval.
            key = (row.account_id, row.scope, row.series_key, row.metric_mode, row_started) if row.metric_mode == "window_total" else (row.account_id, row.scope, row.series_key, row.metric_mode, row_started, row_ended)
            previous = latest.get(key)
            previous_rank = (
                (
                    _utc_datetime(previous.window_ended_at, field="window_ended_at"),
                    _utc_datetime(previous.observed_at, field="observed_at"),
                    _utc_datetime(previous.created_at, field="created_at"),
                    previous.id,
                )
                if previous is not None
                else None
            )
            if previous_rank is None or (row_ended, row_observed, row_created, row.id) > previous_rank:
                latest[key] = row

        totals: defaultdict[str, int | float] = defaultdict(int)
        by_platform: defaultdict[str, defaultdict[str, int | float]] = defaultdict(lambda: defaultdict(int))
        by_account: defaultdict[str, defaultdict[str, int | float]] = defaultdict(lambda: defaultdict(int))
        for row in latest.values():
            if row.status == "unavailable":
                continue
            for metric, value in (row.metrics_json or {}).items():
                if metric not in _ADDITIVE_METRICS:
                    continue
                totals[metric] += value
                by_platform[row.platform][metric] += value
                by_account[row.account_id][metric] += value

        latest_by_account: defaultdict[str, list[PersonalIPMetricObservationRow]] = defaultdict(list)
        for row in latest.values():
            latest_by_account[row.account_id].append(row)
        by_account_status: dict[str, str] = {}
        for account_id in sorted(active_ids):
            account_rows = latest_by_account.get(account_id, [])
            statuses = {row.status for row in account_rows}
            if not statuses:
                by_account_status[account_id] = "missing"
            elif statuses == {"unavailable"}:
                by_account_status[account_id] = "unavailable"
            elif "partial" in statuses or "unavailable" in statuses:
                by_account_status[account_id] = "partial"
            else:
                by_account_status[account_id] = "observed"

        by_platform_status: dict[str, str] = {}
        for platform in sorted({account.platform for account in accounts}):
            statuses = {by_account_status[account.id] for account in accounts if account.platform == platform}
            if statuses == {"observed"}:
                by_platform_status[platform] = "observed"
            elif statuses == {"unavailable"}:
                by_platform_status[platform] = "unavailable"
            elif statuses == {"missing"}:
                by_platform_status[platform] = "missing"
            else:
                by_platform_status[platform] = "partial"

        by_metric: dict[str, dict[str, list[str]]] = {}
        returned_metrics = {metric for row in latest.values() for metric in (row.metrics_json or {}) if metric in _ADDITIVE_METRICS}
        for metric in sorted(returned_metrics | {"views"}):
            metric_statuses = {"observed": [], "partial": [], "unavailable": [], "missing": []}
            for account_id in sorted(active_ids):
                account_rows = latest_by_account.get(account_id, [])
                metric_rows = [row for row in account_rows if metric in (row.metrics_json or {}) and row.status != "unavailable"]
                if metric_rows:
                    status = "observed" if by_account_status[account_id] == "observed" and all(row.status == "observed" for row in metric_rows) else "partial"
                elif by_account_status[account_id] == "unavailable":
                    status = "unavailable"
                else:
                    status = "missing"
                metric_statuses[status].append(account_id)
            by_metric[metric] = {f"{status}_account_ids": values for status, values in metric_statuses.items()}

        observed_accounts = {account_id for account_id, status in by_account_status.items() if status == "observed"}
        partial_accounts = {account_id for account_id, status in by_account_status.items() if status == "partial"}
        unavailable_accounts = {account_id for account_id, status in by_account_status.items() if status == "unavailable"}
        missing_accounts = {account_id for account_id, status in by_account_status.items() if status == "missing"}
        overall_status = "complete" if active_ids and not (partial_accounts or unavailable_accounts or missing_accounts) else "partial"
        if not active_ids:
            overall_status = "unavailable"
        return {
            "window_started_at": coerce_iso(started),
            "window_ended_at": coerce_iso(ended),
            "totals": dict(sorted(totals.items())),
            "by_platform": {key: dict(sorted(value.items())) for key, value in sorted(by_platform.items())},
            "by_account": {key: dict(sorted(value.items())) for key, value in sorted(by_account.items())},
            "observation_count": len(window_rows),
            "deduplicated_count": len(latest),
            "excluded_snapshot_count": len(snapshot_rows),
            "coverage": {
                "status": overall_status,
                "observed_account_ids": sorted(observed_accounts),
                "partial_account_ids": sorted(partial_accounts),
                "unavailable_account_ids": sorted(unavailable_accounts),
                "missing_account_ids": sorted(missing_accounts),
                "active_account_count": len(active_ids),
                "by_account_status": by_account_status,
                "by_platform_status": by_platform_status,
                "by_metric": by_metric,
            },
        }
