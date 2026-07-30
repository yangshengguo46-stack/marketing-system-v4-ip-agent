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
    dashboard_url: str
    creator_hosts: tuple[str, ...] = ()
    authenticated_hosts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowserLoginCookieRule:
    hosts: tuple[str, ...]
    cookie_sets: tuple[tuple[str, ...], ...]


BROWSER_PLATFORMS: dict[str, BrowserPlatform] = {
    "douyin": BrowserPlatform(
        "抖音",
        "https://creator.douyin.com/",
        "https://creator.douyin.com/creator-micro/home",
    ),
    "wechat_channels": BrowserPlatform(
        "视频号",
        "https://channels.weixin.qq.com/platform",
        "https://channels.weixin.qq.com/platform/data/overview",
    ),
    "wechat_official": BrowserPlatform(
        "公众号",
        "https://mp.weixin.qq.com/",
        "https://mp.weixin.qq.com/",
    ),
    "xiaohongshu": BrowserPlatform(
        "小红书",
        "https://creator.xiaohongshu.com/",
        "https://creator.xiaohongshu.com/new/home",
    ),
    "x": BrowserPlatform(
        "X",
        "https://x.com/",
        "https://analytics.x.com/",
        creator_hosts=("analytics.x.com",),
        authenticated_hosts=("analytics.x.com",),
    ),
    "instagram": BrowserPlatform(
        "Instagram",
        "https://www.instagram.com/",
        "https://www.instagram.com/professional_dashboard/",
    ),
    "youtube": BrowserPlatform(
        "YouTube",
        "https://studio.youtube.com/",
        "https://studio.youtube.com/",
    ),
    "tiktok": BrowserPlatform(
        "TikTok",
        "https://www.tiktok.com/tiktokstudio",
        "https://www.tiktok.com/tiktokstudio/analytics",
    ),
}

_LOGIN_COOKIE_RULES: dict[str, BrowserLoginCookieRule] = {
    "douyin": BrowserLoginCookieRule(
        hosts=("douyin.com",),
        cookie_sets=(("sessionid",), ("sessionid_ss",), ("sid_guard",)),
    ),
    "wechat_channels": BrowserLoginCookieRule(
        hosts=("channels.weixin.qq.com",),
        cookie_sets=(("finder_username",), ("wxuin", "pass_ticket"), ("wxuin", "sessionid")),
    ),
    "wechat_official": BrowserLoginCookieRule(
        hosts=("mp.weixin.qq.com",),
        cookie_sets=(("slave_sid", "slave_user"),),
    ),
    "xiaohongshu": BrowserLoginCookieRule(
        hosts=("xiaohongshu.com",),
        cookie_sets=(("web_session",),),
    ),
    "x": BrowserLoginCookieRule(
        hosts=("x.com", "twitter.com"),
        cookie_sets=(("auth_token", "ct0"),),
    ),
    "instagram": BrowserLoginCookieRule(
        hosts=("instagram.com",),
        cookie_sets=(("sessionid", "ds_user_id"),),
    ),
    "youtube": BrowserLoginCookieRule(
        hosts=("youtube.com", "google.com"),
        cookie_sets=(("SAPISID", "SID"),),
    ),
    "tiktok": BrowserLoginCookieRule(
        hosts=("tiktok.com",),
        cookie_sets=(("sessionid",), ("sessionid_ss",), ("sid_tt",)),
    ),
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
_DOUYIN_LOGIN_TEXT_MARKERS = (
    "接收短信验证码",
    "请输入验证码",
    "扫码登录",
    "验证码登录",
    "手机号登录",
)
_DOUYIN_DASHBOARD_TEXT_MARKERS = (
    "机构服务权益",
    "入驻签约",
    "达人管理",
    "经营分析",
    "成长激励",
)


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
    allowed_hosts = {expected_host, *config.creator_hosts}
    return host in allowed_hosts and any(marker in path for marker in _LOGIN_CHALLENGE_PATH_MARKERS)


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
    host = (parsed.hostname or "").lower()
    if host not in {expected_host, *config.creator_hosts}:
        return False
    path = parsed.path.lower() or "/"
    if host in config.authenticated_hosts and not browser_login_challenge(platform, url):
        return True
    if any(_path_matches_prefix(path, prefix) for prefix in _LOGIN_SUCCESS_PATH_PREFIXES.get(platform, ())):
        return True
    return challenge_seen and platform in _CHALLENGE_RETURN_PLATFORMS and not browser_login_challenge(platform, url)


def browser_login_page_succeeded(platform: str, url: str, page_text: str) -> bool:
    """Recognize authenticated same-URL dashboards without reading credentials."""
    if platform != "douyin" or browser_login_challenge(platform, url):
        return False
    config = BROWSER_PLATFORMS[platform]
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    expected_host = (urlsplit(config.start_url).hostname or "").lower()
    if (parsed.hostname or "").lower() != expected_host:
        return False

    normalized_text = " ".join(page_text.split())
    if any(marker in normalized_text for marker in _DOUYIN_LOGIN_TEXT_MARKERS):
        return False
    dashboard_matches = sum(marker in normalized_text for marker in _DOUYIN_DASHBOARD_TEXT_MARKERS)
    return dashboard_matches >= 2


def browser_login_cookie_rule(
    platform: str,
    url: str,
) -> BrowserLoginCookieRule | None:
    """Return a first-party cookie-name rule only on the platform's own page."""
    rule = _LOGIN_COOKIE_RULES.get(platform)
    if rule is None:
        return None
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in rule.hosts):
        return None
    return rule


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
