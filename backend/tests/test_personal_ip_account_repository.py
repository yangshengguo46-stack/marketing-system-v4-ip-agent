import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository


@pytest.mark.asyncio
async def test_personal_ip_account_crud_and_owner_isolation(tmp_path):
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    repo = PersonalIPAccountRepository(sf)

    created = await repo.create(
        owner_user_id="user-1",
        platform="douyin",
        display_name="老杨说 AI",
        handle="laoyang-ai",
        metadata={"positioning_version": 3},
    )

    assert created["id"].startswith("acct-")
    assert "content_pillars" not in created
    assert "promise_to_audience" not in created
    assert created["metadata"] == {"positioning_version": 3}
    assert await repo.get(created["id"], owner_user_id="user-2") is None
    assert await repo.list("user-2") == []

    updated = await repo.update(
        created["id"],
        owner_user_id="user-1",
        updates={
            "display_name": "老杨的 AI 智能体",
            "metadata": {"positioning_version": 4},
        },
    )
    assert updated is not None
    assert updated["display_name"] == "老杨的 AI 智能体"

    assert await repo.delete(created["id"], owner_user_id="user-2") is False
    assert await repo.delete(created["id"], owner_user_id="user-1") is True
    assert await repo.get(created["id"], owner_user_id="user-1") is None
    await close_engine()


@pytest.mark.asyncio
async def test_personal_ip_account_list_hides_archived_by_default(tmp_path):
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    repo = PersonalIPAccountRepository(sf)

    created = await repo.create(
        owner_user_id="user-1",
        platform="xiaohongshu",
        display_name="测试账号",
    )
    await repo.update(
        created["id"],
        owner_user_id="user-1",
        updates={"status": "archived"},
    )

    assert await repo.list("user-1") == []
    assert len(await repo.list("user-1", include_archived=True)) == 1
    await close_engine()
