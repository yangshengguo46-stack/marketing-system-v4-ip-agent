# 八平台数据采集与全组合查询交接

## 结论

本工作线补齐了“今天全平台浏览量多少”的可测试闭环：

`owner 全部 active accounts -> 各账号隔离浏览器 profile -> rendered DOM 详细观测 -> 今日窗口指标 -> owner 全组合聚合`

新入口：

- 原生工具：`personal_ip_collect_browser_portfolio_today`
- Gateway：`POST /api/personal-ip/metrics/collect/browser-portfolio-today`
- 只读聚合：`personal_ip_metrics_aggregate` / `GET /api/personal-ip/metrics/aggregate`

组合采集入口没有 `account_id` 参数，也不读取 thread 中选中的浏览器账号。账号选择仍只影响一次具体浏览器操作，不能成为会话权限或组合查询过滤器。

## 八平台核对矩阵

| 平台 | 安全数据页入口 | rendered-label 今日浏览指标 | 详细业务数据 | 当前完备性与真实登录状态 |
|---|---|---|---|---|
| 抖音 | `creator.douyin.com/creator-micro/home` | 播放量/视频播放量/作品播放量 | 通用 DOM；已存在 dashboard 与 content inventory 专用解析，作品列表可按声明数量和“没有更多作品”证明完整 | 专用内容列表可达 observed；dashboard/今日组合指标仍为 partial。本工作树没有可直接运行的持久登录 profile，未新增真实登录验收 |
| 视频号 | `channels.weixin.qq.com/platform/data/overview` | 播放量/视频播放次数/视频播放量/播放次数 | 页面正文、标题、表格/网格、数据卡、链接、截图摘要 | 今日标签适配器有 fixture 回归；未登录实测，保持 partial/unavailable |
| 公众号 | `mp.weixin.qq.com/`（登录后由平台重定向） | 阅读次数/阅读量/图文阅读次数；阅读人数单独保留，不冒充 views | 同上；最终 URL query/fragment 会剥离 | fixture 回归；未登录实测，保持 partial/unavailable |
| 小红书 | `creator.xiaohongshu.com/new/home` | 观看量/浏览量/笔记浏览量；曝光量单独保留，不冒充 views | 同上 | fixture 回归；未登录实测，保持 partial/unavailable |
| X | `analytics.x.com/`（与 `x.com` 同账号 profile） | Post views/Video views/Views；Impressions 单独保留，不冒充 views | 同上 | fixture 回归；未登录实测，保持 partial/unavailable |
| Instagram | `instagram.com/professional_dashboard/` | Content views/Video views/Views；Impressions 单独保留 | 同上 | fixture 回归；未登录实测，保持 partial/unavailable |
| YouTube | `studio.youtube.com/` | Video views/Views | 同上 | fixture 回归；未登录实测，保持 partial/unavailable |
| TikTok | `tiktok.com/tiktokstudio/analytics` | Post views/Video views/Views | 同上 | fixture 回归；未登录实测，保持 partial/unavailable |

所有 dashboard 适配器都会保留 `direct_metrics`、命中的原始 `metric_labels` 和 `metric_window`。只有页面明确出现“今日”“今天”“本日”或 `Today` 时，组合采集才会把直接计数写入请求的 today `window_total`。昨日、近 7 日、近 28 日、显式其他日期段或未知窗口只进入详细观测，不会被当成今天。

## 覆盖率语义

- `observed`：该账号请求窗口有直接、完整的可加指标证据。
- `partial`：有数值，但页面/适配器尚未证明完整账号窗口。当前浏览器今日适配器统一保守写为 partial。
- `unavailable`：账号被扫描，但需要登录、页面没有今日窗口或没有解析到 today views；指标为空，不写 0。
- `missing`：该 active account 没有该窗口指标行，例如浏览器启动/采集失败或平台不在八平台注册表。
- `not_configured`：八平台覆盖图中该平台没有 active account；它不是用户组合里的缺失账号。

`PersonalIPMetricRepository.aggregate` 现在只聚合 owner 的 active accounts，排除 archived account 的旧观测；账号状态互斥，并增加 `coverage.by_account_status`、`coverage.by_platform_status` 和 `coverage.by_metric`。即使其他指标存在，缺少 views 的账号仍会出现在 `coverage.by_metric.views.missing_account_ids`，而 `totals.views` 在没有有效数据时保持不存在。

## 持久化与凭据边界

- 浏览器 profile：owner/account 隔离，session key 为账号级；路径和凭据不进入工具结果。
- 详细证据：`personal_ip_platform_observations`，contract 为 `personal-ip-platform-observation-v1`。保存 sanitized source URL、observed-at、records、summary、coverage、evidence 和 digest。
- 可加指标：`personal_ip_metric_observations`。组合采集写 account-scope/browser/window_total 行，再走同一 owner-wide aggregate。
- DOM 提取器只读取 rendered body/headings/tables/data blocks/links，并生成 full-page screenshot SHA-256；不访问 cookie、browser storage、请求头或网络响应体。
- repository 会递归拒绝 cookie/token/password/authorization/secret 等字段和值；URL query 和 fragment 不持久化。

## 回归

新增/扩展覆盖：

- 八平台 dashboard 标签、K/M/B/万/亿计数和 today/7d/28d 窗口区分。
- 从假浏览器 rendered DOM 到详细 observation、metric row、全组合 aggregate 的真实 SQLite 端到端测试。
- 两个账号有 partial views、两个 unavailable、四个采集失败后 missing 的完整组合断言。
- per-metric views coverage、missing 不变成 0、archived account 不参与组合。
- 同一 series 的递进式今日 `window_total` 只取最新 cutoff，不重复相加。
- Gateway 组合采集路由与原生工具都没有 account filter。
- 原生工具注册和 harness -> app import firewall。

已通过的聚焦命令：

```bash
cd backend
uv run pytest tests/test_personal_ip_browser_login_detection.py tests/test_personal_ip_douyin_browser_collection.py tests/test_personal_ip_browser_portfolio_metrics.py tests/test_personal_ip_metric_repository.py tests/test_personal_ip_metric_router.py tests/test_personal_ip_tools.py tests/test_harness_boundary.py -q
```

结果：`50 passed`。

全量后端回归：`make test`，结果 `8665 passed, 54 skipped`。

## 剩余真实阻塞

- 2026-07-22 做了未登录、只读的公开入口复核：抖音和小红书返回各自创作平台页面，YouTube Studio 跳转 Google 登录，TikTok Studio Analytics 返回 TikTok Studio 页面。视频号、公众号在当前网页抓取环境不可达，X 被安全抓取器拒绝，Instagram 被限流；这些结果只能确认入口/登录门，不能替代账号内业务数据验收。
- 这 7 个平台仍需要各自真实创作者账号登录后做 UI 文案、数据页路径、SPA 加载和日期筛选验收：视频号、公众号、小红书、X、Instagram、YouTube、TikTok。本轮按要求没有要求用户登录。
- 指定 worktree 内没有正在运行的 Gateway（8001/2026 均未监听），也没有可用的本地 `.deer-flow` 浏览器 profile，因此本轮没有重新打开抖音账号做 live 采集；没有读取、复制或输出任何 Cookie/Token/密码。
- 平台 UI 文案变更时，fixture 适配器会安全降级为 unavailable/missing，不会误写 0；要把某平台从 partial 提升为 observed，仍需真实登录页面证明窗口、分页和账号范围完整。
