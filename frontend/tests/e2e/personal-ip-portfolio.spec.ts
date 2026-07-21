import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const EMPTY_ACCOUNT = {
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
  metadata: { connection_mode: "local_browser_profile" },
  created_at: "2026-07-21T00:00:00Z",
  updated_at: "2026-07-21T00:00:00Z",
};

test("portfolio shows all eight platforms and opens manual login", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  let accounts: (typeof EMPTY_ACCOUNT)[] = [];
  await page.route("**/api/personal-ip/subjects", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
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

  await page.goto("/workspace/personal-ip");

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

  const tiktokCard = page
    .locator('[data-slot="card"]')
    .filter({ hasText: "TikTok" });
  await tiktokCard.getByRole("button", { name: "登录账号" }).click();

  await expect(page.getByRole("dialog")).toContainText("TikTok · TikTok账号");
  await expect(page.getByRole("dialog")).toContainText(
    "请本人完成扫码、验证码或双重验证",
  );
});
