"""First-party, bounded Douyin public-web adapter for the evidence MCP.

The adapter intentionally uses ordinary rendered pages and a user-authorized
persistent browser profile.  It does not implement signature reverse
engineering, export cookies, persist raw responses, or infer that site-wide
recommendations belong to the requested account.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from deerflow.community.url_safety import resolve_host_addresses, validate_public_http_url

DOUYIN_INPUT_HOSTS = frozenset(
    {
        "douyin.com",
        "www.douyin.com",
        "v.douyin.com",
        "iesdouyin.com",
        "www.iesdouyin.com",
    }
)
DOUYIN_VIDEO_PATH = re.compile(r"/(?:share/)?video/(?P<id>[0-9]{8,})")
DOUYIN_PROFILE_PATH = re.compile(r"/(?:share/)?user/(?P<sec_uid>[A-Za-z0-9_-]{16,})")
DOUYIN_WORK_SCOPE = '[data-e2e="user-post-list"]'

_MAX_CAPTURE_BYTES = 5 * 1024 * 1024
_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
_MAX_REDIRECTS = 6
_API_PATH_MARKERS = ("/aweme/v1/web/aweme/post/", "/aweme/v1/web/aweme/detail/")
_SESSION_COOKIE_NAMES = frozenset({"sessionid", "sessionid_ss", "sid_guard", "uid_tt", "uid_tt_ss"})


def _clean_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def canonical_http_url(value: str) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError as exc:
        raise ValueError("reference must be a valid HTTP(S) URL") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("reference must be a valid HTTP(S) URL")
    host = parsed.hostname.lower()
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme.lower(), host, parsed.path or "/", "", ""))


def validate_public_url(value: str, *, action: str) -> None:
    error = validate_public_http_url(
        value,
        allow_proxy_fake_ip=True,
        action=action,
        resolver=resolve_host_addresses,
    )
    if error:
        raise ValueError(error.removeprefix("Error: ").strip())


def validate_douyin_reference(value: str) -> str:
    canonical = canonical_http_url(value)
    host = (urlsplit(canonical).hostname or "").lower()
    if host not in DOUYIN_INPUT_HOSTS:
        raise ValueError("reference must be a Douyin profile, work, or share URL")
    validate_public_url(value, action="inspect")
    return canonical


def _headless() -> bool:
    return os.getenv("IP_AGENT_EVIDENCE_BROWSER_HEADLESS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _timeout_ms() -> int:
    raw = os.getenv("IP_AGENT_EVIDENCE_BROWSER_TIMEOUT_MS", "30000")
    with contextlib.suppress(ValueError):
        return max(5_000, min(int(raw), 120_000))
    return 30_000


def _configured_profile_dir() -> Path | None:
    raw = os.getenv("IP_AGENT_EVIDENCE_BROWSER_PROFILE_DIR", "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


async def _resolve_bounded_redirects(value: str) -> str:
    """Resolve ordinary redirects while requiring every document hop to stay on Douyin."""
    current = str(value or "").strip()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; IP-Agent-Evidence/1.0)"}
    async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS):
            validate_douyin_reference(current)
            response = await client.get(current)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return current
            location = response.headers.get("location")
            if not location:
                raise ValueError("Douyin redirect did not provide a location")
            current = urljoin(current, location)
    raise ValueError("Douyin reference exceeded the redirect limit")


def _aweme_candidates(payload: Any, *, depth: int = 0, visited: int = 0) -> list[Mapping[str, Any]]:
    if depth > 5 or visited > 500:
        return []
    if isinstance(payload, Mapping):
        candidates: list[Mapping[str, Any]] = []
        detail = payload.get("aweme_detail")
        if isinstance(detail, Mapping):
            candidates.append(detail)
        aweme_list = payload.get("aweme_list")
        if isinstance(aweme_list, list):
            candidates.extend(item for item in aweme_list[:20] if isinstance(item, Mapping))
        for key in ("data", "result", "aweme", "item_list"):
            child = payload.get(key)
            if isinstance(child, Mapping | list):
                candidates.extend(_aweme_candidates(child, depth=depth + 1, visited=visited + len(candidates)))
        return candidates
    if isinstance(payload, list):
        candidates: list[Mapping[str, Any]] = []
        for item in payload[:20]:
            candidates.extend(_aweme_candidates(item, depth=depth + 1, visited=visited + len(candidates)))
        return candidates
    return []


def _optional_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return value
    return None


def _work_from_aweme(item: Mapping[str, Any], *, expected_sec_uid: str) -> dict[str, Any] | None:
    author = item.get("author")
    if not isinstance(author, Mapping) or str(author.get("sec_uid") or "") != expected_sec_uid:
        return None
    work_id = str(item.get("aweme_id") or "").strip()
    if not work_id.isdigit() or len(work_id) < 8:
        return None
    statistics = item.get("statistics") if isinstance(item.get("statistics"), Mapping) else {}
    engagement = {
        "likes": _optional_number(statistics.get("digg_count")),
        "comments": _optional_number(statistics.get("comment_count")),
        "shares": _optional_number(statistics.get("share_count")),
        "collects": _optional_number(statistics.get("collect_count")),
    }
    engagement = {key: value for key, value in engagement.items() if value is not None}
    created = item.get("create_time")
    published_at = None
    if isinstance(created, int | float) and not isinstance(created, bool) and created > 0:
        with contextlib.suppress(ValueError, OSError, OverflowError):
            published_at = datetime.fromtimestamp(float(created), tz=UTC).isoformat()
    return {
        "work_id": work_id,
        "work_url": f"https://www.douyin.com/video/{work_id}",
        "visible_label": None,
        "title": _clean_text(item.get("desc"), limit=500) or None,
        "is_pinned": True if item.get("is_top") in {1, True} else None,
        "published_label": None,
        "published_at": published_at,
        "public_engagement": engagement or None,
        "ownership_evidence": "api_author_match",
    }


def _profile_from_aweme(item: Mapping[str, Any], *, expected_sec_uid: str) -> dict[str, Any] | None:
    author = item.get("author")
    if not isinstance(author, Mapping) or str(author.get("sec_uid") or "") != expected_sec_uid:
        return None
    return {
        "display_name": _clean_text(author.get("nickname"), limit=100) or None,
        "visible_profile_text": _clean_text(author.get("signature"), limit=1_000) or None,
    }


async def _launch_context(*, headless: bool):
    try:
        from playwright.async_api import async_playwright  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on browser extra
        raise RuntimeError("Playwright browser support is not installed") from exc

    temporary: tempfile.TemporaryDirectory[str] | None = None
    profile_dir = _configured_profile_dir()
    if profile_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="ip-evidence-browser-")
        profile_dir = Path(temporary.name)
    playwright = await async_playwright().start()
    try:
        context = await playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=headless,
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
        )
    except Exception:
        await playwright.stop()
        if temporary is not None:
            temporary.cleanup()
        raise
    return playwright, context, temporary


async def _close_context(playwright: Any, context: Any, temporary: tempfile.TemporaryDirectory[str] | None) -> None:
    with contextlib.suppress(Exception):
        await context.close()
    with contextlib.suppress(Exception):
        await playwright.stop()
    if temporary is not None:
        temporary.cleanup()


async def _guard_document_route(route: Any, request: Any) -> None:
    if request.resource_type == "document":
        with contextlib.suppress(ValueError):
            canonical = canonical_http_url(request.url)
            if (urlsplit(canonical).hostname or "").lower() in DOUYIN_INPUT_HOSTS:
                await route.continue_()
                return
        await route.abort()
        return
    await route.continue_()


async def fetch_douyin_account_pages(url: str, max_posts: int, _session_hint: str | None = None) -> list[dict[str, Any]]:
    """Read only the requested profile header, post DOM scope and author-matched API items."""
    validate_douyin_reference(url)
    resolved = await _resolve_bounded_redirects(url)
    playwright, context, temporary = await _launch_context(headless=_headless())
    page = context.pages[0] if context.pages else await context.new_page()
    captured_responses: list[Any] = []

    def capture(response: Any) -> None:
        if not any(marker in response.url for marker in _API_PATH_MARKERS):
            return
        length = response.headers.get("content-length")
        if length:
            with contextlib.suppress(ValueError):
                if int(length) > _MAX_CAPTURE_BYTES:
                    return
        captured_responses.append(response)

    page.on("response", capture)
    await page.route("**/*", _guard_document_route)
    pages: list[dict[str, Any]] = []
    try:
        try:
            await page.goto(resolved, wait_until="domcontentloaded", timeout=_timeout_ms())
        except Exception as exc:
            if exc.__class__.__name__ != "TimeoutError":
                raise
        await page.wait_for_timeout(1_500)
        final_url = page.url
        validate_douyin_reference(final_url)
        profile_match = DOUYIN_PROFILE_PATH.search(urlsplit(canonical_http_url(final_url)).path)
        if profile_match is None:
            raise ValueError("reference did not resolve to a Douyin account profile")
        expected_sec_uid = profile_match.group("sec_uid")

        for _ in range(6):
            scoped = await page.evaluate(
                """
                ({ selector, limit }) => {
                  const clean = (value, max) => String(value || '').replace(/\\s+/g, ' ').trim().slice(0, max);
                  const root = document.querySelector(selector);
                  const header = document.querySelector('[data-e2e="user-info"]') ||
                    document.querySelector('[data-e2e="user-detail"]') ||
                    document.querySelector('main header');
                  const links = [];
                  if (root) {
                    for (const link of root.querySelectorAll('a[href]')) {
                      let href = '';
                      try {
                        const parsed = new URL(link.href, location.href);
                        href = parsed.origin + parsed.pathname;
                      } catch (_) {}
                      const text = clean(link.innerText || link.getAttribute('aria-label'), 500);
                      if (href || text) links.push({href, text});
                      if (links.length >= limit) break;
                    }
                  }
                  return {
                    title: clean(document.title, 300),
                    headings: header ? Array.from(header.querySelectorAll('h1,h2,[data-e2e="user-info-name"]')).map(x => clean(x.innerText, 200)).filter(Boolean).slice(0, 10) : [],
                    profile_text: header ? clean(header.innerText, 2000) : null,
                    scope_found: Boolean(root),
                    work_links: links,
                  };
                }
                """,
                {"selector": DOUYIN_WORK_SCOPE, "limit": max(1, min(max_posts, 12))},
            )
            pages.append(
                {
                    "url": final_url,
                    "title": scoped.get("title"),
                    "headings": scoped.get("headings") or [],
                    "visible_text": scoped.get("profile_text"),
                    "work_links": scoped.get("work_links") or [],
                    "work_scope_found": bool(scoped.get("scope_found")),
                    "account_sec_uid": expected_sec_uid,
                }
            )
            observed = {match.group("id") for link in scoped.get("work_links") or [] if isinstance(link, Mapping) and (match := DOUYIN_VIDEO_PATH.search(urlsplit(str(link.get("href") or "")).path)) is not None}
            if len(observed) >= max_posts:
                break
            await page.mouse.wheel(0, 1_600)
            await page.wait_for_timeout(500)

        captured_awemes: list[Mapping[str, Any]] = []
        for response in captured_responses:
            with contextlib.suppress(Exception):
                captured_awemes.extend(_aweme_candidates(await response.json())[:20])
        api_works: list[dict[str, Any]] = []
        api_profile = None
        seen: set[str] = set()
        for aweme in captured_awemes:
            work = _work_from_aweme(aweme, expected_sec_uid=expected_sec_uid)
            if work is None or work["work_id"] in seen:
                continue
            seen.add(work["work_id"])
            api_works.append(work)
            api_profile = api_profile or _profile_from_aweme(aweme, expected_sec_uid=expected_sec_uid)
            if len(api_works) >= max_posts:
                break
        if pages:
            pages[0]["api_works"] = api_works
            pages[0]["api_profile"] = api_profile
        return pages
    finally:
        page.remove_listener("response", capture)
        await _close_context(playwright, context, temporary)


def _video_metadata_from_aweme(item: Mapping[str, Any]) -> dict[str, Any]:
    author = item.get("author") if isinstance(item.get("author"), Mapping) else {}
    statistics = item.get("statistics") if isinstance(item.get("statistics"), Mapping) else {}
    return {
        key: value
        for key, value in {
            "id": item.get("aweme_id"),
            "title": _clean_text(item.get("desc"), limit=500) or None,
            "uploader": _clean_text(author.get("nickname"), limit=100) or None,
            "timestamp": item.get("create_time"),
            "duration": item.get("duration"),
            "like_count": _optional_number(statistics.get("digg_count")),
            "comment_count": _optional_number(statistics.get("comment_count")),
            "repost_count": _optional_number(statistics.get("share_count")),
        }.items()
        if value is not None
    }


def _media_urls_from_aweme(item: Mapping[str, Any]) -> list[str]:
    video = item.get("video") if isinstance(item.get("video"), Mapping) else {}
    urls: list[str] = []
    for key in ("play_addr", "download_addr", "play_addr_h264"):
        address = video.get(key)
        if not isinstance(address, Mapping):
            continue
        for value in address.get("url_list") or []:
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                urls.append(value)
    return urls


async def resolve_douyin_video(reference: str) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Resolve one exact work to a public media URL and internal-only browser cookies."""
    validate_douyin_reference(reference)
    resolved = await _resolve_bounded_redirects(reference)
    playwright, context, temporary = await _launch_context(headless=_headless())
    page = context.pages[0] if context.pages else await context.new_page()
    captured_responses: list[Any] = []

    def capture(response: Any) -> None:
        if not any(marker in response.url for marker in _API_PATH_MARKERS):
            return
        captured_responses.append(response)

    page.on("response", capture)
    await page.route("**/*", _guard_document_route)
    try:
        detail_response = None
        try:
            async with page.expect_response(
                lambda response: "/aweme/v1/web/aweme/detail/" in response.url,
                timeout=_timeout_ms(),
            ) as response_info:
                try:
                    await page.goto(resolved, wait_until="domcontentloaded", timeout=_timeout_ms())
                except Exception as exc:
                    if exc.__class__.__name__ != "TimeoutError":
                        raise
            detail_response = await response_info.value
        except Exception as exc:
            if exc.__class__.__name__ != "TimeoutError":
                raise
        await page.wait_for_timeout(2_000)
        validate_douyin_reference(page.url)
        expected = DOUYIN_VIDEO_PATH.search(urlsplit(canonical_http_url(page.url)).path)
        expected_id = expected.group("id") if expected else None
        captured_awemes: list[Mapping[str, Any]] = []
        if detail_response is not None:
            with contextlib.suppress(Exception):
                captured_awemes.extend(_aweme_candidates(await detail_response.json())[:10])
        for response in captured_responses:
            with contextlib.suppress(Exception):
                captured_awemes.extend(_aweme_candidates(await response.json())[:10])

        selected = next(
            (item for item in captured_awemes if expected_id is None or str(item.get("aweme_id") or "") == expected_id),
            None,
        )
        media_urls = _media_urls_from_aweme(selected) if selected is not None else []
        if not media_urls:
            current_src = await page.evaluate(
                """() => {
                  const video = document.querySelector('video');
                  return video ? (video.currentSrc || video.src || '') : '';
                }"""
            )
            if isinstance(current_src, str) and current_src.startswith(("http://", "https://")):
                media_urls.append(current_src)
        if not media_urls:
            raise ValueError("Douyin work page did not expose a verifiable media stream")
        media_url = media_urls[0]
        validate_public_url(media_url, action="download")
        cookies = await context.cookies([media_url])
        metadata = _video_metadata_from_aweme(selected) if selected is not None else {}
        return media_url, metadata, cookies
    finally:
        page.remove_listener("response", capture)
        await _close_context(playwright, context, temporary)


async def login_douyin() -> bool:
    """Open the dedicated evidence profile for a user-completed Douyin login."""
    if _configured_profile_dir() is None:
        raise RuntimeError("IP_AGENT_EVIDENCE_BROWSER_PROFILE_DIR is required for login")
    playwright, context, temporary = await _launch_context(headless=False)
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=_timeout_ms())
        print("请在浏览器中完成抖音登录。完成后回到终端按回车；Cookie 内容不会被打印或导出。", flush=True)
        await asyncio.to_thread(input)
        cookies = await context.cookies()
        return bool({str(item.get("name") or "") for item in cookies} & _SESSION_COOKIE_NAMES)
    finally:
        await _close_context(playwright, context, temporary)
