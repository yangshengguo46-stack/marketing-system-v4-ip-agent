import { expect, type Page, test } from "@playwright/test";

import {
  type PersonalIPContentLineage,
  type PersonalIPContentWork,
  type PersonalIPVideoProduction,
} from "@/core/personal-ip";

import { mockLangGraphAPI } from "./utils/mock-api";

const objective = {
  desired_change: "让初次创业者能开始记录第一次客户访谈",
  audience_situation: "有业务想法，但不知道如何开始验证",
  business_context: "客户访谈工作坊",
  constraints: ["不虚构客户结果"],
};

const work: PersonalIPContentWork = {
  id: "content-work-1",
  objective_id: "objective-server-1",
  thread_id: "thread-server-1",
  subject_id: null,
  title: "第一次客户访谈",
  entry_route: "benchmark",
  objective,
  status: "active",
  created_by_run_id: "run-private-1",
  created_at: "2026-08-05T01:00:00Z",
  updated_at: "2026-08-05T02:00:00Z",
};

const lineage: PersonalIPContentLineage = {
  content_work: work,
  breakdown_versions: [
    {
      id: "breakdown-1",
      content_work_id: work.id,
      version_number: 1,
      source_kind: "platform_content",
      source_identity: { internal_source: "must-not-render" },
      source_digest: "digest-must-not-render",
      observations: [
        {
          observation: "开头先展示了一个具体的行动阻力。",
          evidence_refs: ["evidence-private-1"],
        },
      ],
      interpretations: [
        {
          interpretation: "具体阻力可能帮助受众快速自我定位。",
          state: "hypothesized",
          based_on_observations: [0],
        },
      ],
      limitations: ["没有发布后转化观测"],
      created_at: "2026-08-05T01:10:00Z",
    },
  ],
  direction_versions: [
    {
      id: "direction-1",
      content_work_id: work.id,
      version_number: 1,
      parent_direction_version_id: null,
      breakdown_version_ids: ["breakdown-1"],
      objective_snapshot: objective,
      direction: {
        premise: "第一次访谈不需要先成为研究专家。",
        audience_situation: objective.audience_situation,
        core_tension: "想验证，又怕问错问题。",
        content_promise: "给出今天就能执行的第一步。",
        creative_route: "行动示范",
        rationale: "用真实可执行动作降低开始门槛。",
        truth_mode: "factual",
        business_relevance: "连接工作坊课程",
        claim_basis: [
          {
            claim: "这是一个行动示例",
            state: "user_asserted",
            usage: "factual",
            evidence_refs: [],
          },
        ],
      },
      created_at: "2026-08-05T01:20:00Z",
    },
  ],
  script_versions: [
    {
      id: "script-1",
      content_work_id: work.id,
      direction_version_id: "direction-1",
      version_number: 1,
      parent_script_version_id: null,
      title: "别等问题完美才开始",
      story_mode: "factual",
      script_text: "今天先约一个人，只问他上一次遇到这个问题时做了什么。",
      claim_basis: [],
      creative_elements: [],
      locked_story: null,
      locked_story_digest: null,
      production_notes: {
        production_id: "client-must-not-infer-this-binding",
      },
      created_at: "2026-08-05T01:30:00Z",
    },
  ],
};

const linkedProduction: PersonalIPVideoProduction = {
  id: "video-production-1",
  contract_version: "personal-ip-video-production-v2",
  thread_id: "production-thread-1",
  content_work_id: work.id,
  script_version_id: "script-1",
  title: "正式剧本制作",
  status: "awaiting_review",
  current_stage: "finishing",
  event_count: 11,
  final_artifact: null,
  source_kind: "script",
  source: {
    raw_secret: "must-not-render-production-source",
    preview_ref: "file:///private/preview-must-not-render.mp4",
    provider_payload: "provider-payload-must-not-render",
  },
  delivery_spec: {},
  provider_policy: {},
  budget: {},
  subject_id: null,
  target_account_ids: [],
  created_at: "2026-08-05T01:40:00Z",
  updated_at: "2026-08-05T02:10:00Z",
};

const completedProduction: PersonalIPVideoProduction = {
  ...linkedProduction,
  status: "completed",
  current_stage: "delivery",
  event_count: 13,
  final_artifact: {
    id: "final-artifact-1",
    contract_version: "personal-ip-final-artifact-v1",
    production_id: linkedProduction.id,
    content_sha256: "d".repeat(64),
    size_bytes: 2_621_440,
    mime_type: "video/mp4",
    artifact_digest: "e".repeat(64),
    content_available: true,
    created_at: "2026-08-05T02:09:00Z",
  },
};

