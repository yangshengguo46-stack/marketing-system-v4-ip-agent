from deerflow.personal_ip.browser_profiles import (
    browser_login_challenge,
    browser_login_succeeded,
)


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
