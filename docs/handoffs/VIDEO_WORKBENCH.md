# IP Agent video production workbench handoff

Date: 2026-07-22

Branch: `parallel/video-workbench`

Baseline: `3e56b0a`

## Delivered

- Added the pure `personal-ip-video-workbench-v1` projection and an owner-scoped
  Gateway read endpoint derived from the existing immutable production ledger.
- Added the dedicated `/workspace/personal-ip/video` master-detail workbench
  for projects, nine stages, script/blueprint, assets, storyboard, tasks and
  retries, candidates and consistency, voice/timeline, delivery QA and receipt
  details.
- Kept creation, progression and recovery in DeerFlow conversations through the
  native begin/event/read tools. No second runtime, state machine, migration or
  mutable projection was introduced.
- Restricted workbench confirmations to candidate selection, real paid calls
  and real publishing. Business evidence is never auto-promoted into a rule.
- Preserved provider/model/task id, cost state, failure category, attempt,
  `retry_of`, artifact/hash and QA evidence while stripping query/fragment data
  from displayed artifact references.
- Connected the read model to the receipt shape emitted by the existing free
  local video E2E.
- Added optional ledger-derived asset version/coverage/lineage, structured
  first/last-frame shot semantics, adjacent-shot bridge evidence, directed
  recovery scope, automated candidate QA and normalized timeline clips. Older
  sparse events remain valid and simply render without those optional details.

## Reference provenance

Jellyfish commit `a9678194ddf2d9be3ccbe78d4287d87d5089e123`
(Apache-2.0) was inspected for project-lobby, tabbed-workbench, asset/task,
readiness and timeline information architecture. No Jellyfish code or assets
were copied into DeerFlow. The inspected paths are recorded in
`docs/VIDEO_WORKBENCH.md`.

## 旧版审计矩阵

审计源：用户自有只读工作树
`/Users/yangyucheng/projects/video-studio`，审计时 HEAD `37ad124`。该目录存在
大量未提交和未跟踪改动；审计仅使用读取命令，没有修改、格式化、清理、恢复或
提交任何旧项目文件。

| 旧版来源 / 能力 | 决策 | 在 DeerFlow 原生工作台中的处理与理由 |
|---|---|---|
| `src/video-studio/index.tsx` 的顶栏阶段、左镜头栏、中画布、右项目引用布局 | adapt | 保留“阶段—镜头—证据”的信息层级，改为九阶段横向账本轨与原生 Tabs；不复制旧皮肤和可变项目控制面。 |
| `director-console.tsx/.css` 的四阶段精简导演台 | adapt | 采用紧凑项目/资产/分镜/剪辑层次与镜头局部定位；四阶段被当前不可变九阶段取代，创建与推进仍回到 DeerFlow 对话。 |
| `demo-showcase.tsx/.css` 的 result-first 证据定位 | adapt | 保留“主张应定位到 exact 回执/产物”的原则；舍弃客户首映营销壳、冻结演示专用状态和 Evidence Runtime 入口。 |
| 项目中心、全自动/协作模式、传统新建表单 | discard | 会把 UI 变成另一套项目运行时和表单应用；当前 UI 只列账本制作并跳回 DeerFlow 创建/推进。 |
| 角色/场景/道具/声音资产槽和独立资产库 | adapt | 读模型展示类型、版本、source SHA、lineage、coverage、route；不迁入全局可变 JSON 库、账号绑定、知识库凭据或上传写路径。 |
| 资产母板与 `product_asset_storyboard.py` 的 source-version/coverage 语义 | adapt | 接受账本已有 `asset_version`、coverage、projection、generation route 字段并只读展示；不硬编码模型、26 视图作业或 Provider submit。 |
| `shot_semantics.py` 的关系、离散动作 cue、首尾帧合同 | adopt | 将分镜事件中的首帧、尾帧、motion、preserve/change、dialogue/camera 投影为镜头卡；不在 UI 编译 prompt 或执行语义校验。 |
| `shot_state_bridge.py` 的相邻镜头 inherited state、cut/axis、hash 绑定 | adapt | `consistency_checked` 中已有 bridge 时展示 from/to、状态 SHA 与镜头关系；不恢复 paid authorization 或旧桥接执行器。 |
| `spherical_assets.py` 的 camera-matched coverage 与逐级覆盖 | adapt | coverage tier / view evidence 作为资产版本证据展示；不把完整球面包变成当前账本之外的硬门或第二状态。 |
| `generated_shot_qa.py` 的技术门、首帧锚定、内部切镜、整镜播放 | adapt | 候选卡展示账本中的 automated QA 数值/布尔结果；不在 Gateway 重跑 FFmpeg/SSIM，也不把自动 QA 冒充人工选片。 |
| `approved_assembly.py` 的 exact source/receipt/hash admission | adopt | 延续“选中候选 + exact artifact/hash + delivery QA”才可交付的证据链；现有账本已经强制 delivery output 与 QA output 一致，不复制渲染器。 |
| `timeline_interchange.py` 的视频/音频轨、clip timing、external media SHA | adapt | 读模型兼容账本中的 normalized tracks/clips/fps/duration/source SHA 并展示；不引入 OTIO 作为第二真相，也不在工作台写时间线。 |
| `media_flow.py` 的 content-addressed 局部失效与显式 rework target | adapt | 失败回执投影 source/category/affected shots/assets，并生成回到 DeerFlow 的恢复指令；不会自动重试或覆盖失败证据。 |
| `media_flow.py` / `workgraph.py` 的 DAG 执行、claim/settle/review 状态机 | discard | DeerFlow 与 `personal_ip_video_production_events` 已是唯一编排者/业务真相；迁入会形成第二套运行时。 |
| `director_asset_library.py` 的原子 JSON、跨项目 pin/activate | discard | 属于旧可变资产存储和会话式写路径；仅吸收内容寻址和版本可见性，不迁移存储。 |
| `workflow_routes.py` 的 director/media 上传、生成、run-next、review、final 路由 | discard | 当前只复用 Personal-IP begin/event/read 与 owner-scoped Gateway；不恢复旧 mutation API、provider adapter 或凭据面。 |
| 失败测试中的 `shot_execution_drift` / `canonical_asset_defect` / `shot_contract_defect` 与 cascade | adopt | 作为账本事件的失败来源和局部恢复范围展示；资产/合同缺陷仍必须由 DeerFlow 产生新的事件链，不能在 UI 隐式修复。 |
| 候选选择、真实付费、真实发布的精确确认 | adopt | 仅这三类继续显示确认；证据晋级、普通 QA 和阶段推进不向用户索要批准。 |

