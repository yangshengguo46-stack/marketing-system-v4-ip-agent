# 编导路线阶段统一输出合同 v1

这是隔离研究合同。本阶段只完成语义内核与近、中、远三路发散，不写故事、脚本、分镜、发布
或复盘，不得把结果描述为已验证定位或爆款结论。

只使用输入 `facts` 中明确给出的事实。未提供的人生、能力、受众反应和经营结果只能写入
`creative_assumptions`。输出必须是合法 JSON，不要 Markdown，不要增加字段：

```json
{
  "schema_version": "ip-director-route-result-v1",
  "epistemic_state": "creative",
  "facts_used": ["输入事实ID"],
  "creative_assumptions": ["明确的待验证假设"],
  "semantic_kernel": {
    "surface_terms": ["输入中的表面词"],
    "head_concept": "中心概念",
    "modifiers": ["没有丢失的修饰信息"],
    "literal_action": "表面业务世界中的实际动作",
    "human_action": "该动作在人类世界中的抽象动作",
    "relationship_at_stake": "该动作会改变的关系状态",
    "social_rule": "约束这段关系的社会规则",
    "desire_conflict": "两个不能轻易兼得的合理欲望"
  },
  "directions": [
    {
      "id": "稳定且唯一的候选ID",
      "semantic_distance": "near | mid | far",
      "industry_role": "subject | metaphor | stage | absent",
      "content_subject": "内容真正持续讲什么",
      "association_path": ["逐步可解释的语义路径"],
      "structure_mapping": [
        {"source_edge": "联想来源中的关系或因果边", "target_edge": "当前主体世界中的对应边"}
      ],
      "audience_tension": "观众正在面对的具体矛盾",
      "expression_mode": "适合该方向的内容表现",
      "subject_ownership": "为什么属于当前主体而不是任意同行",
      "business_attribution": "内容之外如何归因给主体和目标",
      "evidence_refs": ["输入事实ID"],
      "creative_assumptions": ["本候选依赖的待验证假设"]
    }
  ],
  "recommendation": {
    "selected_direction_ref": "被选候选ID",
    "reason": "为什么本轮选择它",
    "tradeoff": "主动放弃什么",
    "why_not_near": "为什么没有停在最安全的行业近邻"
  }
}
```

`directions` 必须恰好三项且各有一项 `near`、`mid`、`far`：

- `near` 的 `industry_role` 只能是 `subject`；
- `mid` 的 `industry_role` 只能是 `metaphor`；
- `far` 的 `industry_role` 只能是 `stage` 或 `absent`。

近、中、远是平行选择，不是质量等级。只能选择输入 `selection_policy.allowed_distances` 允许的
距离。中、远路线的 `structure_mapping` 至少给出两条不同的对应边。

