# 编导故事阶段统一输出合同 v2

这是隔离研究合同。本阶段只把已冻结路线编译成一句话故事，不重新解释中心概念、生成新方向、
切换语义距离或扩展到脚本、分镜和运营。

`facts_used` 必须逐字复制输入事实。新人物、事件、对白和结果都是创作假设。内部结构要明确：
谁是主人公、当集目标结果、两个选择为何互斥、代价由谁承担，以及如何在输入条件下拍出来。

输出必须是合法 JSON，不要 Markdown，不要增加字段：

```json
{
  "schema_version": "ip-director-story-result-v2",
  "epistemic_state": "creative_hypothesis",
  "source_route_sha256": "输入提供的冻结路线SHA-256",
  "selected_direction_ref": "冻结路线中被选候选ID",
  "facts_used": [
    {"id": "输入事实ID", "statement": "逐字复制该事实"}
  ],
  "creative_assumptions": ["虚构人物、事件或待验证假设"],
  "commercial_object_mode": "absent | causal",
  "substitution_test_hypothesis": "移除或替换商业对象后哪条因果边改变；不改变则必须 absent",
  "story_world": {
    "actors": [
      {
        "id": "唯一人物ID",
        "role": "subject_self | fictional_character",
        "camera_presence": "on_camera | off_camera | voice_only",
        "description": "人物在本故事中的身份"
      }
    ],
    "protagonist_ref": "人物ID",
    "trigger": "触发事件",
    "want": "人物想要的关系或状态",
    "goal": "可判断成败的当集目标",
    "initial_tactic": "最初行动策略",
    "counterforce": "现实反作用",
    "feedback": "行动收到的具体反馈",
    "strategy_change": "收到反馈后的换招",
    "costly_choice": {
      "option_a": "只能选择的第一条路径",
      "option_b": "只能选择的第二条路径",
      "chosen": "实际选择",
      "why_incompatible_now": "为什么当下不能同时拥有"
    },
    "cost": {
      "bearer_ref": "必须等于 protagonist_ref",
      "paid": "主人公实际付出的代价",
      "persists_after_scene": "场景结束后仍存在的后果"
    },
    "goal_outcome": {
      "status": "achieved | failed | transformed",
      "result": "目标如何被明确兑现、失败或改写"
    },
    "relationship_before": "事件前的关系状态",
    "relationship_after": "事件后的关系状态",
    "state_change": "人物世界中可见且包含目标结果的改变",
    "viewer_question": "观众为了确认什么而继续看",
    "causal_edges": [
      {"from": "trigger", "to": "initial_tactic", "because": "具体因果"},
      {"from": "initial_tactic", "to": "feedback", "because": "具体因果"},
      {"from": "feedback", "to": "strategy_change", "because": "具体因果"},
      {"from": "strategy_change", "to": "costly_choice", "because": "具体因果"},
      {"from": "costly_choice", "to": "cost", "because": "具体因果"},
      {"from": "cost", "to": "goal_outcome", "because": "具体因果"},
      {"from": "goal_outcome", "to": "state_change", "because": "具体因果"}
    ]
  },
  "production_translation": {
    "telling_mode": "真实采用的表演或讲述方式",
    "on_camera_actor_refs": ["实际需要出镜的人物ID"],
    "off_camera_actor_refs": ["只存在于口述、声音或画外的人物ID"],
    "required_visible_actions": ["镜头内必须实际完成的动作"],
    "constraint_fit_hypothesis": "为什么符合输入中的拍摄条件"
  },
  "business_bridge": {
    "meaning_attributed_to_subject_hypothesis": "观众可能把什么意义归因给主体",
    "connection_to_objective_hypothesis": "故事之外可能如何连接用户目标"
  },
  "logline": "一行一句话故事"
}
```

故事世界和商业世界必须分开。账号、平台、流量、粉丝、咨询、订单和成交不得成为故事人物的
欲望、反作用、代价或结局。商业对象只有 `absent` 或 `causal`；不存在顺手露出的第三种模式。

