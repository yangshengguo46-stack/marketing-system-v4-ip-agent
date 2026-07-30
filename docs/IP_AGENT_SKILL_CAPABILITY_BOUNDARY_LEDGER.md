# IP Agent Skill 能力与边界台账

审计日期：2026-07-30

主报告：
[IP_AGENT_INFLUENCE_ASSET_FIRST_PRINCIPLES_RESEARCH.md](IP_AGENT_INFLUENCE_ASSET_FIRST_PRINCIPLES_RESEARCH.md)

## 台账口径

仓库有 96 个公共 Skill 包，其中 77 个在
`product/defaults/agents/ip-agent/config.yaml` 中激活。本台账逐项覆盖这 77 个激活包。

层级：

- `O`：编排与路由
- `D`：决策与创意意图
- `S`：生产规格
- `X`：工具执行
- `E`：证据、QA 与学习

处置：

- `保留`：边界基本清楚
- `扩域`：能力可保留，但需要从个人创作者扩展到多载体 IP
- `收窄`：与兄弟 Skill 重叠，需要限制触发和输出
- `共享协议`：保留多个入口，但公共逻辑应抽到同一引用或编译器
- `下游`：只能消费已批准策略，不能代替 IP 资产战略
- `可选`：不是普通用户主流程，只在明确需求时调用

## 一、产品总控

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `personal-ip-operator` | O/E | 读取 owner-scoped 产品状态，协调策略、账号、视频、发布、指标和复盘 | 它是产品运行总控，不应亲自发明电影方法或平台规则；账号只作为具体操作目标 | 扩域为多载体 IP 组合总控 |
| `design-ip-differentiation` | D/E | 把人、品牌、产品或组织的独有事实编译成可验证差异化论题 | 位于经营策略与电影化表达之前；只产出选择、戏剧和识别协议，不替代脚本、工种或平台适配 | 新增并接入原生版本/观察账本 |

## 二、八平台账号诊断

八个 Skill 都只能补充平台的一手规则、资格限制和表面适配。内容七层、漏斗、样本门槛、
新号结构性证据和最终决策必须由一个服务端编译器统一。

| Skill | 层级 | 唯一职责 | 平台特殊边界 | 处置 |
| --- | --- | --- | --- | --- |
| `diagnose-douyin-account` | D/E | 抖音内容、推荐资格、商业漏斗和账号结构诊断 | 不把流量池传说或低播放当作死号证据 | 共享协议，保留抖音一手来源 |
| `diagnose-wechat-channels-account` | D/E | 视频号内容、社交分发与账号约束 | 当前一手证据不足时不得编造统一排名公式 | 共享协议 |
| `diagnose-wechat-official-account` | D/E | 公众号文章、订阅、分享、搜一搜与转化诊断 | 图文和订阅关系不能照搬短视频指标 | 共享协议 |
| `diagnose-xiaohongshu-account` | D/E | 小红书笔记、搜索、收藏、分享、意向与转化 | 搜索和社区语境是平台适配，不代替内容价值 | 共享协议 |
| `diagnose-x-account` | D/E | X 的内容、网络关系、推荐资格与转化诊断 | 开源推荐系统证据不能被误写成普遍内容规律 | 共享协议 |
| `diagnose-instagram-account` | D/E | Instagram 内容、Reels、推荐资格与转化诊断 | 格式适配和资格修复优先于平台玄学 | 共享协议 |
| `diagnose-youtube-account` | D/E | YouTube 搜索、推荐、满意度、观看与转化诊断 | 长短视频和搜索意图需区分 | 共享协议 |
| `diagnose-tiktok-account` | D/E | TikTok For You 资格、内容行为和转化诊断 | 资格限制可证明，未公开权重必须保持未知 | 共享协议 |

本轮实施后仍有的共同缺口：

- 策略 v4 已用独立的影响力、行为和经济目标替代旧二分决策；旧
  `objective_mode` 只为历史行兼容，仍需要后续数据库迁移彻底移除；
- 账号诊断 v2 已同时编译影响力、行为与经济结果：品牌认知成功但暂未转化不会被误判为
  “自娱自乐”；三类结果存在未测量项时只能保持未证实；
- 已有识别、信任、意向、采用、转化、经济和延展观察契约，并区分支持、反证、混合和
  不确定结果，但还缺真实主体的纵向样本；
