from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.browser_collection import (
    BrowserPlatformCollectionError,
    BrowserPlatformCollectionService,
    DouyinBrowserCollectionError,
    DouyinBrowserCollectionService,
    parse_douyin_content_inventory,
    parse_douyin_dashboard_summary,
)


@pytest.mark.asyncio
async def test_browser_platform_collection_captures_generic_rendered_business_data() -> None:
    accounts = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-x", "platform": "x", "display_name": "X account", "status": "active"}))
    observations = SimpleNamespace(record=AsyncMock(side_effect=lambda **kwargs: {"id": "platform-observation-x", "platform": "x", **kwargs}))
    session = SimpleNamespace(
        current_url=AsyncMock(return_value="https://x.com/home?utm_source=private"),
        navigate=AsyncMock(),
        extract_business_page=AsyncMock(
            return_value={
                "url": "https://x.com/home?utm_source=private",
                "title": "Home / X",
                "visible_text": "Analytics 28 days Impressions 12,345 Engagements 678",
                "text_truncated": False,
                "headings": ["Analytics"],
                "tables": [],
                "data_blocks": ["Impressions 12,345", "Engagements 678"],
                "links": [{"text": "Analytics", "href": "https://x.com/i/account_analytics?token=not-persisted"}],
            }
        ),
        screenshot_bytes=AsyncMock(return_value=b"x-page"),
    )
    service = BrowserPlatformCollectionService(accounts=accounts, observations=observations, settle_seconds=0)

    result = await service.collect_creator_page(
        owner_user_id="user-1",
        account_id="acct-x",
        observation_key="x:dashboard:2026-07-22T10",
        dataset="dashboard",
        session=session,
    )

    assert result["platform"] == "x"
    kwargs = observations.record.await_args.kwargs
    assert kwargs["status"] == "partial"
    assert kwargs["source_url"] == "https://x.com/home"
    assert kwargs["records"][0]["links"][0]["href"] == "https://x.com/i/account_analytics"
    assert kwargs["coverage"]["platform_adapter"] == "generic_rendered_dom"
    session.navigate.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_platform_collection_rejects_cross_platform_navigation() -> None:
    accounts = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-x", "platform": "x", "status": "active"}))
    service = BrowserPlatformCollectionService(accounts=accounts, observations=SimpleNamespace(), settle_seconds=0)

    with pytest.raises(BrowserPlatformCollectionError, match="safe X creator URL"):
        await service.collect_creator_page(
            owner_user_id="user-1",
            account_id="acct-x",
            observation_key="x:unsafe:1",
            dataset="dashboard",
            target_url="https://creator.douyin.com/creator-micro/home",
            session=SimpleNamespace(),
        )


def test_douyin_content_inventory_parser_normalizes_post_metrics() -> None:
    text = (
        "作品管理 全部作品 共 2 个作品 "
        "00:16 第一条 #创业 编辑作品 设置权限 作品置顶 删除作品 "
        "2026年06月01日 16:10 已发布 播放 201 点赞 2 评论 1 分享 0 "
        "01:06 私密 第二条 #一人公司 编辑作品 设置权限 删除作品 "
        "2026年05月23日 20:03 播放 - 点赞 - 评论 - 分享 - 没有更多作品"
    )

    parsed = parse_douyin_content_inventory(text)

    assert parsed["declared_content_count"] == 2
    assert parsed["listing_complete"] is True
    assert parsed["items"] == [
        {
            "record_type": "content_item",
            "title": "第一条 #创业",
            "duration_seconds": 16,
            "visibility": "public",
            "publication_status": "published",
            "published_at": "2026-06-01T16:10:00+08:00",
            "metrics": {"views": 201, "likes": 2, "comments": 1, "shares": 0},
        },
        {
            "record_type": "content_item",
            "title": "第二条 #一人公司",
            "duration_seconds": 66,
            "visibility": "private",
            "publication_status": "published",
            "published_at": "2026-05-23T20:03:00+08:00",
            "metrics": {"views": None, "likes": None, "comments": None, "shares": None},
        },
    ]


def test_douyin_dashboard_parser_keeps_exact_platform_window() -> None:
    parsed = parse_douyin_dashboard_summary("关注 2 粉丝 4 获赞 56 数据中心 统计周期：2026.07.14-2026.07.20 数据总览 时间 近7日 播放量 播放量 9 较前7日+8 主页访问量 19 较前7日+10 作品分享 0 较前7日0 作品评论 0 较前7日0")

    assert parsed == {
        "following_snapshot": 2,
        "followers_snapshot": 4,
        "likes_received_snapshot": 56,
        "window_started_on": "2026-07-14",
        "window_ended_on": "2026-07-20",
        "window_label": "近7日",
        "views": 9,
        "profile_visits": 19,
        "shares": 0,
        "comments": 0,
    }