const legacyUnboundProduction: PersonalIPVideoProduction = {
  ...linkedProduction,
  id: "legacy-video-production",
  contract_version: "personal-ip-video-production-v1",
  thread_id: "unrelated-production-thread",
  content_work_id: null,
  script_version_id: null,
  title: "不能按时间猜测的旧制作",
  source: { raw_secret: "must-not-render-legacy-source" },
};

async function mockContentAPIs(
  page: Page,
  productions:
    | PersonalIPVideoProduction[]
    | (() => PersonalIPVideoProduction[]),
) {
  let requestedProductionWorkId: string | null = null;
  await page.route("**/api/personal-ip/content-works**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/personal-ip/content-works") {
      await route.fulfill({ status: 200, json: [work] });
      return;
    }
    if (pathname === `/api/personal-ip/content-works/${work.id}`) {
      await route.fulfill({ status: 200, json: lineage });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/personal-ip/video-productions?*", async (route) => {
    requestedProductionWorkId = new URL(route.request().url()).searchParams.get(
      "content_work_id",
    );
    await route.fulfill({
      status: 200,
      json: typeof productions === "function" ? productions() : productions,
    });
  });
  return () => requestedProductionWorkId;
}

test("content page renders authoritative lineage and official Production bindings", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  const requestedProductionWorkId = await mockContentAPIs(page, [
    linkedProduction,
  ]);

  await page.goto("/workspace/content");

  await expect(
    page.getByRole("heading", {
      name: "Breakdown → Writer Brain → Production",
    }),
  ).toBeVisible();
  await expect(
    page.locator("[data-sidebar='sidebar'] a[href='/workspace/content']"),
  ).toBeVisible();
  await expect(page.getByTestId("content-objective-id")).toHaveText(
    "objective-server-1",
  );
  await expect(page.getByTestId("content-linked-task")).toHaveAttribute(
    "href",
    "/workspace/chats/thread-server-1",
  );

  await expect(page.getByTestId("content-breakdown-board")).toContainText(
    "开头先展示了一个具体的行动阻力",
  );
  await expect(page.getByTestId("content-writer-brain-board")).toContainText(
    "别等问题完美才开始",
  );
  await expect(page.getByTestId("production-binding-status")).toHaveText(
    "已绑定 Production",
  );
  await expect(page.getByTestId("linked-production")).toContainText(
    "正式剧本制作",
  );
  await expect(page.getByTestId("linked-production")).toContainText("待审核");
  await expect(page.getByTestId("linked-production")).toContainText("后期");
  await expect(page.getByTestId("production-event-count")).toHaveText(
    "11 条不可变制作回执",
  );
  await expect(page.getByTestId("final-artifact-unavailable")).toContainText(
    "正式成片未完成",
  );
  await expect(page.getByTestId("final-artifact-player")).toHaveCount(0);
  await expect(page.getByTestId("linked-production-task")).toHaveAttribute(
    "href",
    "/workspace/chats/production-thread-1",
  );
  expect(requestedProductionWorkId()).toBe(work.id);
  await expect(
    page.getByText("client-must-not-infer-this-binding"),
  ).toHaveCount(0);
  await expect(page.getByText("must-not-render", { exact: false })).toHaveCount(
    0,
  );
  await expect(page.getByText("must-not-render-production-source")).toHaveCount(
    0,
  );
  await expect(page.getByText("preview-must-not-render")).toHaveCount(0);
  await expect(page.getByText("provider-payload-must-not-render")).toHaveCount(
    0,
  );

  await page.getByRole("link", { name: "开始任务" }).first().click();
  await page.waitForURL("**/workspace/chats/new?content_entry=zero_start");
  await expect(page.getByRole("textbox").first()).toHaveValue(
    /我要从零起盘一条原创内容/,
  );
});

