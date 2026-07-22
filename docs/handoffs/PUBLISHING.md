# 八平台发布与回执恢复交接

更新时间：2026-07-22

## 本地完成范围

- 审核并加固 `personal_ip_prepare_browser_publish` / `personal_ip_finish_browser_publish`。
- 保持会话权限为认证用户的完整账号组合；`account_id` 只选择本次发布的 owner/account 浏览器 profile，不写入或收窄会话授权上下文。
- 八个平台都要求 post-specific 公开页。创作者后台、首页、内容列表以及仅同域但非帖子页不再构成 `published` 证明。
- 通用 native/REST 回执入口拒绝 browser executor；browser receipt 必须走 prepare/finish，不能绕过 live-page proof。
- prepare 在 receipt 为 `failed` 或 `unknown` 时可用新的 pending attempt key 恢复；已是 `pending` 的不同 handoff key 不会开启第二次提交。
- 相同 finish attempt key、状态、证据、时间和外部 URL/ID 的重复回调直接返回已存 receipt，不再依赖仍然存活的浏览器页面；矛盾回调继续拒绝。
- `published` 后的 `failed` / `unknown` 新 attempt 仍由单调状态机拒绝，成功不可降级。
- 新增 `make personal-ip-publish-acceptance`，只使用临时 SQLite 与 mocked Browser observation，不访问平台、不发帖、不发消息、不改设置。

## 自动验收矩阵

| 平台 | 接受的公开页样例 | 明确拒绝的非公开证明 |
| --- | --- | --- |
| 抖音 | `douyin.com/video/<id>`、`douyin.com/note/<id>` | `creator.douyin.com/...` |
| 视频号 | `channels.weixin.qq.com/web/pages/feed?feedId=<id>`、`weixin.qq.com/sph/<id>` | `channels.weixin.qq.com/platform/...` |
| 公众号 | `mp.weixin.qq.com/s/<id>` 或带公开文章标识的 `/s` | `mp.weixin.qq.com/cgi-bin/home` |
| 小红书 | `xiaohongshu.com/explore/<id>`、`/discovery/item/<id>` | `creator.xiaohongshu.com/...` |
| X | `x.com/<handle>/status/<id>`、`twitter.com/<handle>/status/<id>` | `/home` |
| Instagram | `/p/<id>`、`/reel/<id>`、`/tv/<id>` | 站点首页 |
| YouTube | `/watch?v=<id>`、`youtu.be/<id>`、`/shorts/<id>`、`/live/<id>` | `studio.youtube.com/...` |
| TikTok | `/@<handle>/video/<id>`、`/@<handle>/photo/<id>` | `/tiktokstudio/...` |

每个平台的端到端模拟都覆盖：页面未跳转、错误账号、错误平台、prepare 幂等回放、`unknown` 后重试、`failed` 后重试、成功回调响应丢失后的重复回放、矛盾重复回调和成功不可降级。

本地执行：

```bash
make personal-ip-publish-acceptance
```

本工作线回归结果：

- `make personal-ip-publish-acceptance`：57 passed。
- Personal-IP、Douyin 与 Browser Automation 相关后端回归：194 passed，1 skipped（可选真实 Chromium 集成未运行）。
- 前端 ESLint 与 TypeScript：通过。
- `frontend/tests/e2e/personal-ip-portfolio.spec.ts`：1 passed；补齐 cockpit mock 并把 TikTok 卡片选择限定到精确 card title，避免命中别的嵌套卡片。
- `make lint` 的 Ruff rule check 通过；全仓 format check 仍报告基线已有的 `tests/test_doctor.py`、`tests/test_personal_ip_context.py`、`tests/test_personal_ip_subject_repository.py`，本工作线未修改这三个文件。

## 仍需真人发布验收

以下步骤会产生真实外部写操作，本工作线没有执行。必须由用户对每个平台、每次发布单独批准后再做：

1. 先在 `/workspace/personal-ip` 确认目标账号，真人完成密码、二维码、CAPTCHA 或 MFA；不要把凭据发进聊天。
2. 准备一条明确获批的低风险测试内容，记录 exact request、`operation_key`、`idempotency_key` 和第一条 `pending_attempt_key`。
3. 调用 prepare 后，人工核对浏览器里当前平台和发布账号；核对失败立即停止，不点提交。
4. 获得该次单独批准后才点击真实提交。若提交结果为 `unknown`，先在创作者后台和公开端搜索是否已经产生帖子，避免盲目重试导致重复发布。
5. 打开该帖的公开详情页，确认作者确属目标账号，再以公开 URL/ID 调用 finish。保存的证据应只有规范化 URL、标题、可见文本摘要和业务说明，不含 cookie、token、查询凭据或页面原文。
6. 模拟响应丢失后重放完全相同的 finish callback，确认 receipt 不新增 attempt；再发送不同状态或不同 URL/ID 的同 key callback，确认冲突。
7. 对 `failed` 和确认未实际发布的 `unknown` 分别用新 handoff/result key 恢复；确认历史 attempt 只追加。
8. 在成功 receipt 上尝试记录晚到的 `failed` / `unknown`，确认拒绝且 `published_at`、公开 URL/ID 不变。

真人验收应逐平台记录：目标账号 ID、公开作者/handle、receipt ID、attempt keys、公开 URL/ID、时间、是否发生重定向、实际页面形态及任何需要新增的安全 URL 规则。尤其需要实测视频号公开分享页和各平台当前重定向形态；如页面规则变化，应新增精确测试向量，不要退回“只校验域名”。

## 已知边界

- 自动矩阵证明本地状态机、owner/account 选择和 URL 规则，不等价于真实发布完成。
- 当前错误账号门禁验证的是所选 owner/account profile 与 receipt 一致；公开页面作者仍需真人核对。若未来将可信平台 handle/作者 ID 写入账号元数据，可再增加机器校验。
- 没有修改 `docs/IP_AGENT_PRODUCT_LEDGER.md`，总台账分数不得用本地模拟测试冒充真人发布验收。
