from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_metrics import PersonalIPMetricRepository
from deerflow.persistence.personal_ip_platform_observations import PersonalIPPlatformObservationRepository
from deerflow.personal_ip.browser_collection import BrowserPlatformCollectionService, BrowserPortfolioMetricCollectionService


def _page(url: str, text: str) -> dict:
    return {
        "url": url,
        "title": "Creator dashboard",
        "visible_text": text,
        "text_truncated": False,
        "headings": ["Analytics"],
        "tables": [],
        "data_blocks": [text],
        "links": [],
    }


@pytest.mark.asyncio
async def test_browser_portfolio_today_views_seals_evidence_and_preserves_full_account_coverage(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    observations = PersonalIPPlatformObservationRepository(sf)
    metrics = PersonalIPMetricRepository(sf)

    account_by_platform = {}
    for platform in (
        "douyin",
        "wechat_channels",
        "wechat_official",
        "xiaohongshu",
        "x",
        "instagram",
        "youtube",
        "tiktok",
    ):
        account_by_platform[platform] = await accounts.create(
            owner_user_id="user-1",
            platform=platform,
            display_name=f"{platform} account",
        )

    sessions = {
        account_by_platform["douyin"]["id"]: SimpleNamespace(
            current_url=AsyncMock(return_value="https://creator.douyin.com/creator-micro/home"),
            navigate=AsyncMock(),
            extract_business_page=AsyncMock(return_value=_page("https://creator.douyin.com/creator-micro/home", "今日 播放量 120 点赞 8")),
            screenshot_bytes=AsyncMock(return_value=b"douyin"),
        ),
        account_by_platform["youtube"]["id"]: SimpleNamespace(
            current_url=AsyncMock(return_value="https://studio.youtube.com/channel/channel-1"),
            navigate=AsyncMock(),
            extract_business_page=AsyncMock(return_value=_page("https://studio.youtube.com/channel/channel-1", "Today Views 80 Comments 3")),
            screenshot_bytes=AsyncMock(return_value=b"youtube"),
        ),
        account_by_platform["xiaohongshu"]["id"]: SimpleNamespace(
            current_url=AsyncMock(return_value="https://creator.xiaohongshu.com/new/home"),
            navigate=AsyncMock(),
            extract_business_page=AsyncMock(return_value=_page("https://creator.xiaohongshu.com/new/home", "近7日 笔记浏览量 300")),
            screenshot_bytes=AsyncMock(return_value=b"xiaohongshu"),
        ),
        account_by_platform["instagram"]["id"]: SimpleNamespace(
            current_url=AsyncMock(return_value="https://www.instagram.com/accounts/login/"),
            navigate=AsyncMock(),
            extract_business_page=AsyncMock(return_value=_page("https://www.instagram.com/accounts/login/", "Log in")),
            screenshot_bytes=AsyncMock(return_value=b"must-not-run"),
        ),
    }
    for platform in ("wechat_channels", "wechat_official", "x", "tiktok"):
        sessions[account_by_platform[platform]["id"]] = SimpleNamespace(
            current_url=AsyncMock(return_value="about:blank"),
            navigate=AsyncMock(),
            extract_business_page=AsyncMock(side_effect=RuntimeError("provider detail must stay hidden")),
            screenshot_bytes=AsyncMock(),
        )

    @contextmanager
    def acquire(*, owner_user_id: str, account: dict):
        assert owner_user_id == "user-1"
        yield sessions[account["id"]]

    service = BrowserPortfolioMetricCollectionService(
        accounts=accounts,
        observations=observations,
        metrics=metrics,
        session_factory=acquire,
        page_collector=BrowserPlatformCollectionService(accounts=accounts, observations=observations, settle_seconds=0),
    )
    end = datetime.now(UTC)
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)

    result = await service.collect_today(
        owner_user_id="user-1",
        collection_key="today:2026-07-22T12Z",
        window_started_at=start,
        window_ended_at=end,
    )

    coverage = result["aggregate"]["coverage"]
    assert result["status"] == "partial"
    assert result["aggregate"]["totals"]["views"] == 200
    assert set(coverage["partial_account_ids"]) == {
        account_by_platform["douyin"]["id"],
        account_by_platform["youtube"]["id"],
    }
    assert set(coverage["unavailable_account_ids"]) == {
        account_by_platform["xiaohongshu"]["id"],
        account_by_platform["instagram"]["id"],
    }
    assert set(coverage["missing_account_ids"]) == {
        account_by_platform["wechat_channels"]["id"],
        account_by_platform["wechat_official"]["id"],
        account_by_platform["x"]["id"],
        account_by_platform["tiktok"]["id"],
    }
    assert coverage["by_metric"]["views"]["partial_account_ids"] == sorted([account_by_platform["douyin"]["id"], account_by_platform["youtube"]["id"]])
    assert result["coverage"]["platforms"]["instagram"]["status"] == "unavailable"
    assert result["coverage"]["platforms"]["x"]["status"] == "missing"
    assert len(await observations.list("user-1", limit=100)) == 4
    assert len(await metrics.list("user-1", limit=100)) == 4
    assert "provider detail" not in str(result)
    await close_engine()
