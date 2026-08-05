# IP Agent 产品总台账

最后复核：2026-08-05。

本文件是唯一当前产品状态记录。`IP_AGENT.md` 规定运行边界；历史实验、失败样本和研究材料只保存在 `product/research/ip-agent/`，不能反向冒充现役能力。

## 最终产品定义

IP Agent 是一套面向人物、品牌、产品和组织的内容生产系统，不是“写几句文案”的聊天机器人。客户只看到三个核心板块：

```text
零起盘 ───────────────────────────┐
                                  ├─> 编剧脑 ─> 制作 ─> 成片 / 发布结果
精确链接或上传 ─> 拆解 ───────────┘                    │
        ↑                                              │
        └──────── 真实观测与制作反馈（后续控制回路） ───┘
```

编剧脑固定为两层：起盘决策脑理解人物、业务、产品、目标、资源和限制并选择方向；内容创作脑把方向变成故事与完整可拍剧本。反馈连接三块，但不是第四个产品板块。

## 三大核心板块

| 核心板块 | 系统角色 | 当前状态 | 已经成立 | 明确边界 |
| --- | --- | --- | --- | --- |
| 拆解 | 传感器：把指定外部内容变成可引用证据 | 现役 | 精确作品链接或上传视频可执行固定 `full + 12` 分析；同任务 Evidence 回执可保存为不可变 `BreakdownVersion` | 账号主页仍受登录态和平台稳定性影响；视觉估计不能冒充精确光学参数 |
| 编剧脑 | 决策器与创作器：先定方向，再写完整剧本 | 现役 | 零起盘与对标路线汇入同一 `ContentWork`；正式 `DirectionVersion`、`ScriptVersion` 可保存、读取和派生 | 模型输出仍须经过事实/虚构边界闸门；质量判断不等于传播效果保证 |
| 制作 | 执行器：从确定剧本建立制作任务 | 有界接通 | 内容板可从精确 `ScriptVersion` 启动一个或多个绑定 production；已有 production 可封存一等 formal Artifact，并在内容板/制作台按可用性播放、下载或重新导入原文件 | 默认 Agent 仍不暴露通用视频生产工具；新谱系的真实供应商生成、费用、QA 与成片全链尚未验收 |

### 拆解的准确口径

- 精确视频拆解：现役。默认 Agent 对明确作品链接或上传文件调用一次完整视频证据分析。
- 外部素材只有在同一任务里存在精确匹配的 Evidence MCP 调用与 ToolMessage 时才能入账。服务端校验 request、item、来源、哈希和完整 typed snapshot，REST 或模型不能伪造。
- `BreakdownVersion` 分开保存可观察内容、解释假设和限制；来源观测不会自动升级为可迁移因果机制。
- 景别、机位、运动、剪辑和声音可作为视觉/听觉观察；精确焦段只有源文件元数据或足够标定条件时才可确认。
- MediaKit Smart Strategy、Video Understanding Chat、Remux 和 Vibe 是不同合同，当前保持隔离，不因 Evidence 已接通而自动成为现役产品能力。

### 编剧脑的准确口径

- 起盘决策脑由 Lead Agent 负责：结合目标、观众情境、真实材料与限制，形成前提、张力、承诺、路线、理由和 truth mode。
- 内容创作脑由有界 Writer Brain 负责：事实型只读取显式 claim basis；纯虚构先让隔离故事发动机锁定一条因果故事，再做制作翻译；混合型同时保留事实依据和创作披露。
- 纯虚构故事发动机看不到 Owner 身份、履历、商业目标、品牌、产品、账号或拍摄条件。正式脚本还要经过第二个 fail-closed 边界审查；失败时 Work、Direction、Script 均不部分提交。
- 修改稿派生新版本，不覆盖旧稿。正式 Script 不能通过通用 REST 绕过 Writer Brain。

### 制作的准确口径

- 复用唯一的 `personal_ip_video_productions` 与 event 账本，不建立第二套制作数据库。
- production 的来源由服务端从精确 ScriptVersion 重建并封存；调用方不能粘贴或覆盖来源。后来出现的新 ScriptVersion 不会改绑旧 production。
- 同一 ScriptVersion 可以因比例、平台或制作模式分叉为多个 production；归档 Work 只允许精确幂等重放，不允许新任务。
- linked production 只能由“最新锁定时间线 → 精确最新成功交付执行 → 最新通过 QA → `personal-ip-final-artifact-v1`”的原子封存进入 completed。QA preview、普通 event artifact、原始 ref 或任意本地文件都不能冒充正式成片。
- Artifact 的不可变身份与本地字节可用性分开。JSON 备份只保存元数据和回执；恢复后显示“成片回执已恢复，文件待重新导入”，只有原字节的 SHA-256、大小和规范 MIME 再次精确通过服务端校验后才恢复播放。
- “已建立绑定制作任务”不等于“供应商已生成资产或交付成片”。后者必须由 production events、最终 Artifact、费用/审批和 QA 回执共同证明。

## 两个现役入口

