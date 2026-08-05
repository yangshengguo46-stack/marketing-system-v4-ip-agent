# IP Agent 工具与 Skill 能力库存（非产品状态台账）

复核日期：2026-08-05。

文件名保留 `LEDGER` 仅为兼容既有链接和机械测试。本文件是源码库存投影，不能发布
“已交付”“当前主线”或完成度结论；客户可达状态只看 `IP_AGENT_PRODUCT_LEDGER.md`。

这份文档是仓库内 Agent 工具与 `skills/public` 方法包的唯一分类清单，回答三件事：

1. 默认 IP Agent 此刻真正能调用什么；
2. DeerFlow 还保留哪些执行工具，但被默认 IP Agent 隔离；
3. 仓库有哪些 Skill 研究资产，它们分别解决什么问题。

产品合同仍以 `IP_AGENT.md` 为准，交付状态仍以
`IP_AGENT_PRODUCT_LEDGER.md` 为准。本清单不把“源码存在”写成“现役能力”。

## 口径与状态

本清单只统计模型可调用工具及其适配器，不把 REST API、数据库仓库、后台服务、
中间件或前端按钮重复算作工具。

| 状态 | 含义 |
| --- | --- |
| 现役 | 当前 `ip-agent` 的最终模型工具集合允许调用 |
| 保留但隔离 | 运行代码仍在，供专用界面、API、其他 Agent 或以后显式启用；默认 IP Agent 看不到 |
| 条件能力 | 只有配置、模型、模式或扩展满足条件时才组装；默认 IP Agent 仍受精确白名单约束 |
| 研究隔离 | 源码或 `SKILL.md` 可审查，但默认 `skills: []`，模型不能发现、加载或执行 |
| 已退役 | 旧语义工具、路由和表已在迁移 0021 删除，不列为可用能力 |

当前数量：

- 默认 IP Agent：10 个精确白名单工具，0 个 Skill；
- 当前全局配置：16 个配置工具，其中 6 个进入白名单，10 个被隔离；
- DeerFlow 原生固定工具：43 个，其中 `ask_clarification` 进入白名单，其余 42 个隔离；
- 公共 Skill 包：97 个，全部研究隔离；
- Evidence MCP 的 2 个 MediaKit 证据工具进入默认 IP Agent；其余 MCP、ACP、记忆、自修改、子 Agent、Skill 管理和 Plan Mode 工具不进入默认 IP Agent。

## 一、默认 IP Agent 的 10 个现役工具

来源：`product/defaults/agents/ip-agent/config.yaml`。过滤发生在配置工具、内置工具、
MCP、ACP、子 Agent、Skill 和记忆工具全部组装之后；Plan Mode 注入的
`write_todos` 也受同一能力边界约束。

<!-- BEGIN ACTIVE IP AGENT TOOLS -->
| 工具 | 能力与用途 | 边界 |
| --- | --- | --- |
| `web_search` | 对确需时效或外部证据的问题做公开网页检索，并返回可引用来源 | 不用于普通常识；当前 Ark 搜索是否可用取决于外部账号能力，失败时不得伪造来源 |
| `image_search` | 搜索公开图片和视觉参考 | 只发现参考，不证明版权、身份或视频机制 |
| `ls` | 列出允许工作区内的目录内容 | 只读，不创建、移动或删除文件 |
| `read_file` | 读取明确路径的文本或结构化文件 | 只读，按需读取，不扫描无关私有内容 |
| `glob` | 按路径模式发现文件 | 只发现候选，不读取内容、不写入 |
| `grep` | 在允许文件中搜索文本 | 只读检索，不修改命中项 |
| `view_image` | 读取并展示本地图片供视觉判断 | 仅在当前模型支持视觉时组装；不处理非图片文件 |
| `ask_clarification` | 缺少决定性材料时向用户索取一个必要信息 | 不把可自行回答的问题变成固定访谈；账号无法确认时索要平台或主页/视频链接 |
| `ip_evidence_collect_douyin_benchmark_account` | 读取用户指定的抖音主页和作品清单 | 只观察指定公开账号；不修改平台内容 |
| `ip_evidence_inspect_reference_videos` | 用本地工具链和 MediaKit 分析指定作品链接或上传视频的台词、字幕、场景和故事线 | 配置 `MEDIAKIT_API_KEY` 后直接执行云分析；返回观察结果，不把分析结果伪装成用户事实 |
<!-- END ACTIVE IP AGENT TOOLS -->

