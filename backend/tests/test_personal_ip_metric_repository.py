from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_metrics import PersonalIPMetricRepository
from deerflow.persistence.personal_ip_publish_receipts import PersonalIPPublishReceiptRepository

START = datetime(2026, 7, 21, 0, 0, tzinfo=UTC)
END = datetime(2026, 7, 22, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_metrics_aggregate_all_accounts_with_explicit_coverage(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    metrics = PersonalIPMetricRepository(sf)
    douyin = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="抖音号")
    xhs = await accounts.create(owner_user_id="user-1", platform="xiaohongshu", display_name="小红书号")
    missing = await accounts.create(owner_user_id="user-1", platform="bilibili", display_name="B站号")

    await metrics.record(
        owner_user_id="user-1",
        observation_key="douyin:2026-07-21:first",
        series_key="daily-summary",
        account_id=douyin["id"],
        receipt_id=None,
        scope="account",
        metric_mode="window_total",
        source="platform_api",
        status="observed",
        window_started_at=START,
        window_ended_at=END,
        observed_at=datetime(2026, 7, 22, 0, 5, tzinfo=UTC),
        metrics={"views": 100, "likes": 10, "completion_rate": 0.42},
        coverage={"permissions": ["read_insights"]},
    )
    await metrics.record(
        owner_user_id="user-1",
        observation_key="douyin:2026-07-21:refetch",
        series_key="daily-summary",
        account_id=douyin["id"],
        receipt_id=None,
        scope="account",
        metric_mode="window_total",
        source="platform_api",
        status="observed",
        window_started_at=START,
        window_ended_at=END,
        observed_at=datetime(2026, 7, 22, 0, 10, tzinfo=UTC),
        metrics={"views": 120, "likes": 12, "completion_rate": 0.45},
        coverage={"permissions": ["read_insights"]},
    )
    await metrics.record(
        owner_user_id="user-1",
        observation_key="xhs:2026-07-21",
        series_key="daily-summary",
        account_id=xhs["id"],
        receipt_id=None,
        scope="account",
        metric_mode="window_total",
        source="browser",
        status="partial",
        window_started_at=START,
        window_ended_at=END,
        observed_at=datetime(2026, 7, 22, 0, 8, tzinfo=UTC),
        metrics={"views": 200, "likes": 20, "saves": 8},
        coverage={"missing_metrics": ["shares"]},
    )
    await metrics.record(
        owner_user_id="user-1",
        observation_key="douyin:cumulative-snapshot",
        account_id=douyin["id"],
        receipt_id=None,
        scope="account",
        metric_mode="snapshot",
        source="platform_api",
        status="observed",
        observed_at=datetime(2026, 7, 22, 0, 9, tzinfo=UTC),
        metrics={"views": 999999},
        coverage={},
    )

    result = await metrics.aggregate(owner_user_id="user-1", window_started_at=START, window_ended_at=END)

    assert result["totals"] == {"likes": 32, "saves": 8, "views": 320}
    assert result["by_platform"]["douyin"]["views"] == 120
    assert result["by_platform"]["xiaohongshu"]["views"] == 200
    assert result["observation_count"] == 3
    assert result["deduplicated_count"] == 2
    assert result["excluded_snapshot_count"] == 1
    assert result["coverage"]["partial_account_ids"] == [xhs["id"]]
    assert result["coverage"]["missing_account_ids"] == [missing["id"]]
    assert "completion_rate" not in result["totals"]
    assert (await metrics.aggregate(owner_user_id="user-2", window_started_at=START, window_ended_at=END))["totals"] == {}
    await close_engine()


@pytest.mark.asyncio
async def test_metric_observation_is_idempotent_and_validates_publish_receipt_account(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    accounts = PersonalIPAccountRepository(sf)
    receipts = PersonalIPPublishReceiptRepository(sf)
    metrics = PersonalIPMetricRepository(sf)
    account = await accounts.create(owner_user_id="user-1", platform="douyin", display_name="发布账号")
    other = await accounts.create(owner_user_id="user-1", platform="xiaohongshu", display_name="其他账号")
    receipt = await receipts.begin(
        owner_user_id="user-1",
        operation_key="publish:metrics",
        idempotency_key="idem-metrics",
        account_id=account["id"],
        preflight_id=None,
        executor="platform_api",
        request_payload={"caption": "测试"},
    )

    kwargs = {
        "owner_user_id": "user-1",
        "observation_key": "post:metrics:t+1d",
        "account_id": account["id"],
        "receipt_id": receipt["id"],
        "scope": "post",
        "metric_mode": "snapshot",
        "source": "platform_api",
        "status": "observed",
        "observed_at": datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
        "metrics": {"views": 1000, "likes": 50},
        "coverage": {},
    }
    created = await metrics.record(**kwargs)
    replayed = await metrics.record(**kwargs)

    assert replayed == created
    assert created["platform"] == "douyin"
    assert created["series_key"] == f"receipt:{receipt['id']}"
    assert await metrics.get(created["id"], owner_user_id="user-2") is None

    with pytest.raises(ValueError, match="receipt belongs to a different account"):
        await metrics.record(**{**kwargs, "observation_key": "wrong-account", "account_id": other["id"]})
    with pytest.raises(ValueError, match="already records a different observation"):
        await metrics.record(**{**kwargs, "metrics": {"views": 2000}})
    await close_engine()
