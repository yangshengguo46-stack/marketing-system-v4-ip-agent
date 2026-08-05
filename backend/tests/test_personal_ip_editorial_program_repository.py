from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import func, select

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.persistence.personal_ip_content.model import (
    PersonalIPEditorialProgramVersionRow,
)
from deerflow.persistence.personal_ip_subjects import PersonalIPSubjectRepository
from deerflow.personal_ip.content_contracts import (
    SCRIPT_BOUNDARY_VERIFIER_VERSION,
    ContentWorkAppend,
    ContentWorkCreate,
    DirectionDraft,
    EditorialProgramDraft,
    ScriptDraft,
    direction_decision_digest,
    editorial_program_decision_digest,
    editorial_program_decision_payload,
    script_boundary_verifier_input_digest,
    script_decision_digest,
    semantic_causal_route_digest,
)


def _program(
    *,
    title: str = "黄金礼品的人情故事",
    parent_program_version_id: str | None = None,
    revision: str = "初版",
) -> EditorialProgramDraft:
    return EditorialProgramDraft.model_validate(
        {
            "title": title,
            "mission": {
                "goal_priority": ["trust", "conversion"],
                "time_horizon": "near_term",
                "deadline_or_window": "未来30天",
                "desired_action": "让观众把品牌纳入送礼备选",
                "success_signal": "观众主动询问送礼场景和选择方法",
                "cost_of_delay": "",
                "rationale": "先建立对送礼难题的理解，再承接产品选择。",
            },
            "audience": {
                "situation": "需要送出体面又不显得功利的礼物",
                "state": "hypothesized",
                "uncertainties": ["具体关系和预算尚不确定"],
            },
            "attribution": {
                "primary_carrier": {"kind": "brand", "identity": "测试品牌"},
                "supporting_carriers": [{"kind": "product", "identity": "黄金礼品"}],
                "desired_association": "懂送礼背后的人情尺度",
                "attribution_guard": "人物故事不得冒充Owner真实经历",
                "rationale": "品牌承接长期信任，产品只作为场景中的证据。",
            },
            "differentiation": {
                "statement": f"不只讲礼物价值，而是解决人情尺度（{revision}）",
                "contrast": "单纯展示材质、工艺和价格",
                "basis": [
                    {
                        "claim": "送礼选择同时受关系、场合和表达意图影响",
                        "state": "hypothesized",
                    }
                ],
                "reason_to_choose": "用关系选择法降低决策焦虑",
                "reason_to_believe": "后续内容会持续用具体送礼场景验证",
                "sacrifice": "不以参数罗列作为主内容",
                "test_signal": "观众能否描述自己要处理的关系场景",
                "uncertainties": ["这一假设尚未被发布数据验证"],
            },
            "editorial_spine": {
                "source_concepts": ["黄金礼品", "礼品", "送礼"],
                "human_theme": "人情世故",
                "recurring_question": "怎样把关系表达得体面又真诚",
                "boundary": "不伪造真实经历，不把产品当作人物因果的终点",
            },
            "parent_program_version_id": parent_program_version_id,
        }
    )


def _direction(
    program: EditorialProgramDraft,
    *,
    parent_direction_version_id: str | None = None,
    breakdown_version_ids: list[str] | None = None,
) -> DirectionDraft:
    return DirectionDraft.model_validate(
        {
            "contract_version": "personal-ip-direction-v2",
            "premise": "送礼送的不是东西，而是对关系分寸的判断",
            "audience_situation": "面对重要关系却不知道如何选礼的人",
            "core_tension": "想显得重视，又怕给对方压力",
            "content_promise": "看懂一次送礼选择背后的人情逻辑",
            "creative_route": "从黄金礼品逐层联想到送礼和人情世故",
            "rationale": "语义因果负责找到人性主题，本稿只做该主题下的单集取舍。",
            "truth_mode": "fictional",
            "business_relevance": "服务于品牌的长期信任与近期转化。",
            "route_kind": "semantic_story",
            "semantic_route": {
                "association_path": ["黄金礼品", "礼品", "送礼", "人情世故"],
                "human_theme": "人情世故",
                "causal_pattern": "越想用价值证明重视，越可能忽略对方的接受边界",
                "episode_tension": "贵重是诚意还是负担",
                "mission_bridge": "先帮观众看懂关系，再让产品成为可选工具",
                "attribution_guard": "信任归因于品牌的判断力，不归因于虚构人物",
            },
            "editorial_program_digest": editorial_program_decision_digest(program),
            "claim_basis": [],
            "breakdown_version_ids": breakdown_version_ids or [],
            "parent_direction_version_id": parent_direction_version_id,
        }
    )