## 二、当前配置存在但被默认 IP Agent 隔离的 10 个工具

| 能力域 | 工具 | 功能 | 隔离原因 |
| --- | --- | --- | --- |
| 文件写入 | `write_file` | 新建或覆盖文件 | 当前 Agent 是只读基线 |
| 文件写入 | `str_replace` | 精确替换文件内容 | 当前 Agent 是只读基线 |
| 浏览器 | `browser_navigate` | 打开网页 | 默认公开研究走搜索，不自动打开交互浏览器 |
| 浏览器 | `browser_snapshot` | 读取渲染 DOM 快照 | 只留给显式浏览器操作流程 |
| 浏览器 | `browser_click` | 点击网页元素 | 会改变页面状态，默认隔离 |
| 浏览器 | `browser_type` | 向网页输入内容 | 可能提交敏感或外部数据，默认隔离 |
| 浏览器 | `browser_get_text` | 读取当前网页文本 | 只留给已授权渲染页/登录后台流程 |
| 浏览器 | `browser_back` | 浏览器返回 | 只留给显式浏览器会话 |
| 浏览器 | `browser_screenshot` | 截取当前网页 | 只留给显式浏览器会话和隐私边界 |
| 浏览器 | `browser_close` | 关闭浏览器会话 | 只留给显式浏览器会话 |

## 三、保留但隔离的 DeerFlow 原生工具

<!-- BEGIN ISOLATED NATIVE BUILTIN TOOLS -->
### 3.1 通用交付与 Skill 审查

| 工具 | 功能 |
| --- | --- |
| `present_files` | 把生成文件呈现给用户查看或下载；默认 IP Agent没有写入和交付文件能力，因此隔离 |
| `review_skill_package` | 只读审查一个不可信 Skill 包，不安装、不激活、不执行 |

### 3.2 发布执行与回执（5 个）

| 工具 | 功能 |
| --- | --- |
| `personal_ip_begin_publish_receipt` | 冻结一次发布请求及版权、披露和合规声明，不执行发布 |
| `personal_ip_prepare_browser_publish` | 将发布回执绑定到选定账号的隔离浏览器会话 |
| `personal_ip_finish_browser_publish` | 用帖子级公开证据封存浏览器发布结果 |
| `personal_ip_record_publish_attempt` | 追加记录 API、UI-TARS 或人工等非浏览器发布尝试 |
| `personal_ip_read_publish_receipt` | 读取一次发布请求和全部追加式尝试 |

这些是纯执行与证据工具；发布已经不依赖 preflight 或经营资格判断。

### 3.3 视频任务、合同、制作与交付（23 个）

