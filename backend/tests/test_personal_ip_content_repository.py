from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.content_contracts import (
    ContentWorkAppend,
    ContentWorkCreate,
    ScriptDraft,
    script_decision_digest,
)


def _seed() -> dict:
    return {
        "recurring_conflict": "一个人总用玩笑维持关系，真正求助时仍被当成玩笑",
        "desire_a": "继续讨人喜欢",
        "desire_b": "冒险说出真话",
        "relationship_at_stake": "一段靠轻松表象维系的友情",
        "causal_pattern": "旧策略让误解加深，换招后必须承担失去认可的代价",
        "tone": "克制",
    }


def _direction(*, parent: str | None = None) -> dict:
    return {
        "premise": "玩笑成为真话的障碍",
        "audience_situation": "习惯用轻松逃避认真表达的人",
        "core_tension": "被喜欢与被真正理解不能同时靠旧策略获得",
        "content_promise": "看见一次说真话如何改变关系",
        "creative_route": "纯虚构关系故事",
        "rationale": "用可观察的行动和代价呈现冲突，不复述经营者履历。",
        "truth_mode": "fictional",
        "business_relevance": "方向判断保留在故事外层。",
        "parent_direction_version_id": parent,
    }


def _script(*, parent: str | None = None, direction_id: str | None = None, suffix: str = "") -> dict:
    return {
        "title": f"玩笑之外{suffix}",
        "story_mode": "fictional",
        "script_text": f"他第一次没有用笑声收尾，而朋友也第一次停下来听完。{suffix}",
        "story_engine_seed": _seed(),
        "locked_story": "一个总用玩笑维持友情的人，在真正求助仍被当成玩笑后改用直说，冒着失去好感的代价让朋友第一次认真听完。",
        "creative_elements": [
            {
                "element": "主人公、朋友及事件均为虚构",
                "kind": "fictional",
                "disclosure": "作为虚构故事保存，不映射为 Owner 事实",
            }
        ],
        "production_notes": {"separate_from_story": True},
        "parent_script_version_id": parent,
        "direction_version_id": direction_id,
    }


def _create_request(subject_id: str) -> ContentWorkCreate:
    return ContentWorkCreate.model_validate(
        {
            "idempotency_key": "run-1:tool-1",
            "subject_id": subject_id,
            "title": "第一次认真说话",
            "entry_route": "zero_start",
            "objective": {
                "desired_change": "让观众愿意认真表达一次",
                "audience_situation": "关系中总用玩笑回避的人",
            },
            "direction": _direction(),
            "script": _script(),
        }
    )


def _verified_script_digests(script: ScriptDraft | None) -> frozenset[str]:
    if script is None:
        return frozenset()
    return frozenset({script_decision_digest(script)})


@pytest.mark.asyncio
async def test_postgres_content_mutation_uses_owner_lifecycle_lock() -> None:
    operations: list[tuple[object, object | None]] = []

    class FakeSession:
        def __init__(self) -> None:
            self.bind = type("Bind", (), {"dialect": postgresql.dialect()})()

        def get_bind(self):
            return self.bind

        async def execute(self, statement, params=None):
            operations.append((statement, params))

    await PersonalIPContentRepository._lock_owner_lifecycle(  # noqa: SLF001
        FakeSession(),  # type: ignore[arg-type]
        "owner-lock-test",
    )

    assert len(operations) == 1
    assert operations[0][1] == {"lock_key": "personal-ip-data-lifecycle:owner-lock-test"}
    assert "pg_advisory_xact_lock(hashtext" in str(operations[0][0])