本次实现没有从旧项目复制代码或 CSS；采用的是用户自有项目中的信息架构和纯语义，
并全部约束在当前事件账本读模型内。Jellyfish 仍只提供 Apache-2.0 的项目/任务/
时间线结构参考，两类参考都没有混入新的 Agent runtime。

## Verification

- Backend focused workbench/router tests: 8 passed.
- Related Personal-IP/video/tools/cockpit backend regression: 39 passed.
- Frontend unit suite: 702 passed.
- Frontend ESLint and TypeScript: passed.
- Production build: passed.
- Relevant Personal-IP Playwright acceptance on Chromium: 2 passed (portfolio
  plus video workbench).
- Browser-controlled desktop inspection: 1440×900; asset version/coverage,
  first-to-last shot semantics, directed recovery, cross-shot bridge, automated
  QA, timeline clip/hash, publish gate and delivery receipt verified.
- Free local video E2E: passed twice with the same production id, 11 events,
  final SHA256 and zero paid calls. The second run re-hashed and resumed all
  successful receipts without duplicating events.

Local acceptance result:

```text
production_id: video-production-257e248b609145a48450dd924fd35072
status/current_stage: completed/delivery
event_count: 11 on both runs
finisher: ffmpeg
qa_passed: true
paid_calls_executed: 0
final size: 42081 bytes
final sha256: c9289f71072fda815941a0c47e4e8efbbebaa3813b0896c5a6c9367870d8f9e8
```

The broader Playwright suite was also attempted. Its unrelated legacy chat,
landing and mobile-sidebar assertions still look for the upstream DeerFlow
placeholder/welcome/brand strings, while this branch intentionally renders the
IP Agent copy (for example, “Name the account, platform, and outcome…”). The
run was stopped after 82/105 cases; this workbench did not change those pages.
The scoped Personal-IP suite above is clean.

Screenshot deliverable:
`outputs/video-workbench-storyboard-1440x900.png` and
`outputs/video-workbench-1440x900.png` in the Codex task output directory.

## Real API acceptance still required

No paid Seedream, Seedance, speech or cloud MediaKit request was made. With an
explicit approval in a future active user session:

1. Inspect the generated paid checkpoints and authorize the exact call count.
2. Execute one Seedream asset request and ingest its authoritative receipt.
3. Execute one Seedance shot request, including a real failed/retried task if
   available, and verify provider task id, cost state and `retry_of` in the
   workbench.
4. Execute one Doubao Speech request and verify its voice/timeline receipt.
5. Prefer local MediaKit finishing; use cloud MediaKit only if separately
   approved, then verify final artifact hash and exact-output delivery QA.
6. Exercise a real publish confirmation only after the authenticated platform
   page proves the final public URL.

Every provider result must be ingested through the existing event/receipt
pipeline. Do not reconstruct receipts from console text or expose credentials.
