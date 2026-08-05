from __future__ import annotations

import hashlib
import json

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.content_contracts import (
    ContentWorkCreate,
    SemanticCausalRoute,
    StoryEngineSeed,
    WriterBrainRequest,
    semantic_causal_route_digest,
)
from deerflow.personal_ip.writer_brain import (
    WriterBrainService,
    render_story_engine_input,
    validate_locked_story,
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


SEMANTIC_ROUTE = {
    "association_path": ["幽默表达样本", "关系里的回避", "认真表达"],
    "human_theme": "认真表达",
    "causal_pattern": "旧策略让误解加深，换招后必须承担失去认可的代价",
    "episode_tension": "继续讨人喜欢与冒险说真话不能兼得",
    "mission_bridge": "让观众记住认真表达的关系议题",
    "attribution_guard": "不把真实创作者经历或商业目标塞进虚构人物",
}
SEMANTIC_DIGEST = semantic_causal_route_digest(SemanticCausalRoute.model_validate(SEMANTIC_ROUTE))
BOUNDARY_OK = json.dumps(
    {
        "supported": True,
        "unsupported_spans": [],
        "reason_codes": [],
        "semantic_route_supported": True,
        "semantic_route_digest": SEMANTIC_DIGEST,
    },
    ensure_ascii=False,
    separators=(",", ":"),
)
BOUNDARY_DIRECT_OK = '{"supported":true,"unsupported_spans":[],"reason_codes":[],"semantic_route_supported":true,"semantic_route_digest":null}'


def _program(*, semantic: bool) -> dict:
    payload = {
        "title": "认真表达内容主线" if semantic else "公开演示内容主线",
        "mission": {
            "goal_priority": ["recognition"] if semantic else ["trust"],
            "time_horizon": "long_term" if semantic else "near_term",
            "deadline_or_window": "未来一年" if semantic else "本月",
            "desired_action": "记住认真表达的关系议题" if semantic else "理解项目已经启动",
            "success_signal": "观众能复述关系议题" if semantic else "出现基于真实进展的询问",
            "non_goals": ["不把创作故事登记成真实履历"],
            "rationale": "先固定当前最重要的结果，不让故事改写任务。",
        },
        "audience": {
            "situation": "关系中常用玩笑回避认真表达的人" if semantic else "还不知道项目进展的人",
            "state": "hypothesized",
            "uncertainties": ["尚无发布后观察"],
        },
        "attribution": {
            "primary_carrier": {"kind": "person", "identity": "创作者本人"},
            "supporting_carriers": [],
            "desired_association": "能说清关系中的两难" if semantic else "只用真实进展建立可信度",
            "attribution_guard": "真实本人不是虚构故事主人公",
            "rationale": "归因给人的判断，不归因给一次虚构事件。",
        },
        "differentiation": {
            "statement": "从认真表达的具体两难切入" if semantic else "用可核对进展而非效果承诺",
            "contrast": "泛化情绪口号" if semantic else "空泛结果宣传",
            "basis": [{"claim": "用户选择本轮内容目标", "state": "user_asserted"}],
            "reason_to_choose": "议题具体且可反复观察" if semantic else "信息可核对",
            "reason_to_believe": "只使用明确提供的事实",
            "sacrifice": "不编造履历或效果",
            "test_signal": "观众能准确复述本轮承诺",
            "uncertainties": ["差异化仍待真实发布验证"],
        },
    }
    if semantic:
        payload["editorial_spine"] = {
            "source_concepts": ["幽默表达样本"],
            "human_theme": "认真表达",
            "recurring_question": "一个人何时愿意放弃讨喜而说真话",
            "boundary": "不虚构 Owner 经历，不让商业目标进入故事因果",
        }
    return payload


def _fiction_request(subject_id: str | None = None) -> WriterBrainRequest:
    return WriterBrainRequest.model_validate(
        {
            "subject_id": subject_id,
            "work_title": "第一次认真说话",
            "entry_route": "zero_start",
            "objective": {
                "desired_change": "让观众愿意认真表达一次",
                "audience_situation": "关系中总用玩笑回避的人",
                "business_context": "这段目标不得进入纯故事模型",
            },
            "editorial_program": _program(semantic=True),
            "direction": {
                "contract_version": "personal-ip-direction-v2",
                "premise": "玩笑成为真话的障碍",
                "audience_situation": "习惯用轻松逃避认真表达的人",
                "core_tension": "被喜欢与被真正理解无法继续靠同一旧策略获得",
                "content_promise": "看见一次说真话如何改变关系",
                "creative_route": "纯虚构关系故事",
                "rationale": "方向理由留在决策层，不进入故事。",
                "truth_mode": "fictional",
                "route_kind": "semantic_story",
                "semantic_route": SEMANTIC_ROUTE,
                "business_relevance": "用于一个商业目标，但不得污染故事。",
            },
            "story_engine_seed": _seed(),
            "production_translation": {
                "form": "scene",
                "setting": "一张餐桌",
                "constraints": ["一人可分饰两角"],
            },
        }
    )


class _FakeModel:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)


