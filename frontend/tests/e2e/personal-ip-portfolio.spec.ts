import { expect, test } from "@playwright/test";

import {
  type PersonalIPAccount,
  type PersonalIPOperatingCockpit,
} from "@/core/personal-ip";

import { mockLangGraphAPI } from "./utils/mock-api";

const EMPTY_ACCOUNT: PersonalIPAccount = {
  id: "acct-tiktok",
  owner_user_id: "default",
  subject_id: null,
  platform: "tiktok",
  display_name: "TikTok账号",
  handle: null,
  avatar_url: null,
  promise_to_audience: "",
  primary_audience: "",
  content_pillars: [],
  voice_and_boundaries: [],
  business_goal: "",
  status: "active",
  metadata: {
    connection_mode: "local_browser_profile",
    connection_state: "pending_login",
  },
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const EMPTY_COCKPIT: PersonalIPOperatingCockpit = {
  contract_version: "personal-ip-operating-cockpit-v1",
  generated_at: "2026-07-22T00:00:00Z",
  portfolio: {
    subject_count: 0,
    account_count: 0,
    platform_count: 0,
    platforms: [],
  },
  stages: Object.fromEntries(
    [
      "modeling",
      "preflight",
      "publishing",
      "performance",
      "retrospective",
      "evidence",
    ].map((id) => [id, { state: "empty", total: 0, pending: 0 }]),
  ) as PersonalIPOperatingCockpit["stages"],
  queues: {
    accounts_needing_model_input: [],
    preflights_awaiting_publish: [],
    published_receipts_awaiting_metrics: [],
    published_receipts_awaiting_retrospective: [],
  },
  recent: {},
  video: {
    contract_version: "personal-ip-video-production-v1",
    production_count: 0,
    active_count: 0,
    completed_count: 0,
    blocked_production_ids: [],
    awaiting_review_production_ids: [],
    stages: Object.fromEntries(
      [
        "intake",
        "blueprint",
        "assets",
        "storyboard",
        "generation",
        "consistency",
        "selection",
        "finishing",
        "delivery",
      ].map((id) => [id, 0]),
    ) as PersonalIPOperatingCockpit["video"]["stages"],
    recent: [],
  },
  coverage: { history_limit: 20, possibly_truncated: [] },
};

test("portfolio shows all eight platforms and opens manual login", async ({
  page,
}) => {
  const screenshotDirectory = process.env.ONBOARDING_UI_SCREENSHOT_DIR;
  await page.setViewportSize({ width: 1440, height: 900 });
  mockLangGraphAPI(page);
  let accounts: PersonalIPAccount[] = [];
  await page.route("**/api/personal-ip/subjects", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/personal-ip/cockpit", (route) =>
    route.fulfill({ status: 200, json: EMPTY_COCKPIT }),
  );
  await page.route("**/api/personal-ip/accounts", async (route) => {
    if (route.request().method() === "POST") {
      const input = route.request().postDataJSON() as Record<string, unknown>;
      const created = { ...EMPTY_ACCOUNT, ...input };
      accounts = [created];
      await route.fulfill({ status: 201, json: created });
      return;
    }
    await route.fulfill({ status: 200, json: accounts });
  });
  await page.route("**/api/personal-ip/accounts/*", async (route) => {
    if (route.request().method() !== "PATCH") {
      await route.fallback();
      return;
    }
    const accountId = decodeURIComponent(
      new URL(route.request().url()).pathname.split("/").at(-1) ?? "",
    );
    const updates = route
      .request()
      .postDataJSON() as Partial<PersonalIPAccount>;
    const current = accounts.find((account) => account.id === accountId);
    if (!current) {
      await route.fulfill({ status: 404, json: { detail: "not found" } });
      return;
    }
    const updated = { ...current, ...updates };
    accounts = accounts.map((account) =>
      account.id === accountId ? updated : account,
    );
    await route.fulfill({ status: 200, json: updated });
  });

  await page.goto("/workspace/personal-ip");

  await expect(page.getByText("首次使用从这里开始")).toBeVisible();
  await expect(page.getByText("不需要公司统一认证")).toBeVisible();
  await expect(page.getByText("深度读取业务数据")).toBeVisible();
  await expect(page.getByText("Cookie、Token、密码和浏览器目录")).toBeVisible();

  const connectionSummary = page.getByLabel("连接状态摘要");
  await expect(connectionSummary).toContainText("未添加");
  await expect(connectionSummary).toContainText("待登录");
  await expect(connectionSummary).toContainText("已登录");
  await expect(connectionSummary).toContainText("采集受限");
  await expect(connectionSummary).toContainText("可执行");

  for (const label of [
    "抖音",
    "视频号",
    "公众号",
    "小红书",
    "X",
    "Instagram",
    "YouTube",
    "TikTok",
  ]) {
    await expect(
      page
        .locator('[data-slot="card-title"]')
        .getByText(label, { exact: true }),
    ).toBeVisible();
  }
  if (screenshotDirectory) {
    await page
      .locator('[aria-labelledby="platform-connections-title"]')
      .screenshot({ path: `${screenshotDirectory}/onboarding-overview.png` });
  }

  const tiktokCard = page
    .locator('[data-slot="card"]')
    .filter({ hasText: "TikTok" });
  await page.evaluate(() => {
    const sockets: Array<{
      onopen: (() => void) | null;
      onmessage: ((event: { data: string }) => void) | null;
      onclose: (() => void) | null;
      readyState: number;
      emit: (payload: unknown) => void;
      fail: () => void;
    }> = [];
    class MockWebSocket {
      static OPEN = 1;
      onopen: (() => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onclose: (() => void) | null = null;
      onerror: (() => void) | null = null;
      readyState = 0;

      constructor() {
        sockets.push(this);
        queueMicrotask(() => {
          this.readyState = MockWebSocket.OPEN;
          this.onopen?.();
        });
      }

      send() {
        return undefined;
      }

      close() {
        this.readyState = 3;
        this.onclose?.();
      }

      emit(payload: unknown) {
        this.onmessage?.({ data: JSON.stringify(payload) });
      }

      fail() {
        this.readyState = 3;
        this.onerror?.();
      }
    }
    Object.assign(window, {
      WebSocket: MockWebSocket,
      __loginSockets: sockets,
    });
  });
  await tiktokCard.getByRole("button", { name: "添加并登录" }).click();

  await expect(page.getByRole("dialog")).toContainText("TikTok · TikTok账号");
  await expect(page.getByRole("dialog")).toContainText(
    "登录状态只保存在这个账号的独立浏览器中",
  );
  const browserSurface = page.getByRole("dialog").locator("main");
  const browserBox = await browserSurface.boundingBox();
  expect(browserBox).not.toBeNull();
  expect((browserBox?.width ?? 0) / (browserBox?.height ?? 1)).toBeGreaterThan(
    1.5,
  );
  if (screenshotDirectory) {
    await page.getByRole("dialog").screenshot({
      path: `${screenshotDirectory}/account-login-landscape.png`,
    });
  }

  await page.evaluate(() => {
    const sockets = Reflect.get(window, "__loginSockets") as Array<{
      fail: () => void;
    }>;
    sockets.at(-1)?.fail();
  });
  await expect(page.getByText("连接中断。可以立即重新连接")).toBeVisible();
  await page.getByRole("button", { name: "重新连接" }).click();

  await page.evaluate(() => {
    const sockets = Reflect.get(window, "__loginSockets") as Array<{
      emit: (payload: unknown) => void;
    }>;
    sockets.at(-1)?.emit({ type: "account_authenticated" });
  });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(tiktokCard.getByText("已登录", { exact: true })).toBeVisible();
});
