# IP Agent 产品总台账历史快照（截至 2026-08-04）

> `research_quarantined`：这是旧产品总台账的原文快照，用于追溯实验、Run、Token、哈希和失败结论。
> 它不再代表当前产品状态；当前唯一产品状态见 `docs/IP_AGENT_PRODUCT_LEDGER.md`。

以下内容保留旧台账在 2026-08-04 当时的原始叙述和状态词，仅供历史复盘。
其中的“当前”“现役”“已解决”和“唯一总台账”均按快照日期理解，不得用于判断今天的产品能力。

最后复核：2026-08-04。

## 全局主要矛盾

> 用户需要从真实对象出发，得到能够改变目标受众识别、记忆、信任、选择与行动，
> 并能根据真实结果持续纠偏的 IP 系统；但当前仓库只有分散的底座、传感器、方法库和
> 执行账本，尚未用统一本体、保真信息主干和可归因反馈闭环组成一个整体。

当前占支配地位的一面不是 M2 的剧情强度，而是系统没有共同的业务对象和可信信息通道。
工具、Skill、模型、MCP 或数据表的存在不等于产品链路成立。M2-E4 及其他下游实验先冻结，
直到系统主干的前置门通过。

## 四论系统宪法

| 视角 | 系统必须回答 | IP Agent 的权威结论 | 禁止退化成 |
| --- | --- | --- | --- |
| 系统论 | 整体目的、边界、层级、库存、流量和延迟是什么 | IP 是主体与目标受众之间随时间变化的识别、记忆、信任、期待、偏好和行动关系；内容是干预，平台是环境，指标是延迟且有噪声的观测 | 产出内容数量、搜索助手、单条爆款分数 |
| 本体论 | 存在哪些对象、关系、状态和权威来源 | `Owner → Subject → IPObjective → IPDirectionVersion`；`EvidenceItem → Claim → Interpretation → MechanismHypothesis`；再进入 `Work → WorkVersion → Artifact → Publication → Observation → OutcomeAssessment → LearningDecision` | 让对话历史、提示词、Skill 或模型回答冒充业务数据库 |
| 信息论 | 身份、含义、来源、覆盖与限制能否跨边界保真 | 任何跨模块对象都必须携带稳定 ID、产生者、来源、观测/有效时间、版本/哈希、覆盖范围、限制和认知状态 | 字符串搬运、名称猜测、将部分采样写成全量事实 |
| 控制论 | 目标、状态估计、行动、反馈、延迟和纠偏如何闭环 | 用户是共同控制者；Agent 产生可证伪假设和行动方案；真实发布与观测才能促成学习结论 | 用硬门代替创作判断、用短期播放操纵长期方向 |

系统永久分离四个世界：现实事实、认知声明、创作虚构和执行回执。创作虚构合法；
将创作冒充用户事实或来源观测不合法。统一认知状态为 `user_asserted`、`source_observed`、
`derived`、`hypothesized`、`creative`、`unknown`、`contradicted`。

## 执行制度

1. 同一时间只允许一个“当前主要矛盾”；其他问题只登记为次要矛盾。
2. 每轮先冻结验证假设、真实样本和失败标准，再实现最小变化。
3. 每一个可观测小批次立即跑相应层的单元、合同/集成和真实样本，不等多层一起完工。
4. 真实验收未通过，不进入下游、不追加提示词或服务器经营硬门、
   不把原型提交成产品能力。
5. 失败先记录发生层级和真实输出；同一解法反复失败后标记“方案淘汰”，
   更换路径而不在下游打补丁。
6. 只有通过验收的矛盾才登记正式提交，并把下一个问题提升为主要矛盾。
7. 并行任务只做可独立审计的读取工作；同一权威文件和同一运行合同始终只有一个写入者。
8. 每个批次必须保留最近通过基线；失败代码不提升到默认运行配置，实验产物留在隔离区。

状态只使用：`当前主要矛盾`、`待转化`、`验证中`、`已解决`、`外部阻塞`、`方案淘汰`。

### 边写边测批次合同

| 开工前必填 | 改动后立即留证 | 通过才允许 |
| --- | --- | --- |
| 唯一矛盾、最小因果假设、保护基线、真实样本、失败标准 | 变更面、单元结果、合同/集成结果、真实 E2E、实际输入/工具/模型/Token/时延和产物哈希 | 更新现役合同、提升默认能力、记录正式提交、转化下一矛盾 |

文档/合同批次先跑唯一性、状态词汇、死链接和现役/目标态声明检查；信息边界批次先跑字面保真、
身份绑定、coverage 传播和长对话压缩测试；业务纵切批次必须追踪稳定 ID 直到真实观测。

## 主要矛盾序列

| 编号 | 主要矛盾 | 主要方面 | 状态 | 矛盾转化条件 |
| --- | --- | --- | --- | --- |
| MF 系统主干 | 用户需要一条可归因、可纠偏的完整 IP 生命链，与已有能力缺少统一目的、本体、信息主干和控制闭环的冲突 | 当前先修复信息与权威边界，并建立跨证据、作品、成片、发布、观测的业务主键 | 当前主要矛盾 | MF-E1 信息底座通过后进入本体主干；首条纵切成立后才恢复 M2 方法实验 |
| M0 纯净基线 | 模型受旧语义、工具和隐式流程污染，与自然回答需求冲突 | 旧运行链路占用了模型注意力并制造互相矛盾的指令 | 已解决 | 纯净 Chat 成为永久对照组 |
| M1 真实证据 | Agent 必须看见真实对标内容，与账号和视频证据提取不稳定冲突 | 三账号及真实 Agent 回放证明了隔离 Sensor 路径；四论审计又发现缓存键、截断 coverage、精确作品绑定和 MCP trust 传播尚未闭合 | 待转化 | 在 MF-E1 中完成信息保真回归后，再决定 M1 是否恢复为已解决 |
| M2 专业综合 | 已有真实证据和方法，与模型不能形成完整原创方案冲突 | M2-E3 已证明六段组合方法无净增益；继续优化剧情会掩盖上游对象、证据和因果链没有正式状态的系统问题 | 待转化 | MF-E3 首条业务纵切建立稳定对象和上下游 ID 后，才重启 M2-E4 |
| M3 用户表现 | 脚本成立，与用户未必能在镜头前完成表达冲突 | 素人表演、镜头恐惧和制作形式的真实适配尚未验证 | 待转化 | 建立试拍证据和真人/旁白/无真人/数字人选择路径 |
| M4 账号诊断 | 用户可能自我感觉良好，与真实影响力和转化不足冲突 | 尚未建立内容为主、平台适配为辅的强账号诊断 | 待转化 | 能基于真实作品、指标和转化给出可回指证据的结论 |
| M5 执行闭环 | 已有判断和内容，与发布、采集、制作不能稳定形成闭环冲突 | 保留的执行能力尚未重新接入纯净 Agent | 待转化 | 发布、数据和视频生产按真实任务分别通过 |
| M6 持续成长 | 单轮能力成立，与长期经验无法积累和规模化冲突 | 记忆和子 Agent 是否创造净增益尚未证明 | 待转化 | 只在 M1–M5 成立后做有无记忆/子 Agent 对照 |

## 当前主要矛盾：MF 系统主干

### 系统建设批次

| 批次 | 唯一验证假设 | 开工前冻结的通过条件 | 当前状态 | 下一转化 |
| --- | --- | --- | --- | --- |
| MF-E0 系统宪法 | 先统一目的、本体、信息与控制合同，才能阻止后续再用局部补丁修系统 | `IP_AGENT.md` 明确分开现役与目标态；本台账只有一个当前主要矛盾；状态词汇、文档指针和默认运行声明通过机械检查 | 已解决 | MF-E1 信息边界 |
| MF-E1 信息边界 | 先保证名称、身份、证据覆盖和实际 Agent 在所有边界不失真，才有资格评价模型与方法 | 外部消息权威、实际 Agent 身份、中文字面往返、长对话摘要注入、MCP trust、缓存键、截断 coverage、精确作品归属和最终请求观测全部有回归 | 验证中 | MF-E2 业务本体 |
| MF-E2 业务本体 | 用最小 Shared Kernel 和 bounded context 消除同名异义与多权威 | 定义并用 competency questions 验证 Owner/Subject/Account/Work/Artifact/Publication/Evidence/Claim 的身份、时间和上下游关系；不恢复旧 strategy/preflight 表 | 待转化 | MF-E3 首条纵切 |
| MF-E3 首条纵切 | 只有完整走通一条作品生命链，才能证明子系统已组成产品 | 同一真实样本以稳定 ID 贯穿证据、假设、IP 方向、作品版本、成片、发布、观测和学习；任一断点失败即停 | 待转化 | 恢复 M2-E4，同时进入 MF-E4 |
| MF-E4 状态化编排 | 编排应根据目标、阶段、已有证据、缺口和前步结果选择下一合法动作，而不是最后一句关键词 | 网页、视频工作台、定时任务与 IM 进入同一产品身份；工具结果能合法促成下一阶段 | 待转化 | MF-E5 多时标反馈 |
| MF-E5 多时标反馈 | 分开即时语义、生产、发布结果和长期 IP 关系，才能避免短期指标导致系统振荡 | 观测窗口、基线、结果成熟度、假设版本和学习适用范围都可追溯；缺失不变零，相关不冒充因果 | 待转化 | 再评估记忆与子 Agent |

MF-E0 已于 2026-08-02 完成：新增的文档合同守卫验证了现役/目标态分离、唯一当前主要矛盾、
M2-E4 冻结和权威文档指针，`uv run pytest -q tests/test_ip_agent_system_contract.py`
结果为 `4 passed`。该结果只证明系统合同已建立，不声称运行链已实现。

### MF-E1 已登记的前置故障

| 编号 | 已验证现状 | 最小修复假设 | 本批必跑的测试 | 状态 |
| --- | --- | --- | --- | --- |
| MF-I1 MineContext 读副作用 | Workspace 加载的 GET 会为新 Owner 写默认同意、代替用户确认连续录屏并启动 sidecar；当前 IP Agent 不消费该数据 | GET 只读；新 Owner 默认关闭；只有明确 UI 动作才能创建同意和启动采集 | 新 Owner 首次 GET 零写入/零进程；明确开启后可读；关闭/撤回后重复 GET 不重启 | 已解决 |
| MF-I2 产品运行身份 | 网页传 `ip-agent`，视频工作台要求它不具备的能力，Scheduler 和 IM 默认进入 `lead_agent`，直接 Run API 可选运行时 | 服务器级 `product_runtime_profile` 决定客户入口允许的 Agent/工具/Skill/记忆，不信任前端名称 | 网页、直接 Run、Scheduler、IM 同题及 `lead_agent` 越权覆盖矩阵 | 验证中 |
| MF-I3 外部消息权威与实际 Agent | Gateway 保留外部 `system/ai/tool` 角色，并允许实际 `agent_name` 与持久化 `assistant_id` 不同 | 产品外部输入只能产生 Human 消息；Run 持久化实际执行身份 | 伪造角色、body/config/context 身份冲突和 Owner 隔离回归 | 待转化 |
| MF-I4 长对话保真 | 空 Skill 的 IP Agent 会压缩并删除旧消息，却不挂载将 `summary_text` 重新注入模型的 Durable Context | 摘要注入与 Skill 开关解耦，并对名称、否定、来源和 coverage 使用结构化不变量 | 超阈值多轮对话、assistant-tool 尾部和中文专名往返 | 待转化 |
| MF-I5 MCP trust 与证据保真 | MCP 转换丢弃部分 annotations/`_meta`，清洗主要按工具名；视频缓存键未完整绑定分析参数，截断产物可被标成 completed，精确作品不可证明时存在 DOM 首视频回退 | trust 由能力合同而非名称传播；缓存绑定内容+分析合同+工具链版本；截断和无法绑定均失败关闭 | prompt injection 中和、缓存参数交叉、coverage 传播、精确 work id 与错误页回归 | 验证中 |
| MF-I5d MediaKit 供应商边界 | 官方 MediaKit 已提供大量媒体原子能力，而 Evidence MCP 仍混合平台取证、证据封装与手写媒体执行 | MediaKit 作为可替换媒体 Sensor/Effector 内核；Evidence MCP 只保留精确来源、身份、SHA-256、coverage、归一化和收据，不重造官方上传、轮询或媒体算法 | 同一已哈希快照的官方本地探测与 ffprobe A/B；随后验证本地快照云端上传、task 终态和调用收据 | 验证中 |
| MF-I6 最终请求观测 | Run journal 没有保留全部中间件之后的最终模型请求，本地 `run_events.backend` 为 memory | 持久化脱敏后的实际模型、system/messages/tools 结构摘要及各自哈希，不保存凭证或原始私密素材 | 中间件前后差异、重启可查、脱敏与大工具结果上限回归 | 待转化 |

MF-I1 于 2026-08-02 按红绿循环完成。开工前的真实旧实现回归为 `7 failed, 11 passed`，
分别证明默认自动授权、GET 写目录、替用户确认录屏及主动改写既有授权模式。最小修复后：

- GET 只调用纯 `status`，不再授权、迁移、清理数据或启动进程；
- `auto_enable_new_owners=true` 成为拒绝启动的退役配置，默认值和正式/示例配置均为 `false`；
- `/enable` 必须收到字面值 `continuous_screen_capture_confirmed: true`，缺失或 `false` 均为 422；
- 设置页明确说明默认关闭、当前默认 Agent 不读取该数据，并在启动所有显示器的有界采集前弹确认；
- 既有主动授权只按原 scope/mode 恢复，撤销或清除后的重复 GET 不会重启。

后端 MineContext、HTTP、工具和整域数据生命周期定向回归为 `27 passed`；Ruff 全绿；前端
定向单测 `2 passed`，Prettier、ESLint 和 TypeScript 全绿。重启隔离测试栈后的真实 Gateway
回放中，首次 GET 为 200，授权文件数 `0 → 0`，返回 `authorized=false/running=false`；缺失确认
和 `false` 各返回 422，仍为零写入。真实设置页显示“默认关闭/尚未开启”，点击开启检测到原生
确认弹窗；自动化未接受，最终状态和授权文件仍未改变。为避免在验收中真的录制用户屏幕，正向
启动使用临时目录与假进程的服务集成测试，未对真实桌面执行采集。

### MF-I2 分批合同

MF-I2 不一次重构所有入口，先切断已经证实的运行时旁路，再建立统一产品身份。每个子批单独红绿、
单独真实请求验证；前一批未通过时不做后一批。

| 子批 | 唯一验证假设 | 保护基线与失败标准 | 状态 |
| --- | --- | --- | --- |
| MF-I2a Scheduler 关闭即不可执行 | 当 `scheduler.enabled=false` 时，创建和手动触发都在访问 repository/service 前返回明确的 feature-disabled 响应，就能切断当前最直接的 `lead_agent` 旁路 | 保留通用 Scheduler 开启态行为；关闭态 create/trigger 必须零 repo、零 task row、零 run；只改后端入口，不冒充 UI 已隐藏 | 已解决 |
| MF-I2b1 请求身份归一 | 先令 `assistant_id` 成为每轮运行身份的唯一权威，就能消除“Run 记为 `lead_agent`、模型却读 `ip-agent`”的不可归因状态 | 网页必须在 SDK `assistant_id` 中发送 `ip-agent`；显式 `assistant_id` 与 config/context `agent_name` 冲突时必须在创建 Run 前 400，不静默猜测；RunRow、ThreadMeta 和实际 RunnableConfig 必须同值。仅对完全缺少 `assistant_id` 的旧调用保留唯一 `agent_name` 提升兼容，并保留 Agent 创建流的 `lead_agent + is_bootstrap=true` 例外 | 已解决 |
| MF-I2b2a 服务器入口绑定 | 在请求内部身份一致后，由服务器根据受信入口绑定 product profile，而不是相信客户端选择 | 客户 Run 固定 `ip-agent`；IM/Scheduler 只有服务器标记的入口可绑定；bootstrap、其他 Agent、伪造入口和伪造 receipt 都在创建 Run 前拒绝或剥离 | 已解决 |
| MF-I2b2b Owner 精确供给 | 产品身份必须解析到当前 Owner 的精确 Agent 工件，不能回退共享目录或在首次使用时形成半安装状态 | 新 Owner 首次受信产品请求原子安装；并发只形成一个完整目录；symlink、残缺、串 Owner 和漂移全部失败关闭；既有 Owner 文件绝不自动覆盖 | 已解决 |
| MF-I2b2c 产品工件防漂移 | 只校验三项能力声明不能证明实际运行的是同一产品 Agent，必须同时固定精确配置和 SOUL 字节 | profile 绑定 `config.yaml + SOUL.md` 工件哈希；客户不能创建、修改或删除 operator-owned `ip-agent`；任何字节漂移在模型调用和 Run 创建前 503 | 已解决 |
| MF-I2c 界面能力投影 | UI 只展示服务器 capability manifest 中现役且可达的入口 | Scheduler 关闭时导航/线程快捷入口/配方页不可达；视频工作台不再向当前 8+2 工具 Agent 下发其不具备的视频生产指令 | 待转化 |

MF-I2a 的旧实现红测为 `2 failed, 3 passed`，两条失败都证明关闭态仍先访问 repository；加入
入口门后扩大调度回归首次暴露 5 个开启态测试夹具未显式声明 `enabled=true`，将夹具改为明确开启
而没有让生产代码猜测缺失值。最终 Scheduler router、service、repository、model、schedule、claim
和 lifecycle 共 `54 passed`，Ruff/format 全绿。隔离测试栈真实请求中，关闭态 create 和 manual
trigger 都返回 `404 / Scheduled tasks are disabled`，`scheduled_tasks` 行数保持 `0 → 0`。首次真实
回放曾命中未重载的旧 Gateway 并创建 1 条精确测试任务；该记录已按响应中的唯一 task id 删除，
数据库恢复 0 行后重启进程再验收。该批只切断关闭态旁路；Scheduler 开启态仍固定
`assistant_id=lead_agent`，导航仍可见，必须由 MF-I2b2/I2c 继续解决。

