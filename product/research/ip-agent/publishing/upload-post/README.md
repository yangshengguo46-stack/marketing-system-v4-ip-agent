# MoneyPrinterTurbo / Upload-Post 发布能力审计

审计日期：2026-08-04

本目录是研究隔离资产，不是现役产品能力。生产 Python 包、Gateway、
Agent 工具和默认 MCP 配置不得 import 或注册本目录内容。

## 结论

不直接复制 MoneyPrinterTurbo 的自动发布代码。它的平台发布本质上是
[Upload-Post](https://docs.upload-post.com/api/upload-video/) REST API 的薄封装，不是
TikTok、Instagram 和 YouTube 的自研适配器。

更值得验证的候选是官方开源
[Upload-Post MCP](https://github.com/Upload-Post/upload-post-mcp)。它符合项目已定的
`Capability MCP -> Child` 架构，但只能作为 M5 发布 Effector 候选：必须先收窄工具面、
补齐幂等绑定，再用真实账号做外部写入验收。

## 固定的上游证据

| 对象 | 固定版本 | 许可证 | 本轮审计范围 |
| --- | --- | --- | --- |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | `254cd028906ee657eab844dc94087cdbea2a7aa8` | MIT | `app/services/upload_post.py`、`app/services/task.py`、配置和发布测试 |
| [Upload-Post MCP](https://github.com/Upload-Post/upload-post-mcp) | `80e2bdc6a372d4fb57cab6f264550f1c3a5dd25b` / npm `0.6.1` | MIT | 官方 MCP 发布、状态、重试、删除、调度和分析工具 |

精确文件和分发包摘要见 [upstream-manifest.json](./upstream-manifest.json)。

## MoneyPrinterTurbo 实际做了什么

`UploadPostService` 的主路径只是：

1. 读取单组 `api_key + username + platforms`；
2. 将本地视频以 multipart 发送到 `POST /api/upload`；
3. 保存供应商返回的 `request_id` 或错误；
4. 生成任务完成后，在进程内线程池异步执行跨平台上传。

值得保留的编排经验：

- 成片生成与发布状态分离，发布失败不覆盖已完成的视频任务；
- 发布队列有并发上限，队列满时明确失败；
- `pending -> processing -> complete/failed` 独立记录；
- 状态写入有限次重试，进程中断后把孤儿任务收敛为失败；
- 发布活动期间禁止删除仍被工作线程读取的任务目录。

不能直接复用的地方：

- 未向 REST API 传入 `Idempotency-Key` 或客户端 `request_id`；
- 未显式使用 `async_upload=true`，也没有在发布主路径轮询 `check_status`；
- 供应商的 `success=true` 可能只表示后台任务已接收，并不等于各平台已发布；
- 没有按平台验证最终 `post_id` / `url` / 作者归属；
- 只有全局 `username`，不具备 Owner、Subject、Account 之间的权威绑定；
- 返回值主要是供应商原始字典，不是我们的追加式发布回执。

## 官方 Upload-Post MCP 的能力与边界

npm `@upload-post/mcp@0.6.1` 实际暴露 51 个工具；官方文档中仍有“45 个”的
滞后口径。工具面包括发布、调度、状态、历史、分析、评论、私信、队列、
FFmpeg 和删除等多类能力。它支持本地 stdio、自托管 HTTP 与官方托管端点，
也支持 API Key 和 OAuth 2.1。

对我们当前的八平台，它只能覆盖 X、Instagram、YouTube 和 TikTok。不覆盖
抖音、视频号、公众号和小红书，因此它是四平台供应商，不是八平台总解。

接入前必须修复或包装的问题：

1. `upload_video` 会对外真实发布，但上游 MCP 标注为 `destructiveHint=false`。
   我们必须把它归类为有外部副作用的 Effector，不能依赖该标注决定是否需要确认。
2. MCP 的发布 Schema 没有暴露 REST API 已支持的 `Idempotency-Key` 和客户端
   `request_id`。直接重试可能重复发布。
3. 提交回复不是发布回执。必须保存 `request_id`，按官方节奏轮询，直到各平台进入
   `completed` 或 `failed`；部分成功不得压成一个总成功。
4. 51 个工具不得全量进入 Agent。私信、回评、删除、更新队列、创建用户等能力均不在
   首条发布链路范围。
5. 官方托管连接由 Upload-Post 保管各平台 OAuth Token；本地文件上传会经过其
   R2 暂存区。这是新的供应商信任边界，必须在真实测试中明示。

## 与现有系统的正确组合

现有 `PersonalIPPublishReceiptRepository` 已经拥有 MPT 所缺的 Owner/Account 绑定、
幂等 operation、追加尝试、单调成功、合规声明和平台公开 URL 校验。因此不替换
现有回执帐本，只在其下新增可替换的供应商执行器。

但现有后端只能记录发布意图、尝试和公开页证明，没有 TikTok、Instagram、
YouTube 或 Upload-Post 的真实上传适配器。当前浏览器路径是“用户/受控操作完成发布
后，系统验证公开页并记账”，不是确定性 uploader。因此本研究候选填的是
真实执行缺口，不得把已有 mocked acceptance 写成已经自动发布。

目标边界：

```text
用户确认的 Work/Artifact
  -> 我们的 Owner + Account + 版本 + SHA-256 + 合规声明
  -> 我们的 PublishBatch，按目标账号/平台 fan-out 子 PublishReceipt
  -> durable outbox job + dispatch lease + pending attempt
  -> Capability MCP 的 real_publish 确认门
  -> 收窄的 Upload-Post Child
  -> request_id / 按平台状态 / post_id / public URL
  -> 追加写入 PublishReceipt
  -> 平台观测与指标采集
```

Agent 未来最多只应看见领域语义下的少量能力，不应看见供应商 51 个原始工具：

- `submit_confirmed_publication`：真实外部写入，必须消费本次 `real_publish` 确认；
- `get_publication_status`：只读轮询；
- `retry_failed_publication`：只允许对供应商明确失败的平台执行；
- `collect_publication_metrics`：只读，绑定已发布回执。

账号连接应由 Owner 工作台中的明确 UI 操作完成，不作为 Agent 工具。
每个平台必须拥有独立子回执和独立终态；即使 Upload-Post 支持一次 `platforms[]`
跨平台提交，第一版适配也应按平台分开调用，避免部分成功时无法对单个账号安全重试。

不使用 MPT 的进程内 `ThreadPoolExecutor` 作为产品任务队列。产品路径需要可持久化
outbox、租约和重启恢复；已提交但未收到响应时，先根据加密保存的供应商
`request_id` 查询，不盲目重传视频。

## M5 真实验收前冻结的测试

1. 使用一个真实测试账号，首选 YouTube `unlisted` 或 TikTok `MEDIA_UPLOAD` 草稿；
2. 发布前界面必须展示精确账号、平台、视频哈希、标题/说明、披露和发布时间；
3. 断开首次提交响应后使用同一幂等键恢复，不得生成第二条内容；
4. 覆盖单平台成功、单平台失败和多平台部分成功；
5. Gateway 重启后根据加密保存的 `request_id` 继续轮询，不重提视频；
6. 最终成功必须有平台 `post_id` 或可验证公开 URL；只有“Upload started”直接失败；
7. 错 Owner、错 Account、过期确认、哈希变化和未披露 AI/商业内容全部在网络调用前拒绝；
8. 只有真实外部发布、状态恢复、回执和公开页验证全部通过，才能将该 Child 从研究隔离提升为 M5 能力。

## 本轮状态

- MoneyPrinterTurbo 发布封装：不接入，只保留编排经验。
- Upload-Post MCP：M5 研究候选，未配置密钥，未连接账号，未调用供应商，未进入 Agent。
- 当前主要矛盾 MF-E1 不变；本轮只完成次要矛盾的读取审计，不抢占 M5 实现。
