# 研究库字段

## `films`

- `film_id`：稳定ID；
- `title`、`year`；
- `directors`、`writers`：来源中可解析的主创；
- `canon_inclusions`：来源榜单、排名、并列状态；
- `craft_lenses`：适合研究的工种入口，不是机制结论；
- `study_card`：统一看片问题；
- `provenance`：字段来源。

## `creators`

- `creator_id`、`name`；
- `roles`；
- `representative_works`；
- `mechanism_summaries`：本项目已有研究摘要；
- `evidence_labels`；
- `source_refs`。

## `mechanism_cards`

- `subject_kind`、`subject`、`domain`；
- `mechanism`；
- `evidence_label`；
- `observable_execution`；
- `transfer_question`；
- `failure_mode`；
- `study_lenses`；
- `source_refs`。

## 证据等级

`sourced_fact > cross_source_synthesis > analyst_inference > creative_hypothesis`

这个顺序表示来源距离，不表示创意价值。任何转译到真实账号的规则都必须进入盲预测和复盘闭环。
