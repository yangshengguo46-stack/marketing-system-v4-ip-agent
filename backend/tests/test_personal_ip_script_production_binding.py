from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from app.gateway.routers.personal_ip_video_productions import (
    PersonalIPVideoProductionBeginRequest,
)
from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.persistence.personal_ip_video_productions import PersonalIPVideoProductionRepository
from deerflow.personal_ip.content_contracts import (
    ContentWorkCreate,
    ScriptDraft,
    script_decision_digest,
)


def _content_request(*, key: str, subject_id: str | None, title: str) -> ContentWorkCreate:
    return ContentWorkCreate.model_validate(
        {
            "idempotency_key": key,
            "subject_id": subject_id,
            "title": title,
            "entry_route": "zero_start",
            "objective": {"desired_change": "把已发生的一步讲清楚"},
            "direction": {
                "premise": "从已经完成的动作开始",
                "audience_situation": "还不知道项目进展的人",
                "core_tension": "展示进展但不夸大结果",
                "content_promise": "只说已经发生的事",
                "creative_route": "第一人称事实口述",
                "rationale": "事实足以成立。",
                "truth_mode": "factual",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
            "script": {
                "title": title,
                "story_mode": "factual",
                "script_text": "我今天完成了第一次公开演示。",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
                "production_notes": {"form": "spoken", "setting": "工作台"},
            },
        }
    )


def _verified_script(script: ScriptDraft | None) -> frozenset[str]:
    assert script is not None
    return frozenset({script_decision_digest(script)})


async def _create_content(
    content: PersonalIPContentRepository,
    *,
    key: str,
    subject_id: str | None,
    title: str,
) -> dict:
    request = _content_request(key=key, subject_id=subject_id, title=title)
    return await content.create(
        owner_user_id="owner-1",
        request=request,
        thread_id=f"thread-{key}",
        verified_script_digests=_verified_script(request.script),
    )


def _production_args(*, operation_key: str, work: dict, script: dict) -> dict:
    return {
        "owner_user_id": "owner-1",
        "operation_key": operation_key,
        "title": "制作：" + script["title"],
        "subject_id": None,
        "target_account_ids": [],
        "source_kind": "script",
        "source": {},
        "delivery_spec": {"aspect_ratio": "9:16"},
        "provider_policy": {},
        "budget": {},
        "production_mode": "faceless_material",
        "thread_id": operation_key,
        "content_work_id": work["id"],
        "script_version_id": script["id"],
    }


@pytest.mark.asyncio
async def test_script_version_is_the_immutable_source_for_multiple_productions_and_replay(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    content = PersonalIPContentRepository(sf)
    productions = PersonalIPVideoProductionRepository(sf)
    subject = await subjects.create(owner_user_id="owner-1", display_name="Owner one")
    lineage = await _create_content(
        content,
        key="content-1",
        subject_id=subject["id"],
        title="第一次演示",
    )
    work = lineage["content_work"]
    script = lineage["script_versions"][0]
    args = _production_args(operation_key="production-1", work=work, script=script)
    try:
        created = await productions.begin(**args)
        assert created["contract_version"] == "personal-ip-video-production-v2"
        assert created["content_work_id"] == work["id"]
        assert created["script_version_id"] == script["id"]
        assert created["subject_id"] == subject["id"], "work subject is inherited server-side"
        assert created["source"]["contract_version"] == "personal-ip-script-source-snapshot-v1"
        assert created["source"]["script_text"] == script["script_text"]
        snapshot = {key: value for key, value in created["source"].items() if key not in {"snapshot_sha256", "production_mode"}}
        assert (
            created["source"]["snapshot_sha256"]
            == hashlib.sha256(
                json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        )

        second = await productions.begin(**_production_args(operation_key="production-2", work=work, script=script))
        assert second["id"] != created["id"], "one immutable script may drive many productions"
        assert {
            item["id"]
            for item in await productions.list(
                "owner-1",
                content_work_id=work["id"],
            )
        } == {created["id"], second["id"]}

        await content.archive(work["id"], owner_user_id="owner-1")
        replayed = await productions.begin(**args)
        assert replayed["id"] == created["id"]
        with pytest.raises(ValueError, match="archived"):
            await productions.begin(**_production_args(operation_key="production-after-archive", work=work, script=script))
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_linked_production_rejects_cross_work_owner_subject_and_caller_source(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    content = PersonalIPContentRepository(sf)
    productions = PersonalIPVideoProductionRepository(sf)
    first_subject = await subjects.create(owner_user_id="owner-1", display_name="Owner one")
    other_subject = await subjects.create(owner_user_id="owner-1", display_name="Owner two")
    first = await _create_content(
        content,
        key="content-1",
        subject_id=first_subject["id"],
        title="第一稿",
    )
    second = await _create_content(
        content,
        key="content-2",
        subject_id=other_subject["id"],
        title="第二稿",
    )
    work = first["content_work"]
    script = first["script_versions"][0]
    args = _production_args(operation_key="production-guard", work=work, script=script)
    try:
        with pytest.raises(ValueError, match="provided together"):
            await productions.begin(**{**args, "script_version_id": None})
        with pytest.raises(ValueError, match="server-derived"):
            await productions.begin(**{**args, "source": {"script": "caller override"}})
        with pytest.raises(ValueError, match="subject does not match"):
            await productions.begin(**{**args, "subject_id": other_subject["id"]})
        with pytest.raises(ValueError, match="linked content script not found"):
            await productions.begin(
                **{
                    **args,
                    "content_work_id": second["content_work"]["id"],
                }
            )
        with pytest.raises(ValueError, match="linked content script not found"):
            await productions.begin(**{**args, "owner_user_id": "owner-2"})

        created = await productions.begin(**args)
        conflicting = _production_args(
            operation_key="production-guard",
            work=second["content_work"],
            script=second["script_versions"][0],
        )
        with pytest.raises(ValueError, match="already records"):
            await productions.begin(**conflicting)
        assert (await productions.get(created["id"], owner_user_id="owner-1"))["source"]["script_version_id"] == script["id"]
    finally:
        await close_engine()


@pytest.mark.parametrize(
    "update",
    [
        {"content_work_id": "work-1"},
        {"script_version_id": "script-1"},
        {"content_work_id": "   ", "script_version_id": "   "},
        {
            "content_work_id": "work-1",
            "script_version_id": "script-1",
            "source_kind": "idea",
        },
        {
            "content_work_id": "work-1",
            "script_version_id": "script-1",
            "source": {"script": "caller override"},
        },
    ],
)
def test_router_contract_rejects_invalid_linked_source_matrix(update: dict) -> None:
    payload = {
        "operation_key": "production-router",
        "title": "制作任务",
        "target_account_ids": [],
        "production_mode": "faceless_material",
        "source_kind": "script",
        "source": {},
        "delivery_spec": {},
        **update,
    }
    with pytest.raises(ValidationError):
        PersonalIPVideoProductionBeginRequest.model_validate(payload)
