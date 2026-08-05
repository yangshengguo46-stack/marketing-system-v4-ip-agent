"""Frozen fixtures for the default IP Agent v2 behavior acceptance tests.

The examples in this file are acceptance evidence, not product runtime data.
They deliberately use only production-owned content contracts and never load
the quarantined research catalog or an external Skill.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from deerflow.personal_ip.content_contracts import (
    SCRIPT_BOUNDARY_VERIFIER_VERSION,
    ContentObjective,
    DirectionDraft,
    EditorialProgramDraft,
    ProductionTranslation,
    ScriptDraft,
    StoryEngineSeed,
    WriterBrainRequest,
    direction_decision_digest,
    editorial_program_decision_digest,
    editorial_program_decision_payload,
    script_boundary_verifier_input_digest,
    semantic_causal_route_digest,
    validate_direction_program_binding,
    validate_script_direction_binding,
)


@dataclass(frozen=True)
class BehaviorCase:
    scenario_id: str
    prompt: str
    lineage: dict[str, Any]
    tool_trace: list[dict[str, Any]]
    writer_model_trace: list[dict[str, Any]]
    final_text: str
    expected_route: str
    expected_story_mode: str
    expected_writer_model_calls: tuple[str, ...]
    negative_lineage: dict[str, Any]
    negative_tool_trace: list[dict[str, Any]]
    negative_final_text: str
    negative_failure_code: str


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _difference(
    *,
    statement: str,
    contrast: str,
    basis: list[str],
    reason_to_choose: str,
    reason_to_believe: str,
    sacrifice: str,
    test_signal: str,
) -> dict[str, Any]:
    return {
        "state": "hypothesized",
        "statement": statement,
        "contrast": contrast,
        "basis": [{"claim": claim, "state": "user_asserted"} for claim in basis],
        "reason_to_choose": reason_to_choose,
        "reason_to_believe": reason_to_believe,
        "sacrifice": sacrifice,
        "test_signal": test_signal,
        "uncertainties": ["尚未用真实发布反馈验证"],
    }


def _claim(claim: str, *, usage: str = "attributed_fact") -> dict[str, Any]:
    return {
        "claim": claim,
        "state": "user_asserted",
        "usage": usage,
        "evidence_refs": [],
    }


def _build_lineage(
    *,
    scenario_id: str,
    prompt: str,
    work_title: str,
    objective: dict[str, Any],
    program_payload: dict[str, Any],
    direction_payload: dict[str, Any],
    script_text: str,
    seed_payload: dict[str, Any] | None = None,
    locked_story: str | None = None,
    production_translation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    objective_value = ContentObjective.model_validate(objective).model_dump(mode="json")
    translation_value = ProductionTranslation.model_validate(production_translation or {}).model_dump(mode="json")
    program = EditorialProgramDraft.model_validate(program_payload)
    program_digest = editorial_program_decision_digest(program)
    bound_direction = DirectionDraft.model_validate(
        {
            **direction_payload,
            "editorial_program_digest": program_digest,
        }
    )
    validate_direction_program_binding(program, bound_direction)

    bound_seed: StoryEngineSeed | None = None
    semantic_digest: str | None = None
    if bound_direction.semantic_route is not None:
        semantic_digest = semantic_causal_route_digest(bound_direction.semantic_route)
        assert seed_payload is not None
        bound_seed = StoryEngineSeed.model_validate(
            {
                **seed_payload,
                "semantic_route_digest": semantic_digest,
            }
        )

    verifier_digest = script_boundary_verifier_input_digest(
        bound_direction,
        locked_story=locked_story,
        script_text=script_text,
    )
    boundary_receipt = {
        "supported": True,
        "unsupported_spans": [],
        "reason_codes": [],
        "semantic_route_supported": True,
        "semantic_route_digest": semantic_digest,
        "verifier_input_sha256": verifier_digest,
    }
    production_notes = {
        **translation_value,
        "boundary_verifier_version": SCRIPT_BOUNDARY_VERIFIER_VERSION,
        "boundary_receipt": boundary_receipt,
        "boundary_receipt_sha256": _sha256_json(boundary_receipt),
        "editorial_program_sha256": program_digest,
        "direction_decision_sha256": direction_decision_digest(bound_direction),
    }
    if locked_story is not None:
        production_notes["source_story_sha256"] = hashlib.sha256(locked_story.encode("utf-8")).hexdigest()
    if semantic_digest is not None:
        production_notes["semantic_route_sha256"] = semantic_digest

    live_claims = list(bound_direction.claim_basis)
    if bound_direction.truth_mode == "fictional":
        live_claims = [claim for claim in live_claims if claim.usage == "excluded"]
    creative_elements: list[dict[str, Any]] = []
    if locked_story is not None:
        creative_elements.append(
            {
                "element": locked_story,
                "kind": "fictional",
                "disclosure": "人物、事件与因果链为创作，不登记为 Owner 或来源事实",
            }
        )
    direction_id = f"direction-{scenario_id}-v1"
    script = ScriptDraft.model_validate(
        {
            "title": work_title,
            "story_mode": bound_direction.truth_mode,
            "script_text": script_text,
            "claim_basis": [claim.model_dump(mode="json") for claim in live_claims],
            "creative_elements": creative_elements,
            "story_engine_seed": (bound_seed.model_dump(mode="json") if bound_seed is not None else None),
            "locked_story": locked_story,
            "production_notes": production_notes,
            "direction_version_id": direction_id,
        }
    )
    validate_script_direction_binding(bound_direction, script)

    program_id = f"program-{scenario_id}"
    program_version_id = f"program-version-{scenario_id}-v1"
    work_id = f"work-{scenario_id}"
    script_id = f"script-{scenario_id}-v1"
    run_id = f"run-{scenario_id}"
    thread_id = f"thread-{scenario_id}"
    tool_call_id = f"tool-{scenario_id}"

    lineage = {
        "content_work": {
            "id": work_id,
            "owner_user_id": "owner-acceptance",
            "subject_id": None,
            "title": work_title,
            "entry_route": "zero_start",
            "objective_id": f"objective-{scenario_id}",
            "objective": copy.deepcopy(objective_value),
            "editorial_program_version_id": program_version_id,
            "status": "active",
            "operation_key": f"{run_id}:{tool_call_id}",
            "created_by_run_id": run_id,
            "thread_id": thread_id,
        },
        "editorial_program_version": {
            "id": program_version_id,
            "program_id": program_id,
            "subject_id": None,
            "version_number": 1,
            "parent_program_version_id": None,
            "title": program.title,
            "decision": editorial_program_decision_payload(program),
        },
        "breakdown_versions": [],
        "direction_versions": [
            {
                "id": direction_id,
                "owner_user_id": "owner-acceptance",
                "content_work_id": work_id,
                "version_number": 1,
                "parent_direction_version_id": None,
                "breakdown_version_ids": [],
                "objective_snapshot": copy.deepcopy(objective_value),
                "direction": bound_direction.model_dump(mode="json"),
                "created_by_run_id": run_id,
            }
        ],
        "script_versions": [
            {
                "id": script_id,
                "owner_user_id": "owner-acceptance",
                "content_work_id": work_id,
                "direction_version_id": direction_id,
                "version_number": 1,
                "parent_script_version_id": None,
                "title": script.title,
                "story_mode": script.story_mode,
                "script_text": script.script_text,
                "claim_basis": [claim.model_dump(mode="json") for claim in script.claim_basis],
                "creative_elements": [element.model_dump(mode="json") for element in script.creative_elements],
                "story_engine_seed": (script.story_engine_seed.model_dump(mode="json") if script.story_engine_seed is not None else None),
                "locked_story": script.locked_story,
                "locked_story_digest": (hashlib.sha256(locked_story.encode("utf-8")).hexdigest() if locked_story is not None else None),
                "production_notes": script.production_notes,
                "created_by_run_id": run_id,
            }
        ],
    }

    caller_direction = bound_direction.model_dump(mode="json")
    caller_direction["editorial_program_digest"] = None
    caller_seed = copy.deepcopy(seed_payload)
    request = WriterBrainRequest.model_validate(
        {
            "work_title": work_title,
            "entry_route": "zero_start",
            "objective": objective_value,
            "editorial_program": program.model_dump(mode="json"),
            "direction": caller_direction,
            "story_engine_seed": caller_seed,
            "production_translation": translation_value,
        }
    )
    raw_model_request = request.model_dump(mode="json")
    raw_model_request["direction"].pop("contract_version")
    raw_model_request["direction"].pop("editorial_program_digest")
    if raw_model_request["story_engine_seed"] is not None:
        raw_model_request["story_engine_seed"].pop("semantic_route_digest")
    tool_result = {
        "operation_status": "ok",
        "schema_version": "personal-ip-writer-brain-v2",
        "content_work_id": work_id,
        "breakdown_version_id": None,
        "editorial_program_version_id": program_version_id,
        "editorial_program_version_number": 1,
        "direction_version_id": direction_id,
        "direction_version_number": 1,
        "script_version_id": script_id,
        "script_version_number": 1,
        "story_mode": script.story_mode,
        "locked_story": script.locked_story,
        "locked_story_sha256": lineage["script_versions"][0]["locked_story_digest"],
        "script_text": script.script_text,
        "replayed": False,
    }
    tool_trace = [
        {
            "call_id": tool_call_id,
            "name": "ip_content_write",
            "status": "ok",
            "owner_user_id": "owner-acceptance",
            "run_id": run_id,
            "thread_id": thread_id,
            "arguments": {"request": raw_model_request},
            "result": tool_result,
        }
    ]
    final_text = f"已保存为第1版正式脚本。\n\n{script.script_text}"
    assert prompt.strip()
    return lineage, tool_trace, final_text


URGENT_PROMPT = "我是果农，800斤桃已进入7天采摘窗口，过期会软烂；5斤装49元，可以展示成熟度、分拣、称重和当天发货。当前第一目标是在7天内卖出去，不做长期人物IP。请直接策划并保存第一条完整直售脚本，不要反问。"


def _urgent_program(*, misclassified: bool = False) -> dict[str, Any]:
    return {
        "title": "七天采摘窗口" if not misclassified else "果农人物故事",
        "mission": {
            "goal_priority": (["recognition", "trust"] if misclassified else ["conversion", "trust"]),
            "time_horizon": "long_term" if misclassified else "urgent",
            "deadline_or_window": "未来一年" if misclassified else "未来七天",
            "desired_action": "持续关注果农" if misclassified else "当天下单",
            "success_signal": ("观众记住果农的人生故事" if misclassified else "出现可核对订单或采购询盘"),
            "cost_of_delay": "" if misclassified else "桃过期会软烂",
            "non_goals": ["不强行做长期人物故事"],
            "rationale": ("把果农身份包装成长期故事。" if misclassified else "不可逆的成熟窗口优先于长期认知。"),
        },
        "audience": {
            "situation": "需要当季水果且关心成熟度和履约的买家",
            "state": "hypothesized",
            "uncertainties": ["零售与团购占比尚未核对"],
        },
        "attribution": {
            "primary_carrier": {
                "kind": "person" if misclassified else "product",
                "identity": "果农本人" if misclassified else "七天采摘窗口的桃",
            },
            "supporting_carriers": ([] if misclassified else [{"kind": "person", "identity": "实际履约的果农"}]),
            "desired_association": ("有人生故事的果农" if misclassified else "成熟度和发货过程透明"),
            "attribution_guard": "不把急售效果偷换为长期个人 IP 已建成",
            "rationale": "当前任务先对产品成交负责。",
        },
        "differentiation": _difference(
            statement="用当天成熟度、分拣、称重和发货证据代替鲜甜口号",
            contrast="只说鲜甜却不给履约信息",
            basis=["用户能展示当天成熟度、分拣、称重和发货"],
            reason_to_choose="直接回答下单前的顾虑",
            reason_to_believe="所有信息可现场核对",
            sacrifice="本轮不以长期人物叙事为优先",
            test_signal="买家围绕下单和履约询问",
        ),
        "editorial_spine": None,
    }


def _urgent_direction() -> dict[str, Any]:
    return {
        "contract_version": "personal-ip-direction-v2",
        "premise": "用当天现场证据和明确价格降低下单顾虑",
        "audience_situation": "买家担心成熟度、价格和发货时间",
        "core_tension": "七天销售窗口与购买顾虑",
        "content_promise": "给出可核对的产品、价格和履约信息",
        "creative_route": "现场演示后给出明确报价与截止时间",
        "rationale": "直接服务当下成交，不强行故事化。",
        "truth_mode": "factual",
        "business_relevance": "在七天窗口内尽快出货",
        "route_kind": "offer",
        "semantic_route": None,
        "claim_basis": [
            _claim("800斤桃已进入7天采摘窗口"),
            _claim("过期会软烂"),
            _claim("5斤装49元"),
            _claim("可以展示成熟度、分拣、称重和当天发货"),
        ],
    }


LONG_TERM_PROMPT = "水果目前不急卖，未来一年希望观众记住果农本人。第一条不要卖货，要做一条明确标注虚构的短剧情，围绕“看不到回报时还守不守承诺”；水果、果园和节气只是语义入口，不能把剧情冒充我的真实经历。请直接保存完整脚本。"


def _long_term_program(*, misclassified: bool = False) -> dict[str, Any]:
    return {
        "title": "果农与节气的长期人物主线",
        "mission": {
            "goal_priority": ["recognition", "trust"],
            "time_horizon": "long_term",
            "deadline_or_window": "未来一年",
            "desired_action": "持续记住并关注这个人",
            "success_signal": "观众能复述人物与承诺的核心议题",
            "cost_of_delay": "",
            "non_goals": ["不把每条都做成急售广告"],
            "rationale": "用户此时选择积累长期人物认知。",
        },
        "audience": {
            "situation": "对长期坚持已感到疲惫的人",
            "state": "hypothesized",
            "uncertainties": ["实际受众尚未用发布反馈校验"],
        },
        "attribution": {
            "primary_carrier": {
                "kind": "product" if misclassified else "person",
                "identity": "当季水果" if misclassified else "果农本人",
            },
            "supporting_carriers": ([{"kind": "person", "identity": "果农本人"}] if misclassified else [{"kind": "product", "identity": "当季水果"}]),
            "desired_association": ("值得购买的当季水果" if misclassified else "看不到回报仍认真守承诺的人"),
            "attribution_guard": "水果是行动证据，虚构事件不冒充果农真实经历",
            "rationale": "长期认知应稳定落在人身上。",
        },
        "differentiation": _difference(
            statement="从节气劳动中持续追问承诺与回报的两难",
            contrast="只展示水果和丰收的流水账",
            basis=["用户明确选择一年人物认知目标与承诺议题"],
            reason_to_choose="主题能跨作品持续变化",
            reason_to_believe="主题只作为待验证的创作假设",
            sacrifice="不把短期销量写成人物价值证明",
            test_signal="观众能复述人物所面对的承诺问题",
        ),
        "editorial_spine": {
            "source_concepts": ["水果", "果园", "节气"],
            "human_theme": "人与承诺",
            "recurring_question": "看不到回报时还要不要守住承诺",
            "boundary": "不把销量写成人物道德价值的证明",
        },
    }


LONG_TERM_CAUSAL_PATTERN = "为了即时回报放弃一次承诺，关系便失去信任"


def _long_term_direction() -> dict[str, Any]:
    return {
        "contract_version": "personal-ip-direction-v2",
        "premise": "在一次看不到回报的守候中做选择",
        "audience_situation": "对长期坚持已感到疲惫的人",
        "core_tension": "即时回报与长期承诺",
        "content_promise": "看见一次真正有代价的选择",
        "creative_route": "从节气逐层联想到人与承诺，再用行业隔离的虚构人物展开",
        "rationale": "为持续人物认知服务，不冒充 Owner 真实经历。",
        "truth_mode": "fictional",
        "business_relevance": "让长期认知落在果农本人的判断上",
        "route_kind": "semantic_story",
        "semantic_route": {
            "association_path": ["节气", "反复守候", "人与承诺"],
            "human_theme": "人与承诺",
            "causal_pattern": LONG_TERM_CAUSAL_PATTERN,
            "episode_tension": "眼前结果与长期信任不能兼得",
            "mission_bridge": "让观众记住人物所持续面对的承诺议题",
            "attribution_guard": "虚构事件不冒充果农真实经历",
        },
        "claim_basis": [],
    }


def _long_term_seed() -> dict[str, Any]:
    return {
        "recurring_conflict": "一个人反复在眼前回报与旧日约定之间摇摆",
        "desire_a": "马上得到回报",
        "desire_b": "守住对另一个人的承诺",
        "relationship_at_stake": "两人之间的信任",
        "causal_pattern": LONG_TERM_CAUSAL_PATTERN,
        "tone": "克制",
    }


MCN_PROMPT = (
    "我经营 Northstar Creators，要做 TikTok MCN 官方账号。未来一年优先级明确为："
    "机构品牌认知第一、合格创作者申请第二、信任作为支撑；不是老板个人IP。"
    "我们真实实行分成、结算和退出规则透明，创作者保留内容决定权，也不承诺爆款或收入。"
    "第一条请解释“加入后第一周实际会发生什么”，直接保存完整脚本。"
)


def _mcn_program(*, misclassified: bool = False) -> dict[str, Any]:
    return {
        "title": "Northstar 官方品牌与创作者招募主线",
        "mission": {
            "goal_priority": ["recognition", "conversion", "trust"],
            "time_horizon": "long_term",
            "deadline_or_window": "未来一年",
            "desired_action": "先形成清晰品牌认知，匹配的创作者再提交申请",
            "success_signal": "目标创作者能复述机构边界并产生合格申请",
            "cost_of_delay": "",
            "non_goals": ["不做老板个人 IP", "不用收入保证吸引申请"],
            "rationale": "品牌认知是第一优先级，创作者申请是第二优先级。",
        },
        "audience": {
            "situation": "正在判断机构是否透明、是否尊重创作自主权的 TikTok 创作者",
            "state": "hypothesized",
            "uncertainties": ["创作者所处阶段与主要品类尚待验证"],
        },
        "attribution": {
            "primary_carrier": {
                "kind": "person" if misclassified else "brand",
                "identity": "MCN 老板本人" if misclassified else "Northstar Creators",
            },
            "supporting_carriers": ([{"kind": "brand", "identity": "Northstar Creators"}] if misclassified else [{"kind": "organization", "identity": "Northstar MCN 机构"}]),
            "desired_association": ("懂流量的 MCN 老板" if misclassified else "把合作边界和创作者自主权讲清楚的机构品牌"),
            "attribution_guard": "出镜人只是机构规则的解释者，不把价值偷换给老板个人",
            "rationale": "官方账号要让机构品牌累积认知和信任。",
        },
        "differentiation": _difference(
            statement="用透明的分成、结算、退出和创作决定权规则代替赋能口号",
            contrast="只说专业、资源多和赋能",
            basis=[
                "用户明确表示分成、结算和退出规则透明",
                "用户明确表示创作者保留内容决定权",
            ],
            reason_to_choose="让创作者能在申请前判断是否适配",
            reason_to_believe="规则由用户明确提供且可持续公开",
            sacrifice="不承诺爆款或收入",
            test_signal="创作者能复述合作边界并提交合格申请",
        ),
        "editorial_spine": None,
    }


def _mcn_direction() -> dict[str, Any]:
    return {
        "contract_version": "personal-ip-direction-v2",
        "premise": "把加入机构后第一周的步骤和权利边界讲清楚",
        "audience_situation": "创作者担心签约后失去内容决定权或遇到不透明规则",
        "core_tension": "借助组织力量与保留创作自主权",
        "content_promise": "说清第一周会发生什么以及机构不会承诺什么",
        "creative_route": "按时间顺序解释第一周流程、规则和申请条件",
        "rationale": "用真实规则降低决策不确定性，不需要虚构故事。",
        "truth_mode": "factual",
        "business_relevance": "同时服务品牌认知和合格创作者申请",
        "route_kind": "explanation",
        "semantic_route": None,
        "claim_basis": [
            _claim("分成、结算和退出规则透明"),
            _claim("创作者保留内容决定权"),
            _claim("机构不承诺爆款或收入"),
        ],
    }


MOM_PROMPT = "我曾是地下乐队鼓手，停了5年，现在也是孩子的母亲，准备通过一年真实训练重返舞台。我做的是个人IP，孩子不出镜，也不做育儿内容。第一条记录训练第一天，请直接保存完整脚本。"


def _mom_program(*, misclassified: bool = False) -> dict[str, Any]:
    return {
        "title": "一年真实训练重返舞台",
        "mission": {
            "goal_priority": ["recognition", "trust"],
            "time_horizon": "long_term",
            "deadline_or_window": "未来一年",
            "desired_action": "记住并持续关注本人的训练与回归",
            "success_signal": "观众能复述前地下乐队鼓手用一年重返舞台的目标",
            "cost_of_delay": "",
            "non_goals": ["不做育儿内容", "孩子不出镜"],
            "rationale": "用户要积累本人重新开始的长期认知。",
        },
        "audience": {
            "situation": ("想看宝妈育儿经验的母婴人群" if misclassified else "在长时间中断后想重新开始的人"),
            "state": "hypothesized",
            "uncertainties": ["实际受众尚未用发布反馈校验"],
        },
        "attribution": {
            "primary_carrier": {
                "kind": "person",
                "identity": "宝妈鼓手" if misclassified else "前地下乐队鼓手本人",
            },
            "supporting_carriers": [],
            "desired_association": ("会打鼓的宝妈" if misclassified else "中断五年后仍在认真训练重返舞台的人"),
            "attribution_guard": ("孩子是母婴内容的主角" if misclassified else "孩子只构成时间和隐私边界，不出镜也不作为内容主角"),
            "rationale": "归因应落在本人的真实经历和一年训练目标。",
        },
        "differentiation": _difference(
            statement=("宝妈如何兼顾带娃与爱好" if misclassified else "前地下乐队鼓手用一年真实训练重返舞台"),
            contrast="只用生活阶段标签替代本人真实目标",
            basis=["用户表示曾是地下乐队鼓手、停顿五年并计划用一年重返舞台"],
            reason_to_choose="目标具体、有时间窗且可持续记录",
            reason_to_believe="依据用户明确提供的经历与目标",
            sacrifice="不把宝妈标签自动扩展为母婴定位",
            test_signal="观众能复述鼓手重返舞台的一年目标",
        ),
        "editorial_spine": None,
    }


def _mom_direction() -> dict[str, Any]:
    return {
        "contract_version": "personal-ip-direction-v2",
        "premise": "五年没有系统训练后完成重返舞台计划的第一天",
        "audience_situation": "在长时间中断后想重新开始的人",
        "core_tension": "过去的鼓手身份与当下真实基础之间的落差",
        "content_promise": "只记录第一天真实训练的起点，不预告成功结果",
        "creative_route": "展示第一天训练的开始、卡顿和下一步",
        "rationale": "用真实行动建立人物认知，不用家庭标签代替本人目标。",
        "truth_mode": "factual",
        "business_relevance": "建立前地下乐队鼓手重新开始的个人认知",
        "route_kind": "demonstration",
        "semantic_route": None,
        "claim_basis": [
            _claim("用户曾是地下乐队鼓手"),
            _claim("用户停了五年"),
            _claim("用户准备通过一年真实训练重返舞台"),
            _claim("孩子不出镜，不做育儿内容", usage="excluded"),
        ],
    }


def _case(
    *,
    scenario_id: str,
    prompt: str,
    work_title: str,
    objective: dict[str, Any],
    program_factory: Callable[..., dict[str, Any]],
    direction_payload: dict[str, Any],
    script_text: str,
    expected_route: str,
    expected_story_mode: str,
    expected_writer_model_calls: tuple[str, ...],
    negative_failure_code: str,
    seed_payload: dict[str, Any] | None = None,
    locked_story: str | None = None,
    production_translation: dict[str, Any] | None = None,
) -> BehaviorCase:
    lineage, tool_trace, final_text = _build_lineage(
        scenario_id=scenario_id,
        prompt=prompt,
        work_title=work_title,
        objective=objective,
        program_payload=program_factory(misclassified=False),
        direction_payload=direction_payload,
        script_text=script_text,
        seed_payload=seed_payload,
        locked_story=locked_story,
        production_translation=production_translation,
    )
    negative_lineage, negative_tool_trace, negative_final_text = _build_lineage(
        scenario_id=scenario_id,
        prompt=prompt,
        work_title=work_title,
        objective=objective,
        program_payload=program_factory(misclassified=True),
        direction_payload=direction_payload,
        script_text=script_text,
        seed_payload=seed_payload,
        locked_story=locked_story,
        production_translation=production_translation,
    )
    writer_model_trace = [
        {
            "call_index": index,
            "run_name": run_name,
            "status": "success",
        }
        for index, run_name in enumerate(expected_writer_model_calls, start=1)
    ]
    return BehaviorCase(
        scenario_id=scenario_id,
        prompt=prompt,
        lineage=lineage,
        tool_trace=tool_trace,
        writer_model_trace=writer_model_trace,
        final_text=final_text,
        expected_route=expected_route,
        expected_story_mode=expected_story_mode,
        expected_writer_model_calls=expected_writer_model_calls,
        negative_lineage=negative_lineage,
        negative_tool_trace=negative_tool_trace,
        negative_final_text=negative_final_text,
        negative_failure_code=negative_failure_code,
    )


CASES = (
    _case(
        scenario_id="urgent_fruit_offer",
        prompt=URGENT_PROMPT,
        work_title="七天采摘窗口直售",
        objective={
            "desired_change": "让需要当季桃的买家在七天内下单",
            "audience_situation": "担心成熟度、价格和发货的买家",
            "business_context": "800斤桃已进入七天采摘窗口",
        },
        program_factory=_urgent_program,
        direction_payload=_urgent_direction(),
        script_text=("这800斤桃已进入7天采摘窗口，过期会软烂。今天直接展示成熟度、分拣和称重：5斤装49元，当天发货。需要的请在采摘窗口内下单。"),
        expected_route="offer",
        expected_story_mode="factual",
        expected_writer_model_calls=(
            "ip-agent-script-writer-v2",
            "ip-agent-script-boundary-verifier-v2",
        ),
        negative_failure_code="URGENT_FRUIT_NOT_CONVERSION_PRODUCT",
        production_translation={"form": "spoken", "setting": "桃园分拣台"},
    ),
    _case(
        scenario_id="long_term_person_semantic_story",
        prompt=LONG_TERM_PROMPT,
        work_title="看不到回报的约定",
        objective={
            "desired_change": "让观众记住一个关于承诺的长期人物议题",
            "audience_situation": "对长期坚持已感到疲惫的人",
            "business_context": "本轮不以销售为优先",
        },
        program_factory=_long_term_program,
        direction_payload=_long_term_direction(),
        seed_payload=_long_term_seed(),
        locked_story=("他想立即换取一次回报，但旧办法让他爽约；于是转而坦白自己的动摇；他只能在眼前收获与守住约定之间选择后者；代价是失去这次机会；最终对方愿意再信任他一次。"),
        script_text=("【虚构剧情】他本可立即换取一次回报，却发现这意味着再次爽约。他放下辩解，承认自己动摇过，最后选择守住约定，失去了眼前机会。对方没有立刻原谅，只是愿意再信他一次。人物与事件均为虚构。"),
        expected_route="semantic_story",
        expected_story_mode="fictional",
        expected_writer_model_calls=(
            "ip-agent-story-engine-v2",
            "ip-agent-script-writer-v2",
            "ip-agent-script-boundary-verifier-v2",
        ),
        negative_failure_code="LONG_TERM_PERSON_ATTRIBUTION_LOST",
        production_translation={"form": "scene", "setting": "一张餐桌"},
    ),
    _case(
        scenario_id="mcn_brand_explanation",
        prompt=MCN_PROMPT,
        work_title="加入 Northstar 后的第一周",
        objective={
            "desired_change": "让目标创作者理解品牌边界并判断是否申请",
            "audience_situation": "正在选择 TikTok MCN 的创作者",
            "business_context": "品牌认知第一，合格申请第二",
        },
        program_factory=_mcn_program,
        direction_payload=_mcn_direction(),
        script_text=("加入 Northstar 后的第一周，我们先说清分成、结算和退出规则，再一起确认你想做的内容方向。内容决定权仍然属于创作者。我们不承诺爆款或收入；如果你认同这些合作边界，再提交申请。"),
        expected_route="explanation",
        expected_story_mode="factual",
        expected_writer_model_calls=(
            "ip-agent-script-writer-v2",
            "ip-agent-script-boundary-verifier-v2",
        ),
        negative_failure_code="MCN_BRAND_ATTRIBUTION_LOST",
        production_translation={"form": "spoken", "setting": "机构公开工作区"},
    ),
    _case(
        scenario_id="drummer_mom_demonstration",
        prompt=MOM_PROMPT,
        work_title="重返舞台训练第一天",
        objective={
            "desired_change": "让观众记住前地下乐队鼓手重新开始的一年目标",
            "audience_situation": "在长时间中断后想重新开始的人",
            "business_context": "孩子不出镜，不做育儿内容",
            "constraints": ["孩子不出镜", "不把家庭生活当作内容主角"],
        },
        program_factory=_mom_program,
        direction_payload=_mom_direction(),
        script_text=("我曾是地下乐队鼓手，停了五年。今天是用一年真实训练重返舞台的第一天。我只记录现在能打到哪里、哪里卡住，不预告一年后一定成功。今天的目标只有一个：完成第一次训练，明天继续。"),
        expected_route="demonstration",
        expected_story_mode="factual",
        expected_writer_model_calls=(
            "ip-agent-script-writer-v2",
            "ip-agent-script-boundary-verifier-v2",
        ),
        negative_failure_code="MOM_ROLE_BECAME_POSITIONING",
        production_translation={
            "form": "spoken",
            "setting": "练习室",
            "constraints": ["孩子不出镜"],
        },
    ),
)


def broken_lineage(case: BehaviorCase) -> dict[str, Any]:
    value = copy.deepcopy(case.lineage)
    value["content_work"]["editorial_program_version_id"] = "program-version-from-another-work"
    return value


def broken_boundary_receipt(case: BehaviorCase) -> dict[str, Any]:
    value = copy.deepcopy(case.lineage)
    value["script_versions"][0]["production_notes"]["direction_decision_sha256"] = "0" * 64
    return value


def forbidden_tool_trace(case: BehaviorCase) -> list[dict[str, Any]]:
    value = copy.deepcopy(case.tool_trace)
    value.insert(
        0,
        {
            "call_id": f"web-{case.scenario_id}",
            "name": "web_search",
            "status": "ok",
            "arguments": {"query": "不必要的外部搜索"},
            "result": {"results": []},
        },
    )
    return value


def invalid_writer_model_trace(
    case: BehaviorCase,
    mutation: str,
) -> list[dict[str, Any]]:
    value = copy.deepcopy(case.writer_model_trace)
    if mutation == "missing":
        value.pop()
    elif mutation == "extra":
        value.append(
            {
                "call_index": len(value) + 1,
                "run_name": "ip-agent-script-writer-v2",
                "status": "success",
            }
        )
    elif mutation == "wrong_name":
        value[0]["run_name"] = "ip-agent-unapproved-writer"
    else:  # pragma: no cover - fixture authoring guard
        raise ValueError(f"unknown writer trace mutation: {mutation}")
    return value


def invalid_final_text(case: BehaviorCase, mutation: str) -> str:
    if mutation == "missing_script":
        return "已保存为第1版正式脚本，这里只给一句摘要。"
    if mutation == "missing_version":
        return case.lineage["script_versions"][0]["script_text"]
    if mutation == "internal_leak":
        return f"{case.final_text}\nip_content_write={case.lineage['script_versions'][0]['id']} schema=personal-ip-writer-brain-v2 digest=sha256"
    raise ValueError(f"unknown final text mutation: {mutation}")


def mismatched_tool_result_version(
    case: BehaviorCase,
    field: str,
) -> list[dict[str, Any]]:
    value = copy.deepcopy(case.tool_trace)
    key = {
        "program": "editorial_program_version_number",
        "direction": "direction_version_number",
        "script": "script_version_number",
    }[field]
    value[0]["result"][key] = 2
    return value


__all__ = [
    "BehaviorCase",
    "CASES",
    "broken_boundary_receipt",
    "broken_lineage",
    "forbidden_tool_trace",
    "invalid_final_text",
    "invalid_writer_model_trace",
    "mismatched_tool_result_version",
]
