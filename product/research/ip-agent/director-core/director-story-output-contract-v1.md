# 编导故事阶段统一输出合同 v1

这是隔离研究合同。本阶段接收已经机械验收并冻结的路线结果，只把被选路线编译成一句话故事。
不得重新解释中心概念、生成新方向、切换语义距离或扩展到脚本、分镜、发布和复盘。

只使用原始 `facts` 和冻结路线。没有发生过的人物、事件与结果允许虚构，但必须写入
`creative_assumptions`，不得冒充本人经历、客户案例或经营事实。

输出必须是合法 JSON，不要 Markdown，不要增加字段：

```json
{
  "schema_version": "ip-director-story-result-v1",
  "epistemic_state": "creative",
  "source_route_sha256": "输入提供的冻结路线SHA-256",
  "selected_direction_ref": "冻结路线中被选候选ID",
  "facts_used": ["输入事实ID"],
  "creative_assumptions": ["虚构人物、事件或待验证假设"],
  "commercial_object_mode": "absent | causal",
  "substitution_test": "移除或替换商业对象后哪条具体因果边改变；不改变则必须 absent",
  "story_world": {
    "actors": ["故事行动者"],
    "trigger": "触发事件",
    "want": "人物想要的关系或状态",
    "goal": "可判断成败的当集目标",
    "initial_tactic": "最初行动策略",
    "counterforce": "现实反作用",
    "feedback": "行动收到的具体反馈",
    "strategy_change": "收到反馈后的换招",
    "costly_choice": "两样不能兼得的选择",
    "cost": "选择实际付出的代价",
    "relationship_before": "事件前的关系状态",
    "relationship_after": "事件后的关系状态",
    "state_change": "结尾可见改变的关系、身份、信息、能力、资源或规则",
    "viewer_question": "观众为了确认什么而继续看",
    "causal_edges": [
      {"from": "trigger", "to": "initial_tactic", "because": "具体因果"},
      {"from": "initial_tactic", "to": "feedback", "because": "具体因果"},
      {"from": "feedback", "to": "strategy_change", "because": "具体因果"},
      {"from": "strategy_change", "to": "costly_choice", "because": "具体因果"},
      {"from": "costly_choice", "to": "state_change", "because": "具体因果"}
    ]
  },
  "business_bridge": {
    "meaning_attributed_to_subject": "观众可能把什么意义归因给主体",
    "connection_to_objective": "故事之外如何连接用户目标"
  },
  "logline": "一行一句话故事"
}
```

故事世界和商业世界必须分开。账号、平台、流量、粉丝、咨询、订单和成交不得成为故事人物的
欲望、反作用、代价或结局。商业对象只有两种状态：

- `absent`：完成语义任务后从故事和一句话彻底退出；
- `causal`：其独特用途、规则或后果改变具体因果，普通替代物无法维持同一故事。

不存在“顺手露出”的第三种模式。