def _legacy_direction() -> DirectionDraft:
    return DirectionDraft.model_validate(
        {
            "premise": "旧版方向仍可读",
            "audience_situation": "旧稿观众",
            "core_tension": "旧稿冲突",
            "content_promise": "旧稿承诺",
            "creative_route": "旧版路由",
            "rationale": "保留迁移前方向的兼容性。",
            "truth_mode": "factual",
        }
    )


def _create_request(
    *,
    key: str,
    subject_id: str,
    title: str,
    direction: DirectionDraft,
    program: EditorialProgramDraft | None = None,
    program_version_id: str | None = None,
) -> ContentWorkCreate:
    return ContentWorkCreate(
        idempotency_key=key,
        subject_id=subject_id,
        title=title,
        entry_route="zero_start",
        objective={
            "desired_change": "让观众能用关系分寸选礼",
            "audience_situation": "有明确送礼对象但不知道如何选择",
        },
        editorial_program=program,
        editorial_program_version_id=program_version_id,
        direction=direction,
    )


def _direction_receipt(direction: DirectionDraft) -> frozenset[str]:
    return frozenset({direction_decision_digest(direction)})


async def _program_count(session_factory) -> int:
    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(PersonalIPEditorialProgramVersionRow))
        return int(count or 0)


@pytest.mark.asyncio
async def test_editorial_program_is_reusable_versioned_owner_scoped_and_immutable(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    subjects = PersonalIPSubjectRepository(session_factory)
    repo = PersonalIPContentRepository(session_factory)
    try:
        subject = await subjects.create(
            owner_user_id="owner-1",
            display_name="黄金礼品品牌",
        )
        other_subject = await subjects.create(
            owner_user_id="owner-1",
            display_name="其他品牌",
        )

        program_v1 = _program()
        direction_v1 = _direction(program_v1)
        first_request = _create_request(
            key="editorial:create-v1",
            subject_id=subject["id"],
            title="第一条人情故事",
            program=program_v1,
            direction=direction_v1,
        )
        first = await repo.create(
            owner_user_id="owner-1",
            request=first_request,
            created_by_run_id="writer-run-1",
            verified_program_digests=frozenset({editorial_program_decision_digest(program_v1)}),
            verified_direction_digests=_direction_receipt(direction_v1),
        )

        first_program = first["editorial_program_version"]
        assert first_program is not None
        assert first_program["version_number"] == 1
        assert first_program["subject_id"] == subject["id"]
        assert first_program["decision"] == editorial_program_decision_payload(program_v1)
        assert {
            "owner_user_id",
            "operation_key",
            "operation_digest",
            "created_by_run_id",
        }.isdisjoint(first_program)
        assert first["content_work"]["editorial_program_version_id"] == first_program["id"]
        assert first["direction_versions"][0]["direction"]["editorial_program_digest"] == editorial_program_decision_digest(program_v1)
        assert await repo.get_editorial_program_version(first_program["id"], owner_user_id="owner-2") is None
        assert await repo.get_editorial_program_version(first_program["id"], owner_user_id="owner-1") == first_program

        reused_direction = _direction(program_v1)
        reused = await repo.create(
            owner_user_id="owner-1",
            request=_create_request(
                key="editorial:reuse-v1",
                subject_id=subject["id"],
                title="第二条人情故事",
                program_version_id=first_program["id"],
                direction=reused_direction,
            ),
            verified_direction_digests=_direction_receipt(reused_direction),
        )
        assert reused["editorial_program_version"]["id"] == first_program["id"]
        assert reused["content_work"]["editorial_program_version_id"] == first_program["id"]

        program_v2 = _program(
            title="黄金礼品的人情故（第二版）",
            parent_program_version_id=first_program["id"],
            revision="第二版",
        )
        direction_v2 = _direction(program_v2)
        revised = await repo.create(
            owner_user_id="owner-1",
            request=_create_request(
                key="editorial:create-v2",
                subject_id=subject["id"],
                title="第三条人情故事",
                program=program_v2,
                direction=direction_v2,
            ),
            verified_program_digests=frozenset({editorial_program_decision_digest(program_v2)}),
            verified_direction_digests=_direction_receipt(direction_v2),
        )
        second_program = revised["editorial_program_version"]
        assert second_program["version_number"] == 2
        assert second_program["program_id"] == first_program["program_id"]
        assert second_program["parent_program_version_id"] == first_program["id"]

        wrong_binding = ContentWorkAppend(
            idempotency_key="editorial:attempt-rebind",
            editorial_program_version_id=second_program["id"],
            direction=_direction(program_v2),
        )
        with pytest.raises(ValueError, match="cannot rebind"):
            await repo.append(
                first["content_work"]["id"],
                owner_user_id="owner-1",
                request=wrong_binding,
                verified_direction_digests=_direction_receipt(wrong_binding.direction),
            )

        next_direction = _direction(
            program_v1,
            parent_direction_version_id=first["direction_versions"][0]["id"],
        )
        appended = await repo.append(
            first["content_work"]["id"],
            owner_user_id="owner-1",
            request=ContentWorkAppend(
                idempotency_key="editorial:direction-v2",
                direction=next_direction,
            ),
            verified_direction_digests=_direction_receipt(next_direction),
        )
        assert appended is not None
        assert appended["editorial_program_version"]["id"] == first_program["id"]
        assert appended["direction_version"]["version_number"] == 2

        count_before_rejection = len(await repo.list("owner-1", include_archived=True))
        mismatched_direction = _direction(program_v1)
        with pytest.raises(ValueError, match="subject does not match"):
            await repo.create(
                owner_user_id="owner-1",
                request=_create_request(
                    key="editorial:wrong-subject",
                    subject_id=other_subject["id"],
                    title="不得绑定的稿件",
                    program_version_id=first_program["id"],
                    direction=mismatched_direction,
                ),
                verified_direction_digests=_direction_receipt(mismatched_direction),
            )
        assert len(await repo.list("owner-1", include_archived=True)) == (count_before_rejection)
        assert await _program_count(session_factory) == 2
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_editorial_program_and_v2_direction_require_receipts_and_commit_atomically(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    subjects = PersonalIPSubjectRepository(session_factory)
    repo = PersonalIPContentRepository(session_factory)
    try:
        subject = await subjects.create(
            owner_user_id="owner-1",
            display_name="原子性测试品牌",
        )
        program = _program()
        direction = _direction(program)

        with pytest.raises(ValueError, match="DirectionVersion requires"):
            await repo.create(
                owner_user_id="owner-1",
                request=_create_request(
                    key="editorial:missing-direction-receipt",
                    subject_id=subject["id"],
                    title="缺方向回执",
                    program=program,
                    direction=direction,
                ),
                verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
            )
        assert await repo.list("owner-1", include_archived=True) == []
        assert await _program_count(session_factory) == 0

        with pytest.raises(ValueError, match="decision receipt"):
            await repo.create(
                owner_user_id="owner-1",
                request=_create_request(
                    key="editorial:missing-program-receipt",
                    subject_id=subject["id"],
                    title="缺母盘回执",
                    program=program,
                    direction=direction,
                ),
                verified_direction_digests=_direction_receipt(direction),
            )
        assert await repo.list("owner-1", include_archived=True) == []
        assert await _program_count(session_factory) == 0

        invalid_direction = _direction(
            program,
            breakdown_version_ids=["breakdown-does-not-exist"],
        )
        with pytest.raises(ValueError, match="breakdown version"):
            await repo.create(
                owner_user_id="owner-1",
                request=_create_request(
                    key="editorial:atomic-failure",
                    subject_id=subject["id"],
                    title="后续验证失败",
                    program=program,
                    direction=invalid_direction,
                ),
                verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
                verified_direction_digests=_direction_receipt(invalid_direction),
            )
        assert await repo.list("owner-1", include_archived=True) == []
        assert await _program_count(session_factory) == 0

        script = ScriptDraft.model_validate(
            {
                "title": "送礼分寸",
                "story_mode": "factual",
                "script_text": "这是Owner明确要测试的送礼内容方向。",
                "claim_basis": [
                    {
                        "claim": "Owner要测试送礼场景内容",
                        "state": "user_asserted",
                        "usage": "attributed_fact",
                    }
                ],
            }
        )
        with pytest.raises(ValueError, match="ScriptVersion requires"):
            await repo.create(
                owner_user_id="owner-1",
                request=ContentWorkCreate(
                    **_create_request(
                        key="editorial:atomic-script-failure",
                        subject_id=subject["id"],
                        title="三层原子提交",
                        program=program,
                        direction=direction,
                    ).model_dump(mode="python", exclude={"script"}),
                    script=script,
                ),
                verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
                verified_direction_digests=_direction_receipt(direction),
            )
        assert await repo.list("owner-1", include_archived=True) == []
        assert await _program_count(session_factory) == 0

        created = await repo.create(
            owner_user_id="owner-1",
            request=_create_request(
                key="editorial:valid",
                subject_id=subject["id"],
                title="有效新稿",
                program=program,
                direction=direction,
            ),
            verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
            verified_direction_digests=_direction_receipt(direction),
        )
        program_version_id = created["editorial_program_version"]["id"]

        replayed = await repo.create(
            owner_user_id="owner-1",
            request=_create_request(
                key="editorial:valid",
                subject_id=subject["id"],
                title="有效新稿",
                program=program,
                direction=direction,
            ),
        )
        assert replayed["replayed"] is True
        assert replayed["editorial_program_version"]["id"] == program_version_id

        legacy = await repo.create(
            owner_user_id="owner-1",
            request=_create_request(
                key="editorial:legacy-v1",
                subject_id=subject["id"],
                title="旧版稿件",
                direction=_legacy_direction(),
            ),
        )
        assert legacy["editorial_program_version"] is None
        second_legacy_direction = await repo.append(
            legacy["content_work"]["id"],
            owner_user_id="owner-1",
            request=ContentWorkAppend(
                idempotency_key="editorial:legacy-v1-second",
                direction=_legacy_direction(),
            ),
        )
        assert second_legacy_direction is not None
        assert second_legacy_direction["direction_version"]["version_number"] == 2
        late_binding_direction = _direction(program)
        migrated = await repo.append(
            legacy["content_work"]["id"],
            owner_user_id="owner-1",
            request=ContentWorkAppend(
                idempotency_key="editorial:late-binding",
                editorial_program_version_id=program_version_id,
                direction=late_binding_direction,
            ),
            verified_direction_digests=_direction_receipt(late_binding_direction),
        )
        assert migrated is not None
        assert migrated["editorial_program_version"]["id"] == program_version_id
        assert migrated["direction_version"]["version_number"] == 3
        legacy_lineage = await repo.get_lineage(legacy["content_work"]["id"], owner_user_id="owner-1")
        assert legacy_lineage is not None
        assert legacy_lineage["editorial_program_version"]["id"] == (program_version_id)
        assert [version["direction"]["contract_version"] for version in legacy_lineage["direction_versions"]] == [
            "personal-ip-direction-v1",
            "personal-ip-direction-v1",
            "personal-ip-direction-v2",
        ]

        with pytest.raises(ValueError, match="requires v2"):
            await repo.append(
                legacy["content_work"]["id"],
                owner_user_id="owner-1",
                request=ContentWorkAppend(
                    idempotency_key="editorial:no-v1-after-binding",
                    direction=_legacy_direction(),
                ),
            )
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_repository_rejects_a_broken_semantic_seed_binding_atomically(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    subjects = PersonalIPSubjectRepository(session_factory)
    repo = PersonalIPContentRepository(session_factory)
    try:
        subject = await subjects.create(
            owner_user_id="owner-1",
            display_name="语义绑定测试品牌",
        )
        program = _program()
        direction = _direction(program)
        assert direction.semantic_route is not None
        route_digest = semantic_causal_route_digest(direction.semantic_route)
        script_text = "他越想用贵重证明重视，越让对方感到越界。"
        locked_story = "他越想证明重视，对方却越后退；于是他改为先询问边界，必须在立即证明自己和尊重对方之间选择，承担被误解的代价。"
        boundary_receipt = {
            "supported": True,
            "unsupported_spans": [],
            "reason_codes": [],
            "semantic_route_supported": True,
            "semantic_route_digest": route_digest,
            "verifier_input_sha256": script_boundary_verifier_input_digest(
                direction,
                locked_story=locked_story,
                script_text=script_text,
            ),
        }
        boundary_digest = hashlib.sha256(
            json.dumps(
                boundary_receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        broken_script = ScriptDraft.model_validate(
            {
                "title": "不得持久化的断裂剧本",
                "story_mode": "fictional",
                "script_text": script_text,
                "story_engine_seed": {
                    "recurring_conflict": "一个人反复用过度付出证明重视",
                    "desire_a": "让对方马上感到被重视",
                    "desire_b": "守住对方的接受边界",
                    "relationship_at_stake": "两人之间的信任",
                    "causal_pattern": direction.semantic_route.causal_pattern,
                    "semantic_route_digest": "0" * 64,
                },
                "locked_story": locked_story,
                "creative_elements": [
                    {
                        "element": "人物与事件为虚构",
                        "kind": "fictional",
                        "disclosure": "不登记为 Owner 经历",
                    }
                ],
                "production_notes": {
                    "boundary_verifier_version": SCRIPT_BOUNDARY_VERIFIER_VERSION,
                    "boundary_receipt": boundary_receipt,
                    "boundary_receipt_sha256": boundary_digest,
                    "editorial_program_sha256": editorial_program_decision_digest(program),
                    "direction_decision_sha256": direction_decision_digest(direction),
                    "semantic_route_sha256": route_digest,
                },
            }
        )
        request = ContentWorkCreate.model_validate(
            {
                "idempotency_key": "editorial:broken-semantic-script",
                "subject_id": subject["id"],
                "title": "语义断裂原子性",
                "entry_route": "zero_start",
                "objective": {"desired_change": "拒绝断裂语义回执"},
                "editorial_program": program,
                "direction": direction,
                "script": broken_script,
            }
        )

        with pytest.raises(ValueError, match="story seed does not bind"):
            await repo.create(
                owner_user_id="owner-1",
                request=request,
                verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
                verified_direction_digests=_direction_receipt(direction),
                verified_script_digests=frozenset({script_decision_digest(broken_script)}),
            )
        assert await repo.list("owner-1", include_archived=True) == []
        assert await _program_count(session_factory) == 0
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_repository_rejects_program_route_mismatch_atomically(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    subjects = PersonalIPSubjectRepository(session_factory)
    repo = PersonalIPContentRepository(session_factory)
    try:
        subject = await subjects.create(
            owner_user_id="owner-1",
            display_name="路径原子性测试品牌",
        )
        program = _program()
        direction_payload = _direction(program).model_dump(mode="json")
        direction_payload["semantic_route"]["association_path"][0] = "非方案源概念"
        broken_direction = DirectionDraft.model_validate(direction_payload)
        request = ContentWorkCreate.model_validate(
            {
                "idempotency_key": "editorial:broken-program-route",
                "subject_id": subject["id"],
                "title": "不得持久化的路径",
                "entry_route": "zero_start",
                "objective": {"desired_change": "拒绝与总编导方案断裂的语义路径"},
                "editorial_program": program,
                "direction": broken_direction,
            }
        )

        with pytest.raises(ValueError, match="must start from a selected source concept"):
            await repo.create(
                owner_user_id="owner-1",
                request=request,
                verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
                verified_direction_digests=_direction_receipt(broken_direction),
            )
        assert await repo.list("owner-1", include_archived=True) == []
        assert await _program_count(session_factory) == 0
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_repository_rejects_script_replaced_after_verification_atomically(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    subjects = PersonalIPSubjectRepository(session_factory)
    repo = PersonalIPContentRepository(session_factory)
    try:
        subject = await subjects.create(
            owner_user_id="owner-1",
            display_name="剧本回执原子性测试品牌",
        )
        program = _program()
        direction = _direction(program)
        assert direction.semantic_route is not None
        route_digest = semantic_causal_route_digest(direction.semantic_route)
        reviewed_script_text = "他先问清对方的接受边界，再选择如何表达重视。"
        replaced_script_text = "验证完成后被替换成了一段未核验的新断言。"
        locked_story = "他想立刻证明重视，对方却越后退；他转而先问边界，只能在自证与尊重之间选择，代价是暂时被误解，最终关系重新建立信任。"
        boundary_receipt = {
            "supported": True,
            "unsupported_spans": [],
            "reason_codes": [],
            "semantic_route_supported": True,
            "semantic_route_digest": route_digest,
            "verifier_input_sha256": script_boundary_verifier_input_digest(
                direction,
                locked_story=locked_story,
                script_text=reviewed_script_text,
            ),
        }
        boundary_digest = hashlib.sha256(
            json.dumps(
                boundary_receipt,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        script = ScriptDraft.model_validate(
            {
                "title": "被替换的正式稿",
                "story_mode": "fictional",
                "script_text": replaced_script_text,
                "story_engine_seed": {
                    "recurring_conflict": "一个人反复用过度付出证明重视",
                    "desire_a": "让对方马上感到被重视",
                    "desire_b": "守住对方的接受边界",
                    "relationship_at_stake": "两人之间的信任",
                    "causal_pattern": direction.semantic_route.causal_pattern,
                    "semantic_route_digest": route_digest,
                },
                "locked_story": locked_story,
                "creative_elements": [
                    {
                        "element": "人物与事件为虚构",
                        "kind": "fictional",
                        "disclosure": "不登记为 Owner 经历",
                    }
                ],
                "production_notes": {
                    "boundary_verifier_version": SCRIPT_BOUNDARY_VERIFIER_VERSION,
                    "boundary_receipt": boundary_receipt,
                    "boundary_receipt_sha256": boundary_digest,
                    "editorial_program_sha256": editorial_program_decision_digest(program),
                    "direction_decision_sha256": direction_decision_digest(direction),
                    "semantic_route_sha256": route_digest,
                },
            }
        )
        request = ContentWorkCreate.model_validate(
            {
                "idempotency_key": "editorial:replaced-after-verification",
                "subject_id": subject["id"],
                "title": "剧本回执精确绑定",
                "entry_route": "zero_start",
                "objective": {"desired_change": "拒绝验证后被替换的正式稿"},
                "editorial_program": program,
                "direction": direction,
                "script": script,
            }
        )

        with pytest.raises(ValueError, match="exact verifier input"):
            await repo.create(
                owner_user_id="owner-1",
                request=request,
                verified_program_digests=frozenset({editorial_program_decision_digest(program)}),
                verified_direction_digests=_direction_receipt(direction),
                verified_script_digests=frozenset({script_decision_digest(script)}),
            )
        assert await repo.list("owner-1", include_archived=True) == []
        assert await _program_count(session_factory) == 0
    finally:
        await close_engine()