| 工具 | 功能 |
| --- | --- |
| `personal_ip_begin_video_production` | 创建绑定任务线程的不可变视频制作请求 |
| `personal_ip_compile_video_plan` | 编译并封存无脸素材或生成电影化模式的视频计划 |
| `personal_ip_compile_video_asset_manifest` | 编译带来源、权利和哈希的素材清单 |
| `personal_ip_compile_video_storyboard` | 编译模式化分镜与逐镜合同 |
| `personal_ip_compile_video_timeline_revision` | 把人工或 Agent 的剪辑操作追加为共享时间线版本 |
| `personal_ip_compile_video_narration` | 将精确旁白文本绑定到素材型分镜 |
| `personal_ip_compile_video_material_selection` | 为每个镜头封存经画面检查和权利确认的素材区间 |
| `personal_ip_compile_video_narration_timing` | 用实际 TTS 回执校准旁白时长 |
| `personal_ip_compile_video_continuity` | 为生成型分镜编译哈希链连续性合同 |
| `personal_ip_compile_generated_shot_qa` | 计算候选镜头的确定性技术与时间门槛 |
| `personal_ip_render_local_remotion_scene` | 使用锁定版本的 Remotion 与本地 FFmpeg 渲染候选 |
| `personal_ip_run_local_generated_shot_qa` | 对本地生成镜头测量并封存机械 QA 证据 |
| `personal_ip_compile_approved_video_assembly` | 只允许已选择且 QA 通过的精确候选哈希进入组装 |
| `personal_ip_ingest_media_execution` | 校验并追加 Seedance、Seedream、语音、MediaKit 或 FFmpeg 执行回执 |
| `personal_ip_inspect_local_video_material` | 提取时间戳帧和联系表，封存本地素材机械检查 |
| `personal_ip_interpolate_video_candidate` | 用 FFmpeg `minterpolate` 生成不覆盖源文件的平滑运动候选 |
| `personal_ip_lock_video_final_edit` | 锁定最终时间线作为唯一交付 QA 输入 |
| `personal_ip_render_locked_video_delivery` | 渲染、校验并交付已锁定时间线 |
| `personal_ip_record_video_production_event` | 向同一视频账本追加阶段、供应商、审核或交付事件 |
| `personal_ip_reserve_video_budget` | 付费调用前原子预留最高预算 |
| `personal_ip_settle_video_budget` | 根据真实供应商账单结算已调用尝试 |
| `personal_ip_release_video_budget` | 仅在确认未调用供应商时释放预留 |
| `personal_ip_read_video_production` | 读取一个 Owner 范围内的视频任务及完整事件历史 |

### 3.4 平台事实、指标、本地上下文和账号目标（12 个）

| 工具 | 功能 |
| --- | --- |
| `personal_ip_collect_browser_page` | 从八平台已登录创作者页面采集详细、去凭证的业务事实 |
| `personal_ip_collect_browser_portfolio_today` | 遍历全部活跃账号，采集并汇总页面明确显示的今日数据 |
| `personal_ip_metrics_aggregate` | 汇总 Owner 全组合的可加指标，显式保留缺失、部分和不可用覆盖 |
| `personal_ip_minecontext_sync` | 通过隐私边界同步最小化本地上下文摘要 |
| `personal_ip_minecontext_evidence` | 读取已封存且用途获准的本地证据摘要 |
| `personal_ip_performance_inventory` | 列出组合范围内的连接和近期发布回执，不暴露凭证 |
| `personal_ip_platform_observation_inventory` | 列出全部账号的近期平台观察摘要与覆盖 |
| `personal_ip_read_platform_observation` | 读取一条 Owner 范围内的详细平台观察 |
| `personal_ip_record_browser_observation` | 将浏览器看到的账号、内容、受众、评论和转化事实封存为观察 |
| `personal_ip_select_browser_account` | 为下一次浏览器操作选择具体账号和隔离 Profile，不缩窄对话权限 |
| `personal_ip_sync_douyin_portfolio` | 同步全部可发现抖音已发布作品的累计计数与区间增量 |
| `personal_ip_sync_douyin_post` | 通过加密连接同步一条抖音作品的官方计数 |
<!-- END ISOLATED NATIVE BUILTIN TOOLS -->

这些工具保留真实数据采集与执行能力，但不再生成账号“继续/调整/重启”、高潜、
投流或爆款结论。

## 四、条件组装和扩展工具