test("a completed delivery renders only its formal final Artifact", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  await mockContentAPIs(page, [completedProduction]);

  await page.goto("/workspace/content");

  const production = page.getByTestId("linked-production");
  await expect(production.getByTestId("final-artifact")).toContainText(
    "交付 QA 已通过",
  );
  await expect(production.getByTestId("final-artifact-hash")).toHaveText(
    `SHA-256 ${"d".repeat(12)}…`,
  );
  await expect(production.getByTestId("final-artifact-size")).toContainText(
    "video/mp4 · 2.5 MB",
  );
  await expect(production.getByTestId("final-artifact-player")).toHaveAttribute(
    "src",
    /\/api\/personal-ip\/artifacts\/final-artifact-1\/content$/,
  );
  await expect(
    production.getByTestId("final-artifact-download"),
  ).toHaveAttribute(
    "href",
    /\/api\/personal-ip\/artifacts\/final-artifact-1\/content$/,
  );
  await expect(page.getByText("preview-must-not-render")).toHaveCount(0);
  await expect(page.getByText("provider-payload-must-not-render")).toHaveCount(
    0,
  );
});

test("a restored final Artifact receipt requires verified file re-import before playback", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  let contentAvailable = false;
  let uploadAttempts = 0;
  let uploadedContentType: string | undefined;
  let uploadedBytes: Buffer | null = null;
  const restoredProduction: PersonalIPVideoProduction = {
    ...completedProduction,
    final_artifact: {
      ...completedProduction.final_artifact!,
      size_bytes: 4,
      content_available: false,
    },
  };
  await mockContentAPIs(page, () => [
    {
      ...restoredProduction,
      final_artifact: {
        ...restoredProduction.final_artifact!,
        content_available: contentAvailable,
      },
    },
  ]);
  await page.route(
    "**/api/personal-ip/artifacts/final-artifact-1/content",
    async (route) => {
      uploadAttempts += 1;
      uploadedContentType = route.request().headers()["content-type"];
      uploadedBytes = route.request().postDataBuffer();
      if (uploadAttempts === 1) {
        await route.fulfill({
          status: 422,
          json: { detail: "文件 SHA-256 与成片回执不匹配" },
        });
        return;
      }
      contentAvailable = true;
      await route.fulfill({
        status: 200,
        json: {
          ...restoredProduction.final_artifact,
          content_available: true,
        },
      });
    },
  );

  await page.goto("/workspace/content");

  const production = page.getByTestId("linked-production");
  await expect(production).toContainText("成片回执已恢复，文件待重新导入");
  await expect(production.getByTestId("final-artifact-player")).toHaveCount(0);
  await expect(production.getByTestId("final-artifact-download")).toHaveCount(
    0,
  );

  const fileInput = production.getByTestId("final-artifact-content-file-input");
  await fileInput.setInputFiles({
    name: "not-a-video.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("nope"),
  });
  await expect(
    production.getByTestId("final-artifact-content-error"),
  ).toHaveText("请选择视频文件（video/*）");
  expect(uploadAttempts).toBe(0);

  const replacement = {
    name: "restored-final.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from([1, 2, 3, 4]),
  };
  await fileInput.setInputFiles(replacement);
  await expect(
    production.getByTestId("final-artifact-content-error"),
  ).toHaveText("文件 SHA-256 与成片回执不匹配");
  await fileInput.setInputFiles(replacement);

  await expect.poll(() => uploadAttempts).toBe(2);
  expect(uploadedContentType).toBe("video/mp4");
  expect(uploadedBytes).toEqual(Buffer.from([1, 2, 3, 4]));
  await expect(production.getByTestId("final-artifact-player")).toBeVisible();
  await expect(production.getByTestId("final-artifact-download")).toBeVisible();
  await expect(
    production.getByTestId("final-artifact-content-missing"),
  ).toHaveCount(0);
});

test("an unbound formal script starts a bounded Production task", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  await mockContentAPIs(page, [legacyUnboundProduction]);

  await page.goto("/workspace/content");

  await expect(page.getByTestId("production-binding-status")).toHaveText(
    "未绑定 Production",
  );
  await expect(page.getByText("不能按时间猜测的旧制作")).toHaveCount(0);
  await expect(page.getByText("must-not-render-legacy-source")).toHaveCount(0);
  const productionEntry = page.getByTestId("start-linked-production");
  await expect(productionEntry).toHaveAttribute(
    "href",
    "/workspace/chats/new?production_content_work_id=content-work-1&production_script_version_id=script-1",
  );

  await productionEntry.click();
  await page.waitForURL(
    "**/workspace/chats/new?production_content_work_id=content-work-1&production_script_version_id=script-1",
  );
  await expect(page.getByRole("textbox").first()).toHaveValue(
    /内容作品 content-work-1.*正式剧本版本 script-1/,
  );
});