@pytest.mark.asyncio
async def test_douyin_browser_collection_seals_visible_business_data_with_coverage() -> None:
    accounts = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "acct-1",
                "owner_user_id": "user-1",
                "platform": "douyin",
                "display_name": "抖音号",
                "status": "active",
            }
        )
    )
    observations = SimpleNamespace(
        record=AsyncMock(
            side_effect=lambda **kwargs: {
                "id": "platform-observation-1",
                "platform": "douyin",
                **kwargs,
            }
        )
    )
    session = SimpleNamespace(
        current_url=AsyncMock(return_value="https://creator.douyin.com/creator-micro/home?tab=data"),
        navigate=AsyncMock(),
        extract_business_page=AsyncMock(
            return_value={
                "url": "https://creator.douyin.com/creator-micro/home?tab=data",
                "title": "抖音创作者中心",
                "visible_text": "昨日播放量 1,200 新增粉丝 15",
                "text_truncated": False,
                "headings": ["核心数据"],
                "tables": [{"rows": [["指标", "数值"], ["播放量", "1,200"]]}],
                "data_blocks": ["昨日播放量 1,200", "新增粉丝 15"],
                "links": [
                    {
                        "text": "作品数据",
                        "href": "https://creator.douyin.com/creator-micro/data/video?ticket=must-not-persist",
                    }
                ],
            }
        ),
        screenshot_bytes=AsyncMock(return_value=b"png-business-evidence"),
    )
    service = DouyinBrowserCollectionService(accounts=accounts, observations=observations, settle_seconds=0)

    result = await service.collect_creator_page(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:dashboard:2026-07-21T12",
        dataset="dashboard",
        session=session,
    )

    assert result["id"] == "platform-observation-1"
    kwargs = observations.record.await_args.kwargs
    assert kwargs["source"] == "browser"
    assert kwargs["status"] == "partial"
    assert kwargs["source_url"] == "https://creator.douyin.com/creator-micro/home"
    assert kwargs["records"][0]["links"][0]["href"] == "https://creator.douyin.com/creator-micro/data/video"
    assert kwargs["records"][0]["tables"][0]["rows"][1] == ["播放量", "1,200"]
    assert kwargs["summary"]["table_row_count"] == 2
    assert kwargs["coverage"]["pagination_state"] == "single_loaded_page"
    assert len(kwargs["evidence"]["screenshot_sha256"]) == 64
    session.navigate.assert_not_awaited()


@pytest.mark.asyncio
async def test_douyin_browser_collection_navigates_only_to_safe_creator_urls() -> None:
    accounts = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-1", "platform": "douyin", "status": "active"}))
    observations = SimpleNamespace(record=AsyncMock())
    session = SimpleNamespace(
        current_url=AsyncMock(return_value="about:blank"),
        navigate=AsyncMock(),
        extract_business_page=AsyncMock(
            return_value={
                "url": "https://creator.douyin.com/creator-micro/content/manage",
                "title": "作品管理",
                "visible_text": "作品列表",
                "text_truncated": False,
                "headings": [],
                "tables": [],
                "data_blocks": [],
                "links": [],
            }
        ),
        screenshot_bytes=AsyncMock(return_value=b"png"),
    )
    service = DouyinBrowserCollectionService(accounts=accounts, observations=observations, settle_seconds=0)

    await service.collect_creator_page(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:content:1",
        dataset="content_inventory",
        target_url="https://creator.douyin.com/creator-micro/content/manage",
        session=session,
    )
    session.navigate.assert_awaited_once_with("https://creator.douyin.com/creator-micro/content/manage")

    with pytest.raises(DouyinBrowserCollectionError, match="safe Douyin creator URL"):
        await service.collect_creator_page(
            owner_user_id="user-1",
            account_id="acct-1",
            observation_key="douyin:unsafe:1",
            dataset="content_inventory",
            target_url="https://evil.example/steal",
            session=session,
        )
    with pytest.raises(DouyinBrowserCollectionError, match="must not contain a query"):
        await service.collect_creator_page(
            owner_user_id="user-1",
            account_id="acct-1",
            observation_key="douyin:unsafe:2",
            dataset="content_inventory",
            target_url="https://creator.douyin.com/creator-micro/content/manage?token=secret",
            session=session,
        )


