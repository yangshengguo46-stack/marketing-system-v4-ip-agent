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
  status: "active",
  metadata: {
    connection_mode: "local_browser_profile",
    connection_state: "pending_login",
  },
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

const EMPTY_COCKPIT: PersonalIPOperatingCockpit = {
  contract_version: "personal-ip-operating-cockpit-v6",
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
    subjects_needing_strategy_validation: [],
    subjects_needing_differentiation_validation: [],
    preflights_awaiting_publish: [],
    published_receipts_awaiting_metrics: [],
    published_receipts_awaiting_retrospective: [],
  },
  recent: {},
  alerts: {
    summary: {
      total: 0,
      blocking: 0,
      warning: 0,
      by_category: { loop: 0, provider: 0, cost: 0 },
    },
    items: [],
  },
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
  coverage: {
    history_limit: 20,
    video_alert_detail_limit: 50,
    possibly_truncated: [],
  },
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
  await page.route("**/api/personal-ip/accounts/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (route.request().method() === "POST" && pathname.endsWith("/logout")) {
      const accountId = decodeURIComponent(pathname.split("/").at(-2) ?? "");
      const current = accounts.find((account) => account.id === accountId);
      if (!current) {
        await route.fulfill({ status: 404, json: { detail: "not found" } });
        return;
      }
      const updated = {
        ...current,
        metadata: {
          ...current.metadata,
          browser_authenticated: false,
          connection_state: "pending_login",
          execution_ready: false,
        },
      };
      accounts = accounts.map((account) =>
        account.id === accountId ? updated : account,
      );
      await route.fulfill({ status: 200, json: updated });
      return;
    }
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

  await expect(page.getByText("本地上下文（MineContext）")).toHaveCount(0);
  await expect(page.getByText("首次使用从这里开始")).toHaveCount(0);
  await expect(page.getByText("连接状态摘要")).toHaveCount(0);
  await expect(page.getByText("下一步", { exact: true })).toHaveCount(0);
  await expect(page.getByLabel("平台账号")).toBeVisible();

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

  const tiktokCard = page.locator('[data-slot="card"]').filter({
    has: page
      .locator('[data-slot="card-title"]')
      .getByText("TikTok", { exact: true }),
  });
  await page.evaluate(() => {
    const sockets: Array<{
      onopen: (() => void) | null;
      onmessage: ((event: { data: string }) => void) | null;
      onclose: (() => void) | null;
      readyState: number;
      sent: string[];
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
      sent: string[] = [];

      constructor() {
        sockets.push(this);
        queueMicrotask(() => {
          this.readyState = MockWebSocket.OPEN;
          this.onopen?.();
        });
      }

      send(payload: string) {
        this.sent.push(payload);
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
  await tiktokCard.getByRole("button", { name: "登录", exact: true }).click();

  await expect(page.getByRole("dialog")).toContainText("TikTok · TikTok账号");
  await expect(page.getByRole("dialog")).toContainText(
    "登录状态只保存在这个账号的独立浏览器中",
  );
  await expect
    .poll(() =>
      page.evaluate(() => {
        return (
          Reflect.get(window, "__loginSockets") as Array<{
            emit: (payload: unknown) => void;
          }>
        ).length;
      }),
    )
    .toBeGreaterThan(0);
  await page.evaluate(() => {
    const sockets = Reflect.get(window, "__loginSockets") as Array<{
      emit: (payload: unknown) => void;
    }>;
    sockets.at(-1)?.emit({
      type: "presentation",
      mode: "native_window",
    });
  });
  await expect(page.getByTestId("native-account-login")).toContainText(
    "平台登录窗口已打开",
  );
  await expect(page.getByTestId("browser-interaction-surface")).toHaveCount(0);
  if (screenshotDirectory) {
    await page.getByRole("dialog").screenshot({
      path: `${screenshotDirectory}/account-login-native-window.png`,
    });
  }

  await page.evaluate(() => {
    const sockets = Reflect.get(window, "__loginSockets") as Array<{
      fail: () => void;
    }>;
    sockets.at(-1)?.fail();
  });
  await expect(page.getByTestId("native-account-login")).toContainText(
    "登录窗口已断开",
  );
  await page.waitForTimeout(1_000);
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (
            Reflect.get(window, "__loginSockets") as Array<{
              emit: (payload: unknown) => void;
            }>
          ).length,
      ),
    )
    .toBe(1);

  await page.getByRole("button", { name: "Close", exact: true }).click();
  await tiktokCard.getByRole("button", { name: "登录", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (
            Reflect.get(window, "__loginSockets") as Array<{
              emit: (payload: unknown) => void;
            }>
          ).length,
      ),
    )
    .toBeGreaterThan(1);

  await page.evaluate(() => {
    const sockets = Reflect.get(window, "__loginSockets") as Array<{
      emit: (payload: unknown) => void;
    }>;
    sockets.at(-1)?.emit({
      type: "presentation",
      mode: "native_window",
    });
    sockets.at(-1)?.emit({ type: "account_authenticated" });
  });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(tiktokCard.getByText("已登录", { exact: true })).toBeVisible();
  await expect(
    tiktokCard.getByRole("button", { name: "退出登录", exact: true }),
  ).toBeVisible();
  await tiktokCard
    .getByRole("button", { name: "退出登录", exact: true })
    .click();
  await expect(tiktokCard.getByText("待登录", { exact: true })).toBeVisible();
  await expect(
    tiktokCard.getByRole("button", { name: "登录", exact: true }),
  ).toBeVisible();
});
