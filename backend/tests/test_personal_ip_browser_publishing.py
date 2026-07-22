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
    ("platform", "url"),
    [
        ("wechat_channels", "https://channels.weixin.qq.com/platform/post/1"),
        ("wechat_official", "https://mp.weixin.qq.com/s/abc"),
        ("xiaohongshu", "https://www.xiaohongshu.com/explore/abc"),
        ("x", "https://x.com/example/status/1"),
        ("instagram", "https://www.instagram.com/p/abc/"),
        ("youtube", "https://youtu.be/abc"),
        ("tiktok", "https://www.tiktok.com/@example/video/1"),
    ],
)
def test_all_portfolio_platforms_have_publication_host_rules(platform: str, url: str) -> None:
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
