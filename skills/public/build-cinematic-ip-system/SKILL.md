---
name: build-cinematic-ip-system
description: 作为电影化个人IP的总控入口，判断项目所处阶段，并编排真实证据、欲望—行为、影视研究、长期圣经、题材、情绪、单集编剧、视觉导演、表演指导和连续性审片。用户要“从零搭建IP”“把电影方法做成账号系统”“做完整方案”或不确定该调用哪个子Skill时使用。
---

# 电影化个人IP总控

用最小必要的子Skill完成当前目标。系统覆盖真实证据、欲望—行为0号协议、影视研究库、八轨96模块训练、创作生产和发布校准。不要每次都跑完整流水线，也不要在人物为何行动尚未清楚时直接堆结构、情绪、镜头和滤镜。

先调用 `personal_ip_operating_cockpit` 读取全账号组合，再为相关主体调用
`personal_ip_read_strategy_context`。项目原生主体策略、preflight、发布回执、指标、
复盘、证据晋升和视频制作台账是唯一运行状态；不得依据聊天重建平行台账。账号仅在
具体发布、采集或浏览器操作中作为目标。

## 先诊断阶段

| 当前材料 | 下一步 |
|---|---|
| 有真实经历、聊天、视频、人物关系但未分事实/推断/同意 | `$ingest-ip-evidence` |
| 有具体结构/情绪/镜头/工种问题，要从库中选样 | `$query-cinematic-library` |
| 只有对标创作者、影片或课程 | `$distill-screen-methods` |
| 想系统训练某个电影工种或给团队补课 | `$run-cinematic-curriculum` |
| 有选题或人物，但说不清谁想要什么、为何行动 | `$engineer-desire-behavior` |
| 有欲望口号但没有具体目标、行动、代价和变化 | `$engineer-desire-behavior` |
| 有很多经历但说不清长期矛盾 | `$develop-theme-premise` |
| 有本人/业务，但没有长期前提 | `$design-ip-series-bible` |
| 前提成立但人物像标签、关系不会变化 | `$design-character-relations` |
| 有前提，但题材和持续事件不清 | `$route-ip-genre-engine` |
| 已选题材，需要该题材的专业结构 | 调用对应的 `$write-*` 类型编剧室 |
| 题材清楚，但账号/单集情绪混乱 | `$shape-ip-emotion` |
| 因果散、反转硬、伏笔与暗线混乱 | `$engineer-plot-information` |
| 有当日素材，要写可拍单集 | `$write-ip-episode` |
| 已有节点，要写重场戏和对白 | `$write-scenes-dialogue` |
| 人物只站着说话或群戏空间混乱 | `$direct-scene-blocking` |
| 要跨部门导演阐述和拍摄优先级 | `$previsualize-screen-direction` |
| 有脚本，要设计调度、镜头和光色 | `$direct-ip-visual-language` |
| 要精确处理焦段、机位、距离和运动 | `$design-cinematography` |
| 要精确处理布光、颜色、滤镜和调色 | `$design-light-color-texture` |
| 要用空间、道具、服装建立世界 | `$design-production-world` |
| 要从剧本阶段设计声音与音乐 | `$design-screen-sound` |
| 有场景，要导演演员或本人出镜 | `$coach-ip-screen-performance` |
| 已有素材或粗剪，要重组节奏 | `$edit-screen-rhythm` |
| 有方案/脚本/成片计划，要找漏洞 | `$audit-ip-continuity` |
| 准备发布、回收指标、复盘或升级方法 | `$calibrate-cinematic-ip` |

详细路由见 `references/orchestration.md`。

## 标准工作流

### 从零构建

1. 建立主体范围，把真实人物、事件、同意、限制和未知写入原生主体策略及证据引用。
2. 从研究库选择3–6个互补机制；没有现成卡再深挖，不按名人拼贴。
3. 冻结生命周期欲望账本：主体、欲望、成功/失败状态、反欲望、进度证据和伦理边界。
4. 开发主题问题和强前提。
5. 产出IP圣经、人物关系与现实/伦理边界。
6. 为账号选一个主类型、最多两个辅助类型，并调用对应类型编剧室。
7. 定义账号情绪承诺、信息系统与第一季波形。
8. 每个样集先完成欲望—行为映射，再用三个不同事件做压力测试和场景/对白。
9. 设计调度与导演预演，按需调用摄影、光色、美术、声音与表演工种。
10. 剪辑后做连续性验收；发布前通过原生 preflight 冻结欲望映射和盲预测。
11. 登记发布、指标和复盘；至少3条完整复盘后才升级局部方法。

### 只有一条视频

先用单集编剧；若用户已有定稿，直接进入视觉/表演。只有当本条依赖长期设定时才回补圣经。

### 账号卡住

1. 审查最近3–10条的承诺和五线变化；
2. 判断是事件枯竭、人物复位、类型漂移、情绪疲劳还是执行问题；
3. 只调用对应Skill修复；
4. 设计一个可比较的新样集。

## 共享状态

在各Skill之间传递同一份最小状态：

```yaml
ip:
  premise:
  lifecycle_question:
  lifecycle_desire:
    subject:
    root_drive:
      value: unknown
      evidence_status: unknown
    conscious_want:
    success_state:
    failure_state:
    counter_desires: []
    observable_progress: []
    ethical_boundaries: []
  audience_emotional_promise:
  primary_genre:
  secondary_genres: []
episode:
  event_goal:
  desire_behavior:
    subject:
    conscious_want:
    episode_goal:
    trigger:
    counterforces: []
    stakes:
    tactics: []
    observable_actions: []
    costly_choice:
    state_change:
    viewer_desire:
    silent_test:
  character_delta:
  long_arc_delta:
production:
  platform:
  duration:
  frame:
  people:
  locations:
  gear:
craft:
  blocking:
  camera_grammar:
  light_color_grammar:
  production_world:
  sound_grammar:
  edit_grammar:
boundaries:
  factual:
  privacy:
  consent:
  imitation:
calibration:
  subject_id:
  operation_scope:
  preflight_id:
  metric_window:
  retrospective_count:
  method_version:
```

若前一步没有明确某字段，保留 `unknown`，不要在后一步悄悄补成事实。

## 决策原则

- 故事问题优先于视觉包装；
- 欲望—行为链优先于起承转合模板；
- 人物行动优先于情绪标签；
- 观众信息优先于“悬疑感”；
- 片内色彩规则优先于滤镜名称；
- 单集兑现优先于长期挖坑；
- 静音行为测试不通过，不用旁白和台词解释补洞；
- 真人同意和事实边界优先于戏剧效果；
- 机制验证优先于对标相似度。
- 真实证据优先于戏剧补全；
- 发布前预测不可回写；
- 指标缺失保留为缺失；
- 三条完整复盘和留出样本优先于一次爆款经验。
- 只调用当前问题需要的细分Skill，避免30个Skill一次性占满上下文。

## 总控输出

1. 当前阶段与最主要瓶颈；
2. 本轮采用的能力路径与理由；
3. 当前判断和已确认前提；
4. 本轮交付；
5. 未知项和风险；
6. 下一次只需做的一步。

客户输出不得出现 Skill 名、路径、工具名、内部字段名或执行步骤；只描述完成了什么、
依据是什么和下一步是什么。若用户明确只要研究或审查，不擅自扩展到写作、拍摄或
发布。
