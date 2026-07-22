"""Credential-free proof checks for browser-first publication receipts."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_PLATFORM_HOSTS: dict[str, tuple[str, ...]] = {
    "douyin": ("douyin.com",),
    "wechat_channels": ("channels.weixin.qq.com", "weixin.qq.com"),
    "wechat_official": ("mp.weixin.qq.com",),
    "xiaohongshu": ("xiaohongshu.com",),
    "x": ("x.com", "twitter.com"),
    "instagram": ("instagram.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
}
_SAFE_PUBLIC_QUERY_KEYS: dict[str, frozenset[str]] = {
    "wechat_channels": frozenset({"feedId"}),
    "youtube": frozenset({"v"}),
    "wechat_official": frozenset({"__biz", "mid", "idx", "sn"}),
}


def _path_match(path: str, pattern: str) -> str | None:
    match = re.fullmatch(pattern, path.rstrip("/") or "/", flags=re.IGNORECASE)
    if match is None:
        return None
    return str(match.group(1) or "").strip() or None


def _publication_page_id(platform: str, url: str) -> str | None:
    """Return the post-specific identifier encoded by a public page URL."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    if platform == "douyin":
        return _path_match(path, r"/(?:video|note)/([^/]+)")
    if platform == "wechat_channels":
        if host == "channels.weixin.qq.com" and path.rstrip("/").lower() == "/web/pages/feed":
            return str(query.get("feedId") or "").strip() or None
        if host == "weixin.qq.com":
            return _path_match(path, r"/sph/([^/]+)")
        return None
    if platform == "wechat_official":
        path_id = _path_match(path, r"/s/([^/]+)")
        if path_id:
            return path_id
        if path.rstrip("/").lower() == "/s" and all(query.get(key) for key in ("__biz", "mid", "idx")):
            return f"{query['mid']}:{query['idx']}"
        return None
    if platform == "xiaohongshu":
        return _path_match(path, r"/(?:explore|discovery/item)/([^/]+)")
    if platform == "x":
        return _path_match(path, r"/(?:[^/]+/status|i/web/status)/([^/]+)")
    if platform == "instagram":
        return _path_match(path, r"/(?:p|reel|tv)/([^/]+)")
    if platform == "youtube":
        if host == "youtu.be":
            return _path_match(path, r"/([^/]+)")
        if path.rstrip("/").lower() == "/watch":
            return str(query.get("v") or "").strip() or None
        return _path_match(path, r"/(?:shorts|live)/([^/]+)")
    if platform == "tiktok":
        return _path_match(path, r"/@[^/]+/(?:video|photo)/([^/]+)")
    return None


def normalize_publication_url(value: Any, *, platform: str) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("publication evidence URL must be HTTP(S)")
    host = parsed.hostname.lower()
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    safe_keys = _SAFE_PUBLIC_QUERY_KEYS.get(platform, frozenset())
    safe_query = urlencode(sorted((key, item) for key, item in parse_qsl(parsed.query, keep_blank_values=False) if key in safe_keys))
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), host, path, safe_query, ""))


def _host_matches(platform: str, url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _PLATFORM_HOSTS.get(platform, ()))


def verify_browser_publication_evidence(
    *,
    platform: str,
    observed_url: str,
    page_title: str,
    visible_text: str,
    external_url: str | None,
    external_post_id: str | None,
) -> dict[str, Any]:
    """Require the selected browser to visibly prove the declared publication."""
    observed = normalize_publication_url(observed_url, platform=platform)
    if not _host_matches(platform, observed):
        raise ValueError("browser is not showing the selected platform")
    observed_page_id = _publication_page_id(platform, observed)
    if observed_page_id is None:
        raise ValueError("browser is not showing a public post on the selected platform")
    declared_url = normalize_publication_url(external_url, platform=platform) if external_url else None
    post_id = str(external_post_id or "").strip() or None
    if declared_url is None and post_id is None:
        raise ValueError("published browser attempts require an external post URL or post id")
    if declared_url is not None:
        if not platform_publication_url_allowed(platform, declared_url):
            raise ValueError("external post URL is not a public post on the selected platform")
        if declared_url != observed:
            raise ValueError("browser must open the declared published post before sealing success")
    if post_id is not None and post_id != observed_page_id and post_id not in visible_text:
        raise ValueError("external post id is not visible in the current browser evidence")
    text_bytes = visible_text.encode("utf-8")
    return {
        "proof_type": "live_browser_publication_page",
        "observed_url": observed,
        "page_title": " ".join(str(page_title or "").split())[:500],
        "visible_text_sha256": hashlib.sha256(text_bytes).hexdigest(),
        "visible_text_bytes": len(text_bytes),
    }


def platform_publication_url_allowed(platform: str, url: str) -> bool:
    """Return whether a URL identifies a public post on the platform."""
    try:
        normalized = normalize_publication_url(url, platform=platform)
    except ValueError:
        return False
    return _host_matches(platform, normalized) and _publication_page_id(platform, normalized) is not None
