import pytest

from deerflow.personal_ip.browser_profiles import (
    BROWSER_PLATFORMS,
    browser_login_challenge,
    browser_login_cookie_rule,
    browser_login_page_succeeded,
    browser_login_succeeded,
    build_browser_account_target,
)

EXPECTED_PLATFORM_START_URLS = {
    "douyin": "https://creator.douyin.com/",
    "wechat_channels": "https://channels.weixin.qq.com/platform",
    "wechat_official": "https://mp.weixin.qq.com/",
    "xiaohongshu": "https://creator.xiaohongshu.com/",
    "x": "https://x.com/",
    "instagram": "https://www.instagram.com/",
    "youtube": "https://studio.youtube.com/",
    "tiktok": "https://www.tiktok.com/tiktokstudio",
}


@pytest.mark.parametrize(("platform", "start_url"), EXPECTED_PLATFORM_START_URLS.items())
def test_every_platform_builds_an_isolated_target_with_the_registered_login_page(
    platform,
    start_url,
    tmp_path,
):
    target = build_browser_account_target(
        owner_user_id="owner-1",
        account_id=f"acct-{platform}",
        platform=platform,
        display_name=platform,
        user_data_dir=tmp_path / platform,
    )

    assert target.start_url == start_url
    assert target.session_key == f"account:owner-1:acct-{platform}"
    assert target.user_data_dir == tmp_path / platform


def test_backend_registers_exactly_the_eight_customer_platforms():
    assert {platform: config.start_url for platform, config in BROWSER_PLATFORMS.items()} == EXPECTED_PLATFORM_START_URLS


@pytest.mark.parametrize(
    ("platform", "url", "expected_cookie_set"),
    [
        ("douyin", "https://creator.douyin.com/", ("sessionid",)),
        (
            "wechat_channels",
            "https://channels.weixin.qq.com/platform",
            ("wxuin", "sessionid"),
        ),
        (
            "wechat_official",
            "https://mp.weixin.qq.com/",
            ("slave_sid", "slave_user"),
        ),
        ("xiaohongshu", "https://creator.xiaohongshu.com/", ("web_session",)),
        ("x", "https://x.com/home", ("auth_token", "ct0")),
        (
            "instagram",
            "https://www.instagram.com/",
            ("sessionid", "ds_user_id"),
        ),
        (
            "youtube",
            "https://studio.youtube.com/",
            ("SAPISID", "SID"),
        ),
        ("tiktok", "https://www.tiktok.com/tiktokstudio", ("sessionid",)),
    ],
)
def test_every_platform_has_a_first_party_login_cookie_rule(
    platform,
    url,
    expected_cookie_set,
):
    rule = browser_login_cookie_rule(platform, url)

    assert rule is not None
    assert expected_cookie_set in rule.cookie_sets


def test_login_cookie_rule_rejects_a_foreign_page():
    assert browser_login_cookie_rule("douyin", "https://evil.example/") is None


def test_verified_platform_dashboard_urls_are_authenticated():
    assert browser_login_succeeded("douyin", "https://creator.douyin.com/creator-micro/home")
    assert browser_login_succeeded("wechat_channels", "https://channels.weixin.qq.com/platform/post/list")
    assert browser_login_succeeded(
        "wechat_official",
        "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&token=redacted",
    )
    assert browser_login_succeeded("xiaohongshu", "https://creator.xiaohongshu.com/new/home")
    assert browser_login_succeeded("x", "https://x.com/home")
    assert browser_login_succeeded("youtube", "https://studio.youtube.com/channel/channel-id")
    assert browser_login_succeeded("tiktok", "https://www.tiktok.com/tiktokstudio/content")
    assert browser_login_succeeded("x", "https://analytics.x.com/")


def test_start_page_is_not_mistaken_for_success_before_a_login_challenge():
    assert not browser_login_succeeded("instagram", "https://www.instagram.com/")
    assert not browser_login_succeeded("tiktok", "https://www.tiktok.com/tiktokstudio")


def test_return_to_platform_after_observed_login_challenge_is_success():
    assert browser_login_challenge("instagram", "https://www.instagram.com/accounts/login/")
    assert browser_login_succeeded(
        "instagram",
        "https://www.instagram.com/",
        challenge_seen=True,
    )


def test_foreign_host_never_counts_as_platform_login():
    assert not browser_login_succeeded(
        "douyin",
        "https://evil.example/creator-micro/home",
        challenge_seen=True,
    )
    assert not browser_login_succeeded("x", "https://x.com/homeevil")


def test_douyin_same_url_dashboard_uses_visible_page_markers():
    dashboard_text = "机构服务权益 入驻签约 达人管理 经营分析 成长激励"
    assert browser_login_page_succeeded(
        "douyin",
        "https://creator.douyin.com/",
        dashboard_text,
    )
    assert not browser_login_page_succeeded(
        "douyin",
        "https://creator.douyin.com/",
        f"{dashboard_text} 接收短信验证码 请输入验证码",
    )
    assert not browser_login_page_succeeded(
        "douyin",
        "https://evil.example/",
        dashboard_text,
    )