| 入口 | 用户提供 | 系统最小产物 | Breakdown 要求 |
| --- | --- | --- | --- |
| 零起盘 `zero_start` | 人物/品牌/产品、目标、观众情境、真实材料和硬限制中的最少必要信息 | 推荐方向、完整正式脚本、可选制作任务 | 可选；不得为了走流程强迫用户先找对标 |
| 对标 `benchmark` | 精确作品链接或上传文件 | Evidence、拆解版本、方向、完整正式脚本、可选制作任务 | 必须绑定同任务的精确 Evidence 回执 |

“已有账号历史”保留为未来入口，不出现在当前路由或 UI 中。两条现役路线共享同一编剧脑、版本账本和制作账本，不是两套系统。

## 共同内容主线

```text
Owner → Subject → Objective → ContentWork
  → BreakdownVersion → DirectionVersion → ScriptVersion
  → VideoProduction → Artifact → Publication
  → Observation → LearningDecision
```

| 对象 | 当前状态 | 权威含义 |
| --- | --- | --- |
| `objective_id` | 已实现 | 一次作品目标的服务端稳定身份 |
| `content_work_id` | 已实现 | 系统内部一条原创内容的稳定主键；不同于外部平台作品号 |
| `breakdown_version_id` | 已实现 | 绑定来源、覆盖、Evidence snapshot 与哈希的不可变拆解版本 |
| `direction_version_id` | 已实现 | 方向判断、事实引用、创作假设和父版本 |
| `script_version_id` | 已实现 | 经 Writer Brain 与边界闸门生成的完整不可变剧本 |
| `production_id` | 已绑定 | 绑定精确 Work/Script 的制作任务；兼容历史未绑定记录 |
| `artifact_id` | 已实现（成片纵切待真实验收） | 绑定一个 linked completed production 的正式最终成片稳定身份、内容哈希、大小与规范 MIME；运行可用性由 `content_available` 另行表示 |
| `publication_id` | 后续纵切 | 发布回执将来绑定 Work、Script 与 Artifact |
| `observation_id` | 后续纵切 | 发布后指标、评论和制作反馈；缺失保持缺失 |
| `learning_decision_id` | 后续纵切 | 基于成熟观测决定下一版本只改什么 |

任务、聊天、Prompt、Skill、ToolMessage、Run Event 和供应商任务都不能替代这条业务主线。任务只记录来源，不授予 Owner 权限。

## 当前唯一交付主线

| 编号 | 目标 | 状态 | 完成条件 |
| --- | --- | --- | --- |
| V1 内容纵切 | `零起盘 / 精确链接或上传 → BreakdownVersion（按入口）→ DirectionVersion → 完整 ScriptVersion → 绑定 Production` | 最终版 | 同一 Owner/Work 谱系可从正常 UI 与默认 Agent 入口创建、刷新读取、派生和归档；事实、证据、假设、虚构与制作回执分层；旧备份可恢复，跨 Owner/错版本绑定拒绝 |
| V1.1 正式成片实体 | `Production → final Artifact` | 工程链有界接通；真实验收未完成 | Artifact 合同、持久化、封存闸门、Owner 内容读取、内容板/制作台投影、备份恢复、原字节重挂和两阶段文件删除已接通；仍需一条全新真实供应商谱系完成付费/审批、执行、QA、下载哈希、删除恢复和 Gateway 重启后重挂验收 |

V1 不把供应商成片、自动发布、账号历史诊断、长期记忆或方法自动学习冒充已完成。它们只能沿现有主线逐段解冻，不再重构三板与核心身份。

## 后续顺序

| 顺序 | 纵切 | 解冻条件 |
| ---: | --- | --- |
| 1 | `Production → final Artifact` | Artifact 工程合同、存储、UI、备份恢复与重挂已接通；剩余门槛是新内容绑定任务的真实供应商执行、费用/审批、QA 与成片哈希闭环 |
| 2 | `Artifact → Publication → Observation` | 发布回执绑定 Work/Script/Artifact，成熟观察窗口保持缺失值语义 |
| 3 | `Observation → LearningDecision → next ScriptVersion` | 有足够真实样本；相关性不冒充因果，变更保持可追踪 |

## 当前可达运行面

- `/workspace/content` 是三板主界面，提供零起盘、对标拆解、版本读取和正式剧本启动制作入口。
- 默认 `ip-agent` 为八个基线工具、两个 Evidence 工具和四个有界内容工具，共 14 个；`skills: []`、`memory_enabled: false`。
- `/api/personal-ip/content-works` 提供 Owner-scoped 读取、版本追加与归档；外部 Breakdown 和正式 Script 的安全门不能由 REST 绕过。
- Production 板只把 v2、当前 Work、谱系内正式 Script 三者匹配的记录显示为已绑定；legacy 或错配数据不会被猜成绑定。
- `/api/personal-ip/artifacts/{artifact_id}` 只返回去路径的客户安全元数据；`.../content` 是 linked production 正式成片唯一播放/下载入口，支持单 Range。恢复回执只能通过同一入口的 raw `PUT` 重挂原字节；旧 production+sha 路由对 v2 直接 404。
- Owner 备份现行为 v4；使用服务端 HMAC manifest 和 `key_id`，只保存 Artifact 元数据而不包含成片字节。真实 v1-v3 仍先按各自旧字段形状和无密钥 SHA 摘要验证，再只在内存中升级。
- 整体删除 preview 绑定当前数据摘要，confirmation 分别要求备份与 Artifact 文件确认。正式 Artifact 文件先验证并移入 Owner 隔离区，数据库提交后才清除；这不冒充数据库、MineContext、文件系统与进程崩溃之间的全局原子事务，也不递归删除没有 formal Artifact 回执的历史孤儿文件。