| 工具或来源 | 条件 | 默认 IP Agent 状态 |
| --- | --- | --- |
| `setup_agent` | 只在 Agent 首次创建的 bootstrap 流程加入 | 隔离 |
| `update_agent` | 自定义 Agent 且为受信聊天/API入口时加入 | 精确白名单过滤；隔离 |
| `skill_manage` | `skill_evolution.enabled=true` 时加入 | 精确白名单过滤；隔离 |
| `ui_tars_desktop_step` | UI-TARS 显式开启时加入 | 精确白名单过滤；隔离 |
| `task` | 运行请求启用子 Agent 时加入 | 精确白名单过滤；隔离 |
| `tool_search` | 有延迟加载的 MCP 工具时动态生成 | Evidence MCP Schema 由精确路由自动提升；`tool_search` 本身不进入白名单 |
| `describe_skill` | 有可发现 Skill 且开启延迟发现时动态生成 | `skills: []`，不生成 |
| `invoke_acp_agent` | 配置了 ACP Agent 时动态生成 | 精确白名单过滤；隔离 |
| `memory_search` | 记忆工具模式开启 | `memory_enabled: false`，不生成 |
| `memory_add` | 记忆工具模式开启 | `memory_enabled: false`，不生成 |
| `memory_update` | 记忆工具模式开启 | `memory_enabled: false`，不生成 |
| `memory_delete` | 记忆工具模式开启 | `memory_enabled: false`，不生成 |
| `write_todos` | Plan Mode 中间件开启 | 未列入白名单，不注入 |
| MCP 工具 | `extensions_config.json` 中服务器启用并成功连接 | `ip_evidence` 默认启用且 required；其他 MCP 仍受精确白名单 |
| `ip_evidence_collect_douyin_benchmark_account` | 默认 `ip_evidence` MCP | 限域读取一个精确抖音主页；最多 12 条作者归属可验证作品；默认 Agent 现役 |
| `ip_evidence_inspect_reference_videos` | 默认 `ip_evidence` MCP；配置 `MEDIAKIT_API_KEY` | 检查最多 3 条精确视频/上传文件；Agent 公开参数固定为 `full + 12`，一次执行本地证据、ASR、OCR、场景切分和故事线；内部历史深度不是模型选择；每个 stage 隔离，外层超时 3600 秒；默认 Agent 现役 |

这两个条件工具来自同一个自研 stdio Capability MCP。MCP 内部使用确定性 Manifest、
能力探测、精确 Child 绑定、运行上限和输入/输出 Schema 校验；抖音只是首个平台 Child。
以后新增或恢复的平台、供应商、浏览器、重媒体、发布和有状态执行能力沿用同一骨架，
不得注册成新的 Agent 原生特例。正式默认配置是八个基线工具加两个 Evidence MCP 工具。

仓库还保留 `personal_ip_collect_douyin_browser_page` 这个抖音页面采集兼容包装器，
但它没有进入 `BUILTIN_TOOLS`，因此不是模型可调用工具；现役统一入口是
`personal_ip_collect_browser_page`。

## 五、仓库中的可替换工具适配器

这些不是额外并列能力，而是为同一个模型工具名提供不同实现；只有配置选中的实现会组装。

| 统一工具名 | 可选实现 |
| --- | --- |
| `web_search` | Volcengine Ark Responses Web Search、DuckDuckGo、SearXNG、Serper、Brave、Tavily、InfoQuest、Exa、Firecrawl、GroundRoute、FastCRW |
| `web_fetch` | Jina AI、Browserless、Crawl4AI、Exa、Tavily、InfoQuest、Firecrawl、GroundRoute、FastCRW |
| `image_search` | 内置图片搜索、InfoQuest、Serper、Brave |
| `web_capture` | Browserless 页面捕获 |
| `bash` | 沙箱命令执行；本项目当前配置没有注册，LocalSandbox 也默认禁止宿主 Bash |

## 六、97 个公共 Skill：全部研究隔离

以下 97 个目录均真实存在于 `skills/public/*/SKILL.md`，但默认 IP Agent 的
`skills: []` 使它们不可发现、不可加载、不可执行。这里的“功能”只说明研究意图，
不代表已经通过新 IP 第一性原理架构评审，也不代表其旧工具依赖仍可运行。

<!-- BEGIN PUBLIC SKILL INVENTORY -->
### 6.1 IP 战略、内容校准与八平台诊断（13）