MF-I2b1 的红测为 Gateway `5 failed`、IM `2 failed`、网页 Playwright `1 failed`：旧实现
不拒绝冲突身份，RunRow 保存未规范化名称，网页和 IM 均将实际自定义 Agent 伪装成
`lead_agent`。最小修复引入单一 `effective_assistant_id`，把同一值用于 Run、Thread 和
RunnableConfig；冲突在 Run 创建前 400；Channel Skill 白名单也改为读该同一身份。
扩大回归为 Gateway `92 passed`、Channel `270 passed`、SQL ThreadMeta `49 passed`、真实
bootstrap `1 passed`、前端 `pnpm check` 通过，网页请求 Playwright `1 passed`。隔离
Gateway 真实请求中，冲突输入返回 400 且 Run 数保持 0；合法 `IP_AGENT` 输入后
SQLite 中 RunRow/ThreadMeta 均为 `ip-agent`。该正向探针实际产生 `3477` tokens，证明
`interrupt_before=["*"]` 没有实现本轮预期的零模型调用；测试线程及其 Run 已按精确 id
删除，行数回到 `threads=0/runs=0`。MF-I2b1 只解决“一轮一个身份”；客户入口是否必须
运行 `ip-agent`、Scheduler/IM 是否被产品 profile 锁定，仍属 MF-I2b2，不宣称已解决。

MF-I2b2 按三个可独立观察的子批完成，而没有把入口、Owner 文件和工具装配揉成一次重构：

- b2a 新增 operator-owned `product-runtime-profile.yaml`。产品客户入口固定为 `ip-agent`；IM 与
  Scheduler 必须由服务器写入受信入口标记；客户端的入口标记、产品 receipt、bootstrap 和其他
  Agent 选择不能提升能力。`product_entrypoint` 只参与本次绑定，不进入实时或持久化 config；
  Thread metadata 中伪造的产品 receipt 会被删除并由服务器 Run receipt 替换。曾将 YAML 的
  `off` 写成未加引号的标量，解析后变成布尔值并导致真实请求 503；先用产品文件合同测试复现，
  再固定为字符串 `"off"`，没有在加载器中为错误配置增加猜测兼容。
- b2b 在受信入口、模型调用和 Run 创建之前执行 Owner 精确供给。新 Owner 缺少产品 Agent 时，
  从正式默认工件原子安装；已有目录只验证、不修补、不覆盖，也禁止回退到旧共享 Agent。
  并发红测在 macOS 暴露 `ENOTEMPTY` 与 Linux `EEXIST` 差异后，收口为同一原子结果；隔离
  evidence Profile 则验证当前 Owner 已有且与当前 profile 一致的工件，不被当时的正式八工具模板误覆盖。
- b2c 使用确定性 framed-byte SHA-256 绑定精确 `config.yaml + SOUL.md`，并关闭客户对
  operator-owned `ip-agent` 的创建、修改和删除。这里的 `declared_capability_digest` 只证明
  profile 声明一致，工件哈希只证明 Agent 文件字节一致；“最终实际装配了哪些工具”仍需在
  MF-E2/MF-I6 用运行时 capability manifest 和最终请求观测证明，当前不作越界宣称。

定向红绿与扩大回归结果：产品 profile、Owner 供给、Gateway、Thread、测试模式和自定义 Agent
共 `38 passed`；安装器 `4 passed`；扩大后端核心 `248 passed`；全量 Channel `273 passed`；
系统合同、Skill 基线和安装器 `18 passed`。隔离测试栈真实正向 Run
`5a3aa994-6c50-4b38-9af6-aed3e06176cd` 只执行一次模型调用，输入 `3423`、输出 `2`、合计
`3425` tokens；Run/Thread/实际配置均为 `ip-agent`，持久化 config 只剩业务 context。真实
bootstrap 返回 403、其他 Agent 返回 409，二者均零 Run；临时改写隔离 Agent 的 SOUL 后返回
503 且零 Run，恢复后工件哈希重新一致。所有精确测试 Thread/Run 已删除并复核为 0，测试
Profile 和登录状态均保留。该批尚未解决 MF-I2c 的界面能力投影，也未解决实际工具装配证明，
因此 MF-I2 总项仍为“验证中”。

MF-I2c 开工前冻结：现有控制面已经知道测试栈 `scheduler.enabled=false`，产品运行 Profile 又明确
声明 `video_workbench="off"`，但 `/api/features` 没有投影这两项；侧栏与线程页无条件显示
定时任务入口，直达页立即请求 Scheduler API，视频工作台还会挂载 Agent 会话并注入它不具备的
图片生成、视频生成和账本写入指令。本批只增加一个不暴露工具名或 Skill 名的服务器
`workspace-capabilities-v1` 投影，并让 UI 消费它：Scheduler 不可用时不显示两个入口、直达页
不请求任务 API并返回工作区；视频工作台 Agent 不可用时不挂载 Agent 会话、不显示输入框、
不自动提交快捷动作，但保留只读工作台与已有人工编辑接口。能力清单缺失或读取失败一律按不可用，
不能靠前端缓存猜测开启。实际模型请求和最终装配工具仍由 MF-I6 验证，本批不得越界宣称。

### MF-I5 分批合同

MF-I5 按“信息是否可信、语义是否完整、来源对象是否精确”拆开验证，不能因为 MCP 调用成功就把
领域证据误判为完整，也不能让远端工具通过返回内容自行声明更高信任级别。

| 子批 | 唯一验证假设 | 保护基线与失败标准 | 状态 |
| --- | --- | --- | --- |
| MF-I5a 证据结果策略、清洗、预算与领域结果 | 由 operator 配置为工具绑定本地结果策略，并让清洗、混合多模态预算和领域结果映射只读取该策略，就能阻止外部内容自提权，同时保留图片/资源和结构化证据 | 未分类工具维持 DeerFlow 旧行为；远端自报 trust 不生效；`partial/failed/truncated` 不得因 MCP transport success 被写成完整成功；大文本不能因同时含图片而绕过预算 | 已解决 |
| MF-I5b MCP 内容块语义保真与撤销 | 保留 `annotations`、`_meta` 和 Audio 的受控语义，并在配置删除/不可读时撤销工具而非继续使用 last-known-good，才能使能力撤销和多模态来源可审计 | 不把凭证或远端控制字段透传给模型；现有 Text/Image/Resource 行为不退化；删除或拒绝配置后旧工具不可继续调用 | 已解决 |
| MF-I5c 视频缓存、coverage 与精确作品绑定 | 缓存键绑定内容、分析合同和工具链版本，截断显式降低 coverage，页面无法证明目标作品时失败关闭，才能阻止旧证据或错误作品污染下游 | 同内容不同分析参数不得串缓存；截断不得为 completed；错误页、首视频回退、作者不匹配必须停止 | 验证中 |

MF-I5a 的红测先固定了四个既有错误：40,056 字符文本与图片组成的混合结果被判定为
`text_extracted=false/needs_budget=false`，不可信文本没有进入统一清洗；Evidence 合同中的
`partial_or_failed` 和 `failed` 又因 MCP transport success 被写成 `success`。最小修复没有增加
提示词或按账号名称写业务硬门，而是增加 operator-owned `deerflow_result_policy`：远端返回中的
同名字段会先被清除，只有本地 `extensions_config` 可将一个 MCP server 声明为
`untrusted_external + evidence + ip-evidence-operation-status-v1`。Evidence Profile 为两个证据工具
绑定该合同，Clean Profile 不绑定；Gateway MCP 管理接口只负责保真往返，不能由普通工具结果
自行提升策略。

在该策略下，sanitizer 对任意已分类 MCP 工具中和 prompt-like 控制文本；输出预算只处理文本块，
同时保留 Image/Resource、artifact、`tool_call_id` 和 `additional_kwargs`；未分类混合内容继续保持
旧行为。领域结果从结构化 artifact 独立映射：账号 `needs_user_input/failed`、视频
`partial_or_failed/failed` 以及 `metadata.truncated=true` 分别形成可追溯的 partial/error/stop 或
summarize 语义，MCP 的 `isError` 和 LangChain transport status 不被伪造。缺少或漂移的合同失败
关闭，来源内容不能仅靠 ToolMessage metadata 冒充受信 Evidence。

边界测试从预期红态收口到 `305 passed`；其中真实 MCP `CallToolResult` 同时包含 40k 恶意文本、
ResourceLink 和 structured content，经过实际转换及 Error→Sanitizer→Budget 中间件顺序后，控制
文本被转义、正文受预算约束、非文本资源和 artifact 保真、领域状态正确。Ruff 与格式检查全绿。
隔离 Evidence Profile 的真实 MCP 发现确认两个工具均携带精确本地策略；使用
`https://v.douyin.com/Q157NhQ4X1Q/` 返回“云沐荟足道官方号”、12 条作品且全部以
`api_author_match` 证明归属。再对精确作品
`https://www.douyin.com/video/7667736489723264970` 深拆，合同为
`ip-reference-video-evidence-v1`、状态 `ok`、`requested=1/completed=1`，原始 source ref、
2,722 字符文本、一个非文本资源、artifact 与结果 meta 全部保留。

真实 Gateway 回放 `1314041e-1dee-4d15-8b69-25db0dafb8f2` 使用实际 `ip-agent` 和同一精确作品，
完成“模型→证据 MCP→模型总结”，两次模型调用分别为 `3,696+70` 和 `5,101+92` tokens，Run
状态 `success`。第一次探针 `6cd367de-846c-4d8c-8fd6-02721d783899` 把测试
`recursion_limit` 错设为 16，在第一次模型调用和工具成功后被 LangGraph 主动终止；将同一测试
参数恢复为 64 后通过，因此不将它伪记为证据链失败。两条精确测试 Thread/Run 均已删除；测试
数据库、Evidence Profile 和用户已登录的抖音浏览器目录未重置。该回放只验收 MF-I5a；内容块
annotations/`_meta`/Audio 和配置撤销由随后 MF-I5b 单独处理。MF-I5 总项仍为“验证中”，因为
视频缓存参数、截断 coverage 和精确作品页面回退尚未解决，也不宣称 Browser/ACP 自动继承合同。

MF-I5b 继续按红绿小批推进。第一组旧实现回归为 `6 failed, 64 passed`：stdio Audio 被字符串化为
普通文本；块级 annotations/`_meta`、结果级 `_meta` 和 ResourceLink 描述全部消失；配置删除后
`_is_cache_stale=false`，旧工具仍可调用。第二组 `4 failed` 进一步证明 HTTP/SSE 仍走第三方有损
转换、Agent 装配在零 enabled server 时绕开 cache、已绑定 stdio 工具可重建已撤销 session，且
Audio 没有体积上限。第三组 `2 failed` 固定了 `isError=true` 在 artifact 构造前抛异常，导致失败
证据再次丢失。扩大回归还抓到未类型化测试替身会被误认成 operator policy；生产边界改为只接受
Pydantic 验证后的 `ToolResultPolicyConfig`，没有在加载器里猜测任意对象。

最小实现建立 `mcp-result-metadata-v1`：协议 annotations、结果/块 `_meta`、ResourceLink 描述和
EmbeddedResource 元数据进入 ToolMessage artifact，不直接进入 provider-facing 内容。该 envelope
显式声明 `credential-redacted-bounded-v1`，递归删除凭证字段、遮蔽值内 secret assignment、去除
URL query/fragment，并限制深度、集合项和字符串长度；因此这里的“保真”是有损且可声明的审计
保真，不是把不可信 `_meta` 原样透传。Audio 保持 LangChain audio block，解码后超过 10 MiB 或
非法 base64 会在模型请求前失败关闭。`isError` 仍保持 transport error，但其脱敏 structured
content/metadata artifact 由错误中间件保留。

stdio、HTTP、SSE 和 WebSocket 统一进入仓库自有 raw-result converter；stdio 保留 Owner/Thread
隔离的持久 session，远端 transport 使用逐调用 ephemeral session，并保留 interceptor header、
callback 和“context manager 吞异常后仍重抛”的既有语义。MCP cache 成为装配可用性的单一权威；
配置从无到有、内容变化、路径变化、禁用、删除或不可读都会改变代次。每个已发现工具携带本地
`server_name + generation`，每次调用在创建/取得 session 前重新核验当前 operator 配置；撤销或
改代后关闭该 server 的 session 并返回明确 ToolException，远端工具不能伪造这一代次。

最终 MCP、Evidence、清洗、预算、错误、测试模式和 session 回归为 `427 passed`；跨 Agent 装配、
ACP、Client、配置热加载和 deferred promotion 为 `214 passed, 1 skipped`；第二轮后端全量回归为
`9088 passed, 71 skipped, 12 warnings`，证明第一轮全量回归暴露的同步包装兼容与测试身份冲突均已
在本批内收口；Ruff/format 全绿。
保留登录态的真实 Evidence Profile 发现两个工具均带同一 operator generation。直接调用精确作品
`7667736489723264970` 返回 `ip-reference-video-evidence-v1 / ok`，内容为 `text + image`，artifact
同时包含 `structured_content + mcp_metadata`。同一真实已绑定账号工具随后只在该探针进程内将
配置路径指向不存在位置，调用在 session 创建前以 `MCP capability was revoked or changed` 拒绝，
session 数保持 `0 → 0`；正式配置文件没有改写。

真实 Agent Run `081d6fe5-65f6-4fef-a4d7-186b1169a771` 只调用一次
`ip_evidence_inspect_reference_videos`，总计 `8,003` tokens。本次平台没有暴露可验证媒体流，最终
回答明确写出“检查未完成/无有效覆盖”和原始 source ref，未冒充完成，因此只算失败关闭路径通过，
不算新的 M1 内容采集成功样本。精确测试 Thread 已返回 200 删除；Evidence Profile、测试数据库和
15 项抖音登录目录未 reset。MF-I5b 不解决正在执行中的远端调用强制抢占，也不覆盖 Browser/ACP；
MF-I5 总项仍等待 MF-I5c 的缓存、coverage 和作品绑定。

MF-I5c 先运行九条行为红测，结果为 `9 failed`，分别证明：同一内容在分析深度、帧数或本地
FFmpeg 构建变化后仍复用同一个 artifact 目录；请求 8 帧只取得 1 帧仍标为
`sampled_frames=completed` 且 item/operation 为 `ok`；MediaKit 明示 `truncated=true` 仍被标为
`completed`，其幂等 token 也不随 MediaKit 构建变化；精确作品链接跳转到另一作品、落入错误页
后捕获无关作品仍被接受；缺少精确作品 API 身份时，页面第一个通用 `<video>` 会被当作目标媒体；
输入合同无法携带预期账号作者，成功结果也没有 request/resolved/observed work id 与 author sec_uid
的三方绑定。上述问题均在生产修改前由
`backend/tests/test_ip_agent_reference_video_integrity.py` 固定；本批不得靠提示词或下游判断掩盖。

MF-I5c 随后只修证据层，不增加编导提示词或经营硬门。抖音视频解析入口现在先冻结目标
work id；请求、短链解析、最终页面和 API 观测必须指向同一作品，API 必须提供非空作者
`sec_uid`，传入账号证据时还必须与预期作者一致。通用首个 `<video>` 回退已删除；错误页、
跨作品跳转、作者不匹配及无法证明精确身份均失败关闭。成功证据显式携带
`requested_work_id`、`resolved_work_id`、`observed_work_id`、`author_sec_uid` 和验证方式，
合同自身再做跨字段一致性校验。

本地工件缓存升级为“完整内容 SHA-256 + 完整分析规格 SHA-256”，规格同时绑定分析深度、
帧数与时间点、合同/流水线版本及 FFmpeg、FFprobe、MediaKit 二进制 SHA-256。精确命中前会
复核 manifest 和每个工件哈希；篡改或不完整产物不会成为命中，生成过程使用同键文件锁、
临时目录和原子替换。MediaKit 幂等 token 同样由内容、能力参数、流水线和完整二进制版本派生。

视频合同因 coverage 语义发生破坏性变化，升级为 `ip-reference-video-evidence-v2`。固定的
`CoverageRecord` 现在区分 `completed/partial/failed/unavailable/not_requested`，记录观测范围、
请求数、实得数、截断和原因码；item、完成数、顶层状态与截断均由子 coverage 机械推导。
机械模式不把未请求的供应商能力算失败；完整模式缺少已请求能力则只能 partial。FFmpeg 场景
命令失败不再读取 stderr 中的伪时间点，成功零场景是有效零观测，超过上限则显式截断。
模型先看到有界身份/coverage 摘要；大体积供应商原始 payload 只保留在结构化 artifact 中。
历史 v1 仍能由结果策略识别，但暂停的 M2 v1 冻结样本不得冒充当前证据，M2 解冻前必须按
v2 重采或显式迁移。

最终完整性文件共 `19 passed`；Evidence/MCP 定向回归为 `43 passed`，IP Agent、Capability MCP
及 MCP 横向回归为 `313 passed`。本批最终后端全量结果为
`9109 passed, 71 skipped, 12 warnings`；台账/安装合同守卫为 `8 passed`，前端
`eslint + tsc --noEmit`、Ruff/format 和 `git diff --check` 全绿。