- 八份公共决策文本容易漂移。

## 三、电影化 IP 矩阵：1 个编排层

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `build-cinematic-ip-system` | O | 编排真实证据、研究、长期叙事、单集和影视工种 | 只能在 IP 资产方向或叙事问题明确后进入；不能代替人物/品牌/产品的资产战略总控 | 收窄为“电影化表达子系统” |

## 四、电影化 IP 矩阵：4 个操作系统

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `query-cinematic-library` | D/E | 从 358 部影片、393 位创作者和 304 张机制卡中选证据样本 | 只检索本地权威库，不代替最新网络研究，也不直接仿写风格 | 保留 |
| `run-cinematic-curriculum` | D/E | 运行八轨 96 模块的工种训练、评分和补课 | 是用户或团队训练，不是每个创作任务的必经步骤 | 可选 |
| `ingest-ip-evidence` | D/E | 区分事实、证词、推断、假设、隐私和同意 | 目前偏真人经历；应接入品牌、产品、角色、方法和权利证据 | 扩域 |
| `calibrate-cinematic-ip` | E | 冻结预测、登记发布、回收指标、复盘并晋升方法 | 不负责写稿或改写历史预测；应扩展到 IP 资产观测 | 扩域 |

## 五、电影化 IP 矩阵：9 个基础模块

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `distill-screen-methods` | D/E | 跨影片、主创、课程和资料综合影视机制 | 不处理单条长视频的原子方法安装，也不做客观视频描述 | 保留 |
| `engineer-desire-behavior` | D | 把人物欲望转成可观察行动、代价和状态变化 | 是叙事发动机，不是所有品牌和产品 IP 的必经步骤 | 收窄为叙事场景 |
| `design-ip-series-bible` | D | 长期前提、人物弧、关系、世界、季度与连续性 | 需要版本化 creative bible；不能只存在聊天 | 保留并补原生契约 |
| `route-ip-genre-engine` | D | 选择或混合题材并生成持续冲突规则 | 只有叙事化内容需要，不能把每个产品账号都影视类型化 | 收窄 |
| `shape-ip-emotion` | D | 设计生命周期、季度、单集、场景和镜头的情绪层级 | 是体验承诺的一部分，不等于完整品牌意义或关系战略 | 保留 |
| `write-ip-episode` | D/S | 将真实素材或选题写成独立成立并推进长期线的单集 | 消费已批准前提、证据和试验目标，不独立定义 IP 定位 | 下游 |
| `direct-ip-visual-language` | D/S | 把故事和情绪转成总体导演意图与视听语法 | 应停在高层导演意图，精确镜头、灯光和生成规格交给工种 Skill | 收窄 |
| `coach-ip-screen-performance` | S | 把真人、素人或演员台词转成可演任务和多条变化 | 只负责真人表演指导；“是否该真人出镜”由表达路由决定 | 收窄并接表现评估 |
| `audit-ip-continuity` | E | 审查故事承诺、人物变化、类型、情绪、真实性和长期连续性 | 不管理生成资产版本，也不代替机械媒体 QA | 保留 |

## 六、电影化 IP 矩阵：11 个工种实验室

| Skill | 层级 | 唯一职责 | 与相邻 Skill 的边界 | 处置 |
| --- | --- | --- | --- | --- |
| `develop-theme-premise` | D | 主题问题、反题、强前提和长期观看理由 | 不做商业定位，不把社会观察冒充用户证据 | 保留 |
| `design-character-relations` | D | 人物目标、需要、盲点、能力、底线、关系功能和弧 | 只处理叙事角色和关系，不等于 IP entity graph | 保留 |
| `engineer-plot-information` | D/S | 因果、信息差、线索、误导、揭示、转折和回收 | 不负责平台钩子公式或剪辑执行 | 保留 |
| `write-scenes-dialogue` | D/S | 场景目标、阻力、策略变化、潜台词和对白行动 | 不负责整集结构和表演执行 | 保留 |
| `direct-scene-blocking` | S | 站位、距离、视线、遮挡、物件和空间变化 | 不决定摄影机参数，不替代表演动机 | 保留 |
| `design-cinematography` | S | 真人/实拍的叙事视点、焦段、机位、运动和覆盖 | 与生成镜头 Skill 区分，优先现场拍摄语法 | 收窄 |
| `design-light-color-texture` | D/S | 系列或影片的光色、质感、Look、LUT 和调色管线 | 是影像 look bible；单镜头灯光和最终调色分别下交 | 收窄 |
| `edit-screen-rhythm` | D/S | 按观众理解、表演、动作、情绪和声音决定剪切 | 不执行机械裁剪、拼接、变速和导出 | 保留 |
| `design-screen-sound` | D/S | 剧本阶段的声音视点、空间、母题、动态、音乐和静默 | 后续 ADR、Foley、音乐选择与混音由专业 Skill | 收窄 |
| `design-production-world` | D/S | 用空间、道具、服装、材质和生活痕迹表达人物和世界 | 做叙事意义；生成生产规格交给 production design | 收窄 |
| `previsualize-screen-direction` | O/S | 导演阐述、跨部门语法、预演需求、拍摄优先级和风险 | 汇总已批准工种意图，不重做全部专业设计 | 保留 |