| Skill | 能力与功能 |
| --- | --- |
| `personal-ip-operator` | 已退役 Personal-IP 总控的研究快照；只用于回看旧方法，不是现役编排器 |
| `ip-strategy-director` | 为人、品牌、产品或组织研究 IP 形态、定位、对标、身份、产品与转化方向 |
| `design-ip-differentiation` | 从独有事实构造可验证的差异化论题、识别系统与选择理由 |
| `ip-content-calibration` | 研究选题、脚本、预测、发布后复盘和受众学习的校准循环 |
| `engineer-audience-response` | 把注意、情绪互动、分享和关注/收藏/行动转成可观察的内容设计假设 |
| `diagnose-douyin-account` | 研究抖音内容、账号、业务事实与平台资格诊断 |
| `diagnose-wechat-channels-account` | 研究视频号内容、社交分发、账号与业务诊断 |
| `diagnose-wechat-official-account` | 研究公众号文章、订阅、分享、搜索与转化诊断 |
| `diagnose-xiaohongshu-account` | 研究小红书笔记、搜索、收藏、受众与转化诊断 |
| `diagnose-x-account` | 研究 X 的内容、关系网络、推荐资格与业务诊断 |
| `diagnose-instagram-account` | 研究 Instagram/Reels 内容、推荐资格、受众与业务诊断 |
| `diagnose-youtube-account` | 研究 YouTube 长短视频、搜索、推荐、满意度与转化诊断 |
| `diagnose-tiktok-account` | 研究 TikTok For You 资格、内容行为、受众与转化诊断 |

### 6.2 电影化 IP 方法矩阵（35）

| Skill | 能力与功能 |
| --- | --- |
| `build-cinematic-ip-system` | 路由电影化 IP 的证据、叙事、类型、单集、视听、表演和连续性研究 |
| `query-cinematic-library` | 检索本地 358 部影片、393 位创作者和 304 张机制卡 |
| `run-cinematic-curriculum` | 运行编剧、导演、摄影、剪辑、声音、表演、美术、纪录八轨训练 |
| `ingest-ip-evidence` | 区分事实、证词、推断、假设、未知、隐私和授权 |
| `calibrate-cinematic-ip` | 研究电影方法的预测、发布观察、复盘与方法校准；旧原生语义依赖已退役 |
| `distill-screen-methods` | 跨影片、主创、课程和资料蒸馏可迁移的影视机制卡 |
| `engineer-desire-behavior` | 将本能驱力、欲望、目标和需要转成行动、反作用、选择与代价 |
| `design-ip-series-bible` | 设计长期前提、人物弧、关系引擎、世界规则、季结构和连续性 |
| `route-ip-genre-engine` | 为叙事化 IP 选择或混合类型并生成持续冲突规则 |
| `shape-ip-emotion` | 设计账号生命周期、季度、单集、场景和镜头的情绪层级 |
| `write-ip-episode` | 将素材或选题写成可拍且推进长期线的单集 |
| `direct-ip-visual-language` | 把故事与情绪转成总体导演意图和视听语法 |
| `coach-ip-screen-performance` | 把台词和情绪转成真人、素人或演员可执行的表演任务 |
| `audit-ip-continuity` | 审查单集事件、人物变化、长期证据、情绪、类型和视听连续性 |
| `develop-theme-premise` | 提炼主题问题、反题、强前提和长期观看理由 |
| `design-character-relations` | 设计人物目标、需要、盲点、能力、底线、关系功能与变化弧 |
| `engineer-plot-information` | 组织因果、信息差、线索、误导、揭示、转折与回收 |
| `write-scenes-dialogue` | 编写具有目标、阻力、策略变化、转向和潜台词的场景对白 |
| `direct-scene-blocking` | 用站位、距离、视线、遮挡、物件和空间变化表达关系与权力 |
| `design-cinematography` | 设计实拍视点、焦段、机位、构图、运动、纵深和覆盖 |
| `design-light-color-texture` | 建立系列光线、色彩、质感、Look、LUT 与调色规则 |
| `edit-screen-rhythm` | 按理解、表演、动作、情绪和声音设计剪切与整体节奏 |
| `design-screen-sound` | 在前期设计对白、环境、画外空间、主观听觉、音乐与静默 |
| `design-production-world` | 用空间、道具、服装、材质、时代和生活痕迹外化人物与世界 |
| `previsualize-screen-direction` | 汇总导演阐述、跨部门视听规则、预演、拍摄优先级和风险 |
| `write-mystery-thriller` | 设计谜题、公平线索、调查、威胁、误导、揭示和回收 |
| `write-comedy-satire` | 用盲点、错位、地位交换、升级和回收设计喜剧与讽刺 |
| `write-crime-power-western` | 设计资源、合法性、组织规则、联盟、背叛、暴力阈值和代价 |
| `write-romance-family-growth` | 设计亲密、家庭、代际、边界、照护、误读与成长选择 |
| `write-scifi-fantasy-animation` | 建立新规则、思想实验、世界边界、视觉隐喻和伦理选择 |
| `write-horror` | 设计安全基线、威胁规则、显露与遮蔽、隔离和残余恐惧 |
| `write-action-adventure` | 设计目标、地理、路径、资源、障碍、升级与身体后果 |
| `write-war-history-epic` | 连接研究事实、私人选择、群体行动、制度、地理与历史后果 |
| `write-musical-performance` | 设计音乐进入点、歌词行动、节奏、身体、摄影和关系变化 |
| `write-documentary-reality` | 不伪造现实地设计任务、选择、场景日志、未知结果、同意与伦理 |

