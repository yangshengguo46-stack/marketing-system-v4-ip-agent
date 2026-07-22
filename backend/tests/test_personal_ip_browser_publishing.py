from __future__ import annotations

import pytest

from deerflow.personal_ip.browser_publishing import (
    platform_publication_url_allowed,
    verify_browser_publication_evidence,
)


def test_browser_publication_requires_visible_selected_platform_proof() -> None:
    proof = verify_browser_publication_evidence(
        platform="douyin",
        observed_url="https://www.douyin.com/video/post-123?share_token=secret#comments",
        page_title="作品标题",
        visible_text="作品标题 post-123",
        external_url="https://www.douyin.com/video/post-123?from=creator",
        external_post_id="post-123",
    )

    assert proof["observed_url"] == "https://www.douyin.com/video/post-123"
    assert proof["proof_type"] == "live_browser_publication_page"
    assert len(proof["visible_text_sha256"]) == 64
    assert "secret" not in str(proof)


@pytest.mark.parametrize(
    ("platform", "url", "normalized"),
    [
        ("douyin", "https://www.douyin.com/video/712345?share_token=secret#comments", "https://www.douyin.com/video/712345"),
        (
            "wechat_channels",
            "https://channels.weixin.qq.com/web/pages/feed?feedId=feed-1&exportkey=secret#comments",
            "https://channels.weixin.qq.com/web/pages/feed?feedId=feed-1",
        ),
        ("wechat_official", "https://mp.weixin.qq.com/s/article-1?scene=1", "https://mp.weixin.qq.com/s/article-1"),
        ("xiaohongshu", "https://www.xiaohongshu.com/explore/note-1?xsec_token=secret", "https://www.xiaohongshu.com/explore/note-1"),
        ("x", "https://x.com/example/status/1001?s=20", "https://x.com/example/status/1001"),
        ("instagram", "https://www.instagram.com/p/post-1/?igsh=secret", "https://www.instagram.com/p/post-1"),
        ("youtube", "https://www.youtube.com/watch?v=video-1&utm_source=creator", "https://www.youtube.com/watch?v=video-1"),
        ("tiktok", "https://www.tiktok.com/@example/video/2001?is_from_webapp=1", "https://www.tiktok.com/@example/video/2001"),
    ],
)
def test_all_portfolio_platforms_have_public_post_rules(platform: str, url: str, normalized: str) -> None:
    assert platform_publication_url_allowed(platform, url)
    proof = verify_browser_publication_evidence(
        platform=platform,
        observed_url=url,
        page_title="公开帖子",
        visible_text=f"公开帖子 {normalized}",
        external_url=url,
        external_post_id=None,
    )
    assert proof["observed_url"] == normalized


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("douyin", "https://creator.douyin.com/creator-micro/content/manage"),
        ("wechat_channels", "https://channels.weixin.qq.com/platform/post/list"),
        ("wechat_official", "https://mp.weixin.qq.com/cgi-bin/home"),
        ("xiaohongshu", "https://creator.xiaohongshu.com/creator/home"),
        ("x", "https://x.com/home"),
        ("instagram", "https://www.instagram.com/"),
        ("youtube", "https://studio.youtube.com/channel/channel-1"),
        ("tiktok", "https://www.tiktok.com/tiktokstudio/content"),
    ],
)
def test_creator_pages_are_not_publication_proof(platform: str, url: str) -> None:
    assert not platform_publication_url_allowed(platform, url)
    with pytest.raises(ValueError, match="public post|selected platform"):
        verify_browser_publication_evidence(
            platform=platform,
            observed_url=url,
            page_title="创作者后台",
            visible_text="post-1",
            external_url=None,
            external_post_id="post-1",
        )


def test_post_id_does_not_match_an_unrelated_url_substring() -> None:
    with pytest.raises(ValueError, match="post id is not visible"):
        verify_browser_publication_evidence(
            platform="youtube",
            observed_url="https://www.youtube.com/watch?v=video-12&utm_source=video-1",
            page_title="公开帖子",
            visible_text="公开帖子",
            external_url=None,
            external_post_id="video-1",
        )


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("douyin", "https://www.douyin.com/note/note-2"),
        ("wechat_channels", "https://weixin.qq.com/sph/feed-2"),
        ("wechat_official", "https://mp.weixin.qq.com/s?__biz=biz-1&mid=10&idx=1&sn=signature"),
        ("xiaohongshu", "https://www.xiaohongshu.com/discovery/item/note-2"),
        ("x", "https://twitter.com/i/web/status/1002"),
        ("instagram", "https://www.instagram.com/tv/post-2"),
        ("youtube", "https://youtu.be/video-2"),
        ("youtube", "https://www.youtube.com/shorts/video-3"),
        ("youtube", "https://www.youtube.com/live/video-4"),
        ("tiktok", "https://www.tiktok.com/@creator/photo/2002"),
    ],
)
def test_supported_publication_url_variants(platform: str, url: str) -> None:
    assert platform_publication_url_allowed(platform, url)


def test_browser_publication_rejects_cross_platform_or_unobserved_claims() -> None:
    with pytest.raises(ValueError, match="selected platform"):
        verify_browser_publication_evidence(
            platform="douyin",
            observed_url="https://example.com/post/1",
            page_title="",
            visible_text="post-1",
            external_url="https://www.douyin.com/video/post-1",
            external_post_id="post-1",
        )
    with pytest.raises(ValueError, match="must open"):
        verify_browser_publication_evidence(
            platform="youtube",
            observed_url="https://www.youtube.com/watch?v=one",
            page_title="One",
            visible_text="one",
            external_url="https://www.youtube.com/watch?v=two",
            external_post_id=None,
        )