## 七、电影化 IP 矩阵：10 个类型编剧室

类型编剧室是可选的内容生成器，不是十种 IP 类型，也不是十个通用增长引擎。

| Skill | 层级 | 唯一职责 | 处置 |
| --- | --- | --- | --- |
| `write-mystery-thriller` | D/S | 谜题、公平线索、调查、威胁、误导、揭示与回收 | 保留，按需 |
| `write-comedy-satire` | D/S | 盲点、错位、地位交换、升级、回收与讽刺边界 | 保留，按需 |
| `write-crime-power-western` | D/S | 资源、合法性、组织规则、联盟、背叛、暴力阈值与代价 | 保留，按需 |
| `write-romance-family-growth` | D/S | 亲密、家庭、代际、边界、照护、误读和成长选择 | 保留，按需 |
| `write-scifi-fantasy-animation` | D/S | 新规则、思想实验、世界边界、视觉隐喻和伦理选择 | 保留，按需 |
| `write-horror` | D/S | 安全基线、威胁规则、显露与遮蔽、隔离和残余恐惧 | 保留，按需 |
| `write-action-adventure` | D/S | 目标、地理、路径、资源、障碍、动作升级和身体后果 | 保留，按需 |
| `write-war-history-epic` | D/S | 研究事实、私人选择、群体行动、制度、地理和历史后果 | 保留，按需 |
| `write-musical-performance` | D/S | 音乐进入点、歌词行动、节奏、身体、摄影与关系变化 | 保留，按需 |
| `write-documentary-reality` | D/S | 不造假地组织现实任务、选择、场景日志、未知结果和同意 | 保留，按需 |

共同边界：

- 先有真实证据、资产方向和内容目标，再选类型；
- 类型不能改变产品事实、权利和用户承诺；
- 类型输出必须回到单集、生产和校准契约；
- 一个品牌或产品不需要被强行选成某种电影类型。

## 八、策略与视频学习

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `ip-strategy-director` | O/D | 自然对话中的实体证据、影响力/行为/经济目标、商业、对标、差异化、定位、身份包和试验 | 已支持人物、品牌、产品、组织并绑定差异化版本；更多实体 subtype 与关系图仍待补 | 扩域 |
| `ip-content-calibration` | D/E | 选题、脚本、预测、发布、复盘和规则学习 | 不定义主体身份；应把平台表现与 IP 资产表现分开 | 扩域 |
| `video-pattern-learning` | D/E | 从视频提取八类生产语法并生成有范围的实验候选 | 只学习生产模式，不提取长视频知识方法，也不复制受保护表达 | 保留 |
| `video-method-distillation` | D/E | 从长视频、课程、访谈和播客提取原子方法候选 | 不做视觉模仿；要求时间证据、跨上下文和兄弟混淆测试 | 保留 |

## 九、通用研究与生成

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `volcengine-stack` | O/X | 在火山/字节能力间选择模型、媒体、语音、理解或计算机操作 | 只做供应商能力路由，不能定义 IP 战略 | 保留 |
| `deep-research` | D/E | 对当前外部问题做多角度网络研究与交叉验证 | 与本地电影库区分；最新平台规则和市场事实走这里 | 保留 |
| `image-generation` | X | 执行图像生成和参考图引导 | 消费已批准视觉与权利规格，不自行决定品牌系统 | 下游 |
| `video-generation` | X | 执行视频生成和参考图引导 | 消费镜头、连续性、预算和 QA 规格 | 下游 |
| `podcast-generation` | X | 将文本转成双主持人播客音频 | 只在内容形式被选择后执行，不默认代表 IP 声音 | 下游 |