### 6.3 对标视频、参考素材与方法提取（4）

| Skill | 能力与功能 |
| --- | --- |
| `video-pattern-learning` | 从有时间证据的视频提取脚本、镜头、剪辑、字幕、声音、表演与转化模式 |
| `video-method-distillation` | 以 Cangjie 方法从长视频、课程、访谈或播客提炼原子方法候选 |
| `precise-video-description` | 将观察到的视频转成客观、按时间排序的主体、场景、运动、空间和摄影描述 |
| `reference-media-analysis` | 在权利和非模仿边界内拆解图片、视频、声音、品牌资产与参考样片 |

### 6.4 生成媒体专业工种（12）

| Skill | 能力与功能 |
| --- | --- |
| `asset-continuity-management` | 管理生成/参考资产、prompt、seed、模型、版本、派生、批准和连续性 |
| `captions-media-accessibility` | 规划、制作和 QA 字幕、SDH、转录、音频描述、闪烁与运动安全 |
| `character-design-continuity` | 建立生成角色 bible、身份锁、表情、姿态、服装和跨镜连续性 |
| `cinematic-shot-direction` | 为 AI 或混合媒体设计精确镜头、覆盖、运动、轴线和可剪连续性 |
| `color-grading-finishing` | 负责校色、镜头匹配、Look、HDR/SDR 色彩管理与最终 QA |
| `dialogue-editing-adr` | 负责对白清理、补录、配音、同步、可懂度、响度和交接 |
| `lighting-direction` | 为生成图片、视频、头像和产品镜头设计灯光规格、连续性与故障修复 |
| `music-supervision-scoring` | 负责音乐任务、版权、配乐、选曲、cue、stem、混音和交接 |
| `performance-direction` | 指导演员替身、数字人、动画角色和 AI 声音的表演与 QA |
| `production-design-direction` | 将叙事、品牌和产品意图转成生成布景、道具、材质和时代规格 |
| `sound-design-foley` | 规划、生成、编辑和 QA Foley、环境、效果、转场和主观声音 |
| `visual-style-direction` | 将 brief 与参考转成原创视觉 token、色彩、构图、材质、镜头和运动系统 |

### 6.5 端到端媒体生产工作流（4）

| Skill | 能力与功能 |
| --- | --- |
| `brand-launch-film-production` | 从已批准品牌战略生产发布片、宣言片、Hero Film 和多平台裁切 |
| `product-ad-production` | 从产品事实、主张、证明和受众任务生产并迭代产品广告 |
| `ugc-ad-production` | 生产 UGC、证言、演示、合规变体和披露明确的合成人物广告 |
| `talking-head-podcast-recut` | 将口播、访谈、播客、直播等长素材安全重组为短内容 |

### 6.6 MediaKit 媒体执行（5）

| Skill | 能力与功能 |
| --- | --- |
| `byted-mediakit-shared` | MediaKit 环境、鉴权、命令、异步任务和错误处理公共规则 |
| `byted-mediakit-editing` | 拼接、裁剪、合成、变速、音量、滤镜、淡入淡出与封装 |
| `byted-mediakit-video` | 视频增强、理解、字幕、抠像、元数据、场景分段与 OCR |
| `byted-mediakit-image` | 图像 OCR、擦除、抠图、增强和质量评估 |
| `byted-mediakit-audio` | 人声分离与音频元数据分析 |

### 6.7 供应商路由与媒体生成（5）

