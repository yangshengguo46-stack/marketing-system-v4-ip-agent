from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_platform_observations import PersonalIPPlatformObservationRepository


@pytest.mark.asyncio
async def test_platform_observation_keeps_detailed_business_data_and_strips_url_secrets(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    observations = PersonalIPPlatformObservationRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音号")

    kwargs = {
        "owner_user_id": "user-1",
        "observation_key": "douyin:dashboard:2026-07-21T12",
        "account_id": account["id"],
        "dataset": "content_inventory",
        "source": "browser",
        "status": "partial",
        "source_url": "https://creator.douyin.com/creator-micro/data/video?tab=all&ticket=secret#detail",
        "observed_at": datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
        "records": [
            {
                "platform_post_id": "video-1",
                "title": "第一条视频",
                "published_at": "2026-07-20T08:00:00+08:00",
                "metrics": {
                    "views": 12345,
                    "likes": 321,
                    "comments": 45,
                    "shares": 17,
                    "average_watch_seconds": 12.8,
                    "completion_rate": 0.41,
                },
            }
        ],
        "summary": {"content_count": 1, "views": 12345},
        "coverage": {
            "pages_scanned": 1,
            "records_seen": 1,
            "has_more": True,
            "missing_sections": ["traffic_sources"],
        },
        "evidence": {
            "capture_refs": ["artifact://browser/douyin-dashboard-20260721.png"],
            "field_sources": {"records[].metrics.views": "页面作品数据表"},
        },
    }

    created = await observations.record(**kwargs)
    replayed = await observations.record(**kwargs)

    assert replayed == created
    assert created["contract_version"] == "personal-ip-platform-observation-v1"
    assert created["platform"] == "douyin"
    assert created["source_url"] == "https://creator.douyin.com/creator-micro/data/video"
    assert created["records"][0]["metrics"]["average_watch_seconds"] == 12.8
    assert created["coverage"]["has_more"] is True
    assert len(created["evidence_digest"]) == 64
    assert await observations.get(created["id"], owner_user_id="user-2") is None
    assert await observations.get_by_key(kwargs["observation_key"], owner_user_id="user-1") == created

    await close_engine()


@pytest.mark.asyncio
async def test_platform_observation_rejects_credential_material_at_any_depth(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    observations = PersonalIPPlatformObservationRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音号")

    base = {
        "owner_user_id": "user-1",
        "observation_key": "douyin:unsafe",
        "account_id": account["id"],
        "dataset": "account_profile",
        "source": "browser",
        "status": "observed",
        "source_url": "https://creator.douyin.com/creator-micro/home",
        "observed_at": datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
        "records": [{"display_name": "创作者"}],
        "summary": {},
        "coverage": {"complete": True},
        "evidence": {},
    }

    with pytest.raises(ValueError, match="credential field"):
        await observations.record(
            **{
                **base,
                "records": [{"display_name": "创作者", "network": {"authorization": "Bearer raw-secret"}}],
            }
        )

    with pytest.raises(ValueError, match="already records a different observation"):
        safe = await observations.record(**base)
        assert safe["status"] == "observed"
        await observations.record(**{**base, "records": [{"display_name": "另一个名字"}]})

    await close_engine()


@pytest.mark.asyncio
async def test_platform_observation_requires_evidence_for_available_data(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    observations = PersonalIPPlatformObservationRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="xiaohongshu", display_name="小红书号")

    common = {
        "owner_user_id": "user-1",
        "account_id": account["id"],
        "dataset": "audience_analytics",
        "source": "browser",
        "source_url": "https://creator.xiaohongshu.com/analytics",
        "observed_at": datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
        "summary": {},
        "coverage": {},
        "evidence": {},
    }

    with pytest.raises(ValueError, match="require records or summary"):
        await observations.record(
            **common,
            observation_key="xhs:empty",
            status="observed",
            records=[],
        )

    unavailable = await observations.record(
        **{
            **common,
            "observation_key": "xhs:unavailable",
            "status": "unavailable",
            "records": [],
            "coverage": {"reason": "creator analytics permission unavailable"},
        }
    )
    assert unavailable["records"] == []
    assert unavailable["platform"] == "xiaohongshu"

    await close_engine()
