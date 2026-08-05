# 编导路线阶段统一输出合同 v2

这是隔离研究合同。内部结构必须把用户原话与创作假设分开；它不是给用户展示的表单。
本阶段只完成语义内核与近、中、远三路发散，不写故事、脚本、分镜、发布或复盘。

`facts_used` 必须逐字复制输入事实，不得改写或增强。除这些逐字事实外，语义、受众、关系、
表达和商业归因全部是待验证假设，因此字段名明确带 `_hypothesis`。

输出必须是合法 JSON，不要 Markdown，不要增加字段：

```json
{
  "schema_version": "ip-director-route-result-v2",
  "epistemic_state": "creative_hypothesis",
  "facts_used": [
    {"id": "输入事实ID", "statement": "逐字复制该事实"}
  ],
  "semantic_kernel": {
    "surface_terms": ["输入中的表面词"],
    "head_concept_hypothesis": "中心概念假设",
    "literal_action": {
      "statement": "不增强事实强度的表面动作",
      "fact_refs": ["输入事实ID"]
    },
    "human_action_hypothesis": "人类动作假设",
    "relationship_hypothesis": "关系变化假设",
    "social_rule_hypothesis": "社会规则假设",
    "desire_conflict_hypothesis": "两个不能轻易兼得的合理欲望假设"
  },
  "directions": [
    {
      "id": "稳定且唯一的候选ID",
      "semantic_distance": "near | mid | far",
      "industry_role": "subject | metaphor | stage | absent",
      "content_subject_hypothesis": "内容真正持续讲什么",
      "association_path_hypothesis": ["逐步可解释的语义路径"],
      "structure_mapping_hypothesis": [
        {"source_edge": "联想来源中的关系或因果边", "target_edge": "当前主体世界中的对应边"}
      ],
      "audience_tension_hypothesis": "观众可能面对的具体矛盾",
      "expression_mode_hypothesis": "适合该方向的表现形式",
      "subject_ownership": {
        "fact_refs": ["输入事实ID"],
        "hypothesis": "这些事实为什么可能形成不可替代性"
      },
      "business_attribution_hypothesis": "内容之外可能如何归因给主体和目标",
      "assumptions": ["本候选依赖的待验证假设"],
      "far_deletion_test": null
    }
  ],
  "recommendation": {
    "selected_direction_ref": "被选候选ID",
    "fact_refs": ["输入事实ID"],
    "assumptions": ["推荐依赖的待验证假设"],
    "reason_hypothesis": "为什么本轮选择它",
    "tradeoff_hypothesis": "主动放弃什么",
    "why_not_near_hypothesis": "为什么没有停在最安全的行业近邻"
  }
}
```

`directions` 必须恰好三项且各有一项 `near`、`mid`、`far`：

- `near` 的 `industry_role` 只能是 `subject`；
- `mid` 的 `industry_role` 只能是 `metaphor`；
- `far` 的 `industry_role` 只能是 `stage` 或 `absent`；
- 近、中路线的 `far_deletion_test` 必须为 `null`；
- 远路线的 `far_deletion_test` 必须改成下面的对象：

```json
{
  "removed_surface_terms": ["逐项删除输入 surface_terms"],
  "remaining_human_subject_hypothesis": "删除职业、产品和场地后仍能持续成立的人类内容主体",
  "ownership_fact_refs": ["证明仍属于当前主体的输入事实ID"]
}
```

中、远路线的 `structure_mapping_hypothesis` 至少给出两条不同的对应边。只能选择输入
`selection_policy.allowed_distances` 允许的距离。近、中、远是平行选择，不是质量等级。

