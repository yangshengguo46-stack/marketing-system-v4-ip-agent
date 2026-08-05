from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.personal_ip.content_contracts import (
    DirectionDraft,
    EditorialProgramDraft,
    MissionDecision,
    StoryEngineSeed,
    WriterBrainRequest,
)


def _difference(*, statement: str, basis: str) -> dict:
    return {
        "state": "hypothesized",
        "statement": statement,
        "contrast": "泛化口号",
        "basis": [{"claim": basis, "state": "user_asserted"}],
        "reason_to_choose": "有明确的现实依据",
        "reason_to_believe": "可以在后续内容中继续核对",
        "sacrifice": "不用一个标签包办全部定位",
        "test_signal": "观众能复述这一具体区别",
        "uncertainties": [],
    }


def _urgent_fruit_program() -> EditorialProgramDraft:
    return EditorialProgramDraft.model_validate(
        {
            "title": "成熟期水果急售",
            "mission": {
                "goal_priority": ["conversion", "trust"],
                "time_horizon": "urgent",
                "deadline_or_window": "未来七天成熟期",
                "desired_action": "当天下单或联系采购",
                "success_signal": "出现可核对订单或采购询盘",
                "cost_of_delay": "成熟水果会烂在地里",
                "non_goals": ["本轮不以长期个人故事为优先"],
                "rationale": "不可逆的成熟窗口优先于长期认知积累",
            },
            "audience": {
                "situation": "需要当季水果且关心鲜度和履约的买家",
                "state": "hypothesized",
                "uncertainties": ["零售和批量采购占比尚未核对"],
            },
            "attribution": {
                "primary_carrier": {"kind": "product", "identity": "当季水果"},
                "supporting_carriers": [{"kind": "person", "identity": "实际履约的果农"}],
                "desired_association": "成熟度透明且发货可核对",
                "attribution_guard": "不把急售效果偷换为长期个人 IP 已建成",
                "rationale": "当前行动先对产品成交负责",
            },
            "differentiation": _difference(
                statement="用当天成熟度、分拣和发货证据代替空泛鲜甜承诺",
                basis="用户能展示当天的果子和履约过程",
            ),
            "editorial_spine": None,
        }
    )


def test_urgent_fruit_sale_selects_product_attribution_and_direct_route() -> None:
    program = _urgent_fruit_program()
    direction = DirectionDraft.model_validate(
        {
            "contract_version": "personal-ip-direction-v2",
            "premise": "用当天现场证据回答买家下单前的关键问题",
            "audience_situation": "买家担心成熟度和发货时间",
            "core_tension": "七天销售窗口与购买顾虑",
            "content_promise": "给出可核对的产品和履约信息",
            "creative_route": "现场演示后给出明确报价与截止时间",
            "rationale": "直接降低当下成交阻力",
            "truth_mode": "factual",
            "business_relevance": "尽快出货",
            "route_kind": "offer",
            "claim_basis": [
                {
                    "claim": "用户表示未来七天是成熟期",
                    "state": "user_asserted",
                    "usage": "attributed_fact",
                }
            ],
        }
    )

    request = WriterBrainRequest.model_validate(
        {
            "work_title": "七天成熟窗口",
            "entry_route": "zero_start",
            "objective": {"desired_change": "让需要的买家当天下单"},
            "editorial_program": program.model_dump(mode="json"),
            "direction": direction.model_dump(mode="json"),
        }
    )

    assert request.editorial_program is not None
    assert request.editorial_program.mission.goal_priority[0] == "conversion"
    assert request.editorial_program.attribution.primary_carrier.kind == "product"
    assert request.direction.route_kind == "offer"
    assert request.direction.semantic_route is None
    assert request.story_engine_seed is None