真实验证分开记账：保留登录态直接检查作品 `7667736489723264970` 时，一次取得三方一致 work id、
作者匹配、`8/8` 帧及 `api_work_and_author_match`，合同为 v2；同一作品第二次受平台响应变化影响，
按新合同失败关闭，没有沿用旧缓存或伪造 coverage。另以真实 FFmpeg 生成的 2 秒本地视频连续
检查两次，第二次为精确 cache hit，分析规格、manifest 与 8 个帧哈希全部一致。主账号页面本轮
能确认“云沐荟足道官方号”及 `sec_uid`，但作品清单返回 0，故只记外部平台部分失败。

两次真实 Gateway Agent 回放均只调用一次视频证据工具；平台未暴露可验证媒体时，最终回答明确
说明没有完成检查。两次总 Token 分别为 `8,772` 和 `8,153`，只证明失败关闭路径，不算 M1 的
公网成功验收。对应测试 Thread/Run 已删除并复核为 `0/0`；测试数据库未 reset，抖音登录目录仍为
15 项。独立复核随后发现模型可见语义内容、coverage 跨字段一致性、历史 v1 提升与响应来源校验
仍有阻塞缺口，因此上述结果只是阶段基线，MF-I5c 与 MF-I5 均退回“验证中”；M1 仍需稳定公网
成功链和既定异类样本后才能重新判定。

### MF-I5d：MediaKit 底座边界调整

2026-08-02 重新核验火山引擎 AI MediaKit 的产品工具表、官方 CLI/Skill 和仓库固定源码后，
确认字节已经提供了不应继续自研的媒体内核，但没有提供 IP 业务本体、平台账号/作品归属、
内容寻址或证据—推断分层。仓库已固定官方 `volcengine/mediakit-cli` 提交
`279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0`，项目二进制为
`0.2.0+ip-agent.279e5bb`；五个上游 Skill 与源码版本一致，仅做 DeerFlow 权限字段翻译，
因此不安装第二套全局 CLI 或 Skill。

边界固定如下：

| 责任 | MediaKit | Evidence MCP / IP Agent |
| --- | --- | --- |
| 媒体原子能力 | 元信息、ASR、OCR、场景/剧情、高光、剪辑、转码、增强和结果交付 | 不再自研同类算法；只做固定版本的薄适配 |
| 平台与身份 | 不负责账号发现或作品归属 | 精确链接、账号/作品 ID、作者绑定、授权浏览器和失败关闭 |
| 信息完整性 | 官方上传和查询均不返回可验证内容 SHA-256；CLI 上传缓存只按路径、大小、mtime | 下载冻结快照、SHA-256、请求摘要、coverage、限制、调用收据和凭证隔离 |
| IP 业务 | 不拥有 Subject、Objective、Direction、Mechanism 或 LearningDecision | 对标因果、IP 方向、原创编导综合和发布反馈闭环 |

首个零成本切片 `MF-I5d-MK1` 已按红绿循环完成。新增内部
`mediakit_adapter.probe_video_metadata`，只把已冻结的本地快照交给官方 CLI 的
`--local video probe-video-metadata`；每次运行使用临时 HOME/输出目录、项目 FFmpeg 优先 PATH、
无 API Key 的精确环境白名单，并校验官方 Schema、源文件前后 SHA-256、返回文件大小和结构。
失败时旧 ffprobe 只作为显式回退，回退原因进入被分析规格哈希绑定的本地收据，不把供应商错误
原文交给模型。Agent 工具、提示词和 v2 Evidence 外部合同没有变化。

真实 A/B 使用仓库 8 秒 MP4，源 SHA-256 为
`90a3e6e61b345e3e6887de14ea7623d210a5000dc2f5545cabaeddb38c154644`。官方 MediaKit 与
项目 ffprobe 对 duration `8.0`、`1280×720`、`24fps`、H.264、AAC 音轨、容器和
`2,449,778` 字节逐字段完全一致；官方 Schema/结果摘要分别为
`4f922dbf25ce58863a155837e636cc6c8daaf3ce7df698f3100bf287b1d0588a`、
`c1ece30960a121a114e61bcd9244d3b548bfa837f40b5140ca732b746130a464`。随后通过完整
`inspect_reference_videos` 机械路径取得 `operation=ok/item=ok`、`4/4` 帧、零场景边界和空限制，
流水线为 `mediakit-evidence-v3`，收据同时固定 FFmpeg、FFprobe 与 MediaKit 二进制摘要。
新增 7 项适配器红绿测试与 93 项既有账号/视频证据回归合计 `100 passed`，Ruff 全绿。

`MF-I5d-MK2` 的模拟验证内部调用器切片已完成，但仍处于“验证中”。调用器合同只接收
Evidence MCP 已下载、私有封存并计算 SHA-256 的同一本地快照，并按官方源码的本地文件自动上传路径
组装固定版 CLI 调用；argv、临时环境、任务终态和失败关闭已通过模拟 subprocess 验证，真实云端上传、
任务提交和结果尚未验收。旧的“二次抓取可变公网 URL”路径已删除。每个视频请求建立独立 `0700`
临时 HOME，四个能力只在该请求内共享 CLI 状态，请求结束即销毁，不跨 Owner、密钥或视频复用。

审计还找到一个官方 CLI 轮询细节：`poll-complete=true` 会进入无界循环并完全忽略
`max-poll-attempts`。新适配器因此不使用 CLI 自动轮询。每个能力的提交子进程最多 180 秒，随后独立轮询阶段
最多 300 秒、每次查询子进程最多 30 秒且总共最多 80 次；四能力目前顺序运行，尚无跨能力的整请求总截止。
只接受同一 `task_id` 的 `completed`，失败终态、
未知状态、错任务号、超时和达到次数上限均失败关闭。调用前后重新校验本地 SHA-256；收据只留
CLI/请求/结果/任务号的摘要，密钥、HOME、本地路径、原始任务号、file id、上传 URL 和原始包装层
不进入 Evidence 或模型。

第二轮独立复核又用恶意 camelCase 供应商输出抓到三个细节漏洞：任务号/文件号/路径字段可绕过
snake_case 清洗、收据结果摘要没有绑定最终对模型暴露的 payload，轮询上限存在一次 off-by-one。现已改为
严格媒体语义字段白名单，递归删除 camelCase/snake_case 运行 ID、URL、路径、密钥回显及字符串中的已知敏感值；
`result_sha256` 必须与最终 Evidence payload 的规范 JSON 完全一致，任何二次改写均整阶段失败关闭；轮询实际次数与声明相等。

由于官方服务不回显内容摘要，成功结果固定标记为
`sealed_local_snapshot_provider_unattested`，coverage 只能是 `partial`，并携带
`PROVIDER_CONTENT_HASH_NOT_ATTESTED`；不得偷换为供应商已证明输入哈希。隔离测试实现仅预留了内部授权 seam，
正式 Evidence MCP 当前固定不授权：只配置 `MEDIAKIT_API_KEY` 仍是零云任务并返回
`unavailable_provider_execution_not_authorized`。这个私有布尔值只是单测 seam，不是成本账本、签名回执或服务器准入服务。

成本准入独立审计同时发现旧视频制作预算允许调用方提交
`paid_calls_require_explicit_approval=false`，且历史未审批 active reservation 可在回放或 provider request 时绕过。现在新建任务
一律由服务器持久化为 `true`，`false`/`null`/`0`/字符串均不能关闭；历史 `false` 任务的精确幂等读仍可回放，
但新预留、旧预留回放和真实 provider request 均重新校验匹配的人工批准。未调用供应商的旧预留可安全释放；已知付费云供应商也不能
把请求谎报为 `free`。这只修复现有视频执行边界，不等于 Evidence 已有通用成本准入。

随后真实复验又发现一个信息入口偏差：测试态 FFmpeg 能从仓库根 `.deer-flow/toolchains` 找到，
但 MediaKit 只搜索后端状态目录和错误层级的项目目录，导致已经固定安装的官方 CLI 被误报为不存在。
该问题已先用失败测试复现，再统一补入与 FFmpeg 相同的仓库根候选。修复后的 8 秒真实 MP4 本地探测
重新得到 `8.0` 秒、`1280×720`、`24fps`、H.264、有音轨和 `2,449,778` 字节；源、CLI、Schema
及结果摘要分别保持为 `90a3e6e6…c154644`、`368129db…657a4db`、`4f922dbf…b1d0588a`、
`c1ece309…30a464`，说明路径修复没有改变证据内容。

本切片现有 21 项 MediaKit 适配器测试。付费提案、决策、未来运输合同与模型边界共有 50 项定向测试；
MediaKit、Evidence、迁移、仓库、Gateway、测试 Profile、数据生命周期、既有视频预算及暂停的 M2
仪器合并回归为 `226 passed`。正式数据生命周期验收为后端 `8 passed`、前端 `3 passed`，既有视频
成本验收为 `35 passed`；Evidence 付费卡前端为 `9 passed`，`eslint + tsc --noEmit` 与 Ruff 通过。

`MF-I5d-MK3` 只完成“服务器登记付费提案”，没有越级实现真实执行：

- 新增 append-only `personal_ip_paid_call_scopes/events`，迁移 `0022` 建表、`0023` 将提案
  `origin_run_id` 与未来一次消费的 `execution_run_id` 分开；Owner、Thread、工具参数、供应商、能力、
  源 SHA-256、阶段摘要、供应商请求摘要、价格状态和过期时间均进入不可变请求摘要；原始 JTI 不落库；
- 未知价格保持 `maximum_amount_micros=null/price_status=unknown`，仓库、HTTP 和前端三层都不可批准，
  不能把“不知道价格”伪装成免费；未知实际费用也只能进入 `reconciliation_required`，不能释放预留；
- Evidence Profile 的受信 bridge 先验证严格 v2 Evidence，再只为“单条视频、有音轨、ASR 未授权”登记
  一项提案；多视频因一个隐藏 grant 无法唯一选择而不出提案，缺少显式 runtime Owner 时零落账；
- 提案卡只存在于 `mcp-result-metadata-v1` 的 artifact 元数据，不进入模型可见文本或严格 Evidence
  `structuredContent`。bridge 先删除来源伪造的保留键，再把可信键置于有界元数据首位；前端只接受精确
  `ip_evidence_inspect_reference_videos`、标准清洗合同，并在展示详情或按钮前用 Owner/Thread GET 真值复核；
- 测试 Profile 精确声明该 bridge 为 required interceptor；导入、构造或 MCP server 装配失败会终止加载，
  不再 warning 后伪装为“Evidence 能力已启动”。原地刷新保留了测试数据库和抖音登录 Profile，真实运行时
  发现结果为两个且仅两个工具：账号采集与视频深拆；
- 跨 run 审批不可达的原设计已纠正：R0 只记录 origin，未来 R1 在原子预留时抢占 execution run；两个 R1
  并发只能一个成功，后续放行、释放、结算与重放都必须匹配同一 R1。

