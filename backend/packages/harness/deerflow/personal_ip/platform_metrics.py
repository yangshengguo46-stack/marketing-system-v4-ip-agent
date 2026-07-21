"""Platform metric collector contracts and the official Douyin implementation."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from deerflow.persistence.personal_ip_metrics import PersonalIPMetricRepository
from deerflow.persistence.personal_ip_platform_connections import PersonalIPPlatformConnectionRepository
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository
from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient

_DOUYIN_VIDEO_QUERY_URL = "https://open.douyin.com/api/apps/v1/video/query/"
_DOUYIN_SCOPE = "ma.video.bind"
_AUTH_CODES = {28001003, 28001008}
_PERMISSION_CODES = {28001014, 28001016, 28001018, 28001019}
_RETRYABLE_CODES = {28001005, 28001006}
_RATE_LIMIT_CODES = {28003017}
_STATISTIC_FIELDS = {
    "play_count": "views",
    "digg_count": "likes",
    "comment_count": "comments",
    "share_count": "shares",
    "download_count": "downloads",
    "forward_count": "forwards",
}
_REQUIRED_METRICS = {"views", "likes", "comments", "shares"}


@dataclass(frozen=True, slots=True)
class PlatformMetricSnapshot:
    """One normalized current-state observation from an external platform."""

    platform: str
    external_item_id: str
    observed_at: datetime
    status: str
    metrics: dict[str, int | float]
    coverage: dict[str, Any]


class PlatformMetricCollector(Protocol):
    platform: str

    async def collect_video_snapshots(self, external_item_ids: Sequence[str]) -> list[PlatformMetricSnapshot]: ...


class PlatformMetricCollectionError(RuntimeError):
    """Sanitized provider failure carrying retry and remediation semantics."""

    def __init__(
        self,
        message: str,
        *,
        category: str,
        retryable: bool,
        provider_code: int | None = None,
        provider_log_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.provider_code = provider_code
        self.provider_log_id = provider_log_id


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_datetime(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return _utc(datetime.fromisoformat(text))


def _clean_required(value: Any, *, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit:
        raise ValueError(f"{field} must contain 1 to {limit} characters")
    return text


def _normalize_item_ids(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item_id = _clean_required(raw, field="external_item_ids", limit=256)
        if item_id not in seen:
            seen.add(item_id)
            result.append(item_id)
    if not result or len(result) > 50:
        raise ValueError("external_item_ids must contain 1 to 50 unique ids")
    return result


def _provider_error(payload: dict[str, Any]) -> PlatformMetricCollectionError | None:
    code = payload.get("err_no")
    if not isinstance(code, int):
        code = None
    nested_extra = payload.get("data", {}).get("extra", {}) if isinstance(payload.get("data"), dict) else {}
    nested_code = nested_extra.get("error_code") if isinstance(nested_extra, dict) else None
    if (code in {None, 0}) and isinstance(nested_code, int) and nested_code != 0:
        code = nested_code
    if code in {None, 0}:
        return None
    log_id = str(payload.get("log_id") or nested_extra.get("logid") or "").strip() or None
    if code in _AUTH_CODES:
        category, retryable = "authentication", False
    elif code in _PERMISSION_CODES:
        category, retryable = "permission", False
    elif code in _RATE_LIMIT_CODES:
        category, retryable = "rate_limited", True
    elif code in _RETRYABLE_CODES:
        category, retryable = "transient", True
    else:
        category, retryable = "provider", False
    return PlatformMetricCollectionError(
        f"Douyin metric query failed with provider code {code}",
        category=category,
        retryable=retryable,
        provider_code=code,
        provider_log_id=log_id,
    )


class DouyinVideoMetricCollector:
    """Query current public-video statistics through Douyin's official OpenAPI."""

    platform = "douyin"

    def __init__(
        self,
        *,
        access_token: str,
        open_id: str,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._access_token = _clean_required(access_token, field="access_token", limit=4096)
        self._open_id = _clean_required(open_id, field="open_id", limit=256)
        self._client = client
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _request(self, item_ids: list[str]) -> dict[str, Any]:
        headers = {"access-token": self._access_token, "content-type": "application/json"}
        request_kwargs = {
            "params": {"open_id": self._open_id},
            "headers": headers,
            "json": {"item_ids": item_ids},
        }
        try:
            if self._client is not None:
                response = await self._client.post(_DOUYIN_VIDEO_QUERY_URL, **request_kwargs)
            else:
                async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
                    response = await client.post(_DOUYIN_VIDEO_QUERY_URL, **request_kwargs)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise PlatformMetricCollectionError("Douyin metric query timed out", category="network", retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            raise PlatformMetricCollectionError(
                f"Douyin metric query returned HTTP {exc.response.status_code}",
                category="http",
                retryable=exc.response.status_code >= 500,
            ) from exc
        except httpx.RequestError as exc:
            raise PlatformMetricCollectionError("Douyin metric query network failure", category="network", retryable=True) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise PlatformMetricCollectionError("Douyin metric query returned invalid JSON", category="response", retryable=False) from exc
        if not isinstance(payload, dict):
            raise PlatformMetricCollectionError("Douyin metric query returned an invalid payload", category="response", retryable=False)
        error = _provider_error(payload)
        if error is not None:
            raise error
        return payload

    async def collect_video_snapshots(self, external_item_ids: Sequence[str]) -> list[PlatformMetricSnapshot]:
        item_ids = _normalize_item_ids(external_item_ids)
        payload = await self._request(item_ids)
        observed_at = _utc(self._clock())
        outer_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        nested_data = outer_data.get("data") if isinstance(outer_data.get("data"), dict) else {}
        returned = nested_data.get("list") if isinstance(nested_data.get("list"), list) else []
        outer_extra = outer_data.get("extra") if isinstance(outer_data.get("extra"), dict) else {}
        log_id = str(payload.get("log_id") or outer_extra.get("logid") or "").strip() or None
        by_item = {str(item.get("item_id")): item for item in returned if isinstance(item, dict) and item.get("item_id")}
        snapshots: list[PlatformMetricSnapshot] = []
        for item_id in item_ids:
            item = by_item.get(item_id)
            common_coverage = {
                "scope": _DOUYIN_SCOPE,
                "provider_log_id": log_id,
                "official_endpoint": _DOUYIN_VIDEO_QUERY_URL,
            }
            if item is None:
                snapshots.append(
                    PlatformMetricSnapshot(
                        platform=self.platform,
                        external_item_id=item_id,
                        observed_at=observed_at,
                        status="unavailable",
                        metrics={},
                        coverage={**common_coverage, "reason": "not_returned_or_private"},
                    )
                )
                continue
            if item.get("create_time") == 0:
                snapshots.append(
                    PlatformMetricSnapshot(
                        platform=self.platform,
                        external_item_id=item_id,
                        observed_at=observed_at,
                        status="unavailable",
                        metrics={},
                        coverage={**common_coverage, "reason": "private_or_unavailable"},
                    )
                )
                continue
            statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
            metrics: dict[str, int | float] = {}
            returned_metric_names: set[str] = set()
            for provider_name, normalized_name in _STATISTIC_FIELDS.items():
                value = statistics.get(provider_name)
                if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                    metrics[normalized_name] = value
                    returned_metric_names.add(normalized_name)
            missing = sorted(_REQUIRED_METRICS - returned_metric_names)
            status = "observed" if not missing else "partial"
            snapshots.append(
                PlatformMetricSnapshot(
                    platform=self.platform,
                    external_item_id=item_id,
                    observed_at=observed_at,
                    status=status,
                    metrics=dict(sorted(metrics.items())),
                    coverage={
                        **common_coverage,
                        "returned_metrics": sorted(returned_metric_names),
                        "missing_metrics": missing,
                        "video_status": item.get("video_status"),
                        "is_reviewed": item.get("is_reviewed"),
                    },
                )
            )
        return snapshots


class PersonalIPMetricCollectionService:
    """Bind a server-side platform collector to existing publish evidence."""

    def __init__(
        self,
        *,
        metrics: PersonalIPMetricRepository,
        publish_receipts: PersonalIPPublishReceiptRepository,
    ) -> None:
        self._metrics = metrics
        self._publish_receipts = publish_receipts

    async def collect_published_post(
        self,
        *,
        owner_user_id: str,
        account_id: str,
        publish_receipt_id: str,
        observation_key: str,
        collector: PlatformMetricCollector,
    ) -> dict[str, Any]:
        receipt = await self._publish_receipts.get(publish_receipt_id, owner_user_id=owner_user_id)
        if receipt is None:
            raise ValueError("Personal-IP publish receipt not found")
        if receipt["status"] != "published":
            raise ValueError("publish receipt must be published before metric collection")
        if receipt["account_id"] != account_id:
            raise ValueError("publish receipt belongs to a different account")
        if receipt["platform"] != collector.platform:
            raise ValueError("metric collector platform does not match the publish account")
        external_post_id = str(receipt.get("external_post_id") or "").strip()
        if not external_post_id:
            raise ValueError("publish receipt has no external post id")
        series_key = f"post:{collector.platform}:{external_post_id}"
        prior_observations = await self._metrics.list(
            owner_user_id,
            receipt_id=publish_receipt_id,
            limit=500,
        )
        snapshots = await collector.collect_video_snapshots([external_post_id])
        if len(snapshots) != 1 or snapshots[0].external_item_id != external_post_id:
            raise PlatformMetricCollectionError("platform collector returned a mismatched post", category="response", retryable=False)
        snapshot = snapshots[0]
        current = await self._metrics.record(
            owner_user_id=owner_user_id,
            observation_key=observation_key,
            series_key=series_key,
            account_id=account_id,
            receipt_id=publish_receipt_id,
            scope="post",
            metric_mode="snapshot",
            source="platform_api",
            status=snapshot.status,
            observed_at=snapshot.observed_at,
            metrics=snapshot.metrics,
            coverage=snapshot.coverage,
        )
        previous = next(
            (observation for observation in prior_observations if observation["metric_mode"] == "snapshot" and observation["series_key"] == series_key and _iso_datetime(observation["observed_at"]) < snapshot.observed_at),
            None,
        )
        if previous is None:
            return {**current, "derived_delta": None}

        previous_metrics = previous.get("metrics") or {}
        current_metrics = snapshot.metrics
        comparable = sorted(set(previous_metrics) & set(current_metrics))
        deltas: dict[str, int | float] = {}
        non_monotonic: list[str] = []
        for metric in comparable:
            before = previous_metrics[metric]
            after = current_metrics[metric]
            if after < before:
                non_monotonic.append(metric)
                continue
            deltas[metric] = after - before
        missing = sorted((set(previous_metrics) | set(current_metrics)) - set(comparable))
        delta_status = "partial" if deltas else "unavailable"
        previous_observed_at = _iso_datetime(previous["observed_at"])
        delta_key = "derived-delta:" + hashlib.sha256(f"{observation_key}|{previous['id']}".encode()).hexdigest()
        delta = await self._metrics.record(
            owner_user_id=owner_user_id,
            observation_key=delta_key,
            series_key=series_key,
            account_id=account_id,
            receipt_id=publish_receipt_id,
            scope="post",
            metric_mode="delta",
            source="platform_api",
            status=delta_status,
            window_started_at=previous_observed_at,
            window_ended_at=snapshot.observed_at,
            observed_at=snapshot.observed_at,
            metrics=deltas,
            coverage={
                "derivation": "consecutive_cumulative_snapshot_difference",
                "scope_limit": "tracked_post_only",
                "baseline_observation_id": previous["id"],
                "current_observation_id": current["id"],
                "missing_metrics": missing,
                "non_monotonic_metrics": non_monotonic,
                "complete_account_window": False,
            },
        )
        return {**current, "derived_delta": delta}


class DouyinAuthorizedMetricCollectionService:
    """Resolve encrypted account credentials and retry one expired-token query."""

    def __init__(
        self,
        *,
        connections: PersonalIPPlatformConnectionRepository,
        metrics: PersonalIPMetricRepository,
        publish_receipts: PersonalIPPublishReceiptRepository,
        oauth_client: DouyinMiniAppOAuthClient,
        http_client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connections = connections
        self._collector_service = PersonalIPMetricCollectionService(
            metrics=metrics,
            publish_receipts=publish_receipts,
        )
        self._oauth_client = oauth_client
        self._http_client = http_client
        self._clock = clock or (lambda: datetime.now(UTC))

    def _collector(self, *, access_token: str, open_id: str) -> DouyinVideoMetricCollector:
        return DouyinVideoMetricCollector(
            access_token=access_token,
            open_id=open_id,
            client=self._http_client,
            clock=self._clock,
        )

    async def collect_published_post(
        self,
        *,
        owner_user_id: str,
        connection_id: str,
        publish_receipt_id: str,
        observation_key: str,
    ) -> dict[str, Any]:
        connection = await self._connections.get(connection_id, owner_user_id=owner_user_id)
        if connection is None or connection["status"] != "connected":
            raise ValueError("Personal-IP platform connection not found")
        if connection["platform"] != "douyin":
            raise ValueError("platform connection is not a Douyin connection")
        if _DOUYIN_SCOPE not in connection["scopes"]:
            raise ValueError("Douyin connection does not grant video-data permission")
        credentials = await self._connections.get_credentials(
            connection_id,
            owner_user_id=owner_user_id,
        )
        if credentials is None:
            raise ValueError("Douyin connection must be authorized again")

        async def _collect(access_token: str) -> dict[str, Any]:
            return await self._collector_service.collect_published_post(
                owner_user_id=owner_user_id,
                account_id=connection["account_id"],
                publish_receipt_id=publish_receipt_id,
                observation_key=observation_key,
                collector=self._collector(
                    access_token=access_token,
                    open_id=connection["external_user_id"],
                ),
            )

        try:
            return await _collect(credentials["access_token"])
        except PlatformMetricCollectionError as exc:
            if exc.category != "authentication":
                raise

        grant = await self._oauth_client.refresh(credentials["refresh_token"])
        now = _utc(self._clock())
        scopes = grant.scopes or list(connection["scopes"])
        if _DOUYIN_SCOPE not in scopes:
            raise ValueError("refreshed Douyin grant has no video-data permission")
        await self._connections.store_grant(
            owner_user_id=owner_user_id,
            account_id=connection["account_id"],
            platform="douyin",
            external_user_id=connection["external_user_id"],
            oauth_open_id=grant.oauth_open_id or connection.get("oauth_open_id"),
            access_token=grant.access_token,
            refresh_token=grant.refresh_token,
            scopes=scopes,
            access_expires_at=now + timedelta(seconds=grant.expires_in),
            refresh_expires_at=now + timedelta(seconds=grant.refresh_expires_in),
            now=now,
        )
        return await _collect(grant.access_token)