@pytest.mark.parametrize(
    ("deadline", "cost"),
    [("未知", "水果可能损耗"), ("未来七天", "")],
)
def test_urgent_mission_fails_closed_without_window_and_delay_cost(
    deadline: str,
    cost: str,
) -> None:
    with pytest.raises(ValidationError):
        MissionDecision.model_validate(
            {
                "goal_priority": ["conversion"],
                "time_horizon": "urgent",
                "deadline_or_window": deadline,
                "desired_action": "下单",
                "success_signal": "可核对订单",
                "cost_of_delay": cost,
                "rationale": "有不可逆窗口",
            }
        )


def test_long_term_fruit_person_route_binds_semantic_theme_separately() -> None:
    urgent = _urgent_fruit_program()
    long_term = EditorialProgramDraft.model_validate(
        {
            **urgent.model_dump(mode="json"),
            "title": "果农与节气的长期人物主线",
            "mission": {
                "goal_priority": ["recognition", "trust"],
                "time_horizon": "long_term",
                "deadline_or_window": "未来一年",
                "desired_action": "持续记住并关注这个人",
                "success_signal": "观众能复述人物与土地的核心议题",
                "cost_of_delay": "",
                "non_goals": ["不把每条都做成急售广告"],
                "rationale": "用户此时选择积累长期人物认知",
            },
            "attribution": {
                "primary_carrier": {"kind": "person", "identity": "果农本人"},
                "supporting_carriers": [{"kind": "product", "identity": "当季水果"}],
                "desired_association": "守住节气与土地承诺的人",
                "attribution_guard": "水果是行动证据，不替代人物归因",
                "rationale": "长期认知需要稳定落在人身上",
            },
            "editorial_spine": {
                "source_concepts": ["水果", "果园", "节气"],
                "human_theme": "人与土地的承诺",
                "recurring_question": "看不到回报时还要不要守住承诺",
                "boundary": "不把销量写成人物道德价值的证明",
            },
        }
    )
    direction = DirectionDraft.model_validate(
        {
            "contract_version": "personal-ip-direction-v2",
            "premise": "在一次没有回报的守候中做选择",
            "audience_situation": "对长期坚持已感到疲惫的人",
            "core_tension": "即时回报与长期承诺",
            "content_promise": "看见一次真正有代价的选择",
            "creative_route": "用虚构人物展开一条与行业隔离的因果链",
            "rationale": "为持续人物认知服务",
            "truth_mode": "fictional",
            "route_kind": "semantic_story",
            "semantic_route": {
                "association_path": ["水果", "节气的劳动", "人与土地的承诺"],
                "human_theme": "人与土地的承诺",
                "causal_pattern": "为了即时回报放弃一次承诺，关系失去信任",
                "episode_tension": "眼前结果与长期信任不能兼得",
                "mission_bridge": "让观众记住主线议题",
                "attribution_guard": "虚构事件不冒充果农真实经历",
            },
        }
    )
    seed = StoryEngineSeed.model_validate(
        {
            "recurring_conflict": "一个人反复在眼前结果与旧日约定之间摇摆",
            "desire_a": "马上得到回报",
            "desire_b": "守住对另一个人的承诺",
            "relationship_at_stake": "两人之间的信任",
            "causal_pattern": "为了即时回报放弃一次承诺，关系失去信任",
        }
    )

    request = WriterBrainRequest.model_validate(
        {
            "work_title": "没有回报的约定",
            "entry_route": "zero_start",
            "objective": {"desired_change": "让观众记住一个长期人物议题"},
            "editorial_program": long_term.model_dump(mode="json"),
            "direction": direction.model_dump(mode="json"),
            "story_engine_seed": seed.model_dump(mode="json"),
        }
    )

    assert urgent.attribution.primary_carrier.kind == "product"
    assert request.editorial_program is not None
    assert request.editorial_program.attribution.primary_carrier.kind == "person"
    assert request.direction.route_kind == "semantic_story"
    assert request.direction.semantic_route is not None