@pytest.mark.asyncio
async def test_douyin_browser_collection_reports_login_required_without_capturing_page_data() -> None:
    accounts = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-1", "platform": "douyin", "status": "active"}))
    observations = SimpleNamespace(record=AsyncMock(side_effect=lambda **kwargs: {"id": "platform-observation-login", **kwargs}))
    session = SimpleNamespace(
        current_url=AsyncMock(return_value="https://sso.douyin.com/login"),
        navigate=AsyncMock(),
        extract_business_page=AsyncMock(),
        screenshot_bytes=AsyncMock(),
    )
    service = DouyinBrowserCollectionService(accounts=accounts, observations=observations, settle_seconds=0)

    result = await service.collect_creator_page(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:dashboard:login-required",
        dataset="dashboard",
        session=session,
    )

    assert result["status"] == "unavailable"
    kwargs = observations.record.await_args.kwargs
    assert kwargs["records"] == []
    assert kwargs["coverage"]["reason"] == "login_required"
    session.extract_business_page.assert_not_awaited()


@pytest.mark.asyncio
async def test_douyin_browser_collection_waits_for_creator_spa_data() -> None:
    accounts = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-1", "platform": "douyin", "status": "active"}))
    observations = SimpleNamespace(record=AsyncMock(side_effect=lambda **kwargs: {"id": "platform-observation-ready", **kwargs}))
    loading = {
        "url": "https://creator.douyin.com/creator-micro/content/manage",
        "title": "抖音创作者中心",
        "visible_text": "加载中，请稍候...",
        "text_truncated": False,
        "headings": [],
        "tables": [],
        "data_blocks": [],
        "links": [],
    }
    ready = {
        **loading,
        "visible_text": "作品管理 共 4 个作品 播放 201 点赞 2 评论 1 分享 0",
        "data_blocks": ["播放 201 点赞 2 评论 1 分享 0"],
    }
    session = SimpleNamespace(
        current_url=AsyncMock(return_value="https://creator.douyin.com/creator-micro/content/manage"),
        navigate=AsyncMock(),
        extract_business_page=AsyncMock(side_effect=[loading, ready]),
        screenshot_bytes=AsyncMock(return_value=b"png"),
    )
    service = DouyinBrowserCollectionService(accounts=accounts, observations=observations, settle_seconds=0.001)

    result = await service.collect_creator_page(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:content:ready",
        dataset="content_inventory",
        session=session,
    )

    assert result["coverage"]["render_state"] == "ready"
    assert result["coverage"]["capture_attempts"] == 2
    assert session.extract_business_page.await_count == 2


@pytest.mark.asyncio
async def test_browser_collection_does_not_wait_for_unrelated_loading_cards() -> None:
    accounts = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-1", "platform": "douyin", "status": "active"}))
    observations = SimpleNamespace(record=AsyncMock(side_effect=lambda **kwargs: {"id": "observation-ready", **kwargs}))
    session = SimpleNamespace(
        current_url=AsyncMock(return_value="https://creator.douyin.com/creator-micro/home"),
        navigate=AsyncMock(),
        extract_business_page=AsyncMock(
            return_value={
                "url": "https://creator.douyin.com/creator-micro/home",
                "title": "抖音创作者中心",
                "visible_text": "关注 2 粉丝 4 获赞 56 数据中心 近7日 播放量 900 热门话题 加载中，请稍候...",
                "text_truncated": False,
                "headings": [],
                "tables": [{"rows": [["播放量", "900"]]}],
                "data_blocks": ["关注 2 粉丝 4 获赞 56"],
                "links": [],
            }
        ),
        screenshot_bytes=AsyncMock(return_value=b"png"),
    )
    service = BrowserPlatformCollectionService(accounts=accounts, observations=observations, settle_seconds=0.001)

    result = await service.collect_creator_page(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:dashboard:partial-widget-loading",
        dataset="dashboard",
        session=session,
    )

    assert result["coverage"]["render_state"] == "ready"
    assert result["coverage"]["capture_attempts"] == 1
    session.extract_business_page.assert_awaited_once()


@pytest.mark.asyncio
async def test_douyin_browser_collection_replays_existing_observation_without_reopening_page() -> None:
    existing = {
        "id": "platform-observation-existing",
        "account_id": "acct-1",
        "platform": "douyin",
        "dataset": "content_inventory",
        "status": "observed",
    }
    accounts = SimpleNamespace(get=AsyncMock(return_value={"id": "acct-1", "platform": "douyin", "status": "active"}))
    observations = SimpleNamespace(get_by_key=AsyncMock(return_value=existing), record=AsyncMock())
    session = SimpleNamespace(current_url=AsyncMock(), navigate=AsyncMock(), extract_business_page=AsyncMock())
    service = DouyinBrowserCollectionService(accounts=accounts, observations=observations, settle_seconds=0)

    result = await service.collect_creator_page(
        owner_user_id="user-1",
        account_id="acct-1",
        observation_key="douyin:content:stable",
        dataset="content_inventory",
        session=session,
    )

    assert result == existing
    session.current_url.assert_not_awaited()
    observations.record.assert_not_awaited()