@pytest.mark.asyncio
async def test_writer_brain_locks_context_free_story_then_persists_script_and_replays(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    content = PersonalIPContentRepository(sf)
    subject = await subjects.create(owner_user_id="owner-1", display_name="真实果园主")
    locked_story = "一个总用玩笑求助的人认真开口后，朋友却仍当笑话，于是他改为承认害怕；他必须在继续讨喜和说真话之间选择，冒着失去好感的代价，终于让朋友第一次认真听完。"
    fake = _FakeModel(
        [
            locked_story,
            "【镜头】餐桌近景。\n他收起笑容：这次我不是开玩笑。\n朋友终于放下筷子。",
            BOUNDARY_OK,
        ]
    )
    service = WriterBrainService(content, subjects=subjects, model_runner=fake)
    request = _fiction_request(subject["id"])
    try:
        result = await service.generate_and_save(
            owner_user_id="owner-1",
            request=request,
            idempotency_key="run-1:tool-1",
            created_by_run_id="run-1",
            app_config=object(),  # The fake runner does not inspect provider configuration.
            thread_id="thread-1",
        )

        assert result["story_mode"] == "fictional"
        assert result["locked_story"] == locked_story
        assert result["locked_story_sha256"] == hashlib.sha256(locked_story.encode()).hexdigest()
        assert len(fake.calls) == 3
        lineage = await content.get_lineage(
            result["content_work_id"],
            owner_user_id="owner-1",
        )
        assert lineage is not None
        notes = lineage["script_versions"][0]["production_notes"]
        assert notes["boundary_receipt"]["semantic_route_digest"] == (SEMANTIC_DIGEST)
        assert notes["boundary_receipt"]["verifier_input_sha256"] == hashlib.sha256(fake.calls[2]["user_content"].encode("utf-8")).hexdigest()
        assert (
            notes["boundary_receipt_sha256"]
            == hashlib.sha256(
                json.dumps(
                    notes["boundary_receipt"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
        )

        story_payload = fake.calls[0]["user_content"]
        parsed_story_payload = json.loads(story_payload)
        assert parsed_story_payload["seed"]["semantic_route_digest"] == SEMANTIC_DIGEST
        assert parsed_story_payload["seed"]["causal_pattern"] == SEMANTIC_ROUTE["causal_pattern"]
        for required_marker in ("但", "转而", "只能", "代价是"):
            assert required_marker in fake.calls[0]["system_instruction"]
        for forbidden in (
            "真实果园主",
            "business_context",
            "objective",
            "production_constraints",
            "一张餐桌",
            "business_relevance",
        ):
            assert forbidden not in story_payload

        script_payload = json.loads(fake.calls[1]["user_content"])
        assert script_payload["locked_story"] == locked_story
        assert script_payload["production_translation"]["setting"] == "一张餐桌"
        assert "business_relevance" not in script_payload

        verifier_payload = json.loads(fake.calls[2]["user_content"])
        assert verifier_payload["locked_story"] == locked_story
        assert verifier_payload["claim_basis"] == []
        assert "不能证明没有音乐、音效" in fake.calls[2]["system_instruction"]
        for forbidden in (
            "真实果园主",
            "business_context",
            "objective",
            "production_translation",
            "business_relevance",
        ):
            assert forbidden not in fake.calls[2]["user_content"]

        replay = await service.generate_and_save(
            owner_user_id="owner-1",
            request=request,
            idempotency_key="run-1:tool-1",
            created_by_run_id="run-retry",
            app_config=object(),
            thread_id="thread-1",
        )
        assert replay["replayed"] is True
        assert replay["script_version_id"] == result["script_version_id"]
        assert len(fake.calls) == 3, "idempotent replay must not spend another model call"

        await content.archive(result["content_work_id"], owner_user_id="owner-1")
        archived_replay = await service.generate_and_save(
            owner_user_id="owner-1",
            request=request,
            idempotency_key="run-1:tool-1",
            created_by_run_id="run-archived-retry",
            app_config=object(),
            thread_id="thread-1",
        )
        assert archived_replay["script_version_id"] == result["script_version_id"]
        with pytest.raises(ValueError, match="archived"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=request.model_copy(
                    update={
                        "content_work_id": result["content_work_id"],
                        "editorial_program": None,
                        "editorial_program_version_id": result["editorial_program_version_id"],
                    }
                ),
                idempotency_key="run-archived:new-tool",
                created_by_run_id="run-archived",
                app_config=object(),
                thread_id="thread-1",
            )
        assert len(fake.calls) == 3
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_legacy_work_program_binding_replays_before_current_state_checks(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    content = PersonalIPContentRepository(sf)
    subject_a = await subjects.create(
        owner_user_id="owner-1",
        display_name="主体甲",
    )
    subject_b = await subjects.create(
        owner_user_id="owner-1",
        display_name="主体乙",
    )
    legacy = await content.create(
        owner_user_id="owner-1",
        request=ContentWorkCreate.model_validate(
            {
                "idempotency_key": "legacy-work:create",
                "subject_id": subject_a["id"],
                "title": "历史作品",
                "entry_route": "zero_start",
                "objective": {"desired_change": "记录一次真实进展"},
                "direction": {
                    "premise": "从真实进展开始",
                    "audience_situation": "还不知道进展的人",
                    "core_tension": "展示进展但不夸大",
                    "content_promise": "只说已经发生的事",
                    "creative_route": "事实口述",
                    "rationale": "保留历史 v1 谱系。",
                    "truth_mode": "factual",
                },
            }
        ),
    )
    request = WriterBrainRequest.model_validate(
        {
            "content_work_id": legacy["content_work"]["id"],
            "subject_id": subject_a["id"],
            "work_title": "历史作品",
            "editorial_program": _program(semantic=False),
            "direction": {
                "contract_version": "personal-ip-direction-v2",
                "premise": "从已完成的一步开始",
                "audience_situation": "还不知道进展的人",
                "core_tension": "展示进展但不夸大结果",
                "content_promise": "只说已经发生的事",
                "creative_route": "第一人称事实口述",
                "rationale": "事实足以成立。",
                "truth_mode": "factual",
                "route_kind": "demonstration",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
        }
    )
    fake = _FakeModel(
        [
            "我今天完成了第一次公开演示。",
            BOUNDARY_DIRECT_OK,
        ]
    )
    service = WriterBrainService(content, subjects=subjects, model_runner=fake)
    try:
        first = await service.generate_and_save(
            owner_user_id="owner-1",
            request=request,
            idempotency_key="legacy-work:bind-v2",
            created_by_run_id="legacy-bind-run",
            app_config=object(),
            thread_id="legacy-thread",
        )
        replay = await service.generate_and_save(
            owner_user_id="owner-1",
            request=request,
            idempotency_key="legacy-work:bind-v2",
            created_by_run_id="legacy-bind-retry",
            app_config=object(),
            thread_id="legacy-thread",
        )
        assert replay["replayed"] is True
        assert replay["script_version_id"] == first["script_version_id"]
        assert len(fake.calls) == 2

        wrong_subject_request = WriterBrainRequest.model_validate(
            {
                **request.model_dump(
                    mode="json",
                    exclude={
                        "content_work_id",
                        "editorial_program",
                        "editorial_program_version_id",
                    },
                ),
                "content_work_id": None,
                "subject_id": subject_b["id"],
                "work_title": "不得跨主体的新作品",
                "entry_route": "zero_start",
                "objective": {"desired_change": "不得读取其他主体判断"},
                "editorial_program_version_id": first["editorial_program_version_id"],
            }
        )
        with pytest.raises(ValueError, match="subject does not match"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=wrong_subject_request,
                idempotency_key="wrong-subject:new-work",
                created_by_run_id="wrong-subject-run",
                app_config=object(),
                thread_id="wrong-subject-thread",
            )
        assert len(fake.calls) == 2, "subject mismatch must fail before model spend"
    finally:
        await close_engine()


@pytest.mark.parametrize("leak_source", ["carrier", "source_concept"])
@pytest.mark.asyncio
async def test_writer_brain_rejects_real_identity_in_seed_before_model_spend(
    tmp_path,
    leak_source: str,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    payload = _fiction_request().model_dump(mode="json")
    if leak_source == "carrier":
        leaked_term = "周大福"
        payload["editorial_program"]["attribution"]["primary_carrier"] = {
            "kind": "brand",
            "identity": leaked_term,
        }
    else:
        leaked_term = "黄金礼品"
        payload["editorial_program"]["editorial_spine"]["source_concepts"] = [leaked_term]
        payload["direction"]["semantic_route"]["association_path"][0] = leaked_term
    payload["story_engine_seed"]["recurring_conflict"] = f"{leaked_term}反复让一个人在两种欲望之间摇摆"
    request = WriterBrainRequest.model_validate(payload)
    fake = _FakeModel([])
    service = WriterBrainService(
        content,
        subjects=PersonalIPSubjectRepository(sf),
        model_runner=fake,
    )
    try:
        with pytest.raises(ValueError, match="story_engine_seed leaked"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=request,
                idempotency_key=f"seed-leak:{leak_source}",
                created_by_run_id="seed-leak-run",
                app_config=object(),
                thread_id="seed-leak-thread",
            )
        assert fake.calls == []
        assert await content.list("owner-1") == []
    finally:
        await close_engine()


@pytest.mark.parametrize(
    ("leak_source", "leaked_term"),
    [("subject", "李"), ("carrier", "金"), ("source_concept", "礼")],
)
@pytest.mark.asyncio
async def test_writer_brain_rejects_single_character_seed_leaks_before_model_spend(
    tmp_path,
    leak_source: str,
    leaked_term: str,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    content = PersonalIPContentRepository(sf)
    payload = _fiction_request().model_dump(mode="json")
    if leak_source == "subject":
        subject = await subjects.create(
            owner_user_id="owner-1",
            display_name=leaked_term,
        )
        payload["subject_id"] = subject["id"]
    elif leak_source == "carrier":
        payload["editorial_program"]["attribution"]["primary_carrier"] = {
            "kind": "brand",
            "identity": leaked_term,
        }
    else:
        payload["editorial_program"]["editorial_spine"]["source_concepts"] = [leaked_term]
        payload["direction"]["semantic_route"]["association_path"][0] = leaked_term
    payload["story_engine_seed"]["recurring_conflict"] = f"{leaked_term}让一个人反复在两种欲望之间摇摆"
    request = WriterBrainRequest.model_validate(payload)
    fake = _FakeModel([])
    service = WriterBrainService(
        content,
        subjects=subjects,
        model_runner=fake,
    )
    try:
        with pytest.raises(ValueError, match="story_engine_seed leaked"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=request,
                idempotency_key=f"single-character-seed-leak:{leak_source}",
                created_by_run_id="single-character-seed-leak-run",
                app_config=object(),
                thread_id="single-character-seed-leak-thread",
            )
        assert fake.calls == []
        assert await content.list("owner-1") == []
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_writer_brain_rejects_story_context_leak_without_persisting(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    fake = _FakeModel(["真实果园主决定拍视频，却失败了，于是改文案；他必须选择流量，承担代价。"])
    service = WriterBrainService(content, subjects=PersonalIPSubjectRepository(sf), model_runner=fake)
    try:
        with pytest.raises(ValueError, match="forbidden context term"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=_fiction_request(),
                idempotency_key="run-1:tool-bad",
                created_by_run_id="run-1",
                app_config=object(),
                thread_id="thread-1",
            )
        assert await content.list("owner-1") == []
        assert len(fake.calls) == 1
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_writer_brain_rejects_subject_leak_in_fictional_script_without_persisting(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    subjects = PersonalIPSubjectRepository(sf)
    content = PersonalIPContentRepository(sf)
    subject = await subjects.create(owner_user_id="owner-1", display_name="真实果园主")
    locked_story = "一个总用玩笑求助的人认真开口后，朋友却仍当笑话，于是他改为承认害怕；他必须在继续讨喜和说真话之间选择，冒着失去好感的代价，终于让朋友第一次认真听完。"
    fake = _FakeModel(
        [
            locked_story,
            "真实果园主收起笑容，朋友第一次听完了他的话。",
        ]
    )
    service = WriterBrainService(content, subjects=subjects, model_runner=fake)
    try:
        with pytest.raises(ValueError, match="leaked forbidden context term"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=_fiction_request(subject["id"]),
                idempotency_key="run-script-leak:tool-1",
                created_by_run_id="run-script-leak",
                app_config=object(),
                thread_id="thread-script-leak",
            )
        assert await content.list("owner-1") == []
        assert len(fake.calls) == 2, "deterministic leak rejection must happen before verifier spend"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_factual_writer_uses_claim_basis_and_skips_fiction_engine(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    fake = _FakeModel(
        [
            "我今天完成了第一次公开演示；这是我本人在本轮提供的事实。",
            BOUNDARY_DIRECT_OK,
        ]
    )
    service = WriterBrainService(content, subjects=PersonalIPSubjectRepository(sf), model_runner=fake)
    request = WriterBrainRequest.model_validate(
        {
            "work_title": "第一次演示",
            "entry_route": "zero_start",
            "objective": {"desired_change": "让观众知道项目已经启动"},
            "editorial_program": _program(semantic=False),
            "direction": {
                "contract_version": "personal-ip-direction-v2",
                "premise": "从完成的一步开始",
                "audience_situation": "还不知道项目进展的人",
                "core_tension": "展示进展但不夸大结果",
                "content_promise": "只说已经发生的事",
                "creative_route": "第一人称事实口述",
                "rationale": "事实足以成立，不添加戏剧事件。",
                "truth_mode": "factual",
                "route_kind": "demonstration",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
            "production_translation": {"form": "spoken"},
        }
    )
    try:
        result = await service.generate_and_save(
            owner_user_id="owner-1",
            request=request,
            idempotency_key="run-fact:tool-1",
            created_by_run_id="run-fact",
            app_config=object(),
            thread_id="thread-fact",
        )
        assert len(fake.calls) == 2
        payload = json.loads(fake.calls[0]["user_content"])
        assert payload["story_mode"] == "factual"
        assert payload["claim_basis"][0]["claim"] == "今天完成了第一次公开演示"
        assert "locked_story" not in payload
        assert result["locked_story_sha256"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_writer_brain_rejects_unsupported_factual_claim_without_partial_commit(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    fake = _FakeModel(
        [
            "我今天完成了第一次公开演示，而且已经帮助一万名客户增长。",
            '{"supported":false,"unsupported_spans":["帮助一万名客户增长"],"reason_codes":["UNSUPPORTED_RESULT"],"semantic_route_supported":true,"semantic_route_digest":null}',
        ]
    )
    service = WriterBrainService(
        content,
        subjects=PersonalIPSubjectRepository(sf),
        model_runner=fake,
    )
    request = WriterBrainRequest.model_validate(
        {
            "work_title": "第一次演示",
            "entry_route": "zero_start",
            "objective": {"desired_change": "让观众知道项目已经启动"},
            "editorial_program": _program(semantic=False),
            "direction": {
                "contract_version": "personal-ip-direction-v2",
                "premise": "从完成的一步开始",
                "audience_situation": "还不知道项目进展的人",
                "core_tension": "展示进展但不夸大结果",
                "content_promise": "只说已经发生的事",
                "creative_route": "第一人称事实口述",
                "rationale": "事实足以成立。",
                "truth_mode": "factual",
                "route_kind": "proof",
                "claim_basis": [
                    {
                        "claim": "今天完成了第一次公开演示",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            },
        }
    )
    try:
        with pytest.raises(ValueError, match="outside its truth boundary"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=request,
                idempotency_key="run-unsupported:tool-1",
                created_by_run_id="run-unsupported",
                app_config=object(),
                thread_id="thread-unsupported",
            )
        assert await content.list("owner-1") == []
    finally:
        await close_engine()


def test_story_engine_serialization_depends_only_on_sanitized_seed() -> None:
    seed = StoryEngineSeed.model_validate(_seed())
    first = render_story_engine_input(seed)
    second = render_story_engine_input(seed)
    assert first == second
    assert "brief" not in first
    assert "facts" not in first
    assert "objective" not in first
    assert "production_constraints" not in first
    assert "frozen_route" not in first


@pytest.mark.parametrize(
    "leak",
    [
        "花店老板",
        "陌生商户",
        "餐饮行业",
        "营销公司",
        "flower shop owner",
        "customers want lower prices",
        "a business in trouble",
        "sales strategy",
        "startup founder",
        "content creator",
        "创业者想获得认可",
        "主播担心失去粉丝",
        "电商运营反复改方案",
    ],
)
def test_story_engine_seed_rejects_industry_context(leak: str) -> None:
    payload = _seed()
    payload["recurring_conflict"] = f"{leak}总在关系里回避说真话"
    with pytest.raises(ValueError, match="industry-neutral"):
        StoryEngineSeed.model_validate(payload)


@pytest.mark.asyncio
async def test_writer_brain_rejects_production_behavior_as_fictional_plot(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    content = PersonalIPContentRepository(sf)
    locked_story = "他想挽回朋友，但道歉仍被拒绝；于是转而承认自己的害怕，他只能在保住面子和坦白之间选择，承担失去认可的代价，最终朋友愿意再听一次。"
    fake = _FakeModel(
        [
            locked_story,
            "他决定拍视频，转而出镜，发布后终于获得认可。",
            BOUNDARY_OK,
        ]
    )
    service = WriterBrainService(
        content,
        subjects=PersonalIPSubjectRepository(sf),
        model_runner=fake,
    )
    try:
        with pytest.raises(ValueError, match="leaked forbidden context term"):
            await service.generate_and_save(
                owner_user_id="owner-1",
                request=_fiction_request(),
                idempotency_key="run-production-plot:tool-1",
                created_by_run_id="run-production-plot",
                app_config=object(),
                thread_id="thread-production-plot",
            )
        assert await content.list("owner-1") == []
        assert len(fake.calls) == 2, "deterministic rejection must precede verifier spend"
    finally:
        await close_engine()


@pytest.mark.parametrize(
    "leak",
    [
        "startup founder想道歉，但仍被拒绝；于是转而坦白，他只能在面子和友情之间选择，代价是失去认可。",
        "内容创作者想被理解，但旧办法失败；于是转而直说，他只能放下面子，代价是失去掌声。",
    ],
)
def test_locked_story_rejects_untranslated_business_context(leak: str) -> None:
    with pytest.raises(ValueError, match="Chinese-only|forbidden context term"):
        validate_locked_story(leak)