## 十、MediaKit 执行

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `byted-mediakit-shared` | X/E | 环境、鉴权、命令结构、模式、异步任务和错误规则 | 只提供公共执行规则 | 保留，修 frontmatter |
| `byted-mediakit-editing` | X | 拼接、裁剪、合成、变速、音量、滤镜和封装 | 不决定叙事剪切点 | 保留，修 frontmatter |
| `byted-mediakit-video` | X/E | 视频增强、理解、字幕、抠像、元数据、分段和 OCR | 分析结果是证据，不自动成为策略 | 保留，修 frontmatter |
| `byted-mediakit-image` | X/E | OCR、擦除、抠图、增强和质量评估 | 不定义视觉风格 | 保留，修 frontmatter |
| `byted-mediakit-audio` | X/E | 人声分离和音频元数据 | 不替代声音设计和混音决策 | 保留，修 frontmatter |

共同问题：五个包的 YAML frontmatter 含当前规范不接受的 `version` 顶层字段；
`allowed-tools: [bash]` 不能在激活时把总控已有的原生工具裁掉。

## 十一、生成媒体专业工种

| Skill | 层级 | 唯一职责 | 与第一方电影化 Skill 的边界 | 处置 |
| --- | --- | --- | --- | --- |
| `reference-media-analysis` | D/S/E | 参考素材的权利、来源、功能拆解、非模仿转译和交接 | 先做安全参考，不直接安装成生产方法 | 保留 |
| `precise-video-description` | E/S | 客观、按时间描述主体、场景、运动、空间和摄影 | 不做创意解释、策略和无障碍字幕 | 保留 |
| `cinematic-shot-direction` | S | 生成/混合媒体的精确镜头、覆盖、运动和可剪连续性 | 消费导演意图；与真人实拍摄影设计区分 | 收窄 |
| `visual-style-direction` | D/S | 将品牌或创意 brief 转成原创、可移植的视觉 token 系统 | 不做供应商 prompt；主文 745 行需渐进披露 | 保留并拆 references |
| `character-design-continuity` | S/E | 生成角色 bible、身份锁、表情、服装、姿态和多镜头连续性 | 管角色外观资产，不审查长期故事承诺 | 保留 |
| `production-design-direction` | S | 将世界和品牌意图转成生成布景、道具、材质和时代规格 | 消费叙事美术意图，不重定义世界意义 | 收窄 |
| `lighting-direction` | S/E | 单镜头或一组镜头的生成灯光规格、连续性和故障修复 | 消费 look bible，不负责最终调色 | 收窄 |
| `performance-direction` | S/E | 合成表演者、头像、动画角色和 AI 声音的表演规格与 QA | 不指导真实用户，也不决定是否选数字人 | 收窄 |
| `asset-continuity-management` | E | 生成/参考资产、prompt、seed、模型、版本、派生和批准管理 | 管生产资产，不管叙事承诺 | 保留 |
| `dialogue-editing-adr` | S/E | 对白清理、补录、配音、同步、可懂度和交接 | 消费声音叙事意图，不选故事内容 | 保留 |
| `sound-design-foley` | S/E | Foley、环境、效果、转场、主观声音、编辑和 QA | 不替代前期声音叙事 | 保留 |
| `music-supervision-scoring` | D/S/E | 音乐任务、版权、配乐、选曲、cue、混音和交接 | 音乐服务已批准的情绪与结构 | 保留 |
| `captions-media-accessibility` | S/E | 字幕、SDH、转录、音频描述、闪烁/运动安全和本地化 | 不等于视频客观描述；是交付与可达性职责 | 保留 |
| `color-grading-finishing` | S/E | 校色、匹配、look、色彩管理、HDR/SDR 和最终 QA | 消费光色 bible，不重新设计品牌视觉 | 保留 |

## 十二、成片工作流