@pytest.mark.asyncio
async def test_content_lineage_is_owner_scoped_immutable_versioned_and_idempotent(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    repo = PersonalIPContentRepository(sf)
    try:
        subject = await subjects.create(owner_user_id="owner-1", display_name="Owner one")
        request = _create_request(subject["id"])
        created = await repo.create(
            owner_user_id="owner-1",
            request=request,
            created_by_run_id="run-1",
            thread_id="thread-1",
            verified_script_digests=_verified_script_digests(request.script),
        )

        assert created["replayed"] is False
        work_id = created["content_work"]["id"]
        assert created["content_work"]["entry_route"] == "zero_start"
        assert created["content_work"]["objective_id"].startswith("objective-")
        assert created["content_work"]["thread_id"] == "thread-1"
        assert [item["version_number"] for item in created["direction_versions"]] == [1]
        assert [item["version_number"] for item in created["script_versions"]] == [1]
        assert created["script_versions"][0]["story_mode"] == "fictional"
        assert created["script_versions"][0]["claim_basis"] == []

        replayed = await repo.create(
            owner_user_id="owner-1",
            request=request,
            created_by_run_id="other-run",
            thread_id="thread-1",
        )
        assert replayed["replayed"] is True
        assert replayed["content_work"]["id"] == work_id
        assert len(replayed["script_versions"]) == 1

        with pytest.raises(ValueError, match="different task"):
            await repo.create(
                owner_user_id="owner-1",
                request=request,
                thread_id="thread-other",
            )

        unverified = request.model_copy(update={"idempotency_key": "direct-script-bypass"})
        with pytest.raises(ValueError, match="verified writer-brain"):
            await repo.create(owner_user_id="owner-1", request=unverified)
        assert len(await repo.list("owner-1", include_archived=True)) == 1

        direction_v1 = created["direction_versions"][0]["id"]
        script_v1 = created["script_versions"][0]["id"]
        append_request = ContentWorkAppend.model_validate(
            {
                "idempotency_key": "run-2:tool-1",
                "direction": _direction(parent=direction_v1),
                "script": _script(parent=script_v1, suffix="第二版"),
            }
        )
        appended = await repo.append(
            work_id,
            owner_user_id="owner-1",
            request=append_request,
            created_by_run_id="run-2",
            verified_script_digests=_verified_script_digests(append_request.script),
        )
        assert appended is not None and appended["replayed"] is False
        assert appended["direction_version"]["version_number"] == 2
        assert appended["script_version"]["version_number"] == 2
        assert appended["script_version"]["direction_version_id"] == appended["direction_version"]["id"]

        append_replay = await repo.append(work_id, owner_user_id="owner-1", request=append_request)
        assert append_replay is not None and append_replay["replayed"] is True
        assert append_replay["script_version"]["id"] == appended["script_version"]["id"]

        assert await repo.has_subject_content(subject["id"], owner_user_id="owner-1") is True
        assert await repo.has_subject_content(subject["id"], owner_user_id="owner-2") is False
        archived = await repo.archive(work_id, owner_user_id="owner-1")
        assert archived is not None and archived["status"] == "archived"

        archived_replay = await repo.append(
            work_id,
            owner_user_id="owner-1",
            request=append_request,
        )
        assert archived_replay is not None and archived_replay["replayed"] is True
        assert archived_replay["script_version"]["id"] == appended["script_version"]["id"]

        new_archived_commit = ContentWorkAppend.model_validate(
            {
                "idempotency_key": "run-3:tool-1",
                "direction": _direction(parent=appended["direction_version"]["id"]),
            }
        )
        with pytest.raises(ValueError, match="archived Personal-IP content work"):
            await repo.append(
                work_id,
                owner_user_id="owner-1",
                request=new_archived_commit,
            )

        lineage = await repo.get_lineage(work_id, owner_user_id="owner-1")
        assert lineage is not None
        assert [item["version_number"] for item in lineage["direction_versions"]] == [1, 2]
        assert [item["version_number"] for item in lineage["script_versions"]] == [1, 2]
        assert await repo.get_lineage(work_id, owner_user_id="owner-2") is None
        assert await repo.append(work_id, owner_user_id="owner-2", request=append_request) is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_concurrent_content_appends_receive_distinct_monotonic_versions(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    repo = PersonalIPContentRepository(sf)
    try:
        subject = await subjects.create(owner_user_id="owner-1", display_name="Owner one")
        request = _create_request(subject["id"])
        created = await repo.create(
            owner_user_id="owner-1",
            request=request,
            verified_script_digests=_verified_script_digests(request.script),
        )
        work_id = created["content_work"]["id"]
        parent_id = created["direction_versions"][0]["id"]

        async def append_direction(key: str, suffix: str):
            return await repo.append(
                work_id,
                owner_user_id="owner-1",
                request=ContentWorkAppend.model_validate(
                    {
                        "idempotency_key": key,
                        "direction": {
                            **_direction(parent=parent_id),
                            "premise": f"并发方向{suffix}",
                        },
                    }
                ),
            )

        first, second = await asyncio.gather(
            append_direction("concurrent-1", "A"),
            append_direction("concurrent-2", "B"),
        )
        assert first is not None and second is not None
        assert {
            first["direction_version"]["version_number"],
            second["direction_version"]["version_number"],
        } == {2, 3}
        lineage = await repo.get_lineage(work_id, owner_user_id="owner-1")
        assert lineage is not None
        assert [item["version_number"] for item in lineage["direction_versions"]] == [1, 2, 3]
    finally:
        await close_engine()


def test_content_contract_enforces_benchmark_and_fact_fiction_boundary() -> None:
    with pytest.raises(ValidationError, match="benchmark entry requires a breakdown"):
        ContentWorkCreate.model_validate(
            {
                "idempotency_key": "missing-breakdown",
                "title": "Benchmark",
                "entry_route": "benchmark",
                "objective": {"desired_change": "理解结构"},
            }
        )

    with pytest.raises(ValidationError, match="source_observed claims require"):
        ScriptDraft.model_validate(
            {
                "title": "事实稿",
                "story_mode": "factual",
                "script_text": "这是一个未经来源绑定的断言。",
                "claim_basis": [
                    {
                        "claim": "未经绑定",
                        "state": "source_observed",
                        "usage": "source_fact",
                    }
                ],
            }
        )

    with pytest.raises(ValidationError, match="fictional scripts cannot present"):
        ScriptDraft.model_validate(
            {
                **_script(),
                "claim_basis": [
                    {
                        "claim": "Owner 说自己就是故事主人公",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            }
        )

    with pytest.raises(ValidationError, match="abstract human conflict"):
        ScriptDraft.model_validate(
            {
                **_script(),
                "story_engine_seed": {**_seed(), "recurring_conflict": "账号流量下降后拍视频"},
            }
        )


def test_content_contract_rejects_credentials_and_raw_provider_payloads() -> None:
    with pytest.raises(ValidationError, match="credential or raw-provider field"):
        ContentWorkCreate.model_validate(
            {
                "idempotency_key": "unsafe-breakdown",
                "title": "不安全来源",
                "entry_route": "benchmark",
                "objective": {"desired_change": "测试输入边界"},
                "breakdown": {
                    "source_kind": "platform_content",
                    "source_identity": {
                        "url": "https://example.invalid/video/1",
                        "provider_payload": {"opaque": "must-not-persist"},
                    },
                    "observations": [{"observation": "画面中有一人", "evidence_refs": ["frame:1"]}],
                },
            }
        )

    with pytest.raises(ValidationError, match="credential or raw-provider field"):
        ScriptDraft.model_validate(
            {
                "title": "不安全制作说明",
                "story_mode": "factual",
                "script_text": "普通内容数据不保存访问令牌。",
                "claim_basis": [
                    {
                        "claim": "普通内容数据不保存访问令牌",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
                "production_notes": {"apiKey": "must-not-persist"},
            }
        )
