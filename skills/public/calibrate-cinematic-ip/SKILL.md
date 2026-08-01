---
name: calibrate-cinematic-ip
description: 通过 Personal-IP 原生服务执行不可变发布前盲预测、追加式发布回执、带覆盖说明的指标回收、预测对照复盘和证据化方法升级。用户要判断某种编剧、导演或情绪机制是否真的适合账号，或要发布后复盘和升级规则时使用。
---

# 电影化IP校准闭环

执行：

```text
证据 → 生命周期欲望 → 单集欲望—行为映射 → 有范围的判断 → 不可变盲预测 → 发布回执
→ 带覆盖的结果 → 复盘 → 可修订的方法假设
```

完整数据契约见 `references/project-data-contract.md`。

## 发布前冻结

先准备：

- 先读 `personal_ip_operating_cockpit` 和对应主体的
  `personal_ip_read_strategy_context`；
- 有主体策略笔记时读取并使用；没有时直接从本轮任务继续，账号只作为本次发布的操作目标；
- 准备目标、完整 `desire_behavior`、情绪承诺、事件/人物/信息/情绪/世界变化、
  暗线增量、开头与兑现；
- 准备指标名、基线、方向、最小变化、置信度和失败信号；
- 为每个候选冻结证据等级、可观察机制假设、预期信号、失败条件、平台分发假设和
  不确定性；
- 记录机制、迁移边界以及不含凭证的证据引用；
- 完成事实、同意、安全和非模仿检查；
- 调用 `personal_ip_run_preflight` 冻结请求与模型回执。

preflight 是不可变快照。要改变方案就创建新 variant，不修改旧预测。账号ID是本次
操作目标，不是对话权限，也不能替代主体策略。

预测不得声称内容“必爆”或把多巴胺、镜像神经元、蔡格尼克效应等名词当作完播、
互动或分享的因果证据。平台分配、受众匹配、竞争、时间和随机反馈必须保留为结果
不确定性的组成部分。

`desire_behavior` 是分析剧情行动的电影方法，不是 preflight 准入证书。需要剧情时尽量写清主体、欲望、目标、阻力、可见行动、代价和状态变化；不适用或信息不足时说明假设并继续。

## 发布与指标

发布动作必须接在已冻结 preflight 之后：

1. 浏览器优先发布时，调用 `personal_ip_prepare_browser_publish`，让用户自行完成
   密码、二维码、验证码与 MFA；提交成功后打开具体公开帖子，再调用
   `personal_ip_finish_browser_publish`。
2. API 或桌面兜底执行使用 `personal_ip_begin_publish_receipt` 和
   `personal_ip_record_publish_attempt`，共用同一回执契约。
3. 只读回收优先使用
   `personal_ip_collect_browser_portfolio_today`、`personal_ip_sync_douyin_portfolio`
   或已授权的单帖同步；分析前用 `personal_ip_performance_inventory` 与
   `personal_ip_metrics_aggregate` 读取完整覆盖。

指标缺失写 `null`，并保留 `missing/partial/unavailable` 覆盖，不能补0。累计快照
不能冒充日增量；同一内容的多个时间窗不能冒充多个独立样本。

## 复盘

调用 `personal_ip_seal_retrospective`，由服务端连接同一发布回执的原始 preflight
和发布后观察，冻结所选 variant、结果与证据摘要。复盘回答：

1. 哪些预测命中/失误；
2. 失误是机制、执行、受众、分发还是测量问题；
3. 哪些评论/时间点/素材能支持判断；
4. 若只改一个变量，反事实是什么；
5. 下一条保留什么、只改什么。

## 方法升级

比较任意相关的复盘与观察，由智能体提出可反驳、可修订的方法假设。服务端只保存
原始预测、发布与结果，不自动晋升或认证经营规律。

规则写成 `if—then—because—exceptions—validation_check`。跨平台、格式或受众的
可迁移判断还要在未参与归纳的留出内容上继续验证；通过局部门槛不等于已经证明普适。

一次爆款、一次低谷、经典影片地位或创作者名气都不能直接升级规则。

## 状态与读取

- 用 `personal_ip_read_preflight`、`personal_ip_read_publish_receipt` 和
  `personal_ip_read_retrospective` 读取精确
  对象；
- 用 `personal_ip_operating_cockpit` 查看主体和全账号组合的待办；
- 不生成外置兼容包，不创建本地 JSONL 台账，不从聊天历史重建状态；
- 客户输出讲清判断、证据、未知和下一步，不暴露内部 Skill 名、工具步骤、字段名和
  路径。