2026-08-02 复核官方公开资料时，[MediaKit 语音转字幕能力](https://www.volcengine.com/docs/6448/2381968?lang=zh)
与[提交任务 API](https://www.volcengine.com/docs/6448/2386124?lang=zh)仍未公开该 CLI 路径可机械绑定的计费 SKU、
取整规则和单次最高金额。[Seed-ASR 模型计费](https://www.volcengine.com/docs/6581/2389072?lang=zh)
公开的小时价属于方舟模型服务，不能据此推定
MediaKit 的 `asr-subtitles` 使用同一结算项；营销资源包价格也不是单次任务的可验证最高价。因此价格状态
继续保持 unknown，不能为了跑通演示自行换算或批准。

本批仍没有发起任何付费云端任务，也没有把 approve 写成“已经执行”。剩余阻塞是实质性的，不用提示词
掩盖：官方 MediaKit 新 ASR 的可核验单次最高价尚未取得；Gateway 尚无批准后的 R1 continuation、
resolver/signer；独立 stdio MCP 尚无真实 verifier/admission 通道；客户端配置别名 `ip_evidence` 与 MCP
内部身份 `ip-agent-evidence` 还需双重绑定；深层 source/stage/provider-request/金额必须在同一事务全部
匹配后才能 `reserved → admitted`；旧 `provider_execution_authorized: bool` 仍只能作单测 seam，绝不能让
一项 ASR 批准扩大为 OCR、场景和剧情四项调用。因此 MK2/MK3 均保持“验证中”。下一最小切片必须先取得
可审计价格上限，再实现 capability-specific 的 R1 原子准入；只有用户明确批准后，才对一条短真实视频
只跑一次 ASR 并结算。视频理解智能策略、剧本还原和 Vibe Editing 等 API-only 能力仍须逐项真实验收，
产品页名称本身不算现役能力。

`MF-I5d-MK4` 于 2026-08-03 在用户明确同意真实付费验证后继续推进，但仍只属于隔离 Evidence Profile，
没有提升为正式默认能力。MediaKit API Key 通过标准输入写入测试状态的私有 Secret 文件，目录权限为
`0700`、文件权限为 `0600`；Key 不进入仓库、扩展配置、命令参数、模型上下文或 Gateway/Frontend 日志。
测试状态继续保留原数据库、抖音登录 Profile 与 6 份可恢复快照。

由于官方 `asr-subtitles` 仍不提供可核验的单次报价上限，新增的 direct-pay 不是伪造供应商报价，而是
Owner 明确接受的一次性本地风险准入限额。迁移 `0024_personal_ip_paid_call_operator_cap` 将
`operator_capped` 与 `quoted` 分开；完整状态机为
`requested → approved → reserved → admitted → reconciliation_required → settled`。下一次调用只有在
Owner、Thread、execution run、工具参数、单个视频 SHA-256、ASR stage、provider request、币种和限额
完全一致时才取得 HMAC 单次 grant；grant 只能授权 ASR，不能扩大为 OCR、场景分割或剧情理解。
Key 缺失不消费 Owner 批准；grant 一旦消费，下载失败、MCP 异常、取消、失败 item、非法结果或缺少收据
也必须进入 `reconciliation_required`，不能永久停在 `admitted`。客户 API/前端合同升级为
`ip-agent-evidence-paid-call-request-v2`，显式区分 `provider_quote`、`local_risk_limit` 与 `unquoted`；
本地限额显示为“本地准入限额”，并明确说明不是服务商报价或账单封顶。

真实云端 ASR 使用仓库已有 3.648 秒内部生成视频，源 SHA-256 为
`f338260bc08f2d6d85b22cb4a9cf1a2f2a2ab41ad914d85ecd85ea6ee0340fcc`。第一次调用证明供应商已完成任务，
同时暴露真实返回字段为 `subtitle_text`，旧语义白名单因此丢失台词；该轮判失败，不以 provider success
冒充产品通过。适配器随后增加 `mediakit-cloud-semantic-allowlist-v2`，将规范化版本纳入 stage digest，
并对供应商结果 URL 增加 HTTPS、官方域名、公共 DNS、重定向、时限、大小与内容类型边界。

第二次真实调用通过，ASR stage SHA-256 为
`df71c9b4f5df0929f0d4d72e9dda9c09ae35b6250278972e8459c5aa31a11b05`，最终脱敏结果 SHA-256 为
`02135252533ab936a382360d6d3757aafcb8de5acbbd227b855d2ae635638dff`。返回两段：
`0.44–2.72s / 每一次生成都有回值 / confidence 0.9775220685535007` 与
`2.72–3.842s / 也能被验证 / confidence 1`。已知原声中的“回执”被识别成“回值”，因此链路技术通过，
但该文本只能作为带置信度的 ASR 证据，不能自动纠正或用于逐字精确引用。供应商未返回实际费用字段，
本轮状态必须保持 `reconciliation_required`，不得伪造结算金额。

真实测试库启动还抓到一项单测未覆盖的迁移兼容问题：早期测试 Profile 的 `0023` 表缺少新列和新约束名，
旧 `0024` 因强行删除不存在的约束导致 Gateway 无法启动。迁移现会识别该旧形态：表为空时原地补齐并
保留其余测试状态；存在旧付费行时因无法补造不可变绑定字段而停止，要求先做 Owner 备份。修复后测试库
已原地升级到 `0024`，Gateway `/docs` 与 Frontend 均返回 HTTP 200，Key 内容未出现在两端日志。

本切片最终定向回归为后端 `102 passed`、前端付费合同 `10 passed`，Ruff、ESLint 与
`tsc --noEmit` 全绿；迁移另外覆盖“当前新库、空旧库原地升级、非空旧库停止”三条路径。此结果只证明
ASR 原子能力、准入运输、真实供应商结果归一化和故障收口；尚未完成一次真实聊天中的
“R0 提案 → 页面批准 → R1 Agent 续跑”整环，也没有验证 OCR、场景、剧情或 IP 编导综合，因此
MF-I5d 继续保持“验证中”；全局 M1 仍按主要矛盾序列保持“待转化”。

#### MF-I5d-MK5：MediaKit 能力边界审计与防腐层止血

2026-08-03 按“系统论 + 本体论 + 信息论 + 控制论”重新审计官方产品文档、固定 CLI 源码、
五个上游 Skill、实际二进制、MediaKit MCP 表面和当前 Evidence 适配层。结论不是“MediaKit
已经把视频理解做完”，而是：它可以成为可替换的媒体 Sensor/Effector 内核，但不能成为账号身份、
内容事实、传播因果或 IP 决策的权威。

官方表面必须分开记账：产品目录约 63 项，固定 CLI `0.2.0` 为 40 条命令，当前官方 MCP 源码为
39 个云工具，MCP 文档只列 13 项，仓库附带 5 个 Skill；“100+”仍是产品能力池或规划口径，不能
写成当前 Agent 合同。固定 CLI 的 40 项由 18 个本地/云端双模式异步命令、1 个仅本地下载命令、
15 个仅云端异步命令、5 个云端同步图像命令和 1 个任务查询命令组成。完整工具名、模式、语义类别、
限制和成熟度现统一落在 `product/volcengine/capabilities.yaml` v2；默认状态为 `inventory`，
`product_promoted` 列表仍为空，Key 存在不等于能力启用或付费授权。

四类对象从此不得混写：

| 对象 | MediaKit 例子 | 允许进入的结论层 |
| --- | --- | --- |
| `Fact` | 本地源文件 SHA-256、已验证账号/作品归属 | 事实，但由平台适配器和 Evidence 封存，不由 MediaKit 宣称 |
| `Observation` | 元信息、ASR、OCR、场景边界 | 带覆盖、置信度和误差的观察；未检出不等于不存在 |
| `ProviderInference` | 剧情线、高光、画面/质量评分 | 供应商解释，不得写成传播因果或“机制已验证” |
| `ArtifactCandidate` | 剪辑、增强、擦除、抠图、高光成片 | 带输入/输出哈希的派生候选，不得回写成原始证据 |

源码审计确认了此前容易造成整条链偏转的边界：`--local/--cloud` 实际是优先顺序而非硬隔离，
可能向另一端降级；上传缓存仅绑定绝对路径、大小和 mtime，TTL 30 天，不绑定 SHA-256、Owner、
Key、endpoint 或 capability；`poll-complete` 无界；ASR/OCR/场景/剧情等 `file` 输出 Schema 只描述
`local_path`，不描述真实终态语义；本地 `fetch-file` 缺少产品级 SSRF/大小/类型边界；源码声明的
资源上限没有完整执行；上游只带极少安装/根命令测试，没有媒体算法或云合同回归。因此上游 5 个
Skill 继续只作隔离参考，不能给 Agent shell 后直接执行。

版本与外部边界也已固定：官方在 2026-04-24 将普通 MediaKit 服务域名从
`amk.cn-beijing.volces.com` 改为 `mediakit.cn-beijing.volces.com`，旧域名只承诺临时兼容；适配器
现显式使用新域名并把 endpoint 纳入 stage/provider-request 摘要。视频理解 Chat API 的
`amk-ark.cn-beijing.volces.com` 是另一合同，未混入当前 CLI。该接口不是普通 ASR/OCR 原子工具，
而是火山方舟 Chat API 的视频前处理封装：MediaKit 负责抽帧和序列化，再由指定 Ark 模型回答问题；
调用者必须同时提供独立的方舟 API Key 与 MediaKit API Key，服务端按
`Bearer {ArkKey}/{MediaKitKey}` 组合，且请求体必须显式填写方舟模型 ID。本轮 Q157 成功调用使用
两把不同的真实凭证和固定模型 `doubao-seed-2-0-pro-260215`，没有把 MediaKit Key 冒充模型 Key。
公网视频 URL 输入最高 5 GB；该上限不能外推到火山方舟另一条直连接口支持的 Base64 输入。
MediaKit Chat 的 `fps` 范围为 `0.01–5`、默认 `1`，并同时受 `max_frames`、
单帧 `max_pixels` 与约 200k 内部 Token 上限约束。它能提供长视频语义、时序分析和总结，但默认返回
仍是模型文本，并不保证逐帧覆盖、时间戳证据或事实正确。因此本轮将其单列为
`provider-semantic-observation / contract_verified / not-integrated / exposure:none`，不计入 CLI 40 项，
也不再用“MediaKit 只是 ASR/OCR”低估它；接入前必须用固定结构化问题和人工标注样本测覆盖率、幻觉、
重复性，并把重要断言与封存帧、ASR、OCR 交叉核验。产品目录中的“视频理解智能策略”是又一独立
API；其合同现已单独核验，不得偷换成 Chat API 或直接进入 Agent。

官方普通上传上限 5 GB、上传源保留
30 天、普通任务结果/下载链接通常保留 24 小时；任务完成后必须立即下载、哈希和封存，临时 URL
不得成为证据地址。官方同时公开了 ASR `0.03 元/输入分钟`的单位价，但没有给每次任务的 provider
quote，也不在普通结果返回实际人民币费用，因此旧台账中“没有可核验单次最高价”应精确理解为
“有单位价、无供应商单次报价和实际结算字段”；本地风险限额仍不能伪装成账单封顶。

固定源码现在增加 `VENDORED_VERSION.json`：上游 commit、Git tree、119 个保留源码文件、唯一排除的
预编译 `mediakit`、40 条命令目录及许可证文件摘要全部进入校验。`scripts/mediakit_source.py` 在构建前
校验完整源码树，在 doctor 时校验运行二进制 `--help-full`；任何新增、删除、改名、内容或目录漂移
直接失败。上游根 `LICENSE`、`package.json` 和 Skill 均写 MIT，但 `Open Source Notice.txt` 又写
产品 Apache-2.0，该矛盾已经记录为发行前必须向上游澄清的许可证阻塞，不再静默忽略。

本轮边写边测还抓到并修复了两个现行 P0：真实 adapter 收据中的 normalization、transport 和可选
结果文件元数据此前会被 `extra=forbid` 的 Evidence 合同拒绝；真实 ASR 的 `subtitle_text` 及
coverage 的 `observation_scope` 又会在模型摘要丢失。合同现严格保留这些字段，文件 transport 必须
同时携带 SHA-256、整数大小和受限 Content-Type，inline 禁止伪造文件元数据；模型可见摘要能看到
两段真实形状的字幕、时间和观察范围。`inspect_reference_videos` 的 MCP annotation 也从错误的
read-only/idempotent 改为非只读、非幂等但非破坏性，因为它会写封存制品且经批准后可能上传并付费。
付费卡新增“媒体会上传至火山引擎 MediaKit”的明确披露；供应商 `client_token` 改为 Owner + call +
stage 的不可逆摘要，避免不同 Owner 的同内容任务误共享账户级幂等结果。

定向回归中，MediaKit adapter、严格视频 Evidence、模型投影、付费 bridge、Owner 级 provider 边界和
Evidence MCP 合计 `108 passed`；源码/目录/能力策略和 doctor 凭证语义另为 `9 passed`，Ruff 对相关
文件通过。该阶段没有新增付费调用；随后 MF-I5d-MK6 的隔离供应商能力审计另执行了两次
operator-run canary，结果见下文及固定回执文件，仍未进入产品 Agent 调用链。

尚未通过的控制面必须先于下一次付费真实测试：供应商异步任务提交后的原始 `task_id` 还没有以加密、
Owner 隔离、可恢复的状态持久化；若进程在提交后超时或崩溃，任务可能已经计费却无法续查。故 ASR
虽然保留“窄样本 real-sample verified”，执行状态标记为暂停新增付费 canary；先建立
`proposed → approved → reserved → submitting → submitted → running → terminal` 的持久控制状态，
再完成真实聊天 `R0 → 页面批准 → R1`。之后按带人工真值的元信息、ASR、OCR、场景切分逐项验收；
剧情线只作为第二路 `ProviderInference`，不默认用于普通 IP/品牌对标。MF-I5d 继续为“验证中”，
M1 仍为“待转化”，
不得提前进入 M2 编导综合。

#### MF-I5d-MK6：MediaKit 全产品替代性审计

2026-08-03 继续按官方当前产品目录、开发指南、API、计费页、固定 CLI/MCP 源码和本地产品实现逐项
审计“是否应放弃自研”。结论是：MediaKit 应替代大量媒体算法和通用执行代码，但不应替代产品的
编辑导演、时间线本体、程序化视觉和控制闭环。此前把它只描述成 ASR/OCR/FFmpeg 底座同样过窄。

必须区分四套容易混淆的合同：

| 合同 | 实际能力 | 关键边界 |
| --- | --- | --- |
| [视频理解 Chat](https://www.volcengine.com/docs/6448/2222229) | 固定模型、`0.01–5 fps` 抽帧、URL 最大 5 GB | 不理解音频，只返回模型回答；不是逐帧事实 |
| [视频理解智能策略](https://www.volcengine.com/docs/6448/2551133) | 最多 10 条、单条 2 小时；可自动选模型、抽帧和音频路径，最多 1000 帧 | 手动 `fps` 才是 `0.2–5`；音频关键词可覆盖档位，复现性更弱；0.01 元/输入分钟加 Ark Token |
| [智能剪辑 Vibe Editing](https://www.volcengine.com/docs/6448/2549864) | 自然语言驱动内容选段、多轨裁剪/变换/特效/转场/声音/字幕和云渲染 | REST 只返回 MP4/MP3 artifact，不返回 EDL、轨道、操作收据或工程；交互式 API/Web SDK 仍写“未来提供” |
| [剧本还原](https://www.volcengine.com/docs/6448/2479866) | 把合格的真人短剧、长剧或电影逆向为场景、镜头、人物、对白等结构化 JSON | 要求硬字幕和同分辨率；明确不适合动画、纪录片、广告、直播；3 元/输入分钟；不是创作剧本工具 |

[智能语义切片](https://www.volcengine.com/docs/6448/2558632) 另按画面、语音和叙事结构返回切点，单条
不超过 3 小时，价格为 0.03 元/输入分钟；结果只有切片时间轴，没有逐段文本或语义标签，所以它是
剪辑 Observation，不是选段决定。[解说视频](https://www.volcengine.com/docs/6448/2479867)、短剧高光、
影视拆条和剧情线均为领域工具，只能在输入满足短剧/影视合同后启用，不能成为普通个人、品牌、产品
IP 或 MV 对标的默认路径。

替代边界固定如下：

| 现有能力 | MediaKit 可替代 | 必须继续由产品拥有 |
| --- | --- | --- |
| `video-use` | 元信息、句段级 ASR/OCR/场景/音频传感器；裁切、拼接、混音、字幕、转码、增强等执行后端；Vibe 粗剪候选 | 对话式素材理解、剪辑策略确认、强类型 EDL/Timeline IR、逐词时间戳与词边界证据、切口补偿、逐切口复查、用户迭代、工程状态和独立 QA |
| HyperFrames | 简单文字、图片、预设转场和普通云合成 | HTML/CSS/SVG、任意程序化构图、确定性 seek/逐帧捕获、变量/组件、源码和检查 |
| Remotion | 简单素材合成可被 MediaKit 或 HyperFrames 覆盖 | React 特有的组件化逐帧工程；仅在真实产品仍需要时保留兼容路径 |
| 图片/音频自研 | 基础编辑、智能裁剪/扩图/擦除/抠图、质量观察、商品场景图、人声分离、端点、转码等通用算法 | 品牌视觉意图、版式系统、素材权利、候选选择、输入输出哈希和最终 QA |

这意味着 `video-use` 不作为一包不受控 helper 进入生产，而应提炼为 provider-neutral 的
`EditingDirector + Timeline IR`；MediaKit 位于它下面。Vibe 只生成可撤销的粗剪候选。真实媒体剪辑
目标路由是 MediaKit 原子 API 或受控本地 FFmpeg 处理真实媒体，复杂程序化画面由 HyperFrames
承担；这不是当前仓库已完成的切换。当前 HyperFrames 只是未注册为现役 Agent 工具的固定模板，
Remotion 仍有现役工具，两套模板都默认静音源视频。只有 HyperFrames 通过同一程序化场景 golden
suite、旧项目迁移可验证后，Remotion 才能退出默认路径，而不是现在凭文档删除。
现有 `video-use` helper 会从 Skill/CWD `.env` 取凭证、整段上传第三方转录、以同名 JSON 而非源哈希缓存，
并允许未校验 EDL 引用任意绝对路径和 FFmpeg filter；这些实现不得直接注册为 Agent 工具，保留的是
它的“先理解素材和目标、确认策略、按词剪、逐切口复查、自然语言迭代”的方法。

本轮零成本真实 A/B 同时否定了“官方 CLI 本地裁切可直接满足 `video-use` 精剪”的假设：对 SHA-256
`f338260b…340fcc` 的已封存 3.648 秒 MP4 请求 `1.00–3.00s`，固定 CLI 本地计划采用 input seek +
stream copy，实际输出
`2.166016s`；项目 FFmpeg 精确重编码参考为 `2.000000s`。因此当前本地 `trim-video` 适合快速无损粗裁，
不适合词边界或逐帧精剪；提升前必须增加精确渲染路径并用口播切口 golden suite 验证。

仓库自身还存在比供应商选择更先验的断层：现有时间线合同声明 video/dialogue/music/subtitle、音量和
转场，最终渲染器却只读第一条 video 轨、忽略其余轨道和参数，并用一条最新配音覆盖全片；当前
HyperFrames/Remotion 固定场景又都把源视频静音。若不先建立同一份真正可执行的 Timeline IR，换任何
供应商都会把工作台里“已保存”的修改丢在最终 MP4 之外。

用户已经明确允许付费验证。本轮没有把未接入的能力冒充产品链路，而是用火山官方 5.067 秒样片执行
两个隔离、可人工核对的 operator-run canary。视频理解 Chat 在 `fps=5` 下正确识别拳击、两名初始
人物及黑白上衣，但把第三人首次清晰出现写成 `3.6s`；逐帧人工标注为 `3.4s`，时间误差 `0.2s`。
该请求消耗 `7912` 输入、`873` 输出（含 `764` reasoning）Token，证明“能看懂大类”不等于“能给
精确剪辑点”。Vibe 按自然语言将同一素材裁成 `0–2s`、720p/30fps，机械复核得到视频和音频均从
`0` 开始且恰为 `2.000s`，三帧抽检未见额外文字或转场；发布价折算的名义合成费约 `0.001 CNY`，
但任务没有返回实际人民币结算字段。它只返回最终 MP4 和说明，仍无 EDL/可编辑工程。完整脱敏回执、
请求/任务/产物哈希和本地裁切 A/B 固定在
`product/research/ip-agent/mediakit/2026-08-03-capability-canaries.yaml`。

这两次是人工保留提交回执和任务引用的研究调用，不解除产品控制缺口。2026-08-03 已完成
Remux 的持久化 submit/query 恢复切片：paid-call scope 在付费 POST 前加密保存精确提交投影，
POST 返回后追加保存任务身份与响应摘要；`submitting` 只能取得一次原子重放权，
`submitted/running/terminal` 只按既有任务号 GET，不重新申请上传地址、不重新上传。查询或进程中断
保持原任务可恢复，不提前结算成死路；Owner 已知 scope 使用精确双键读取，不受历史 500 条批量窗口
影响。实际 PUT 字节还会边流式计算哈希和长度，并在付费 POST 前与封存源比对，关闭同尺寸竞态替换。
组合回归 187 项通过，独立复核 68 项通过且无 P0/P1；这只允许进入单 Owner、单任务、低成本
真实 paid canary，不等于 Evidence MCP 或产品 Agent 已接通。Smart Strategy 只解冻为隔离对照
canary；Vibe、语义切片和剧本还原继续冻结。产品提升列表仍为空。

2026-08-03 根据官方[视频工具计费](https://docs.volcengine.com/docs/6448/2486473?lang=zh)
和[大模型处理工具计费](https://docs.volcengine.com/docs/6448/2486472?lang=zh)重新校正语义：
Remux 按输出时长的毫秒级累计值计费，公开公式为“输出分钟 × `0.21875` × `0.032`”，
即 `0.007 CNY/输出分钟`；Q157 的 `70.867s` 按目录价计算约为 `0.008268 CNY`。
这是可核验的公开费率和估算，仍不是供应商为单次调用签发的 `provider_quote`；折扣、资源包抵扣及最终
账单金额只能在结算后核对。直接 Video Understanding Chat 不收 MediaKit 额外媒体处理费，但按具体
火山方舟模型的 Input/Output Token 收费。因此当前 R1/R2 仍使用相互独立、默认关闭的
`operator_capped` 准入：R1 同时展示公开费率估算，R2 必须冻结具体模型和 Token 单价；
任何一者都不得写成 `quoted/provider_quote`。

同一份官方计费页还揭示了此前只登记、未进入本轮选型的独立能力：
[视频理解智能策略](https://docs.volcengine.com/docs/6448/2551133?lang=zh)另收
`0.01 CNY/输入分钟` 的 MediaKit 预处理费，**同时**继续按实际 Token 收取方舟模型费；这
`0.01` 不是总价。官方[提交 API](https://docs.volcengine.com/docs/6448/2552748?lang=zh)
是带 `client_token`、`task_id` 和任务查询的异步合同，支持 `scene=editing`、音频分析和最多
1000 帧，并返回总输入时长、生成内容与 Token 用量。它与当前同步 Chat 不是一个端点，也不能共享
“MediaKit 处理免费”的结论。其任务结果只返回汇总 Input/Output Token，不拆分音频与非音频 Input；
而 Lite/Mini 的两类输入单价不同，所以开启音频时不能凭该回执给出一个伪精确的方舟价格，只能给有
依据的区间或标记为待账单核对。目录价只用于准入估算；资源包抵扣、折扣和最终现金账单仍需结算证据。
固定 CLI `0.2.0` 及 2026-08-03 的上游 HEAD 均未注册该路由，因此本轮只写独立、限域的 API
adapter/canary，不通过通用 shell 或伪造 CLI 命令接入。

R2 的公开价也已按官方[模型价格](https://docs.volcengine.com/docs/82379/1544106?lang=zh)
冻结为 `doubao-seed-2.0-pro` 标准在线推理的三档价格：输入长度不超过
`32,768/131,072/262,144` Token 时，
输入分别为 `3.2/4.8/9.6 CNY/百万 Token`，输出分别为 `16/24/48 CNY/百万 Token`。
固定版本 `doubao-seed-2-0-pro-260215` 的模型族映射由
[方舟模型版本接口资料](https://api.volcengine.com/api-explorer/?action=ListFoundationModelVersions&groupName=%E5%9F%BA%E7%A1%80%E6%A8%A1%E5%9E%8B&serviceCode=ark&version=2024-01-01)复核。Q157 的实际
`37,501` 输入、`3,812` 输出落入第二档，目录价估算为 `0.271493 CNY`；与 R1 相加约
`0.279761 CNY`。该估算把 provider 返回的 `completion_tokens`（已包含 reasoning）只计一次，
不启用缓存折扣，仍不冒充最终账单。纯价格合同与现有 Chat 适配器定向回归为 `24 passed`。

价格审计同时把 R2 的付费边界定位出来：旧请求发送 `max_tokens=3000`，但 Q157 实际
`completion_tokens=3812`，其中 `reasoning_tokens=2309`；该字段没有封住“推理 + 可见回答”的总量。
适配器现已改用 `max_completion_tokens=3000`，显式请求并回验 `service_tier=default`，两者及固定模型、
问题、采样参数、Schema 都进入请求摘要。2026-08-03 用官方 5.067 秒拳击样片执行一次新的隔离付费验证，
供应商回包确认 `service_tier=default`，`completion_tokens=2929`（含 `reasoning_tokens=1911`），没有超过
冻结上限；输入 `8382`、总计 `11311` Token，用时 `60.106s`。按第一档公开目录价估算为
`73,687 micro-CNY`（`0.073687 CNY`），仍没有供应商实际人民币账单字段。脱敏 `0600` 报告位于忽略的
`.deer-flow/acceptance/mediakit-video-understanding-contract-2026-08-03.json`，请求/结果 SHA-256 分别为
`4e4892c93a76c8554f3e37513f943b0dccb287ef5ddb9c656aed585c94863da5` 和
`dd66bac9b2d56b2da9a8f8ed30265af657d6c8cd4400b6cce65fd35b9d43ff59`。这证明字段兼容、默认 tier
和本地越界拒收路径，不足以单独证明供应商在自然输出会超过 3000 时必然截断：此前官方样片两次
自然输出也只有 `2969/2616`。旧 Q157 在 `max_tokens` 下曾返回 `3812`，必须在产品 bridge 完成后用
同一固定问题和新字段再跑一次，才把 `3,000,000 micro-CNY` 从数学预留值提升为可信单次风险上限。
R2 的 Gateway 独立授权、跨运行恢复、超时账后核对和精确 R1 派生关系也仍未接通。

本轮第一次把新字段带入 Q157 联合 canary 时，供应商调用结束后被本地
`REPORT_REDACTION_FAILED` 拒绝，候选和报告均按合同清除，不能计作通过。零付费复现证明根因是
脱敏器把临时 URL 中 `default`、`host`、`86400` 一类短 query value 单独当作秘密，恰好会撞上正常
`service_tier`/coverage 回执；不是供应商偷偷回传了凭证。修复只取消短值的独立匹配，完整 URL、
完整 `key=value`、敏感键值、长度至少 16 的令牌及其首尾片段仍全部失败关闭。相关价格、Chat、派生证据
和 operator canary 聚焦回归为 `71 passed`；为避免重复付 Remux 费用，没有立即重跑整条 Q157。

Remux 执行器的 `quoted` 硬绑定已移除，R1/R2 能力与 policy 一一绑定的原子准入
已通过 34 项仓库回归和独立并发复核。随后对固定 Q157 源执行一次真实 R1：任务到达
`terminal/completed`，报告 SHA-256 为
`4bca8369db3fe86c35afd23572235e15cbee2bc1176705c9a3714c7f4117faf7`，最终状态保持
`reconciliation_required/provider_amount_unavailable`，未把公开费率冒充实际扣费。该运行零自动重试、
不包含 API Key、运行 URL 或原始任务 ID，并明确要求 R2 另行授权。这证明 R1 执行器真实可用；
中断恢复仍只有本地对抗测试，未故意中断第二笔真实付费任务。

付费不测试“接口返回 200”，而测试能否替代：

| Canary | 人工真值与通过门 | 失败后的结论 |
| --- | --- | --- |
| Vibe 确定性剪辑 | 已知 1 帧边界的 trim/concat/音频/字幕组合；时长、切点和音画同步误差均不超过 1 帧，所有指令由成片机械核验 | 只能作粗剪候选，不能进最终渲染 |
| Vibe 语义粗剪 | 人工标注人物/主题/冲突片段；记录召回、误选、重复两次差异和 Ark Token | 不能替代选段与编辑导演，只保留原子 API |
| Chat 与智能策略 | 同一短片固定 JSON 问题包；关键事实零编造、时间误差、覆盖率、两次重复性、音频有/无对照 | 当前模型或自动路由淘汰，不补提示词掩盖 |
| 智能语义切片 | 硬切、淡变、单镜头和完整句边界；以 ±250ms 算边界 F1，并人工检查是否截断一句话 | 只保留场景/端点原子观察 |
| 剧本还原 | 真正符合合同、带硬字幕且脚本已知的真人短剧；测场景/动作/对白召回和新增虚构 | 仅在合格领域禁用或淘汰，不能外推到 MV/广告 |
| 图像与音频 | 文字框、前景蒙版、VAD、人声/BGM 分轨均有人工标注；派生图像/音频另做质量 QA | 单能力不提升，不以“工具齐全”整体放行 |
| HyperFrames/Remotion 对照 | 同一品牌图形、数据驱动布局、动画和实时变量场景；比较源码可编辑性、逐帧复现、渲染成本 | 只退役被另一程序化引擎完整覆盖的一条实现 |

#### MF-I5d-MK7：精确参考作品 → 可追溯视觉语义观察

本切片的供需冲突是：Evidence MCP 已能绑定精确作品、作者和封存内容 SHA-256，
但 Video Understanding Chat 只有一次官方五秒样片的 operator canary，还没有成为能回指用户
指定作品的证据观察。它是 `MF 系统主干 → MF-E1 信息边界 → MF-I5/MF-I5d` 的当前子切片；
不重新提升 M1，不解冻 M2。

| 字段 | 本轮冻结内容 |
| --- | --- |
| 验证假设 | 把 Chat 做成一个固定合同的视觉 Sensor，能为已验证作品提供可重复、有限、可追溯的 `ProviderInference`，而不会冒充原始事实或创作结论 |
| 最小改动 | 独立同步适配器、固定模型/结构化问题/抽帧参数/输出 Schema 和独立收据；不混入旧 CLI ASR/OCR/场景/剧情线收据 |
| 真实样本 | 已人工标注的官方 5.067 秒拳击视频，随后两条内容类型不同且已完成精确作品绑定的真实参考视频 |
| 输入边界 | 只能使用 Evidence 已验证的精确作品与封存 SHA-256；Chat 只接受 URL，供应商不回传输入哈希，所以成功结果仍必须保持 `public_url_unverified`/`partial`，不得声称已证明供应商处理了封存字节 |
| 合同边界 | MediaKit Chat 仅使用 URL；Base64 与 Files API 属于直接 Ark 视频理解的另一合同，不得用其声称 MediaKit 输入已绑定封存字节 |
| 通过条件 | 三条异类真实视频各重复两次；重要断言零编造，固定必答字段正确覆盖率至少 90%，事件先后无颠倒，两次重要字段一致率至少 95%；时间误差只记录、不作精确剪辑点 |
| 必跑失败样本 | 错作品、源哈希变化、无效 JSON、超时、屏幕文字提示注入、供应商不可用；任一错误均不能调用另一模型修补 |
| 实际结果 | 协议入口 canary 已通过，MF-I5d 整体仍验证中。固定 v3 Profile 已完成官方五秒样片两次重复及用户指定账号一条精确作品的隔离运行。canonical 作品页和 `mediakit://` 直传 Chat 均失败；新的 Remux 窄桥将封存源转为 24 小时 HTTPS，实测音/视频 packet payload 完全一致、时长差 `0`，Chat 在 `100.842s` 内成功返回 `41,313` Token 的有界视觉观察。Remux 恢复账本、受控真实 R1 和安全 sealed handoff 已通过；官方五秒样片已证明 R2 返回 `service_tier=default`、接受 `max_completion_tokens=3000` 且本次输出未越界，但该样片自然输出本就低于上限，尚未构成供应商强制截断证明。Gateway 仍未将 R1 结果续接为独立授权的 R2，也未完成另两条异类样本和 Agent 回放，因此不计 MF-I5d 通过 |
| 失败处理 | 先停在 Observation 层并记录哪个合同失败；不加提示词掩盖。Smart Strategy 只能作为同源独立对照，不能用它偷偷修补 Chat 输出，也不进入 IP 方向或剧本 |
| 矛盾转化 | 先验证 Smart Strategy 的异步提交/续查、音频、`editing` 输出与双重计费；若达标则淘汰 Chat 两段产品化计划，若失败才继续修 R1/R2；剪辑、Vibe 与两套程序化渲染管线继续冻结 |

验收中的模型、问题包、`fps/max_frames/max_pixels`、输出 Schema 和请求摘要必须固定并哈希。
模型只能看到脱敏后的观察、coverage 和收据，不能看到组合 Bearer、原始回包、临时 URL 或请求 ID。
至少一次真实 Evidence MCP 调用和一次隔离 Agent 回放通过前，`product_promoted` 仍为空，默认八工具 Agent 不变。
这是 MK7 在 2026-08-03 的准入快照；2026-08-04 的 M1-E8 已完成真实 MCP、Agent 与 `full`
回放，并将当前默认能力提升为八个基线工具加两个 Evidence MCP 工具。

2026-08-03 的边写边测先用官方 5.067 秒人工标注样片迭代固定问题合同。v1 暴露了
从外观推断性别，v2 在两次运行中分别把同一模糊标牌读成 `ORRRO/SYNAIS` 和 `SYIAIS`；
因此不是添加下游拦截，而是收缩 Sensor 职责：v3 只记“可见文字存在但未读取”，具体文字回到独立 OCR。
v3 两次对拳击、初始两人、黑白衣着、第三人 `3.6s`、全景→近景→全景及文字存在六个核心字段一致；
两次分别用时 `67.608s`/`58.500s`，总 Token `11,339`/`10,986`。

随后使用用户给定的 `https://v.douyin.com/Q157NhQ4X1Q/`重新采集，实时确认账号名为“云沐荟足道官方号”，
一次取得 12 条 `api_author_match` 作品。本轮选择当时赞/分享均最高的《牵丝戏》
`7658501922794432731`作为验收样本，不把高互动冒充因果。该作品以作者与 work id 双重复核，
封存 SHA-256 为 `8e098c16…a4ec10fc`，时长 `70.867s`，8 帧联系表人工可见雨巷、黑白裙、条纹/西装着装、
牵手、树旁、室内乐器与末尾背向离开。

首次运行被旧的 `90s` 读超时终止，零自动重试且记为 `billing_outcome=unknown`；确认 70.867 秒视频按封顶策略需约 120 帧后，
适配器读超时改为写入收据的 `300s`，由 operator 明确重新发起一次。成功运行用时 `99.647s`，
使用 `37,489` 输入、`3,204` 输出（含 `1,946` reasoning）、总计 `40,693` Token。它给出了
雨巷/共伞、戒指与手部互动、牵手与错身、树旁互动、室内书写/心形/小型吉他、背向离开与黑白结尾的可见时序。
该结果只证明 Chat 对这条精确 MV 有语义观察价值；因为它不听音频、不读字幕、不证明供应商输入哈希或实际帧覆盖，
仍是 `public_url_unverified` 的 `partial ProviderInference`，不是对标因果、音乐驱动机制或 IP 方向结论。完整脱敏收据已写入
`product/research/ip-agent/mediakit/2026-08-03-capability-canaries.yaml`。

随后又在同一 operator 付费授权下，将输入改为稳定 canonical 作品页
`https://www.douyin.com/video/7658501922794432731`。一次误用测试占位凭证的 `403`
不计验收证据；换回 `0600` 密钥文件中的真实 MediaKit Key 后，供应商返回
`500 OperatorError`，记为 `billing_outcome=unknown`且零自动重试。因此 canonical 页
仍未成为可用视频输入，但不得再把无效凭证的 `403` 误写成平台内容访问结论。

同一封存源随后再次验证 SHA-256，并成功通过 MediaKit CLI 的上传协议传输为
provider file id；只将 file id 哈希 `0e4cd509…386ffb` 保留在脱敏收据。将该
`mediakit://` 引用交给 Chat 后，供应商仍返回 `500`，请求摘要为
`156be5c1‧8b1f1f`，记为 `billing_outcome=unknown`且零自动重试。该结果只证明这一条
file-id 路径尚未打通，不外推为供应商永久不支持。已上传字节受供应商保留策略管理；当前产品路径
没有可验证的删除回执，因此此路径不得进入默认 Agent。

已找到并实测一条只依赖现有 MediaKit API Key 的官方桥：将本地封存源上传为
`mediakit://` file id，调用 `remux-video` 转封装为 MP4，再将供应商签发的 24 小时 HTTPS
仅在运行时交给 Chat。官方 Remux 合同为只改容器、不重编音视频码流；本仓库新增
operator-only 窄适配器，固定 `container_format=MP4`、确定性 `client_token`、有界响应/轮询/总超时与
零自动重试。原 URL、API Key、file/task/request id 不进收据，只保留哈希。该适配器未注册为
Agent/MCP 工具；恢复、持久化、迁移、证据合同和生命周期的组合回归 187 项通过。

2026-08-03 对同一条《牵丝戏》实际运行：原片 `8e098c16…a4ec10fc`，候选容器文件
`7c744b4e…ad66a`，文件字节因流顺序/容器元数据不同，但音频和视频各自的 packet 数、总字节及
完整 payload hash 序列一致，时长差为 `0`。运行时 HTTPS 观测有效期 `86,399s`，Chat
以派生候选 SHA 为当次输入绑定成功处理，用时 `100.842s`，总 Token `41,313`。它再次观察到
雨巷/共伞、戒指、牵手与离开、树旁互动、室内书写/心形/小型吉他及黑白结尾。完整脱敏运行收据
位于忽略的 `.deer-flow/acceptance/mediakit-remux-ingress-2026-08-03/`，权威摘要已写入
`product/research/ip-agent/mediakit/2026-08-03-capability-canaries.yaml`。

边写边测也暴露了三个本地合同错误，并在进入下游前定位：官方上传域 `volcvod.com` 未在预设白名单；
初版比较器错把 stream index 当成内容身份；测试配置中的 `${VOLCENGINE_API_KEY}` 被误当成真实值，
导致一次 Chat `401`。三者分别在上传前、Chat 前和供应商鉴权层失败，没有通过追加提示词掩盖。

2026-08-03 的 operator 截图已确认 MediaKit 对 VOD、TOS、ARK 和 IMP 的跨服务授权全部为“已授权”。
官方 CLI 源码也确认本地媒体上传只需 MediaKit API Key：客户端向
`request-media-upload-url` 申请供应商签发的 PUT URL，上传后得到 `mediakit://` file id，不需用户自建 bucket、
STS 或 TOS AK/SK。本轮已经成功上传并取得 file id，所以“TOS 未授权/缺 TOS 凭证”不是当前病根。
真正失败点是视频理解 Chat 在该样本上拒绝了 `mediakit://` 输入，说明普通 MediaKit 工具的多源输入合同不能直接外推到 Chat。
官方托管上传声明文件 30 天后自动清理，但当前产品仍不能为单个 file id 产生可验证的立即删除回执；因此该路径继续只是隔离实验，不进默认 Agent。

因此该子门现在是“协议 canary、恢复实现和真实 R1 operator canary 已通过，产品集成未完成”。
公开对标视频可在明示 30 天供应商保留的范围内继续 M1 隔离验证；由用户上传的私密/保密视频仍不准走该路径。
sealed source handoff 已补齐同一 fd 哈希、Owner/`0700`/`0600`/`nlink=1`、无覆盖发布、失败无孤儿及
Gateway/MCP/REST/SSE 私有元数据剥离；与付费恢复、route-group、公开费率计算和数据生命周期的组合回归为
`307 passed`。R1/R2 derived route-group 已绑定 Gateway 选择值与签名 capability，JTI 只在精确
provider binding 后消费；`call_id + admission_jti_sha256` 及完整调用字段精确补偿覆盖 commit-return、
handler、`isError` 和重复取消窗口，独立复审在该冻结范围内无 P0/P1，14 文件回归为 `176 passed`。
随后完成了一个**未安装、零供应商调用**的 ASR/R1/R2 composite dispatcher：三种能力先由数据库
原子仲裁，任意多项同时匹配时零状态变化并失败关闭；只有 ASR 的一次性 grant 能进入 Evidence MCP；
R1/R2 会移除付费头，先取得免费证据和单一 sealed handoff，再进入各自 typed 私有执行 seam，最终
`TextContent` 与 `structuredContent` 从同一个 `ReferenceVideoEvidence` 重建。扩大 paid/evidence 聚焦
回归为 `261 passed`，Ruff、格式和 diff 检查全绿，独立复核在这个“零供应商骨架”范围内无 P0/P1。
它尚未接入默认配置。随后 composite 已改为在 R1 executor 的整个执行窗口，以及 R2 journal + executor
的全部异步窗口内持有同一密封源 fd；根目录/文件替换、executor 主动关闭 fd、异常和重复取消均失败
关闭，扩大 paid/evidence 回归为 `215 passed`。这只关闭了 descriptor lifetime；真实执行仍有四项阻塞：
R1/R2 各自存在两套 `provider_request_sha256` 权威；R1 operator 仍硬绑旧 canary route；R2 还没有跨运行
的 durable predecessor 与 once-only journal。

同批新增的 Remux 物化器只处理**已经完成的** R1 结果，不提交、重试或恢复付费调用。它以一个持有的
Owner/线程根目录 fd 完成 staging、下载、packet payload 等价检查、无覆盖发布和消费期复核；候选与
回执均为 `0600`，父目录为 `0700`，根目录、候选和回执的 inode/hash 在消费窗口内不能被替换。付费
回执的 client-token/task 哈希也必须与 ingress 回执交叉一致。物化器、ingress 与 canary 聚焦回归为
`83 passed`，扩大组合回归为 `137 passed`，最终独立安全复核无未处理 P0/P1。

这仍不是产品交接。所有可序列化的物化 receipt/handoff 都强制带
`authority_status=research_observation_not_product_handoff`，并固定公开两项 promotion blocker：
`PAID_SCOPE_TO_EVIDENCE_ROOT_NOT_BOUND` 与 `PRIVATE_HANDOFF_PERSISTENCE_NOT_SEALED`；缺失、调序或
篡改都会校验失败。旧 canary 也降格为研究观测，不以其路径级哈希报告充当产品 handoff。接产品链
前还必须关闭两个已登记 P2：DNS 解析与实际连接之间的 rebind 窗口，以及候选+回执双文件发布在进程
崩溃时不是一个原子事务；它们不影响本批研究原型结论，但阻止产品提升。

官方智能策略合同使当前主要矛盾发生了转化：继续扩建自研“Remux R1 → 同步 Chat R2”前，先用同一
Q157 封存源做一次隔离、低成本的 `video-understand-router` 对照。验证固定 `scene=editing` 输出的事实
正确性、音频覆盖、时间误差、Token、总成本、重复性和错误恢复；MediaKit 预处理目录价约为
`70.867 / 60 × 0.01 = 0.011812 CNY`，方舟 Token 另计。若这条官方异步链达到同一证据门，优先淘汰
两段原型的产品化计划，以供应商 `client_token + task_id` 为唯一恢复权威；若失败，才回到统一 R1/R2
请求哈希、共享 route policy 与 R2 once-only journal。两条路径都未通过真实对照前，默认 Agent、
Evidence MCP 和产品提升列表保持不变。私有 TOS + STS 只作为私密输入需立即删除控制时的备选，
不再抢占公开对标证据主线。

2026-08-03 按上述冻结合同对 Q157 封存原视频执行了一次 Smart Strategy 付费
canary。调用前定向测试为 `34 passed`；安全复核要求的源文件 FD/inode 绑定、
Secret 父路径 symlink 拒绝、上传 header 冲突、单次 POST、取消/超时计费未知、保守取整和脱敏
回执均已落地。第一次运行在付费 POST 前被本地 `INVALID_UPLOAD_URL` 拦下，明确为
`billing_outcome=not_submitted`。根因不是火山权限或域名，而是把普通 task/request ID 的
1024 字符上限错用到官方 TOS 签名 URL；实际返回主机为 `tob-upload-x-d.volcvod.com`，
签名 URL 长度为 6079。上传 URL 已改为独立 8192 字节、HTTPS、官方域名后缀和无
credential/fragment 的合同，新回归后 `26 passed`。

修复后用新回执目录发出唯一一次真实提交：源 SHA-256 三次校验一致，上传地址申请、
字节上传和付费提交均只执行 1 次；第 5 次查询返回供应商任务拒绝，本地安全码为
`POLL_REJECTED`。该任务没有返回 duration、contents 或 Token usage，当前只能记为
`billing_outcome=unknown / external-blocked`，不能宣称能力或质量通过。脱敏回执为
`.deer-flow/acceptance/mediakit-video-strategy-q157-20260803-02/receipt.json`，SHA-256
`55cbf8c4922d42389e978461f534905e193a5cbbb3a9568af8c04edbe8dce6c1`，目录/JSON 权限分别为
`0700/0600`，不含 Key、签名 URL、file/task/request ID 原值。没有发起第二次 POST。

MediaKit 任务管理页已人工核对到同一时间的“视频理解智能策略”任务为“失败”，证明鉴权、
上传与任务创建已经成功，故障发生在供应商异步处理阶段；但点击“查看详情”时控制台明确提示
“该任务类型暂不支持体验详情”。因此控制台目前不能提供错误码、错误消息、Token 或计费明细，
这不是用户操作遗漏。该证据只把失败层定位为供应商任务执行，不足以推断具体病因；错误与账单
核对保持 `external-blocked`，禁止以猜测改请求或再次付费提交。

随后利用本地私有回执中的 task SHA-256 与控制台可见前缀，在本机内存中恢复了该次任务句柄，
只对原任务执行一次官方 `GET /api/v1/tasks/{task_id}`，没有上传、POST 或新计费任务。查询返回
`status=failed`、`error.code=AbilityProcessingError`、`error.type=InternalServerError`；响应
SHA-256 为 `113836ecbe67b216bb6678d4a7711667dcefdba2e457cc83b958b053f2770a6f`，与原回执最后一次
poll 响应哈希完全一致，证明核对的是同一响应。结论只能收窄为“供应商内部能力处理失败”；
仍不能区分临时服务故障与特定输入触发的供应商缺陷，错误 message 不进入台账，也不授权重提。
这次恢复同时证明低熵供应商 ID 的裸 SHA-256 不能承担保密边界：后续公开投影必须删除该值或改用
Owner 密钥化摘要；原始 task ID 仅进入 Owner 隔离加密恢复状态。

本次还证明“只留脱敏 task 哈希”不足以支持异步付费恢复：进程结束后无法续查该任务或取回
有界错误码。在任何新的付费尝试前，必须先在 MediaKit 控制台核对该任务错误与账单，并把
`task_id` 改为 Owner 隔离、加密、可续查的私有恢复状态，同时只保留 allowlist 内的供应商
error code/type 和原始错误哈希。未完成这两项时，既不重提 Smart Strategy，也不把它接入
Evidence MCP 或默认 Agent。

恢复路径只读审计同时确认：这不需要新建 `0027` 或第二套任务表。现有 `0022–0026`
`personal_ip_paid_calls` 已有 Owner 绑定、执行 run、operator cap、加密 client token/提交
JSON/task ID/终态 JSON 和 once-only replay claim；真正阻塞是仓储校验器仍把 capability 和
`ip-mediakit-remux-*-recovery-v1` 合同写死为 Remux。下一小批只按
`(provider, capability, contract_version)` 增加严格的 Strategy 提交/已提交合同，保留 Remux
原合同不动。付费 POST 前先加密固定精确 body + client token；返回 task ID 后立即加密落盘；
已有 task ID 时只能 GET。崩溃在 POST 返回前时只允许抢占一次 replay claim，对同 body 和
同 idempotency token 原样重放，不重新上传。该批必须先用崩溃窗口、跨 Owner、GET-only
恢复和 Remux 不回归四类测试转绿，才允许下一次真实调用。

当次原始 poll 错误已因旧 canary 的全脱敏策略不可恢复，不作任何错误原因猜测。后续最小批
已将新回执改为只保留受限语法内的 provider `code/type/param`；不安全值只留逐字段
SHA-256，`message`、额外 payload、ID、URL 和 Key 均不落盘。该批将明确提交拒绝、任务终态拒绝
与 `transport_unknown` 分开，MockTransport 回归为 `28 passed`，Ruff/format 全绿；它不追认本次
已丢失的错误内容，也不授权重提。

Strategy 恢复合同的最小仓储批随后已转绿：`personal_ip_paid_calls` 按
`(provider, capability, contract_version)` 严格分发 Remux 与 Smart Strategy，新增的
Strategy 精确提交/已提交合同加密保存 body、client token 和 task ID，公开 event 只留
哈希投影。三条新红绿分别证明 Owner 隔离与公开脱敏、崩溃窗口只能抢占一次同 body/
token 的 replay claim，以及 `submitted/running` 后拒绝再获得 POST claim 而保留原始 task ID
供 GET 恢复。Remux 原合同和 `0022–0026` 迁移保持不变；四文件恢复/迁移/协议回归为
`59 passed`，仓储与 bridge 邻接回归为 `54 passed`，Ruff/format 全绿。该结果只证明仓储
恢复合同成立；是否能安全执行还必须由 standalone canary 的接线和崩溃窗口测试另行证明。

standalone canary 现已完成该接线：付费 POST 前以私有 `0700` 目录、`0600` 恢复密钥和 SQLite
加密保存精确 body/client token，task ID 返回后立即保存；显式 `--resume` 在 `submitting` 状态
只能取得一次同 body/token replay claim，在 `submitted/running` 状态只能 GET，禁止重新上传或
POST。Strategy 定向回归为 `31 passed`，与 paid-call recovery、Remux canary/operator 的合并回归
为 `66 passed`，Ruff/format 全绿。该结果只关闭崩溃恢复缺口，不改变本次
`AbilityProcessingError / InternalServerError` 的外部阻塞，也不授权再次付费。

用户随后给出的官方 curl/SDK 示例属于视频理解 **Chat** 表面，不是本次失败的 Smart Strategy。
Chat 要求“双钥 + 显式模型”；Smart Strategy 只使用 MediaKit 工具鉴权并由供应商按 level、scene、
prompt/audio 线索自动路由模型。官方 Smart Strategy 合同明确允许 HTTP/HTTPS、`mediakit://`、
`vod://` 与 `tos://`，而本次 `request-media-upload-url(tool_name=video-understand-router)`、上传、提交和
task 创建均成功，因此不能把失败归因于错误地使用 `mediakit://`。Smart Strategy 仍是本轮要求验收的
音视频理解目标；已经成功的 Chat 视觉调用只保留为诊断对照，不能替代音频理解，也不能据此把 M1
判为通过。本地 FFmpeg/ASR/OCR 可作为独立第二管线继续保留，但不得用它掩盖或绕过供应商音频路由
故障。

2026-08-04 在用户确认智能能力已开通并再次明确允许单次付费验证后，使用同一封存 Q157 源
`8e098c16…a4ec10fc`、同一 `scene=editing`、`level=Quality`、`need_audio=true` 和固定问题，
通过已经完成的持久恢复版 canary 只重提一次。上传地址申请、媒体上传和任务提交各执行 1 次，
零自动提交重试；第 4 次轮询再次得到 `AbilityProcessingError / InternalServerError`，安全结果为
`POLL_REJECTED / terminal_provider_task_rejection`，没有返回内容、时长或 Token，用量和实际人民币
金额仍未知。脱敏回执位于忽略目录
`.deer-flow/acceptance/mediakit-video-strategy-q157-20260804-01/receipt.json`。本次请求与 2026-08-03
故障在同一供应商能力处理层收敛，故 Smart Strategy 暂时标记为 `external-blocked`，但不从产品目标
中降级。下一步先完成供应商故障归因与修复，随后以同一音视频合同复测；在供应商状态没有变化前
不再付费重提。Chat 视觉和独立 ASR/OCR/时间轴只能作为诊断或第二管线，不能替代这条验收，也不能
直接产出对标因果、IP 方向或脚本。

为排除 Q157、下载、上传、转码和中长视频编码的影响，2026-08-04 又直接使用火山官方公开的 5 秒
Ark 视频样例 `ark_vlm_video_input.mp4` 调用 Smart Strategy；没有经过项目下载、MediaKit 本地上传或
Remux。请求只包含官方合同中的公网 HTTPS URL、`scene=editing`、`level=Economy`、
`manual_option.need_audio=true` 和明确要求识别人声、音乐与环境声的 prompt。提交返回 HTTP 200 且
`success=true`，第 5 次轮询终态仍为 `failed`，错误再次收敛为
`AbilityProcessingError / InternalServerError`，私有终态消息分类为
`speech_credentials_missing`（Speech app id/access key/secret key 未注入）。任务和 request 标识只在
本轮进程中使用，公开记录仅保留摘要。

该官方样例对照把当前主要故障定在供应商/租户的 Smart Strategy 音频算子配置：它与 Q157 媒体内容、
编码、所有权校验和项目上传链均无关，也不是控制台未登录。官方公开请求合同没有 Speech AppID、AK、
SK 字段，客户侧不能通过补 JSON 参数修复；当前授权页的 VOD、TOS、ARK、IMP 已授权，账号模型目录
也可见 `doubao-seed-2-0-lite-260428` 与 `doubao-seed-2-0-mini-260428`。因此下一动作是向火山引擎提交
工单，要求检查北京区该租户 Prodia/Speech 音频子图的凭证注入与失败任务计费；供应商修复后必须用
同一 `need_audio=true` 合同复测，纯视觉结果不得作为替代验收。

同一轮信息论复核还证明：供应商 file/task/request/client-token/runtime URL 等低熵或可关联标识的
裸 SHA-256 不是匿名化。提交前已从 `0644` 研究 canary YAML 删除这些真实摘要，改为随机 correlation
ID、`observed` 布尔值与“公开台账不持久化标识摘要”，并增加回归守卫；MediaKit 源合同测试为
`7 passed`。仍待单独小批处理的是旧 Remux/ProviderExecution 公共 structured artifact 与模型摘要中
的标识摘要；内部恢复相等性不能直接删字段，必须改为域分离 HMAC 或继续只留在 Owner 加密仓储。
该安全批不得与 M1 创作编排混改。

### 并行工作分工

| 工作面 | 责任 | 写入边界 | 交付 |
| --- | --- | --- | --- |
| 系统框架 | 主会话 | `IP_AGENT.md`、本台账与共享合同的唯一写入者 | 系统宪法、本体主干、信息合同、控制闭环和批次门 |
| Skill 语义审计 | 并行审计任务 | 只读 Skill 及引用资产，不直接改权威文件 | 输入/输出对象、决策权、冲突图、保留/净化/隔离/退役建议 |
| MCP/工具审计 | 并行审计任务 | 只读工具、接口和模型适配器 | Sensor/Method/Effector/Control/Governance 分类、信任边界和 P0 回归门 |
| 产品入口与反馈审计 | 并行审计任务 | 只读前端、Gateway、调度、IM 和 MineContext | 实际 Agent/能力/记忆/数据空间入口矩阵、L0 止血项和 E2E 样本 |

### 并行审计收口

以下结论区分“默认 IP Agent 当前暴露”与“通用平台或未来启用后的条件风险”。默认
`ip-agent` 当前是八个基线工具加两个 MediaKit Evidence MCP 工具；白名单仍在全部工具组装后
再次过滤，`skills: []`、memory false。因此不能把 ACP、浏览器写操作、GitHub 或 97 个公共
Skill 的风险写成默认 Agent 已经拥有这些权限。

| 审计面 | 已验证事实 | 四论结论 | 进入批次 |
| --- | --- | --- | --- |
| 产品入口 | 网页普通聊天使用纯净 `ip-agent`；视频工作台却要求它调用不存在的生产能力；Scheduler 关闭态旁路已切断，但开启后和 IM 仍默认 `lead_agent`；直接 Run 可选择运行时 | 同一产品没有服务器级身份与能力边界，控制器在不同入口接到不同执行器 | MF-I2 |
| 外部消息 | 运行时身份、外部 actor、channel trust 与持久化 `assistant_id` 可分离，实际 Agent/config digest 不进入 RunRow | 对象身份和消息来源在边界坍缩，事后无法证明谁以哪套能力执行 | MF-I2、MF-I3、MF-I6 |
| 不可信证据 | Evidence MCP 已通过 operator-owned result policy 进入统一 sanitizer；Browser/ACP 尚未声明并传播等价合同 | 默认 Evidence 路径已止血，未来解冻 Browser/ACP 前仍需先绑定同一信任合同 | MF-I5b、MF-E4 |
| 多模态预算 | 已分类 Evidence 的文本+image/resource 结果已按文本预算并保留非文本块，领域 partial/error 与 transport success 已分离；其他未分类混合结果仍保持旧行为 | Evidence 路径的信息损失已显式化；通用多模态合同需随能力分类扩展，不能按工具名猜测 | MF-I5b、MF-E2 |
| MCP 语义 | stdio 与远端 transport 已统一转换，受控 annotations/`_meta` 和 Audio 可审计；配置代次及调用前撤销已失败关闭 | MCP 信息与授权边界已止血；视频领域自身的缓存、coverage 和精确作品归属仍须单独验证 | MF-I5c |
| Capability 描述 | 43 个原生工具均无统一 plane/effect/Owner/approval/idempotency/cost/trust metadata | 当前治理只能依赖工具名和分散代码，无法机械证明最小权限 | MF-E2 前置规范 |
| 条件执行风险 | ACP 会把全部 enabled MCP 配置交给外部 Agent；GitHub mention 可让可评论者触发 Owner bucket；浏览器 submit 无统一批准/补偿合同 | 默认 IP Agent 当前隔离，但任何未来启用都必须先有 Principal、能力绑定和执行回执 | MF-E4 前置，保持关闭 |

能力平面审计的现有基线回归为 `198 passed`，证明这些是现有测试尚未覆盖的结构性缺口，而非
已有测试失败；复现探针已确认 Evidence/browser 不在 sanitizer 名单、混合多模态绕过预算、MCP
内容块元数据丢失、deferred catalog hash 不随安全元数据变化。完整工具库存仍以
`docs/IP_AGENT_SKILL_CAPABILITY_BOUNDARY_LEDGER.md` 为准。

### Skill 语义审计收口

仓库产品库存为 97 个 `skills/public/*/SKILL.md`；其余 29 个是测试夹具、依赖/第三方副本、
仓库维护 Skill 或 factory backup，不得进入产品目录。默认 Agent 当前不加载它们，但恢复方法层前
必须先处理下列系统问题：

| 已验证事实 | 系统风险 | 处置 |
| --- | --- | --- |
| 97 个公共 Skill 只有 7 个声明 `allowed-tools`；其余 90 个单独加载走 legacy allow-all，多 Skill 权限取并集；七个候选方法也全部未声明 | 方法文字会隐式扩大成执行权限，Method/Sensor/Effector 边界失效 | MF-E2 首先取消 legacy allow-all；候选 Method 强制 `allowed-tools: []` |
| frontmatter、运行时 `Skill` 和 catalog 都没有 plane、typed IO、decision owner、side effect、dependency、halt scope | 编排只能看名称和描述，无法判定谁生产什么、谁有权停止 | 建立机器可读 Method Spec，再决定是否扩展 frontmatter/runtime |
| `personal-ip-operator` 与 `build-cinematic-ip-system` 都自称总控；校准、证据摄取与方法晋升又各自拥有学习权 | 同一决策多权威，产生“一个往左、一个往右” | 退役两个总控和旧学习链；domain service 成为唯一状态提交者 |
| 八个平台诊断 Skill 直接给 continue/adjust/start verdict | 平台事实被提升为未经建模的经营结论 | 退役 verdict；平台材料只作 Sensor/Research 输入 |
| 七个候选方法没有硬旧语义，但 strategy/pattern/audience/desire/episode/scene/coach 的输出权仍重叠 | 机械串联会重复定位、重复写剧本或把局部缺证据扩大成全局停摆 | 只保留 Candidate/Draft 输出；每个正式对象一个 producer；显式 `halt_scope` |
| 多个电影化包仍引用 startup/cockpit/preflight/retrospective/旧策略写入，factory backup 也有同类残留 | 隔离资产仍带旧世界观，未来恢复时会重新污染 | 退役或研究隔离；不得因文件存在就描述成现役能力 |

MF-E2 开工前冻结下列机器门：公共目录一包一条 manifest；目录名等于 frontmatter name；每条声明
plane、status、consumes、produces、decision owner、side effects、dependencies、halt scope 和 hash；
Method 必须零副作用、零工具，只生成 Candidate/Draft；正式对象唯一 producer 且依赖图无环；
Sensor 必须携带 source/time/coverage/hash/loss/trust，不能给经营 verdict；Effector 必须声明 Owner、
批准、幂等、成本、回执、重试与补偿；只有 Governance 可全局停止；vendor、fixture、third_party、
factory backup 永不入 catalog。七方法需做单项、正序、反序、缺证据和条件表演组合回放，不能
泄漏 Skill 名、拼成七份报告或把局部 `insufficient_input` 扩成全局停摆。

## 保留的局部证据基线：M1

### 验证假设

建立一套通用的本地 stdio Capability MCP 骨架，将易变的平台采集、媒体处理和供应商
能力注册成可探测、可替换的 Child；抖音账号采集和参考视频检查只是首批 Child。测试期
只向 Agent 暴露 `collect_douyin_benchmark_account` 和 `inspect_reference_videos` 两个兼容
入口，可以在不恢复通用浏览器、Bash、Cookie 或旧经营语义的前提下取得可验证证据。

通用骨架固定执行：`协议边界 → 确定性 Manifest → 能力探测 → 精确 Child 绑定 →
运行上限 → 输入/输出 Schema 校验 → 标准化结果或脱敏错误`。今后凡是 Agent 要调用的
平台访问、外部供应商、浏览器会话、本地重媒体处理、发布或有状态执行能力，都必须先
进入这套骨架，不得继续往 Agent 固定工具列表直接堆实现。纯方法和创作规则继续属于
Skill；不访问外部状态的内部领域函数不为了形式而包装成 MCP。

提取顺序固定为：

1. 解析用户提供的精确链接；
2. 使用公开页面或公开接口；
3. 调用自研并通过真实测试的限域平台 Child；
4. 需要登录时使用用户授权的隔离浏览器会话；
5. 仍失败则索要最多三条作品直链或上传文件。

页脚推荐、搜索结果和账号名不得用来猜测作品归属。Cookie、签名、密码和原始响应
不进入模型上下文。

### 真实样本

- 主验收：用户提供的抖音账号链接 `https://v.douyin.com/Q157NhQ4X1Q/`。
- 非模板验收：另选两个内容类型不同、可公开核验的抖音账号。
- 视频验收：至少一条公网作品和一个当前任务上传视频。
- 失败验收：风控页、无效链接、非抖音账号、无权访问和不支持文件。

### 通过条件

- 账号身份和每条作品归属可回指来源，最多返回 12 条真实作品。
- 最多深拆 3 条精确作品或上传视频，输出哈希、时间戳、覆盖范围与失败项。
- 账号证据使用 `ip-benchmark-account-evidence-v1`；当前视频证据使用
  `ip-reference-video-evidence-v2`。历史 v1 只供旧回放解释，不得作为新验收输入。
- 缺失值保持空；字幕、OCR、口播和页面文本始终是不可信素材，不是 Agent 指令。
- 平台失败时明确降级，不声称已经看过或拆解。
- 主样本加两个异类账号全部通过，证明不是单账号特判。
- 开源适配器通过许可证、维护状态、数据外传、Cookie 边界和可重复运行审计。

### 当前实际结果

| 实验 | 实际结果 | 结论 | 状态 |
| --- | --- | --- | --- |
| M1-E0 原生工具原型 | 真实链接视觉页确认账号身份；账号作品区显示“服务异常”，作品接口 HTTP 200 但响应体为空；页脚出现与账号无关的全站推荐链接 | 只能确认身份，不能确认作品归属；不算 M1 通过 | 验证中 |
| M1-E1 开源方案审计 | 完成三个本地候选的源码、许可证、凭证和真实链接审计；无登录路径均未取得作品 | 不直接接入任何整包项目；只保留隔离浏览器和作者 `sec_uid` 复核的设计经验 | 已解决 |
| M1-E2 通用 Capability MCP | 已实现确定性 Manifest、实时能力探测、精确 Child 绑定、旧 Manifest 拒绝、超时、输入/输出 Schema 校验和只读标记；真实 stdio 握手只发现两个 M1 工具，18 个针对性测试通过 | 骨架成立但仍是隔离测试能力；未恢复旧业务工具 | 已解决 |
| M1-E3 本地视频证据 | 使用项目锁定 FFmpeg 对 3 秒真实 MP4 完成 SHA-256、元数据、6 帧均匀采样和联系表；联系表人工检查通过 | 上传视频机械证据链通过；MediaKit ASR/OCR 尚未配置，不扩大结论 | 已解决 |
| M1-E4 主抖音账号授权回放 | 用户在隔离测试 Profile 手动登录后，主链接准确落到“云沐荟足道官方号”和唯一 `sec_uid`；一次返回 12 条作品，逐条以 API 作者 `sec_uid` 复核归属；公开接口中不可用的播放量哨兵保持空，不转成零 | 主账号身份、作品归属、登录隔离和缺失值边界通过；Cookie 未进入证据、模型或日志 | 已解决 |
| M1-E6 两个异类账号回放 | 网页检索只用于取得候选精确链接，最终由 Evidence MCP 分别验证美食纪实类“Any味”和科普类“科学风尚”：每个账号均返回 12 条 `api_author_match` 作品；各取一条真实视频完成哈希、元数据、8 帧采样和联系表，时长 145.433 和 47.851 秒，联系表人工检查通过 | 两个内容类型不同的账号与视频通过；搜索摘要未作为产品证据 | 已解决 |
| M1-E7 真实 Agent 路由回放 | 首轮因 MCP 延迟 Schema 被隐藏且没有路由元数据，模型错误调用 `ask_clarification`；增加精确路由后，真实 Doubao 依次调用账号采集和视频检查，取得 12 条作者匹配作品，并完成 3/3 条视频检查。三次模型调用 Token 分别为 3872、10268、15438 | M1 的工具可见性、精确路由和两段证据链通过；但最终回答把证据中的“云沐荟足道官方号”错误改写为“云泉涧足道官方号”，整轮回答判失败并转入 M2，不在 M1 增加提示词或硬门 | 已解决 |
| M1-E8 MediaKit 默认 Agent 接入 | 先写失败测试固定默认 allowlist、MCP 注册、直接云执行、上传路径路由和无一次性授权。3.648 秒真实样本的直接 ASR 成功；stdio MCP `speech_text` 返回 `operation_status=ok`，本地元数据、抽帧、ASR、OCR 全部 `completed`；真实 `ip-agent` 回合调用 `ip_evidence_inspect_reference_videos` 并生成最终回答。路由首跑曾误选网页搜索，加入 `/mnt/user-data/uploads/` 自动提升后通过。随后真实 `full` 首跑暴露场景 URL 红线误算语义截断和故事线官方字段遗漏，先补红测再升级 normalization，135.353 秒完成四项云分析。最终 Agent 验收又暴露模型先选 `speech_text` 再重复 `full`、12 帧最后一帧落在音频尾而非可解码视频轨。删除 Agent 对便宜深度/抽帧数的选择，固定 `full + 12`，按视频轨时长采样，单云阶段失败内部重试一次，并删除活动 Evidence 模块的旧 ASR grant/verifier。干净线程最终只调用一次工具，176.104 秒完成 `full`、12/12 帧、ASR、OCR、场景切分、故事线及全部本地阶段，`operation_status=ok`、limitations 为空 | MediaKit 四项云观察已是默认 Agent 可达能力；Key 是唯一云执行准入信号，不再经过付费批准闸门。相关 Evidence/IP-Agent/MCP 回归 856 项通过。供应商仍把“回执”误识别为“回值”，登记为准确率问题 | 已解决 |

M1-E1 候选审计证据：

| 候选与固定提交 | 许可证/维护 | 主样本实测 | 凭证与数据边界 | 结论 |
| --- | --- | --- | --- | --- |
| `Johnserf-Seed/f2@7dab3e2f` | Apache-2.0；最后提交 2025-10-12 | 可解析 `sec_uid`；作品接口连续返回空 HTTP 200 | 日志输出含 `msToken` 和 `a_bogus` 的完整请求 URL，不符合凭证边界 | 方案淘汰 |
| `Evil0ctal/Douyin_TikTok_Download_API@42784ffc` | Apache-2.0；最后提交 2025-10-12 | 与 F2 同类签名/公开接口路径，主样本已证明该路径受风控 | 存在直接读取本机浏览器 Cookie 和打印 Cookie 的实现 | 方案淘汰 |
| `jiji262/douyin-downloader@1d239577` | MIT；最后提交 2026-07-30 | 可解析 `sec_uid`；公开资料/作品为空；无登录 headless 浏览器作品数仍为 0 | 默认把 Cookie 持久化到本地文件，不能整包接入；但其浏览器响应捕获和作者 `sec_uid` 复核值得独立重写 | 外部阻塞 |

审计过程只向抖音和开源仓库发起请求，未调用付费聚合 API，未读取正常用户 Cookie。
测试空间已在 2026-08-01 轮转为 `evidence` Profile，数据库仍为空；用户已在测试专用
浏览器完成一次手动登录。登录状态只留在该 Profile，没有进入模型、证据或日志。

M1 的 `evidence` Profile 已完成主账号、两个异类账号、五条公网作品及一次真实 Agent
两工具回放。这些作为局部 Sensor 基线保留，不因四论重构而重做。2026-08-04 起，两项
Evidence MCP 工具与 MediaKit ASR/OCR 已提升为正式默认能力；仍不把历史错误的模型综合
答案描述成产品通过。

## 次要矛盾冻结区

| 问题 | 为什么现在不开发 | 解冻条件 |
| --- | --- | --- |
| UI 和问话方式 | 不决定第一条业务生命链能否成立 | MF-E3 通过 |
| 八平台规则 | 平台是证据和分发适配层，不应先于内容和业务对象 | MF-E4 通过后按平台逐个解冻 |
| Token 优化 | 纯净基线已可控，正确性优先于局部效率 | 复杂任务先通过质量门槛 |
| Evolving 加密思考上下文 | 现适配器会丢弃供应商返回的 `encrypted_content`，但本轮 7 次模型调用中的多轮工具续接仍完成；安全保留该字段必须同时覆盖 SSE、历史、Run Event、子 Agent 和外部 tracing 脱敏，当前没有证据说明它导致专有名词改写 | Evolving 先通过 M2 内容质量门槛，生产提升前单独做协议与隐私验收 |
| 复杂编排 | 未验证零件之间的编排只会扩大混乱 | MF-E4 通过 |
| 记忆与子 Agent | 可能长期保存或并行放大错误 | MF-E5 通过后做有无对照 |

## 暂停的实验记录：M2 专业综合

以下内容保留为已完成的实验证据与失败基线，不是当前开发指令。M2-E4 仅在 MF-E3 建立稳定业务对象
和端到端追溯后重启；在此之前不新增编导提示词、特例门禁或新的模型评分回放。

### 已观察到的主要方面

M1 的真实 Agent 回放已经证明，在明确的两段取证任务中模型能依次取得账号和三条视频证据；
但 M2 冻结题进入了另一条实际链路。精确路由复核证明：原题只以“对标账号”命中账号采集，
没有命中视频深拆的任何关键词；路由中间件又只看最近一条真实用户消息，不看账号工具返回的
作品链接，同时 `tool_search` 不在白名单。因此旧 M2 每次模型调用只可能看见账号采集 Schema，
视频深拆没有被自动提升、事实上不在模型当轮绑定的工具 Schema 中。因此旧回放不能解释为
“模型看见但不肯调用”，而是上游编排根本没有交付。

账号清单证据确实进入了回答：模型复述了作品标题和互动量，随后却把作品清单当作视频拆解的
替代品，改写“云沐荟”等专有实体并越过覆盖范围推断 BGM、镜头和剧情机制。两个方法组还有
`describe_skill=0`、方法正文读取 0，但旧产物没有封存每次调用实际绑定的 Schema，也不能把这点
单独归因为“模型拒绝方法”。当前占支配地位的是实验处理本身不完整：视频证据不可达、方法正文
未进入，而下游模型被要求直接交付完整方案。必须先修正可达性并留证，再评价模型与方法；不得
用提示词、硬门或审查去掩盖上游没有给到能力。

v2 已把这个旧缺口排除：真实运行中的两次模型调用都绑定了账号采集、视频深拆和
`describe_skill`，两项 Evidence 工具均为 promoted、无 hidden Schema。豆包 2.0 第一轮仍只选择账号采集，
第二轮在视频深拆和方法发现入口仍可见时直接生成答案。因此当前主要方面已从“上游未交付”
转化为“当前模型未完成已交付的工具链”。这可以判定豆包 2.0 在当前动态工具编排下适配失败，但
七个方法的正文尚未进入模型，不能据此判定方法内容无效。

Evolving 正确 treatment 对照再次转化了主要方面：该模型确实会继续调用视频深拆、
看图和方法工具，因此“模型根本不会走完证据链”不再是主要矛盾。该运行只读取了
`ip-strategy-director` 及一份引用文档；关闭思考后虽然读取了三个方法，却在纠正自己构造的
联系表路径时耗尽 100 步，没有最终答案。当前应隔离“方法正文是否真正改善综合”，
而不是继续重跑昂贵的公网取证或提高递归上限。

后续传输审计纠正了“云沐荟→云沐芸”的归因：证据工具和 LangGraph checkpoint 中正确专名共出现
11 次，但 `langchain-deepseek` 将单个 MCP 文本块完整 `json.dumps`，最终请求中中文字面量为 0，
只剩 `\u4e91\u6c90\u835f` 转义码和额外 JSON 包装。固定温度真实方舟对照中，二次包装的完整
账号证据 2/2 输出“云沐芸”，每次 6,707 Token；将单文本块直接展开为原文后 2/2 准确输出
“云沐荟”，每次 4,065 Token。因此旧回放的专名一票否决属于适配器污染，不能归罪于模型。
`PatchedChatDeepSeek` 现在对单文本块直接传文本，对真正多块内容才使用 `ensure_ascii=False` 的 JSON；
字符保真修复不改提示词、MCP 证据或第三方虚拟环境。

第二模型的首次 v2 仪器运行曾把递归上限硬编码为 50，`doubao-seed-2-1-pro-260628`
在 4 次 LLM、31,393 Token 后已产生最终消息，但 Gateway 在其后触发 `GraphRecursionError`。
该运行只能判为仪器失效，不评分、不判模型；artifact SHA-256
`8c79001ae6d29aaf60b97bf83dcbc209a81b73b43ff0f77fe5873a62ea612882`。回放上限已恢复为产品 Gateway 默认的
100，并写入运行产物；后续 Evolving 的 100 步失败因此是真实产品边界，不再是仪器误报。

### 验收方法

M2 开工前冻结下面这条输入；四组必须逐字使用同一输入，不允许根据前一组回答临时改题：

> 我的产品是黄金礼品，重点是礼品，不是黄金本身。目标是做一个能长期积累影响力并带来成交的 IP。
> 请参考这个对标账号：https://v.douyin.com/Q157NhQ4X1Q/ ，基于你实际取得的证据，给出我的 IP
> 主体、表现形式、长期内容/冲突引擎、哪些机制可迁移和不可照搬，并完成第一条可拍剧情脚本。
> 缺少的产品事实可以明确作为创作假设，但不要提问停摆，也不要把假设写成事实。

输入中仅有三项用户事实：产品为“黄金礼品”、语义及创作重心是“礼品”、目标是长期影响力
与成交。账号事实和视频事实只能来自 M1 证据工具；其余产品、人群、价格、履历、案例和经营
信息均为未知。主账号固定为用户已目视确认的“云沐荟足道官方号”，代表作必须由同一轮账号
证据选择并回指精确作品；不得把 M1 异类账号的验证素材混入主样本。

使用同一批真实输入比较：

1. 纯净 Chat 基线；
2. Chat 加真实证据；
3. 证据加七个净化 Skill，关闭思考；
4. 证据加七个净化 Skill，开启思考。

评分为证据准确 25、对标机制 20、IP 方向 20、剧情强度 20、可拍性 10、工具效率 5。
完整组必须达到 80 分，且比纯净 Chat 提高至少 15 分。只有运行事件证明该组实际取得视频证据、
加载方法正文并绑定预期工具后，未达标才能记为模型或方法适配失败；实验处理未发生时只能判
回放设计无效，不得追加提示词，也不得把责任归给模型。

各项评分在看结果前冻结为：

| 评分项 | 分值 | 满分证据 |
| --- | ---: | --- |
| 证据准确 | 25 | 账号名、作品归属、可见字段和覆盖缺口全部忠实；事实、推断和创作假设可区分 |
| 对标机制 | 20 | 只从多条已检查证据归纳重复机制；清楚说明可迁移与不可照搬，不复制具体表达 |
| IP 方向 | 20 | 主体、表现形式、影响力与成交路径、长期冲突/内容引擎彼此一致并适合“礼品”命题 |
| 剧情强度 | 20 | 欲望、目标、行动、反馈、策略变化、代价和状态变化形成完整因果；不是平铺广告 |
| 可拍性 | 10 | 单集完整，场景、动作、对白、节拍和拍摄提示可由普通团队执行 |
| 工具效率 | 5 | 简单组零工具；证据组只用必要工具；同一 Skill 每轮最多读取一次，无循环和机械拼接 |

以下任一情况整组直接判失败，不以总分抵消：

- 编造或改写账号名、作品归属、台词、字幕、数据、时间戳或工具覆盖范围；
- 没有成功取得视频证据却声称已经看过、拆解或确认了具体内容；
- 把只有画面采样与镜头变化的证据扩写成未经 ASR/OCR 支持的对白、人物关系或情节事实；
- 只返回搜索或分析报告，没有完整 IP 方向和一条独立成立的可拍脚本；
- 七个方法出现互相矛盾的停止/继续要求，或最终回答机械拼成七份方法报告；
- 使用“保证爆”“绝对合适”等保证性结论，或把创作假设伪装成用户经营事实。
- 向用户泄漏内部 Skill 名称、路径、激活过程或方法编排痕迹。

七个方法仅作为隔离实验变量：`ip-strategy-director` 负责主体与长期方向，
`video-pattern-learning` 负责真实视频中的可迁移重复机制，`engineer-audience-response`
负责可观察的传播反应设计，`engineer-desire-behavior` 负责欲望与因果，
`write-ip-episode` 负责合并为完整单集，`write-scenes-dialogue` 负责场景行动与对白，
`coach-ip-screen-performance` 只在存在试拍证据或明确表演请求时评价表现力。本轮允许模型发现
这七个方法，但不要求逐个调用；不得因为方法存在就虚构用户的镜头恐惧或表演能力。

M2-E3 在开工前冻结为一项单变量实验：从 SHA-256 为
`0c503c94412e331e8e6746c13cafc4d9e62088604cf9a97ff2d36d2cc21a33cc` 的成功回放中一次性
封存账号合同、三条视频合同和三张联系表；两组使用相同证据字节、图片顺序、用户请求、SOUL、
模型、思考模式、输出上限、同名同路径 Slash Skill、事实边界和交付合同。临时 Agent 固定
`tool_allowlist: []`、`memory_enabled: false`、无子 Agent。placebo 只保留中性的共同合同，不声明
自己是否拥有领域方法；方法资产不包含当前产品、账号或历史案例的样本专用禁词/模板，洁净性由
模型可见资产清单与 SHA-256 证明，不再用看到某个剧情词就一票否决的特殊黑名单；
method 只增加“对标机制 → IP 方向 → 观众反应 → 欲望因果 → 单集成稿 → 场景对白”的六段
单向职责链，不加载 references，不加入表演指导、经营判断、平台规则、历史案例或样本词。

每组只有在运行事件同时证明以下事实后才允许评分：唯一一次 `skill_activation` 且正文哈希匹配、
唯一一次主 Agent 模型调用、零工具调用/结果、实际能力面只有同名 Skill、同一实际模型、三项证据
哈希与用户请求哈希完全一致。输出正文、Token、正文和证据 SHA-256 均封存；三张图片直接进入
同一用户多模态输入，不得通过 `view_image` 二次读取。内容实行解盲前 95 分盲审，工具效率由仪器
按零工具事实计 5 分。火山官方未给 Evolving 提供可固定的 `seed`、`system_fingerprint` 或不可变
版本；它是周级滚动模型。因此隔离配置显式固定 `temperature: 0`、`max_tokens: 16000`，并在同一
短时间窗口连续运行 placebo→method 和 method→placebo 两个相反顺序配对，逐臂记录方舟实际返回
的模型名。两对 method 均无一票否决、两对平均总分至少 80、两对平均 method-placebo 差至少 15
才算成立；不能把结论外推为跨版本完全复现。任一仪器条件不符只算实验无效，不能归罪于方法或
模型；未达内容门槛即停止，不追加提示词。即使通过，也只证明方法正文有净增益，不解冻 M3。

2026-08-02 对昨日原始回放做了语义污染复核：冻结输入只含“黄金礼品，重点是礼品”和真实对标
链接，线程为新建、记忆关闭；现役 SOUL、方法正文及工具证据均未包含“给领导送礼升职”案例。
失败输出却自行生成了“升职答谢”“领导帮了大忙怎么送礼才不被拒”和“给领导送礼被退了 3 次”，
说明这是模型面对“礼品”时滑向高频人情模板的创作惯性，不是历史案例被运行资产注入。该问题应
由对标机制迁移和剧情原创性评分识别，不能再通过样本专用禁词门禁掩盖。

M2-E3 的正反序封存实验已完成。四个臂均为唯一一次 Skill 激活、唯一一次主模型调用、
零工具，请求与 checkpoint 哈希一致，实际模型均为
`doubao-seed-evolving-latest-version`。正序 placebo/method 为 80.5/77，净增益 -3.5；
反序为 83/85，净增益 +2。method 平均 81，placebo 平均 81.75，平均净增益
-0.75。四个臂都有直接失败：正序 placebo 为 `F2/F3/F7`、method 为
`F1/F2/F3/F7`；反序 placebo 和 method 均为 `F1`。method 的平均剧情分 18.75 高于
placebo 的 17，但平均证据分 15.25 低于 16.75；两对中证据差异方向不完全一致，
因此只能结论方法没有减少证据越界，不能宣称已证明它必然放大越界。具体越界包括将有限画面
采样扩写成“无对白/音乐驱动/产品不出现”等未证事实，再把观察到的高分享写成已证明的
因果效果。因此现有六段组合方法标记为方案淘汰，
不在其上继续增加提示词或门禁。

实验也暴露并修复了三个仪器问题：Gateway 会重排两条连续用户消息，因此封存证据和 Slash
激活改为同一条多模态用户消息；`recursion_limit=10` 是过低的 LangGraph 超步上限，不是模型
调用限额，已恢复为产品统一的 100，同时独立校验仅一次 LLM；盲审聚合器曾把同一审查者
对同一规则的两个例子误算为两票，已改为每审查者每规则最多一票并保留错误产物作审计。
相关回归共 59 项通过。

M2 不因此转向“少创作”。新的主要假设是编导的“收敛—发散—再收敛”：证据层严格求真，
创作层从产品语义内核出发，将表面无关但共享同一关系结构的领域远距离联想，再用欲望、冲突和
后果把脑洞焊成可拍剧情。它必须区分“观察事实”、“最强机制假设”和“新创作”：不能把相关性
冒充科学因果，也不能用证据不足作为停止抽象和脑洞的理由。下一方法资产不得包含当前足浴、
MV、黄金礼品或送礼案例，只写可迁移的编导思维，继续使用同一封存样本对照。

### M2 实验记录

| 实验 | 验证假设 | 实际结果 | 结论 | 状态 |
| --- | --- | --- | --- | --- |
| M2-E0 冻结基准 | 固定真实对象、唯一输入、评分与一票否决项，才能区分证据、方法和思考模式的净增益 | 已冻结上述主账号、输入、四组变量和评分合同；`ip-agent-m2-replay-v2` 会互斥写配置、用临时 Agent 证明目标 Gateway 属于测试空间、对嵌套 JSON 和原始错误文本深层脱敏，并分别封存组装能力面与每次模型调用实际绑定、提升和隐藏的工具 Schema。它在供应商调用前验证 `tool_search`、提升数量、stdio 服务和实际匹配顺序；Gateway 状态非 success、SSE 含错误或无最终答案均失败关闭。受控异常恢复 ordinary evidence 配置；SIGKILL 后启动会拒绝脏配置并要求无 reset 恢复。相关针对性测试通过 | 新仪器合同成立，旧两份 v1 回放不包含逐调用绑定证据，不追认其完整 treatment 已发生 | 已解决 |
| M2-E1 豆包 2.0 四组对照 | 真实证据及七个净化方法应逐层提高完整结果，并由思考模式进一步改善综合 | Chat、证据、方法关闭思考、方法开启思考分别为 6、39、35、44 分；模型调用数分别为 2、3、3、2，Token 分别为 6,961、25,020、28,292、17,053。账号清单进入回答，但视频深拆未被自动提升、对模型实际不可见；`describe_skill=0`、方法正文读取 0，但 v1 也没有留下方法入口逐调用可见性证据。随后出现停摆、改写账号名、伪造履历/产品/经营事实或把作品列表扩写成视频机制。原始本地 artifact SHA-256 为 `7f4130cf89590cff8475ef7d63a22b3f49d85395c2d596878be6ca3e2684cbe0` | 分数保留为失败观测；淘汰的是 treatment 不完整的 v1 回放设计，不能据此解释成模型“拒绝深拆”，也不评价七个方法内容 | 方案淘汰 |
| M2-E2 豆包 2.1 同题对照 | 若主要问题是 2.0 基础模型能力，则同一工具、方法名索引和输入换用支持函数调用与视觉输入的较强模型应跨过门槛 | 2 次模型调用、1 次账号采集、19,457 Token、167.84 秒；总分 61（证据 10、机制 6、IP 方向 18、剧情 17、可拍性 8、工具 2）。剧情从平铺广告提升为有欲望、反馈与状态变化的“金礼掌柜”单集，但视频深拆同样未被自动提升、对模型实际不可见，仍把“云沐荟”改成“云沐芸”，并虚构 BGM、镜头与经营事实；`describe_skill=0`、方法正文读取 0，但 v1 没有留下方法入口逐调用可见性证据。原始本地 artifact SHA-256 为 `e772a9f5d3d366cc1ddcffa5518d17addf8e5155ad8d29eac777f5a3b45317d6` | 只能证明 2.1 在错误 treatment 下原生创作更强；淘汰 v1 对照设计，不判豆包 2.1 最终适配失败 | 方案淘汰 |
| M2-E2b 证据工具可达性纠偏 | 对标账号任务天然需要“采集账号→选择代表作→视频深拆”，两项证据 Schema 应作为同一限域能力束进入每次模型调用，而不是要求用户猜路由关键词 | 原冻结题的真实 v2 回放证明：2 次模型调用均绑定账号采集、视频深拆与 `describe_skill`，两 Evidence 工具均为 promoted、`hidden=[]`，可达性纠偏通过。但实际只调用账号采集 1 次，`inspect=0`、`describe=0`、`read=0`；采集证据为“云沐荟足道官方号”，回答改成“云泉谷足道”，并虚构 90/10、3–5 倍、2 倍、40% 等数字。独立评分 37/100（证据 3、机制 5、IP 14、剧情 6、可拍 7、工具 2）并触发一票否决；2 次 LLM、18,928 Token、114.2 秒。artifact SHA-256 为 `6e3707c4c4ffb3478d8bba2f5fa6ccb18548f09c653576878abbc7106e0e0c54` | 可达性修复已通过，但“只把工具变得可见就能完成链路”的豆包 2.0 方案被真实回放淘汰；不加提示词，转入第二模型的正确 treatment 对照 | 方案淘汰 |
| M2-E2c 第二模型正确 treatment 对照 | 若跳过已可见工具是豆包 2.0 的模型适配问题，则只替换模型、保持冻结输入和 v2 能力面的较强模型应继续调用视频深拆 | 隔离配置已以 `doubao-seed-evolving` 直连方舟 Chat API，运行时解析为 `doubao-seed-evolving-latest-version`。思考组成功完成 7 次 LLM 和 8 次工具执行：账号采集、三视频深拆、三次看图、一次方法发现、两次文件读取；119,809 Token，805.448 秒。原独立评分 74/100（证据 14、机制 16、IP 17、剧情 16、可拍 9、工具 2），并因“云沐荟→云沐芸”一票否决；artifact SHA-256 `0c503c94412e331e8e6746c13cafc4d9e62088604cf9a97ff2d36d2cc21a33cc`。后续已证明该专名错误来自适配器的 MCP 文本二次包装，故旧分数只作污染观测，不是模型专名能力结论。关闭思考组在 8 次 LLM、15 次工具、112,843 Token、291.774 秒后触发 100 步 `GraphRecursionError`；它读取三个方法，但两次构造了错误联系表路径再用 `ls` 纠正，无最终答案；artifact SHA-256 `14ab70236a1fab51c58697b5a534deae0ab1680f9216e9e5236bb2ada37dbd22` | Evolving 证明更强模型能走完动态证据链；专名失真的模型归因撤回，其余覆盖过度、方法交付不完整和工具效率仍不通过，转入封存证据下的单次方法归因 | 已解决 |
| M2-E2d 中文 MCP 证据保真 | 方舟模型应看到 MCP 证据的原始中文语义，而不是 DeepSeek 适配器生成的转义码和额外内嵌 JSON | 重建旧回放最后请求时，checkpoint 中“云沐荟”正确出现 11 次，旧 payload 中字面中文 0 次、转义码 11 次。修复后单文本块直接展开，多块以 Unicode JSON 保留结构；17 项适配器测试通过。真实 `doubao-seed-evolving-latest-version` 固定温度使用同一份 12 条作品证据精确复述 2/2 通过，每次 4,059 输入 + 6 输出 Token；修复前对照 2/2 错成“云沐芸”，每次 6,707 Token | 修复是适配器边界而非提示词或审查门；继续 M2-E3 | 已解决 |
| M2-E3 方法交付归因 | 用同一份封存 M1 证据、同一 Slash Skill 名称和同一单次综合调用，只替换 placebo 与组合方法正文，才能判断方法内容是否有效 | 正反序四臂均为一次 `skill_activation`、一次 LLM、零工具，请求 `c617e8525f5a3a5528db08a83aa050e68741ff73ec3321e6ac2ce0dab1ccd4e2`、证据 `9619235173040d93683e125526843bc9f5243057425d65e83cd1defc615ad488` 一致；placebo/method 正文分别为 `007581d91b2a51748c2c737f708b932cf13ed247eeeb66cf00051ab68dd012a5`/`b12dc091793dca8455c32fff6ddc50bebf4cb419425bd43386dbd8891b17b3d8`，各臂在正反序间保持不变；Token 依次为 29,808、26,811、30,210、25,434。正序 placebo/method 为 80.5/77，反序为 83/85；method/placebo 平均为 81/81.75，净增益 -0.75。正序 placebo/method 直接失败为 `F2/F3/F7`/`F1/F2/F3/F7`，反序均为 `F1`。正序 results/unblinding SHA-256 为 `08d5ca6214698ba67c68395f1986edbae43c72acfeb11f7c2c9042fb78021e45`/`a11ca407618fa0bd54240bb7c86c199d22f800ac4c85fe79a44a7cac00827a05`；反序为 `75b4404bb18ab5a998d47bb28a16a8d2ba03f40940dbde301756004b0b30a213`/`5bcde99d4190362862ffc59b6839d0f71733f58126b6df734c8f272b95858569` | 仪器成立，但六段组合方法没有净增益，也未减少证据越界；停止加提示词，转入编导因果与远距离联想方法对照 | 方案淘汰 |
| M2-E4 编导脑洞归因 | 专业创作的净增益不来自堆叠更多下游步骤，而来自“事实收敛 → 语义内核 → 跨域远联 → 同构关系冲突 → 产品成为不可替代的动作或证物 → 可拍因果” | 尚未执行。保留 M2-E3 的封存证据、placebo、模型与盲审合同；新方法只写通用编导思维，不得出现当前账号、行业、产品或历史剧情样本 | MF-E3 通过后再证明编导脑洞方法相对中性 placebo 的净增益；未通过不解冻 M3，不回复旧组合方法 | 待转化 |

## 已解决基线与保留边界

- M0 纯净基线由提交 `1c87fd8a` 建立，输入体积比污染基线下降超过 50%。
- 旧策略、差异化、预演、复盘、证据晋升、cockpit 与固定首访已由提交
  `fc61bde6` 退役，不得为解决新矛盾而恢复。
- 正式默认 IP Agent 使用八个基线工具加两个 MediaKit Evidence MCP 工具，继续保持 `skills: []` 和 `memory_enabled: false`。
- 主体、账号、OAuth、发布回执、指标观测、视频事件账本和事实工作台继续保留，
  但不生成经营或创作结论。
- Owner 隔离、凭证、OAuth、版权、披露、删除、路径、哈希、不可变回执和幂等性
  属于执行正确性，不是经营硬门，继续保留。专用视频制作面仍管理其预算；默认 MediaKit
  Evidence 路径配置 Key 后直接执行，不恢复逐次付费批准。

## 每轮回写模板

每轮实验必须在当前矛盾下追加一行：

| 字段 | 必填内容 |
| --- | --- |
| 矛盾编号 | 稳定编号，如 `M1-E1` |
| 次要矛盾 | 本轮故意不解决什么 |
| 验证假设 | 最小改动与预期因果 |
| 真实样本 | 链接、上传文件或真实任务 |
| 通过条件 | 实现前冻结，不根据结果临时改门槛 |
| 实际结果 | 完整工具调用、输出、失败、Token 或人工评分 |
| 结论 | 通过、失败、外部阻塞或方案淘汰 |
| 矛盾转化 | 仅通过时填写下一主要矛盾 |
| 提交 | 仅记录已通过验收的提交 |