def test_direct_routes_cannot_smuggle_in_a_semantic_story() -> None:
    with pytest.raises(ValidationError, match="must skip the semantic route"):
        DirectionDraft.model_validate(
            {
                "contract_version": "personal-ip-direction-v2",
                "premise": "直接报价",
                "audience_situation": "已经有购买需求",
                "core_tension": "下单前信息不足",
                "content_promise": "给出准确信息",
                "creative_route": "报价",
                "rationale": "服务当前成交",
                "truth_mode": "factual",
                "route_kind": "offer",
                "semantic_route": {
                    "association_path": ["水果", "人情"],
                    "human_theme": "人情",
                    "causal_pattern": "送错一份礼就失去信任",
                    "episode_tension": "送与不送",
                    "mission_bridge": "促成购买",
                    "attribution_guard": "不冒充真事",
                },
            }
        )


def test_semantic_story_cannot_claim_factual_mode_and_skip_its_seed() -> None:
    with pytest.raises(ValidationError, match="requires truth_mode 'fictional'"):
        DirectionDraft.model_validate(
            {
                "contract_version": "personal-ip-direction-v2",
                "premise": "从礼品联想到人情",
                "audience_situation": "不知道如何送礼的人",
                "core_tension": "贵重与分寸",
                "content_promise": "看见一次选择的代价",
                "creative_route": "虚构人情故事",
                "rationale": "用因果链展开人类冲突",
                "truth_mode": "factual",
                "route_kind": "semantic_story",
                "semantic_route": {
                    "association_path": ["黄金礼品", "送礼", "人情分寸"],
                    "human_theme": "人情分寸",
                    "causal_pattern": "越想证明重视越容易越界",
                    "episode_tension": "价值与边界",
                    "mission_bridge": "建立认知",
                    "attribution_guard": "不冒充真事",
                },
            }
        )


def test_semantic_association_path_must_end_at_the_human_theme() -> None:
    with pytest.raises(ValidationError, match="must end at human_theme"):
        DirectionDraft.model_validate(
            {
                "contract_version": "personal-ip-direction-v2",
                "premise": "从礼品联想到人情",
                "audience_situation": "不知道如何送礼的人",
                "core_tension": "贵重与分寸",
                "content_promise": "看见一次选择的代价",
                "creative_route": "虚构人情故事",
                "rationale": "用因果链展开人类冲突",
                "truth_mode": "fictional",
                "route_kind": "semantic_story",
                "semantic_route": {
                    "association_path": ["人情分寸", "送礼", "黄金礼品"],
                    "human_theme": "人情分寸",
                    "causal_pattern": "越想证明重视越容易越界",
                    "episode_tension": "价值与边界",
                    "mission_bridge": "建立认知",
                    "attribution_guard": "不冒充真事",
                },
            }
        )


def test_mom_label_does_not_replace_person_attribution_or_real_difference() -> None:
    program = EditorialProgramDraft.model_validate(
        {
            "title": "一年重返舞台",
            "mission": {
                "goal_priority": ["recognition", "trust"],
                "time_horizon": "long_term",
                "deadline_or_window": "未来一年",
                "desired_action": "记住并持续关注本人的回归",
                "success_signal": "观众能复述地下鼓手重返舞台的目标",
                "cost_of_delay": "",
                "rationale": "用户此时要积累个人认知",
            },
            "audience": {
                "situation": "对中断后重新开始有共鸣的人",
                "state": "hypothesized",
                "uncertainties": ["实际受众尚未用发布反馈校验"],
            },
            "attribution": {
                "primary_carrier": {"kind": "person", "identity": "前地下乐队鼓手本人"},
                "supporting_carriers": [],
                "desired_association": "中断后仍在认真重返舞台的人",
                "attribution_guard": "孩子只构成时间和隐私边界，不作为内容主角",
                "rationale": "归因应落在本人的真实经历和目标",
            },
            "differentiation": _difference(
                statement="前地下鼓手用一年真实训练重返舞台",
                basis="用户表示自己曾是地下乐队鼓手并计划一年回归",
            ),
            "editorial_spine": None,
        }
    )

    assert program.attribution.primary_carrier.kind == "person"
    assert "宝妈" not in program.attribution.desired_association
    assert "鼓手" in program.differentiation.statement
    assert "孩子只构成时间和隐私边界" in program.attribution.attribution_guard