## 验证证据

- 2026-08-04：干净任务真实调用一次 `ip_evidence_inspect_reference_videos`，176.104 秒完成固定 `full + 12`、ASR、OCR、场景切分和故事线，`operation_status=ok`。
- 2026-08-05：本轮最终后端回归 Personal-IP 50 个文件共 388 项、IP-Agent 400 项、迁移/历史升级 46 项、MediaKit canary 脚本 65 项全部通过，零失败、零跳过；backend Ruff 全量检查与本轮 Python 格式检查通过。
- 2026-08-05：前端单测 742/742 通过，TypeScript、ESLint、Prettier 和生产构建全部通过，生产构建完成 81/81 静态页且包含 `/workspace/content`；此前三板/导航 7/7 定向 Playwright 通过，本轮 Artifact 可用性、失败重试、raw PUT 和制作台刷新 6/6 定向 Playwright 通过。
- 2026-08-05：Owner backup v4 的 HMAC、`key_id`、策略字段、完整 Artifact 谱系和数据摘要均在恢复前校验；错密钥、坏 MAC、成片擦除后伪造 legacy 事件、stale execution、非规范 MIME/路径全部被拒。备份不含二进制，恢复后 `content_available=false`，删除与精确原字节重挂的正反例已通过；v1-v3 只保留历史无密钥摘要兼容。
- 2026-08-05：一条非 mock repository 的 Gateway + SQLite 进程内闭环已通过：linked Work/Script/production、时间线、锁定、受信执行/QA、formal Artifact、Range GET、v4 导出、真实删除、空 Owner 恢复、`content_available=false` 404、raw PUT 重挂与下载 SHA-256 一致均走真实路由与持久层，Artifact digest 未改变。
- 2026-08-05：免费 `make video-e2e-local` 连续两次幂等完成，均为 11 个事件、QA 通过、同一 SHA-256 `f0e6604ace19f32eca3c810ff92320ce0a957dc86b348b000983b8cfec019544`，实际 finisher 为本地 MediaKit CLI。该命令是 legacy/模拟付费供应商的本地机械验收，不冒充 linked formal Artifact 或真实付费供应商终态。
- 2026-08-05：默认 Agent 的正常零起盘 run `22c2da70-bb25-4364-8163-39fbc0de8f34` 为 `success`，生成 Work `content-work-763ecd4ed5a14bd7b6656ce9104ba807`、Direction v1、正式 Script v1，且 Breakdown 数量为 0；随后正常 run `6ff594ae-bd10-4aec-a097-1329ba6b1a5d` 为 `success`，建立精确绑定该 Work/Script 的 production v2。两次均未人为缩小递归预算。
- 2026-08-05：真实上传视频由 MediaKit 用 196.368 秒完成 `full + 12`，12/12 帧、ASR、OCR、场景切分和故事线均完成；谱系 `content-work-b145962a99bb49ce9c1b6717653f183a → breakdown-ec0d7eb6e12e483c8281b8d6564d2e0a → direction-b6d690e760954a8098e3fa68cca2991a → script-40c09e618a1347148e2fc899b4e0ef00 → video-production-b8300d8038f0408eb87964cbc6fd6fad` 经 API、SQLite 和摘要重算一致。
- 2026-08-05：同一 benchmark 的纠偏 run `32959327-06be-46ec-8a92-1c9036a2e75b` 为 `success`，Evidence 调用为 0、Breakdown 数量保持 2，精确复用上述 v2 并派生 Direction v2 / Script v2；ASR 只表述为“两条口语转写、未返回其他口语转写”，音乐、环境声和音效保持未知，机制判断均保留为假设。
- 默认 Agent 产品文件当前摘要为 `988b3ebe5af040d9799991a5c43b75f6943a63abfae7c2d76cc990a87e51e44a`。

## 固定边界

Owner 隔离、凭证保密、OAuth state、权利与披露、删除、路径/哈希/候选一致性、不可变回执和幂等性继续保留。Artifact 身份与字节可用性分开，备份不包含成片二进制，删除与重挂均不得放宽 Owner、路径、SHA-256、大小或 MIME 边界。外部证据、用户事实、推导假设、创作虚构和执行回执必须分开。

旧 strategy、differentiation、preflight、retrospective、evidence promotion、startup cockpit 和固定叙事访谈运行层保持退役。电影化 Skill 与 `product/research/` 只做研究库存；生产包不得导入研究隔离区。

除本文件外，不得新建平行的当前产品状态台账。只有客户入口、真实终态和对应版本/哈希同时存在时才可写“完成”。