| Skill | 能力与功能 |
| --- | --- |
| `volcengine-stack` | 在字节/火山模型、图像、视频、语音、理解、编辑和计算机操作能力间路由 |
| `image-generation` | 根据结构化提示和参考图生成图片 |
| `video-generation` | 根据结构化提示和参考图生成视频 |
| `music-generation` | 使用 MiniMax 音乐 API 生成配乐、主题曲、广告歌或器乐 |
| `podcast-generation` | 将文本转换成双主持人对话式播客音频 |

### 6.8 通用研究、数据与文档（8）

| Skill | 能力与功能 |
| --- | --- |
| `academic-paper-review` | 审阅单篇论文的方法、贡献、文献位置和改进建议 |
| `systematic-literature-review` | 跨多篇论文做系统综述、调查、注释书目和格式化引用 |
| `deep-research` | 对需要时效与多来源的问题做开放网络研究和交叉验证 |
| `github-deep-research` | 对 GitHub 仓库做多轮时间线、指标、竞争与结构研究 |
| `consulting-analysis` | 先设计研究框架，再生成咨询级市场、消费者、品牌或行业报告 |
| `data-analysis` | 分析 Excel/CSV，执行统计、聚合、筛选、连接和导出 |
| `chart-visualization` | 从 26 种图表中选择并生成数据可视化 |
| `code-documentation` | 生成或改进 README、API 文档、架构说明、注释和开发者指南 |

### 6.9 软件设计、集成与部署（4）

| Skill | 能力与功能 |
| --- | --- |
| `frontend-design` | 设计并实现高完成度网页、组件、仪表盘和应用界面 |
| `web-design-guidelines` | 审查 UI、UX、可访问性和 Web 界面规范 |
| `vercel-deploy-claimable` | 创建可认领的 Vercel 预览或生产部署 |
| `claude-to-deerflow` | 通过 HTTP API 调用 DeerFlow、管理任务、上传文件和查询状态 |

### 6.10 其他内容形态（2）

| Skill | 能力与功能 |
| --- | --- |
| `newsletter-generation` | 研究、策划并生成邮件简报、周报或行业摘要 |
| `ppt-generation` | 生成视觉化幻灯片并组合成 PPT/PPTX |

### 6.11 Agent 初始化与 Skill 治理（5）

| Skill | 能力与功能 |
| --- | --- |
| `bootstrap` | 通过适应式对话生成或更新自定义 Agent 的 `SOUL.md` |
| `find-skills` | 发现可能存在的可安装 Skill |
| `skill-creator` | 创建、修改、评测和优化 Skill 及其触发描述 |
| `skill-reviewer` | 审查 Skill 的触发、结构、安全、资源、证据和发布准备度 |
| `surprise-me` | 动态发现并组合多个已启用 Skill 产生创意展示 |
<!-- END PUBLIC SKILL INVENTORY -->

## 七、库存解释边界

- 默认 IP Agent 的专业度目前来自模型、精简 SOUL 和只读证据工具，不来自上述 97 个 Skill。
- 35 个电影模块、Cangjie、平台诊断、HLLM 和视频学习仍是研究库存；未经统一语义审计前不得接回默认运行链。
- 账号、发布、指标、观察和视频工具是事实采集或确定性执行器，不负责定义 IP 战略和创意判断。
- 版权、披露、付费、删除、Owner 隔离、路径、哈希、候选一致性与幂等是安全/执行边界，不属于已退役的经营语义门禁。
- REST API 和专用工作台可以继续调用保留服务；这不等于聊天 Agent 获得了相应模型工具。
- 三板块产品主线见产品总台账。未来启用 Skill 时，应从本库存选择经过纵切验证的最小方法，而不是把 97 个包一次性重新挂回去。

## 八、维护规则

新增、删除或重命名工具/Skill 时，必须在同一提交更新本清单。根测试会核对：

- “现役工具”表与默认 `tool_allowlist` 完全一致；
- 公共 Skill 表与 `skills/public/*/SKILL.md` 完全一致且当前为 97 个；
- Plan Mode 不得绕过 operator 白名单注入 `write_todos`。

历史分类、旧 77-Skill 激活表和旧运行编排由 Git 保存，不在本文继续累积。
