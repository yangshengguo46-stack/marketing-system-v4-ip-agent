import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Sidebar navigation", () => {
  test("sidebar contains only customer-facing work areas", async ({ page }) => {
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");

    // Sidebar uses data-sidebar="menu-button" with asChild rendering on <Link>
    const sidebar = page.locator("[data-sidebar='sidebar']");
    await expect(sidebar.locator("a[href='/workspace/dashboard']")).toBeVisible(
      {
        timeout: 15_000,
      },
    );
    await expect(sidebar.locator("a[href='/workspace/chats']")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      sidebar.locator("a[href='/workspace/personal-ip']"),
    ).toBeVisible();
    await expect(
      sidebar.locator("a[href='/workspace/personal-ip/video']"),
    ).toHaveCount(0);
    await expect(
      sidebar.getByText(/^(平台管理|Platform management)$/),
    ).toBeVisible();
    await expect(sidebar.locator("a[href='/workspace/agents']")).toHaveCount(0);
  });

  test("Dashboard link is above New chat and opens the workbench", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await page.route("**/api/personal-ip/accounts", (route) =>
      route.fulfill({ status: 200, json: [] }),
    );
    await page.route("**/api/personal-ip/metrics?*", (route) =>
      route.fulfill({ status: 200, json: [] }),
    );
    await page.route("**/api/personal-ip/cockpit", (route) =>
      route.fulfill({
        status: 200,
        json: {
          portfolio: {
            subject_count: 0,
            account_count: 0,
            platform_count: 0,
            platforms: [],
          },
          stages: {},
          queues: {
            preflights_awaiting_publish: [],
            published_receipts_awaiting_metrics: [],
            published_receipts_awaiting_retrospective: [],
          },
          recent: {},
          video: {
            production_count: 0,
            active_count: 0,
            completed_count: 0,
            blocked_production_ids: [],
            awaiting_review_production_ids: [],
            stages: {},
            recent: [],
          },
        },
      }),
    );
    await page.goto("/workspace/chats/new");
    const sidebar = page.locator("[data-sidebar='sidebar']");
    const links = sidebar.locator(
      "a[href='/workspace/dashboard'], a[href='/workspace/chats/new']",
    );
    await expect(links).toHaveCount(2);
    await expect(links.nth(0)).toHaveAttribute("href", "/workspace/dashboard");

    await links.nth(0).click();
    await page.waitForURL("**/workspace/dashboard");
    await expect(
      page.getByRole("heading", { name: "今天的增长，哪里值得继续追" }),
    ).toBeVisible();
    await expect(page.getByText("—", { exact: true })).toHaveCount(4);
  });

  test("local context lives in Settings instead of the portfolio", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    let enableCalled = false;
    await page.route("**/api/personal-ip/minecontext", (route) =>
      route.fulfill({
        status: 200,
        json: {
          operator_enabled: true,
          available: true,
          source_verified: true,
          runtime_ready: true,
          authorized: false,
          running: false,
          evidence_count: 0,
          data_location: "local_owner_isolated",
          raw_content_enters_deerflow: false,
        },
      }),
    );
    await page.route("**/api/personal-ip/minecontext/enable", async (route) => {
      expect(route.request().postDataJSON()).toEqual({ retention_days: 30 });
      enableCalled = true;
      await route.fulfill({
        status: 200,
        json: { authorized: true, running: true },
      });
    });

    await page.goto("/workspace/chats/new");
    await page.getByRole("button", { name: /^(设置|Settings)$/ }).click();

    const dialog = page.getByRole("dialog");
    await dialog
      .getByRole("button", { name: /本地上下文|Local context/ })
      .click();
    await expect(dialog.getByText("本地上下文", { exact: true })).toBeVisible();
    await expect(dialog.getByText("允许读取的范围")).toHaveCount(0);
    await expect(dialog.getByText("允许使用的目的")).toHaveCount(0);
    await dialog.getByRole("button", { name: "开启本地上下文" }).click();
    await expect.poll(() => enableCalled).toBe(true);
  });

  test("internal agent management stays hidden when agents_api is off", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await page.route("**/api/features", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ agents_api: { enabled: false } }),
      }),
    );

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    await expect(sidebar.locator("a[href='/workspace/chats']")).toBeVisible({
      timeout: 15_000,
    });
    await expect(sidebar.locator("a[href='/workspace/agents']")).toHaveCount(0);
    await expect(sidebar.getByRole("button", { name: "Agents" })).toHaveCount(
      0,
    );
  });

  test("mobile welcome layout stays within viewport and opens sidebar", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");

    const expectInsideViewport = async (
      locator: ReturnType<typeof page.locator>,
    ) => {
      await expect(locator).toBeVisible({ timeout: 15_000 });
      await expect(locator).toBeInViewport();
    };

    await expectInsideViewport(page.getByRole("textbox").first());
    await expectInsideViewport(page.locator("[data-slot='suggestions-list']"));

    const mobileSidebarTrigger = page
      .locator("[data-sidebar='trigger']:visible")
      .first();
    await expect(mobileSidebarTrigger).toBeVisible();
    await mobileSidebarTrigger.click();

    const mobileSidebar = page.locator(
      "[data-mobile='true'][data-sidebar='sidebar']",
    );
    await expect(mobileSidebar).toBeVisible();
    await expect(
      mobileSidebar.locator("a[href='/workspace/chats']"),
    ).toBeVisible();
    await expect(
      mobileSidebar.locator("a[href='/workspace/agents']"),
    ).toHaveCount(0);
  });
});
