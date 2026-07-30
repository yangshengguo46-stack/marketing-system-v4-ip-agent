import pytest
from pydantic import TypeAdapter

from app.gateway.routers.personal_ip_accounts import PersonalIPSubjectCreateRequest
from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_accounts import PersonalIPAccountRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository


@pytest.mark.asyncio
async def test_subject_crud_and_owner_isolation(tmp_path):
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    repo = PersonalIPSubjectRepository(sf)

    created = await repo.create(
        owner_user_id="user-1",
        display_name="老杨",
        subject_type="creator",
        relationship="self",
        description="本地智能体创业者",
        metadata={"source": "onboarding"},
    )

    assert created["id"].startswith("subject-")
    assert created["relationship"] == "self"
    assert created["metadata"] == {"source": "onboarding"}
    assert await repo.get(created["id"], owner_user_id="user-2") is None
    assert await repo.list("user-2") == []

    updated = await repo.update(
        created["id"],
        owner_user_id="user-1",
        updates={"relationship": "client", "description": "客户经营主体"},
    )
    assert updated is not None
    assert updated["relationship"] == "client"

    assert await repo.delete(created["id"], owner_user_id="user-2") is False
    assert await repo.delete(created["id"], owner_user_id="user-1") is True
    await close_engine()


def test_product_is_a_first_class_operating_subject_type() -> None:
    request = TypeAdapter(PersonalIPSubjectCreateRequest).validate_python(
        {
            "display_name": "IP Agent",
            "subject_type": "product",
            "relationship": "self",
        }
    )
    assert request.subject_type == "product"


@pytest.mark.asyncio
async def test_accounts_can_only_attach_to_active_same_owner_subjects(tmp_path):
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    accounts = PersonalIPAccountRepository(sf)
    own_subject = await subjects.create(owner_user_id="user-1", display_name="自营主体")
    other_subject = await subjects.create(owner_user_id="user-2", display_name="他人主体")

    account = await accounts.create(
        owner_user_id="user-1",
        subject_id=own_subject["id"],
        platform="douyin",
        display_name="老杨说 AI",
    )

    assert account["subject_id"] == own_subject["id"]
    assert [item["id"] for item in await accounts.list("user-1", subject_id=own_subject["id"])] == [account["id"]]
    with pytest.raises(ValueError, match="subject not found"):
        await accounts.update(
            account["id"],
            owner_user_id="user-1",
            updates={"subject_id": other_subject["id"]},
        )

    await subjects.update(
        own_subject["id"],
        owner_user_id="user-1",
        updates={"status": "archived"},
    )
    with pytest.raises(ValueError, match="subject not found"):
        await accounts.create(
            owner_user_id="user-1",
            subject_id=own_subject["id"],
            platform="bilibili",
            display_name="归档主体账号",
        )

    detached = await accounts.update(
        account["id"],
        owner_user_id="user-1",
        updates={"subject_id": None},
    )
    assert detached is not None
    assert detached["subject_id"] is None
    await close_engine()
