"""Credential-free collection of visible creator-backend business data."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from deerflow.community.url_safety import resolve_host_addresses, validate_public_http_url
from deerflow.config import get_app_config
from deerflow.config.paths import get_paths
from deerflow.personal_ip.browser_profiles import (
    BROWSER_PLATFORMS,
    browser_login_cookie_rule,
    browser_login_succeeded,
    build_browser_account_target,
)

_BROWSER_DATASETS = {
    "account_profile",
    "audience_analytics",
    "comments",
    "content_inventory",
    "content_metrics",
    "conversions",
    "dashboard",
    "platform_receipts",
    "traffic_sources",
}
_COMPACT_COUNT = r"(?:-|[0-9][0-9,.]*(?:万|亿|[KkMmBb])?)"
_CONTENT_DURATION = re.compile(r"(?<!日 )(?<!\d)(?P<minutes>\d{2}):(?P<seconds>\d{2})\s+")
_CONTENT_PUBLISHED_AT = re.compile(r"(?P<year>\d{4})年(?P<month>\d{2})月(?P<day>\d{2})日\s+(?P<hour>\d{2}):(?P<minute>\d{2})")
_CONTENT_METRICS = re.compile(rf"播放\s+(?P<views>{_COMPACT_COUNT})\s+点赞\s+(?P<likes>{_COMPACT_COUNT})\s+评论\s+(?P<comments>{_COMPACT_COUNT})\s+分享\s+(?P<shares>{_COMPACT_COUNT})")


@dataclass(frozen=True, slots=True)
class BrowserDashboardMetricAdapter:
    """Rendered-label adapter; it never reads browser storage or network data."""

    metric_labels: dict[str, tuple[str, ...]]


_COMMON_SOCIAL_METRICS = {
    "comments": ("评论", "Comments"),
    "likes": ("点赞", "Likes"),
    "profile_visits": ("主页访问量", "主页访问", "Profile visits", "Profile views"),
    "shares": ("分享", "Shares"),
}

_BROWSER_DASHBOARD_METRIC_ADAPTERS: dict[str, BrowserDashboardMetricAdapter] = {
    "douyin": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "views": ("播放量", "视频播放量", "作品播放量"),
        }
    ),
    "wechat_channels": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "views": ("播放量", "视频播放次数", "视频播放量", "播放次数"),
        }
    ),
    "wechat_official": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "unique_viewers": ("图文阅读人数", "阅读人数"),
            "views": ("阅读次数", "阅读量", "图文阅读次数"),
        }
    ),
    "xiaohongshu": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "impressions": ("曝光量", "曝光数"),
            "views": ("观看量", "观看数", "浏览量", "笔记浏览量"),
        }
    ),
    "x": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "impressions": ("Impressions",),
            "views": ("Post views", "Video views", "Views"),
        }
    ),
    "instagram": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "impressions": ("Impressions",),
            "views": ("Content views", "Video views", "Views"),
        }
    ),
    "youtube": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "watch_time_seconds": ("Watch time (seconds)",),
            "views": ("Video views", "Views"),
        }
    ),
    "tiktok": BrowserDashboardMetricAdapter(
        {
            **_COMMON_SOCIAL_METRICS,
            "views": ("Post views", "Video views", "Views"),
        }
    ),
}

_TODAY_WINDOW = re.compile(r"(?:今日|今天|本日|\bToday\b)", re.IGNORECASE)
_YESTERDAY_WINDOW = re.compile(r"(?:昨日|昨天|\bYesterday\b)", re.IGNORECASE)
_LAST_7_DAYS_WINDOW = re.compile(r"(?:近\s*7\s*日|过去\s*7\s*天|\bLast\s+7\s+days\b|\b7\s+days\b)", re.IGNORECASE)
_LAST_28_DAYS_WINDOW = re.compile(r"(?:近\s*28\s*日|过去\s*28\s*天|\bLast\s+28\s+days\b|\b28\s+days\b)", re.IGNORECASE)


class BrowserPlatformCollectionError(ValueError):
    """Safe, user-actionable browser-first platform collection failure."""


DouyinBrowserCollectionError = BrowserPlatformCollectionError


def _is_playwright_timeout_error(exc: Exception) -> bool:
    """Recognize a navigation timeout without importing optional Playwright."""
    return exc.__class__.__name__ == "TimeoutError" and exc.__class__.__module__.startswith("playwright.")


def _config_int(extra: dict[str, Any], key: str, default: int) -> int:
    value = extra.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _config_bool(extra: dict[str, Any], key: str, default: bool) -> bool:
    value = extra.get(key)
    return value if isinstance(value, bool) else default


def _config_str(extra: dict[str, Any], key: str) -> str | None:
    value = extra.get(key)
    return value.strip() or None if isinstance(value, str) else None


@contextlib.contextmanager
def acquire_account_browser_session(*, owner_user_id: str, account: dict[str, Any]):
    """Reuse the same owner/account Chromium session as login and Browser Control."""
    from deerflow.community.browser_automation.session import get_browser_session_manager  # noqa: PLC0415

    account_id = str(account.get("id") or "").strip()
    if not account_id or account.get("status") != "active":
        raise BrowserPlatformCollectionError("Active Personal-IP account not found")
    paths = get_paths()
    safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
    target = build_browser_account_target(
        owner_user_id=owner_user_id,
        account_id=account_id,
        platform=str(account.get("platform") or ""),
        display_name=str(account.get("display_name") or account_id),
        user_data_dir=paths.ensure_browser_profile_dir(account_id, user_id=safe_user_id),
    )
    tool_config = get_app_config().get_tool_config("browser_navigate")
    extra = (tool_config.model_extra or {}) if tool_config is not None else {}
    manager = get_browser_session_manager()

    def _url_guard(url: str) -> str | None:
        return validate_public_http_url(
            url,
            allow_private_addresses=_config_bool(extra, "allow_private_addresses", False),
            # Clash and similar local proxies commonly answer public creator
            # hosts with RFC 2544 fake-IP addresses (198.18.0.0/15). Browser
            # Control already permits that exact proxy range while continuing
            # to reject real private, loopback and metadata targets. Account
            # collection must use the same policy or a successfully logged-in
            # profile is blocked before its public creator dashboard loads.
            allow_proxy_fake_ip=True,
            action="browse",
            resolver=resolve_host_addresses,
        )

    with manager.acquire_session(
        target.session_key,
        headless=_config_bool(extra, "headless", True),
        timeout_ms=_config_int(extra, "timeout_ms", 30_000),
        viewport={
            "width": _config_int(extra, "viewport_width", 1280),
            "height": _config_int(extra, "viewport_height", 720),
        },
        cdp_url=_config_str(extra, "cdp_url"),
        user_data_dir=str(target.user_data_dir),
        allow_unguarded_cdp=_config_bool(extra, "allow_unguarded_cdp", False),
        url_guard=_url_guard,
    ) as session:
        yield session


def _safe_url(value: Any) -> str:
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise BrowserPlatformCollectionError("Browser page returned an invalid URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise BrowserPlatformCollectionError("Browser page did not return an HTTP(S) URL")
    host = parsed.hostname.lower()
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", "", ""))


def _target_url(value: str, *, platform: str) -> str:
    config = BROWSER_PLATFORMS.get(platform)
    if config is None:
        raise BrowserPlatformCollectionError("This account does not have a browser-first connector")
    expected = urlsplit(config.start_url)
    expected_host = (expected.hostname or "").lower()
    label = "Douyin" if platform == "douyin" else config.label
    raw = str(value or "").strip()
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise BrowserPlatformCollectionError(f"target_url must be a safe {label} creator URL") from exc
    if parsed.query or parsed.fragment:
        raise BrowserPlatformCollectionError("target_url must not contain a query or fragment")
    target_host = (parsed.hostname or "").lower()
    allowed_hosts = {expected_host, *config.creator_hosts}
    if parsed.scheme != "https" or target_host not in allowed_hosts or parsed.username or parsed.password:
        raise BrowserPlatformCollectionError(f"target_url must be a safe {label} creator URL")
    return urlunsplit(("https", target_host, parsed.path or "/", "", ""))


def _clean_text(value: Any, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _compact_count(value: str | None) -> int | float | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text == "-":
        return None
    multiplier = 1
    if text.endswith("万"):
        multiplier = 10_000
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 100_000_000
        text = text[:-1]
    elif text[-1:].lower() == "k":
        multiplier = 1_000
        text = text[:-1]
    elif text[-1:].lower() == "m":
        multiplier = 1_000_000
        text = text[:-1]
    elif text[-1:].lower() == "b":
        multiplier = 1_000_000_000
        text = text[:-1]
    try:
        result = float(text) * multiplier
    except ValueError:
        return None
    return int(result) if result.is_integer() else result


def parse_douyin_content_inventory(visible_text: str) -> dict[str, Any]:
    """Parse rendered Douyin work cards without relying on private APIs."""
    text = _clean_text(visible_text, limit=60_000)
    matches = list(_CONTENT_DURATION.finditer(text))
    items: list[dict[str, Any]] = []
    for index, duration_match in enumerate(matches):
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[duration_match.end() : body_end].strip()
        if "编辑作品" not in body:
            continue
        title_part, remainder = body.split("编辑作品", 1)
        visibility = "private" if title_part.startswith("私密 ") else "public"
        title = title_part.removeprefix("私密 ").strip()
        published_match = _CONTENT_PUBLISHED_AT.search(remainder)
        metric_match = _CONTENT_METRICS.search(remainder)
        if not title or published_match is None or metric_match is None:
            continue
        published_at = f"{published_match.group('year')}-{published_match.group('month')}-{published_match.group('day')}T{published_match.group('hour')}:{published_match.group('minute')}:00+08:00"
        publication_status = "published"
        if "审核中" in remainder:
            publication_status = "reviewing"
        elif "未通过" in remainder:
            publication_status = "rejected"
        items.append(
            {
                "record_type": "content_item",
                "title": title,
                "duration_seconds": int(duration_match.group("minutes")) * 60 + int(duration_match.group("seconds")),
                "visibility": visibility,
                "publication_status": publication_status,
                "published_at": published_at,
                "metrics": {
                    "views": _compact_count(metric_match.group("views")),
                    "likes": _compact_count(metric_match.group("likes")),
                    "comments": _compact_count(metric_match.group("comments")),
                    "shares": _compact_count(metric_match.group("shares")),
                },
            }
        )
    declared_match = re.search(r"共\s*(\d+)\s*个作品", text)
    return {
        "items": items,
        "declared_content_count": int(declared_match.group(1)) if declared_match else None,
        "listing_complete": "没有更多作品" in text,
    }


def _first_count(pattern: str, text: str) -> int | float | None:
    match = re.search(pattern, text)
    return _compact_count(match.group(1)) if match else None


def parse_douyin_dashboard_summary(visible_text: str) -> dict[str, Any]:
    """Extract only direct dashboard counters and their displayed time window."""
    text = _clean_text(visible_text, limit=60_000)
    result: dict[str, Any] = {}
    account_match = re.search(
        rf"关注\s+({_COMPACT_COUNT})\s+粉丝\s+({_COMPACT_COUNT})\s+获赞\s+({_COMPACT_COUNT})",
        text,
    )
    if account_match:
        result.update(
            {
                "following_snapshot": _compact_count(account_match.group(1)),
                "followers_snapshot": _compact_count(account_match.group(2)),
                "likes_received_snapshot": _compact_count(account_match.group(3)),
            }
        )
    window_match = re.search(r"统计周期：(?P<start>\d{4}\.\d{2}\.\d{2})-(?P<end>\d{4}\.\d{2}\.\d{2})", text)
    if window_match:
        result["window_started_on"] = window_match.group("start").replace(".", "-")
        result["window_ended_on"] = window_match.group("end").replace(".", "-")
    label_match = re.search(r"数据总览.*?时间\s+(近\d+日)", text)
    if label_match:
        result["window_label"] = label_match.group(1)
    metric_patterns = {
        "views": rf"播放量\s+播放量\s+({_COMPACT_COUNT})",
        "profile_visits": rf"主页访问量\s+({_COMPACT_COUNT})",
        "shares": rf"作品分享\s+({_COMPACT_COUNT})",
        "comments": rf"作品评论\s+({_COMPACT_COUNT})",
    }
    for key, pattern in metric_patterns.items():
        value = _first_count(pattern, text)
        if value is not None:
            result[key] = value
    return result


def _labeled_count(text: str, labels: tuple[str, ...]) -> tuple[int | float | None, str | None]:
    for label in sorted(labels, key=len, reverse=True):
        escaped = re.escape(label)
        if label.casefold() == "views":
            escaped = r"(?<!Profile )\bViews\b"
        elif label == "浏览量":
            escaped = r"(?<!主页)浏览量"
        patterns = (
            rf"{escaped}\s*(?:[:：]|为)?\s*(?P<value>{_COMPACT_COUNT})",
            rf"(?P<value>{_COMPACT_COUNT})\s*(?:次|个)?\s*{escaped}",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue
            value = _compact_count(match.group("value"))
            if value is not None:
                return value, label
    return None, None


def _displayed_metric_window(text: str) -> dict[str, str]:
    douyin_window = parse_douyin_dashboard_summary(text)
    if douyin_window.get("window_started_on") and douyin_window.get("window_ended_on"):
        return {
            "kind": "date_range",
            "label": str(douyin_window.get("window_label") or "explicit_date_range"),
            "started_on": str(douyin_window["window_started_on"]),
            "ended_on": str(douyin_window["window_ended_on"]),
        }
    matches: list[tuple[str, re.Match[str]]] = []
    for kind, pattern in (
        ("today", _TODAY_WINDOW),
        ("yesterday", _YESTERDAY_WINDOW),
        ("last_7_days", _LAST_7_DAYS_WINDOW),
        ("last_28_days", _LAST_28_DAYS_WINDOW),
    ):
        match = pattern.search(text)
        if match is not None:
            matches.append((kind, match))
    if len(matches) == 1:
        kind, match = matches[0]
        return {"kind": kind, "label": match.group(0)}
    if matches:
        return {"kind": "ambiguous", "label": ",".join(kind for kind, _match in matches)}
    return {"kind": "unknown", "label": "not_displayed"}


def parse_browser_dashboard_metrics(platform: str, visible_text: str) -> dict[str, Any]:
    """Normalize direct rendered dashboard counts for all browser-first platforms.

    A parsed count remains evidence, not proof of account-window completeness.
    Portfolio aggregation promotes it only when the page explicitly displays
    the requested ``today`` window.
    """
    adapter = _BROWSER_DASHBOARD_METRIC_ADAPTERS.get(str(platform or "").strip())
    if adapter is None:
        return {"metrics": {}, "metric_labels": {}, "window": {"kind": "unknown", "label": "unsupported_platform"}}
    text = _clean_text(visible_text, limit=60_000)
    metrics: dict[str, int | float] = {}
    matched_labels: dict[str, str] = {}
    for metric, labels in adapter.metric_labels.items():
        value, label = _labeled_count(text, labels)
        if value is not None and label is not None:
            metrics[metric] = value
            matched_labels[metric] = label
    return {
        "metrics": dict(sorted(metrics.items())),
        "metric_labels": dict(sorted(matched_labels.items())),
        "window": _displayed_metric_window(text),
    }


def _text_list(value: Any, *, item_limit: int, count_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:count_limit]:
        text = _clean_text(item, limit=item_limit)
        if text:
            result.append(text)
    return result


def _tables(value: Any) -> list[dict[str, list[list[str]]]]:
    if not isinstance(value, list):
        return []
    tables: list[dict[str, list[list[str]]]] = []
    rows_seen = 0
    for raw_table in value[:30]:
        if not isinstance(raw_table, dict) or not isinstance(raw_table.get("rows"), list):
            continue
        rows: list[list[str]] = []
        for raw_row in raw_table["rows"]:
            if rows_seen >= 2_000:
                break
            if not isinstance(raw_row, list):
                continue
            cells = [_clean_text(cell, limit=500) for cell in raw_row[:100]]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(cells)
                rows_seen += 1
        if rows:
            tables.append({"rows": rows})
    return tables


def _links(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    links: list[dict[str, str]] = []
    for raw_link in value[:200]:
        if not isinstance(raw_link, dict):
            continue
        text = _clean_text(raw_link.get("text"), limit=300)
        href = ""
        if raw_link.get("href"):
            try:
                href = _safe_url(raw_link["href"])
            except BrowserPlatformCollectionError:
                href = ""
        if text or href:
            links.append({"text": text, "href": href})
    return links


def _rendered_data_ready(extracted: Any) -> bool:
    if not isinstance(extracted, dict):
        return False
    text = _clean_text(extracted.get("visible_text"), limit=60_000)
    has_structured_data = bool(extracted.get("tables")) or bool(extracted.get("data_blocks"))
    loading_only = ("加载中，请稍候" in text or "loading" == text.strip().lower()) and not has_structured_data and len(text) < 100
    if loading_only:
        return False
    return len(text) >= 100 or has_structured_data


class BrowserPlatformCollectionService:
    """Capture rendered creator data for a browser-first account without secrets."""

    def __init__(self, *, accounts, observations, settle_seconds: float = 1.5) -> None:
        self._accounts = accounts
        self._observations = observations
        self._settle_seconds = max(0.0, min(float(settle_seconds), 10.0))

    async def _unavailable(
        self,
        *,
        owner_user_id: str,
        account_id: str,
        observation_key: str,
        dataset: str,
        source_url: str,
        platform: str,
    ) -> dict[str, Any]:
        return await self._observations.record(
            owner_user_id=owner_user_id,
            observation_key=observation_key,
            account_id=account_id,
            dataset=dataset,
            source="browser",
            status="unavailable",
            source_url=source_url,
            observed_at=datetime.now(UTC),
            records=[],
            summary={},
            coverage={
                "reason": "login_required",
                "pages_scanned": 0,
                "records_seen": 0,
            },
            evidence={"capture_method": "url_state_only", "platform_adapter": platform},
        )

    async def collect_creator_page(
        self,
        *,
        owner_user_id: str,
        account_id: str,
        observation_key: str,
        dataset: str,
        session,
        target_url: str | None = None,
    ) -> dict[str, Any]:
        account = await self._accounts.get(account_id, owner_user_id=owner_user_id)
        if account is None or account.get("status") != "active":
            raise BrowserPlatformCollectionError("Active Personal-IP account not found")
        platform = str(account.get("platform") or "").strip()
        platform_config = BROWSER_PLATFORMS.get(platform)
        if platform_config is None:
            raise BrowserPlatformCollectionError("This account does not have a browser-first connector")
        dataset_key = str(dataset or "").strip()
        if dataset_key not in _BROWSER_DATASETS:
            raise BrowserPlatformCollectionError(f"Unsupported {platform_config.label} browser dataset")
        get_by_key = getattr(self._observations, "get_by_key", None)
        if callable(get_by_key):
            existing = await get_by_key(observation_key, owner_user_id=owner_user_id)
            if existing is not None:
                if existing.get("account_id") != account_id or existing.get("dataset") != dataset_key:
                    raise BrowserPlatformCollectionError("observation_key already records a different browser collection")
                return existing
        requested_url = _target_url(target_url, platform=platform) if target_url else None
        if requested_url is None and dataset_key == "dashboard":
            # A retained account session can be sitting on any page visited by
            # an earlier login, publish or collection operation. Dashboard
            # collection is a request for a fresh dashboard read, so route it
            # to the platform's registered analytics/home page instead of
            # interpreting whichever stale page happens to be open.
            requested_url = _target_url(platform_config.dashboard_url, platform=platform)

        before_url = str(await session.current_url() or "")
        if requested_url is not None:
            try:
                await session.navigate(requested_url)
            except Exception as exc:
                # Some creator backends render their authenticated SPA but
                # never finish Playwright's DOMContentLoaded wait. The visible
                # page is still collectible, so only a genuine navigation
                # timeout may continue into the normal URL/login and rendered-
                # DOM checks below. All other failures stay loud.
                if not _is_playwright_timeout_error(exc):
                    raise
        elif not browser_login_succeeded(platform, before_url):
            await session.navigate(platform_config.start_url)

        if self._settle_seconds:
            await asyncio.sleep(self._settle_seconds)

        current_url = str(await session.current_url() or requested_url or platform_config.start_url)
        login_succeeded = browser_login_succeeded(platform, current_url)
        if not login_succeeded:
            cookie_rule = browser_login_cookie_rule(platform, current_url)
            cookie_checker = getattr(session, "has_first_party_cookie_set", None)
            if cookie_rule is not None and callable(cookie_checker):
                login_succeeded = await cookie_checker(
                    domains=cookie_rule.hosts,
                    cookie_sets=cookie_rule.cookie_sets,
                )
        if not login_succeeded:
            return await self._unavailable(
                owner_user_id=owner_user_id,
                account_id=account_id,
                observation_key=observation_key,
                dataset=dataset_key,
                source_url=_safe_url(current_url),
                platform=platform,
            )

        extracted = await session.extract_business_page(max_chars=60_000, max_rows=500)
        capture_attempts = 1
        # Douyin's creator home can remain on its own loading shell longer
        # when several independent platform profiles are refreshed together.
        # Keep polling rendered DOM rather than returning a false empty result;
        # the UI now exposes this wait as account-collection progress.
        maximum_attempts = (12 if platform == "douyin" else 6) if self._settle_seconds else 1
        while not _rendered_data_ready(extracted) and capture_attempts < maximum_attempts:
            await asyncio.sleep(self._settle_seconds)
            extracted = await session.extract_business_page(max_chars=60_000, max_rows=500)
            capture_attempts += 1
        if not isinstance(extracted, dict):
            raise BrowserPlatformCollectionError(f"{platform_config.label} creator page extraction returned no structured data")
        source_url = _safe_url(extracted.get("url") or current_url)
        _target_url(source_url, platform=platform)
        if not login_succeeded and not browser_login_succeeded(platform, source_url):
            return await self._unavailable(
                owner_user_id=owner_user_id,
                account_id=account_id,
                observation_key=observation_key,
                dataset=dataset_key,
                source_url=source_url,
                platform=platform,
            )

        tables = _tables(extracted.get("tables"))
        table_row_count = sum(len(table["rows"]) for table in tables)
        visible_text = _clean_text(extracted.get("visible_text"), limit=60_000)
        record = {
            "record_type": "page_capture",
            "page_title": _clean_text(extracted.get("title"), limit=500),
            "headings": _text_list(extracted.get("headings"), item_limit=500, count_limit=100),
            "tables": tables,
            "data_blocks": _text_list(extracted.get("data_blocks"), item_limit=1_000, count_limit=200),
            "links": _links(extracted.get("links")),
            "visible_text": visible_text,
        }
        records: list[dict[str, Any]] = [record]
        status = "partial"
        summary: dict[str, Any] = {
            "heading_count": len(record["headings"]),
            "table_count": len(tables),
            "table_row_count": table_row_count,
            "data_block_count": len(record["data_blocks"]),
            "link_count": len(record["links"]),
            "visible_text_characters": len(visible_text),
        }
        pagination_state = "single_loaded_page"
        platform_adapter = "generic_rendered_dom"
        if dataset_key == "dashboard":
            parsed_dashboard = parse_browser_dashboard_metrics(platform, visible_text)
            record["direct_metrics"] = parsed_dashboard["metrics"]
            record["metric_labels"] = parsed_dashboard["metric_labels"]
            record["metric_window"] = parsed_dashboard["window"]
            summary.update(
                {
                    "direct_metrics": parsed_dashboard["metrics"],
                    "metric_labels": parsed_dashboard["metric_labels"],
                    "metric_window": parsed_dashboard["window"],
                }
            )
            if platform == "douyin":
                summary.update(parse_douyin_dashboard_summary(visible_text))
            platform_adapter = f"{platform}_dashboard_rendered_labels_v1"
        elif platform == "douyin" and dataset_key == "content_inventory":
            parsed_inventory = parse_douyin_content_inventory(visible_text)
            items = parsed_inventory["items"]
            records.extend(items)
            declared_count = parsed_inventory["declared_content_count"]
            listing_complete = bool(parsed_inventory["listing_complete"])
            summary.update(
                {
                    "declared_content_count": declared_count,
                    "parsed_content_count": len(items),
                    "private_content_count": sum(item["visibility"] == "private" for item in items),
                }
            )
            for metric in ("views", "likes", "comments", "shares"):
                values = [item["metrics"][metric] for item in items if item["metrics"].get(metric) is not None]
                summary[f"{metric}_snapshot"] = sum(values) if values else None
                summary[f"{metric}_observed_content_count"] = len(values)
            if listing_complete:
                pagination_state = "complete_listing"
            if listing_complete and declared_count is not None and declared_count == len(items):
                status = "observed"
            platform_adapter = "douyin_content_inventory_v1"
        screenshot = await session.screenshot_bytes(full_page=True)
        screenshot_digest = hashlib.sha256(bytes(screenshot)).hexdigest()
        observed_at = datetime.now(UTC)
        return await self._observations.record(
            owner_user_id=owner_user_id,
            observation_key=observation_key,
            account_id=account_id,
            dataset=dataset_key,
            source="browser",
            status=status,
            source_url=source_url,
            observed_at=observed_at,
            records=records,
            summary=summary,
            coverage={
                "pages_scanned": 1,
                "records_seen": len(records),
                "pagination_state": pagination_state,
                "render_state": "ready" if _rendered_data_ready(extracted) else "loading_timeout",
                "capture_attempts": capture_attempts,
                "text_truncated": bool(extracted.get("text_truncated")),
                "table_row_limit": 500,
                "platform_adapter": platform_adapter,
            },
            evidence={
                "capture_method": "rendered_dom_and_full_page_screenshot_digest",
                "screenshot_sha256": screenshot_digest,
                "field_sources": {
                    "records[0].visible_text": "rendered document body",
                    "records[0].tables": "rendered table/grid cells",
                    "records[0].data_blocks": "rendered statistic/metric/summary cards",
                    "records[1:]": "deterministically parsed rendered content cards",
                },
            },
        )


def _utc_datetime(value: datetime, *, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise BrowserPlatformCollectionError(f"{field} must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _observation_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _utc_datetime(value, field="observed_at")
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BrowserPlatformCollectionError("Browser observation returned an invalid observed_at") from exc
    return _utc_datetime(parsed, field="observed_at")


def _portfolio_key(prefix: str, *, collection_key: str, account_id: str) -> str:
    collection = " ".join(str(collection_key or "").split())
    if not collection or len(collection) > 128:
        raise BrowserPlatformCollectionError("collection_key must contain 1 to 128 characters")
    digest = hashlib.sha256(f"{collection}|{account_id}".encode()).hexdigest()
    return f"{prefix}:{digest}"


class BrowserPortfolioMetricCollectionService:
    """Collect and aggregate today's direct dashboard metrics for every account."""

    def __init__(
        self,
        *,
        accounts,
        observations,
        metrics,
        session_factory: Callable[..., Any] = acquire_account_browser_session,
        page_collector: BrowserPlatformCollectionService | None = None,
    ) -> None:
        self._accounts = accounts
        self._metrics = metrics
        self._session_factory = session_factory
        self._page_collector = page_collector or BrowserPlatformCollectionService(
            accounts=accounts,
            observations=observations,
        )

    async def collect_today(
        self,
        *,
        owner_user_id: str,
        collection_key: str,
        window_started_at: datetime,
        window_ended_at: datetime,
    ) -> dict[str, Any]:
        if not isinstance(window_started_at, datetime) or window_started_at.tzinfo is None:
            raise BrowserPlatformCollectionError("window_started_at must include the local timezone")
        if any((window_started_at.hour, window_started_at.minute, window_started_at.second, window_started_at.microsecond)):
            raise BrowserPlatformCollectionError("window_started_at must be local-day midnight")
        started = _utc_datetime(window_started_at, field="window_started_at")
        ended = _utc_datetime(window_ended_at, field="window_ended_at")
        if started >= ended or (ended - started).total_seconds() > 26 * 60 * 60:
            raise BrowserPlatformCollectionError("today window must be a positive interval no longer than 26 hours")
        accounts = await self._accounts.list(owner_user_id, include_archived=False)
        results: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        unsupported_account_ids: list[str] = []
        aggregate_ended_at = ended

        for account in accounts:
            account_id = str(account.get("id") or "").strip()
            platform = str(account.get("platform") or "").strip()
            config = BROWSER_PLATFORMS.get(platform)
            if not account_id or config is None:
                if account_id:
                    unsupported_account_ids.append(account_id)
                continue
            observation_key = _portfolio_key(
                "browser-portfolio-observation",
                collection_key=collection_key,
                account_id=account_id,
            )
            metric_key = _portfolio_key(
                "browser-portfolio-metric",
                collection_key=collection_key,
                account_id=account_id,
            )
            try:
                with self._session_factory(owner_user_id=owner_user_id, account=account) as session:
                    observation = await self._page_collector.collect_creator_page(
                        owner_user_id=owner_user_id,
                        account_id=account_id,
                        observation_key=observation_key,
                        dataset="dashboard",
                        target_url=config.dashboard_url,
                        session=session,
                    )
                summary = observation.get("summary") if isinstance(observation.get("summary"), dict) else {}
                direct_metrics = summary.get("direct_metrics") if isinstance(summary.get("direct_metrics"), dict) else {}
                metric_window = summary.get("metric_window") if isinstance(summary.get("metric_window"), dict) else {}
                page_status = str(observation.get("status") or "unavailable")
                reason: str | None = None
                if page_status == "unavailable":
                    metric_status = "unavailable"
                    metrics: dict[str, int | float] = {}
                    observation_coverage = observation.get("coverage") if isinstance(observation.get("coverage"), dict) else {}
                    reason = str(observation_coverage.get("reason") or "browser_page_unavailable")
                elif metric_window.get("kind") != "today":
                    metric_status = "unavailable"
                    metrics = {}
                    reason = "today_window_not_displayed"
                elif not isinstance(direct_metrics.get("views"), (int, float)) or isinstance(direct_metrics.get("views"), bool):
                    metric_status = "unavailable"
                    metrics = {}
                    reason = "today_views_not_extracted"
                else:
                    metric_status = "partial"
                    metrics = {key: value for key, value in direct_metrics.items() if isinstance(value, (int, float)) and not isinstance(value, bool)}
                observed_at = _observation_datetime(observation.get("observed_at"))
                if observed_at <= started or (observed_at - started).total_seconds() > 26 * 60 * 60:
                    raise BrowserPlatformCollectionError("Browser observation falls outside the requested today interval")
                aggregate_ended_at = max(aggregate_ended_at, observed_at)
                coverage = {
                    "collection": "browser_rendered_dashboard",
                    "complete_account_window": False,
                    "displayed_window": metric_window,
                    "platform_observation_id": observation.get("id"),
                    "platform_observation_status": page_status,
                    "requested_window_ended_at": ended.isoformat(),
                    "requested_window_kind": "today",
                }
                if reason is not None:
                    coverage["reason"] = reason
                metric = await self._metrics.record(
                    owner_user_id=owner_user_id,
                    observation_key=metric_key,
                    series_key=f"browser-dashboard:{platform}:{account_id}",
                    account_id=account_id,
                    receipt_id=None,
                    scope="account",
                    metric_mode="window_total",
                    source="browser",
                    status=metric_status,
                    window_started_at=started,
                    window_ended_at=observed_at,
                    observed_at=observed_at,
                    metrics=metrics,
                    coverage=coverage,
                )
                results.append(
                    {
                        "account_id": account_id,
                        "platform": platform,
                        "status": metric_status,
                        "reason": reason,
                        "platform_observation_id": observation.get("id"),
                        "metric_observation_id": metric.get("id"),
                    }
                )
            except BrowserPlatformCollectionError:
                failures.append({"account_id": account_id, "platform": platform, "category": "collection_unavailable"})
            except (RuntimeError, TypeError, ValueError):
                failures.append({"account_id": account_id, "platform": platform, "category": "invalid_collection_result"})
            except Exception:
                failures.append({"account_id": account_id, "platform": platform, "category": "internal"})

        aggregate = await self._metrics.aggregate(
            owner_user_id=owner_user_id,
            window_started_at=started,
            window_ended_at=aggregate_ended_at,
        )
        account_statuses = aggregate.get("coverage", {}).get("by_account_status", {})
        platform_coverage: dict[str, dict[str, Any]] = {}
        for platform in BROWSER_PLATFORMS:
            platform_account_ids = sorted(str(account.get("id")) for account in accounts if account.get("platform") == platform and account.get("id"))
            statuses = {str(account_statuses.get(account_id) or "missing") for account_id in platform_account_ids}
            if not platform_account_ids:
                status = "not_configured"
            elif statuses == {"observed"}:
                status = "observed"
            elif statuses == {"unavailable"}:
                status = "unavailable"
            elif statuses == {"missing"}:
                status = "missing"
            else:
                status = "partial"
            platform_coverage[platform] = {
                "status": status,
                "active_account_ids": platform_account_ids,
            }

        coverage = aggregate.get("coverage", {})
        incomplete = bool(coverage.get("partial_account_ids") or coverage.get("unavailable_account_ids") or coverage.get("missing_account_ids"))
        return {
            "status": "partial" if incomplete else ("complete" if accounts else "unavailable"),
            "collection_key": " ".join(str(collection_key or "").split()),
            "requested_window_ended_at": ended.isoformat(),
            "account_count": len(accounts),
            "collected_count": len(results),
            "failure_count": len(failures),
            "results": results,
            "failures": failures,
            "coverage": {
                "unsupported_account_ids": sorted(unsupported_account_ids),
                "platforms": platform_coverage,
            },
            "aggregate": aggregate,
        }


DouyinBrowserCollectionService = BrowserPlatformCollectionService
