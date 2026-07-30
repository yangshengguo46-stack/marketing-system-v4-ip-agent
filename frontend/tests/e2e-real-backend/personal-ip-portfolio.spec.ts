import { expect, test } from "@playwright/test";

const APP =
  process.env.E2E_APP_URL ??
  `http://localhost:${process.env.E2E_FRONTEND_PORT ?? "3000"}`;

test.describe("Personal-IP portfolio (real backend)", () => {
  test("persists a subject through the UI and renders a real stored account", async ({
    page,
    context,
  }) => {
    const unique = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
    const subjectName = `真实主体-${unique}`;
    const accountName = `真实抖音账号-${unique}`;

    await page.goto("/workspace/personal-ip");
    await expect(page.getByRole("heading", { name: "平台管理" })).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.locator('[data-platform="douyin"]')).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText("还没有经营主体。")).toBeVisible({
      timeout: 60_000,
    });

    await page.getByRole("button", { name: "新建主体" }).click();
    await page.getByLabel("主体名称").fill(subjectName);
    await page.getByLabel("主体类型").click();
    await page.getByRole("option", { name: "产品" }).click();
    const createSubjectResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/personal-ip/subjects",
    );
    await page.getByRole("button", { name: "保存主体" }).click();
    const createdSubjectResponse = await createSubjectResponse;
    expect(
      createdSubjectResponse.status(),
      await createdSubjectResponse.text(),
    ).toBe(201);
    await expect(page.getByText(subjectName, { exact: true })).toBeVisible({
      timeout: 30_000,
    });

    const subjectsResponse = await context.request.get(
      `${APP}/api/personal-ip/subjects`,
    );
    expect(subjectsResponse.status(), await subjectsResponse.text()).toBe(200);
    const subjects = (await subjectsResponse.json()) as Array<{
      id: string;
      display_name: string;
      subject_type: string;
    }>;
    const subject = subjects.find(
      (candidate) => candidate.display_name === subjectName,
    );
    expect(
      subject,
      "UI-created subject must be persisted by the gateway",
    ).toBeTruthy();
    expect(subject!.subject_type).toBe("product");

    const accountResponse = await context.request.post(
      `${APP}/api/personal-ip/accounts`,
      {
        data: {
          subject_id: subject!.id,
          platform: "douyin",
          display_name: accountName,
          handle: null,
          avatar_url: null,
          metadata: {
            connection_mode: "local_browser_profile",
            connection_state: "pending_login",
          },
        },
      },
    );
    expect(accountResponse.status(), await accountResponse.text()).toBe(201);

    await page.reload();
    const douyinCard = page.locator('[data-platform="douyin"]');
    await expect(
      douyinCard.getByText(accountName, { exact: true }),
    ).toBeVisible({ timeout: 30_000 });
    await expect(
      douyinCard.getByText(subjectName, { exact: true }),
    ).toBeVisible();
  });
});