| Skill | 层级 | 唯一职责 | 上下游边界 | 处置 |
| --- | --- | --- | --- | --- |
| `brand-launch-film-production` | O/S/E | 将已批准品牌战略转成发布片、宣言片、hero video 和 cutdown | 它生产品牌片，不建立长期品牌 IP 战略 | 下游 |
| `product-ad-production` | O/S/E | 从产品事实、claim、证明和受众任务生产并迭代广告 | 它生产产品广告，不建立产品 IP、采用和延展系统 | 下游 |
| `ugc-ad-production` | O/S/E | 生产 UGC、证言、演示、合规变体和 synthetic persona 广告 | 需要真实权利、claim 和披露，不能伪造用户证言 | 下游 |
| `talking-head-podcast-recut` | O/S/E | 将长口播、访谈、播客和直播安全切成短内容 | 只能重组已有来源，不得断章取义或擅自构造 IP 立场 | 下游 |

这四个工作流证明系统已经能为品牌和产品“做片”，但不能证明系统已经能为品牌和产品
“建 IP”。它们必须消费上游资产策略、产品事实、表达路由和试验目标。

## 十三、95 个公共包中未激活的 19 个

未激活包：

```text
academic-paper-review
bootstrap
chart-visualization
claude-to-deerflow
code-documentation
consulting-analysis
data-analysis
find-skills
frontend-design
github-deep-research
music-generation
newsletter-generation
ppt-generation
skill-creator
skill-reviewer
surprise-me
systematic-literature-review
vercel-deploy-claimable
web-design-guidelines
```

判断：

- 这些大多是通用研究、数据、开发、部署或其他内容形式能力；
- 不应为了“能力越多越好”全部塞进 IP Agent；
- `skill-reviewer` 和 `skill-creator` 应留在内部治理或明确的开发操作中，不能成为客户可见
  的 Skill 管理面；
- `music-generation`、`newsletter-generation` 等只有在目标内容形式明确时才应动态加入，
  不应扩大默认上下文；
- 通用 `consulting-analysis` 和 `data-analysis` 可以作为后备能力，但不能替代 IP 资产的
  类型化策略和证据契约。

## 十四、跨 Skill 强制交接规则

| 上游 | 下游 | 强制交接内容 |
| --- | --- | --- |
| IP 差异化论题 | 经营策略与电影化总控 | 精确版本、主要/支持实体、目标公众与影响、替代选择、独有事实、选择/相信理由、主动舍弃、戏剧发动机、识别不变量/可控变量/禁用组合、测试和边界 |
| 账号诊断 | 内容试验 | 失败层、样本与覆盖、保持不变变量、预测信号和失败条件 |
| 对标入口 | 模式/方法 Skill | 来源权利、时间证据、分析目的和禁止复制项 |
| 导演意图 | 专业工种 | 戏剧任务、关系、情绪、连续性和预算 |
| look bible | 灯光/调色 | 不变量、容差、参考、色彩管理和品牌/肤色保护项 |
| 真人表达路由 | 表演指导 | 为什么由此人表达、受众、目标行为、可训练问题和同意 |
| 生成表达路由 | synthetic performance | 角色身份、权利、声音/脸同意、行为范围和披露 |
| 编辑意图 | MediaKit | 精确输入、时间范围、操作、输出和 QA；MediaKit 不自行选择剪切点 |
| 生产候选 | QA/交付 | 同一候选 ID、源哈希、选择、QA、组装和最终输出哈希 |
| 发布前预测 | 发布/指标 | 不可变 variant、账号目标、分发假设、观察窗和失败条件 |
| 复盘 | 证据晋升 | 三个不同发布回执、完整覆盖、比较结论和适用范围 |

## 十五、审计结论

77 个 Skill 不是“太多所以应该删除一半”，也不是“已经很多所以不缺能力”。正确结论是：

- 下游表达、制作和执行能力丰富；
- 上游多载体 IP 资产战略薄弱；
- 资产关系、目标模型、IP equity、表现评估和长期创作真相缺少原生契约；
- 多组兄弟 Skill 有合理专业差异，但还没有把差异写成稳定的触发、输入和交接边界；
- 当前大部分 Skill 的保证级别仍是静态存在和局部测试，不是全栈行为回归。

下一轮应先补产品真相与四层路由，再逐组修 Skill 描述和测试；不要继续无边界地增加媒体
工种。
