"""Account-scoped browser targets for local Personal-IP platform operation."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class BrowserPlatform:
    label: str
    start_url: str


BROWSER_PLATFORMS: dict[str, BrowserPlatform] = {
    "douyin": BrowserPlatform("抖音", "https://creator.douyin.com/"),
    "wechat_channels": BrowserPlatform("视频号", "https://channels.weixin.qq.com/platform"),
    "wechat_official": BrowserPlatform("公众号", "https://mp.weixin.qq.com/"),
    "xiaohongshu": BrowserPlatform("小红书", "https://creator.xiaohongshu.com/"),
    "x": BrowserPlatform("X", "https://x.com/"),
    "instagram": BrowserPlatform("Instagram", "https://www.instagram.com/"),
    "youtube": BrowserPlatform("YouTube", "https://studio.youtube.com/"),
    "tiktok": BrowserPlatform("TikTok", "https://www.tiktok.com/tiktokstudio"),
}

_LOGIN_SUCCESS_PATH_PREFIXES: dict[str, tuple[str, ...]] = {
    "douyin": ("/creator-micro/",),
    "wechat_channels": (
        "/platform/account",
        "/platform/content",
        "/platform/data",
        "/platform/home",
        "/platform/live",
        "/platform/post",
    ),
    "wechat_official": ("/cgi-bin/home",),
    "xiaohongshu": ("/creator/home", "/creator/creator/home", "/new/home"),
    "x": ("/home",),
    "instagram": ("/direct/", "/explore/"),
    "youtube": ("/channel/",),
    "tiktok": ("/creator-center/", "/tiktokstudio/analytics", "/tiktokstudio/content", "/tiktokstudio/upload"),
}

_LOGIN_CHALLENGE_HOSTS: dict[str, frozenset[str]] = {
    "douyin": frozenset({"sso.douyin.com"}),
    "youtube": frozenset({"accounts.google.com"}),
}

_LOGIN_CHALLENGE_PATH_MARKERS = (
    "/accounts/login",
    "/i/flow/login",
    "/login",
    "/passport",
    "/signin",
)

_CHALLENGE_RETURN_PLATFORMS = frozenset({"instagram", "tiktok"})


def _path_matches_prefix(path: str, prefix: str) -> bool:
    normalized = prefix.rstrip("/")
    return path == normalized or path.startswith(f"{normalized}/")


def browser_login_challenge(platform: str, url: str) -> bool:
    """Return whether *url* is a known sign-in challenge for the platform."""
    config = BROWSER_PLATFORMS.get(platform)
    if config is None:
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if host in _LOGIN_CHALLENGE_HOSTS.get(platform, frozenset()):
        return True
    expected_host = (urlsplit(config.start_url).hostname or "").lower()
    path = parsed.path.lower()
    return host == expected_host and any(marker in path for marker in _LOGIN_CHALLENGE_PATH_MARKERS)


def browser_login_succeeded(platform: str, url: str, *, challenge_seen: bool = False) -> bool:
    """Recognize only conservative, credential-free platform login signals."""
    config = BROWSER_PLATFORMS.get(platform)
    if config is None:
        return False
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    expected_host = (urlsplit(config.start_url).hostname or "").lower()
    if (parsed.hostname or "").lower() != expected_host:
        return False
    path = parsed.path.lower() or "/"
    if any(_path_matches_prefix(path, prefix) for prefix in _LOGIN_SUCCESS_PATH_PREFIXES.get(platform, ())):
        return True
    return challenge_seen and platform in _CHALLENGE_RETURN_PLATFORMS and not browser_login_challenge(platform, url)


@dataclass(frozen=True, slots=True)
class BrowserAccountTarget:
    owner_user_id: str
    thread_id: str | None
    account_id: str
    platform: str
    display_name: str
    session_key: str
    user_data_dir: Path
    start_url: str


_targets: dict[tuple[str, str], BrowserAccountTarget] = {}
_targets_lock = threading.Lock()


def build_browser_account_target(
    *,
    owner_user_id: str,
    account_id: str,
    platform: str,
    display_name: str,
    user_data_dir: Path,
    thread_id: str | None = None,
) -> BrowserAccountTarget:
    """Build the persistent browser target shared by chat and account login UI."""
    platform_config = BROWSER_PLATFORMS.get(platform)
    if platform_config is None:
        raise ValueError("This platform does not have a browser-first connector")
    return BrowserAccountTarget(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        account_id=account_id,
        platform=platform,
        display_name=display_name,
        session_key=f"account:{owner_user_id}:{account_id}",
        user_data_dir=user_data_dir,
        start_url=platform_config.start_url,
    )


def select_browser_account_target(
    *,
    owner_user_id: str,
    thread_id: str,
    account_id: str,
    platform: str,
    display_name: str,
    user_data_dir: Path,
) -> BrowserAccountTarget:
    """Select one concrete browser target without changing conversation authority."""
    target = build_browser_account_target(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        account_id=account_id,
        platform=platform,
        display_name=display_name,
        user_data_dir=user_data_dir,
    )
    with _targets_lock:
        _targets[(owner_user_id, thread_id)] = target
    return target


def get_browser_account_target(*, owner_user_id: str, thread_id: str) -> BrowserAccountTarget | None:
    with _targets_lock:
        return _targets.get((owner_user_id, thread_id))


def clear_browser_account_target(*, owner_user_id: str, thread_id: str) -> None:
    with _targets_lock:
        _targets.pop((owner_user_id, thread_id), None)
