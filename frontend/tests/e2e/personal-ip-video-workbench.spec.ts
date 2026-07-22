import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const PRODUCTION = {
  id: "video-production-1",
  title: "Agent 回执验收片",
  status: "awaiting_review",
  current_stage: "selection",
  event_count: 10,
  source_kind: "script",
  source: { script: "让每一步执行都有可核验回执。" },
  delivery_spec: { aspect_ratio: "9:16", duration_seconds: 2 },
  provider_policy: { video: ["seedance"], image: ["seedream"] },
  budget: { paid_calls_require_explicit_approval: true },
  created_at: "2026-07-22T05:00:00+00:00",
  updated_at: "2026-07-22T05:10:00+00:00",
};

const FAILED_TASK = {
  id: "event-4",
  event_key: "shot-01:attempt-1",
  sequence: 4,
  event_type: "shot_generation_failed",
  stage: "generation",
  status: "failed",
  entity_type: "shot",
  entity_id: "shot-01",
  shot_id: "shot-01",
  provider: "volcengine-simulated",
  model: "seedance-2.0",
  provider_task_id: "task-attempt-1",
  attempt: 1,
  retry_of: null,
  cost: { status: "unknown", reason: "billing unavailable" },
  failure: {
    category: "provider_timeout",
    message: "executor timed out",
    retryable: true,
  },
  input_refs: ["file:///tmp/video-prompt.json"],
  output_refs: [],
  artifacts: [],
  occurred_at: "2026-07-22T05:04:00+00:00",
};

const RETRY_TASK = {
  ...FAILED_TASK,
  id: "event-5",
  event_key: "shot-01:attempt-2",
  sequence: 5,
  event_type: "shot_generation_completed",
  status: "succeeded",
  entity_type: "candidate",
  entity_id: "shot-01:candidate-2",
  provider_task_id: "task-attempt-2",
  attempt: 2,
  retry_of: "shot-01:attempt-1",
  cost: { status: "known", amount: 0, currency: "CNY" },
  failure: null,
  output_refs: ["file:///tmp/video-e2e/shot-01-attempt-2.mp4"],
  artifacts: [
    {
      ref: "file:///tmp/video-e2e/shot-01-attempt-2.mp4",
      sha256: "c".repeat(64),
      size_bytes: 256,
      mime_type: "video/mp4",
    },
  ],
};

const makeWorkbench = (confirmed = false) => ({
  contract_version: "personal-ip-video-workbench-v1",
  production: confirmed ? { ...PRODUCTION, status: "running" } : PRODUCTION,
  source: { kind: "script", content: PRODUCTION.source },
  stage_summary: [
    "intake",
    "blueprint",
    "assets",
    "storyboard",
    "generation",
    "consistency",
    "selection",
    "finishing",
    "delivery",
  ].map((id, index) => ({
    id,
    label: [
      "剧本理解",
      "影视蓝图",
      "资产建档",
      "分镜",
      "逐镜生成",
      "一致性检查",
      "选片 / 确认",
      "配音剪辑",
      "交付",
    ][index],
    ledger_state:
      index < 6 ? "recorded" : index === 6 ? "attention" : "not_started",
    event_count: index === 4 ? 2 : 1,
    latest_event: null,
  })),
  blueprint: {
    events: [],
    artifacts: [
      {
        ref: "https://user:secret@example.com/blueprint.json?X-Amz-Credential=secret#download",
        sha256: "a".repeat(64),
      },
    ],
  },
  assets: [
    {
      entity_type: "scene",
      id: "asset-01",
      status: "succeeded",
      latest_event: null,
      version: 3,
      source_sha256: "b".repeat(64),
      generation_route: "seedream_character_board",
      projection_mode: "exterior_orbit",
      coverage: { tier: "shot_required", view_ids: ["front"] },
      lineage: { source_version: 2 },
      artifacts: [
        {
          ref: "file:///tmp/video-e2e/asset.png",
          sha256: "b".repeat(64),
          size_bytes: 128,
          mime_type: "image/png",
        },
      ],
      event_ids: ["event-2"],
    },
  ],
  storyboard: { events: [], shot_count: 1, artifacts: [] },
  shots: [
    {
      id: "shot-01",
      spec: {
        order: 1,
        title: "回执卡推进",
        duration_seconds: 2,
        first_frame: "回执卡位于画面中央。",
        last_frame: "校验标记完成点亮。",
        motion: "缓慢推近一次。",
        preserve_elements: ["卡片身份", "画幅"],
        change_elements: ["景别"],
      },
      task_ids: ["event-4", "event-5"],
      candidate_ids: ["shot-01:candidate-2"],
      selected_candidate_id: confirmed ? "shot-01:candidate-2" : null,
    },
  ],
  tasks: [FAILED_TASK, RETRY_TASK],
  candidates: [
    {
      id: "shot-01:candidate-2",
      shot_id: "shot-01",
      status: "succeeded",
      selected: confirmed,
      selection: confirmed ? { id: "selection-event" } : null,
      consistency: {
        checks: { aspect_ratio: true, reference_asset_present: true },
      },
      quality: {
        technical_gate_passed: true,
        internal_cut_gate_passed: true,
        first_frame_anchor_score: 0.94,
      },
      review: null,
      artifacts: RETRY_TASK.artifacts,
      task_ids: ["event-5"],
      event_ids: ["event-5", "event-6"],
    },
  ],
  continuity: {
    bridges: [
      {
        bridge_id: "intro-to-shot-01",
        from_shot_id: "intro",
        to_shot_id: "shot-01",
        inherited_state_sha256: "e".repeat(64),
        preserve_facts: ["卡片身份"],
        cut_kind: "straight_cut",
        axis_relation: "same_axis",
      },
    ],
    recovery_scopes: [
      {
        event_id: "event-4",
        event_key: "shot-01:attempt-1",
        entity_id: "shot-01",
        source: "shot_execution_drift",
        categories: ["provider_timeout"],
        affected_shot_ids: ["shot-01"],
        affected_asset_ids: [],
        retryable: true,
      },
    ],
  },
  confirmations: [
    ...(!confirmed
      ? [
          {
            id: "event-7",
            event_key: "shot-01:selection-review",
            kind: "candidate_selection",
            entity_type: "candidate",
            entity_id: "shot-01:candidate-2",
            reason: "候选通过一致性检查",
            requested_at: "2026-07-22T05:07:00+00:00",
          },
        ]
      : []),
    {
      id: "event-publish-review",
      event_key: "delivery:publish-review",
      kind: "real_publish",
      entity_type: "delivery",
      entity_id: "delivery-v1",
      reason: "发布到真实平台前需要确认最终公开动作",
      requested_at: "2026-07-22T05:11:00+00:00",
    },
  ],
  timeline: {
    events: [],
    fps: 25,
    duration_sec: 2,
    tracks: [
      {
        type: "video",
        entity_id: "timeline-final-v1",
        status: "succeeded",
        artifacts: RETRY_TASK.artifacts,
        clips: [
          {
            id: "clip-shot-01",
            shot_id: "shot-01",
            start_sec: 0,
            duration_sec: 2,
            source_sha256: "c".repeat(64),
          },
        ],
        event_id: "event-9",
      },
      {
        type: "audio",
        entity_id: "voice-01",
        status: "succeeded",
        artifacts: [],
        clips: [],
        event_id: "event-8",
      },
    ],
  },
  delivery: {
    qa_events: [
      {
        id: "event-10",
        payload: {
          contract_version: "personal-ip-delivery-qa-v1",
          passed: true,
          checks: { duration: { passed: true }, audio: { passed: true } },
        },
      },
    ],
    delivery_events: [],
    qa_passed: true,
    artifacts: [
      {
        ref: "file:///tmp/video-e2e/final.mp4",
        sha256: "d".repeat(64),
        size_bytes: 512,
        mime_type: "video/mp4",
      },
    ],
  },
  events: [],
});

test("video workbench exposes ledger evidence, recovery, and candidate confirmation", async ({
  page,
}) => {
  const screenshotDirectory = process.env.VIDEO_WORKBENCH_SCREENSHOT_DIR;
  await page.setViewportSize({ width: 1440, height: 900 });
  mockLangGraphAPI(page);
  let confirmed = false;
  let reviewBody: Record<string, unknown> | null = null;

  await page.route(/\/api\/personal-ip\/video-productions(?:\?.*)?$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([PRODUCTION]),
    }),
  );
  await page.route(
    "**/api/personal-ip/video-productions/video-production-1/workbench",
    (route) => route.fulfill({ status: 200, json: makeWorkbench(confirmed) }),
  );
  await page.route(
    "**/api/personal-ip/video-productions/video-production-1/events",
    async (route) => {
      reviewBody = route.request().postDataJSON() as Record<string, unknown>;
      confirmed = true;
      await route.fulfill({
        status: 200,
        json: { ...PRODUCTION, status: "running" },
      });
    },
  );

  await page.goto("/workspace/personal-ip/video");

  await expect(
    page.getByRole("heading", { name: "视频生产工作台" }),
  ).toBeVisible();
  await expect(page.getByText("Agent 回执验收片").first()).toBeVisible();
  await expect(page.getByText("账本派生 · 不创建第二套状态")).toBeVisible();
  await expect(page.getByText("剧本理解")).toBeVisible();
  await expect(page.getByText("让每一步执行都有可核验回执。")).toBeVisible();
  await expect(
    page.getByText("https://example.com/blueprint.json"),
  ).toBeVisible();
  await expect(page.locator("body")).not.toContainText("X-Amz-Credential");
  await expect(page.locator("body")).not.toContainText("user:secret");

  await page.getByRole("tab", { name: "资产" }).click();
  await expect(page.getByText("v3")).toBeVisible();
  await expect(page.getByText("shot_required")).toBeVisible();

  await page.getByRole("tab", { name: "分镜" }).click();
  await expect(page.getByText("回执卡位于画面中央。")).toBeVisible();
  await expect(page.getByText("校验标记完成点亮。")).toBeVisible();
  await expect(page.getByText("局部恢复范围")).toBeVisible();
  await expect(page.getByText("跨镜状态 · intro → shot-01")).toBeVisible();
  if (screenshotDirectory) {
    await page
      .getByText("跨镜状态 · intro → shot-01")
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `${screenshotDirectory}/video-workbench-storyboard-1440x900.png`,
      fullPage: true,
    });
  }

  await page.getByRole("tab", { name: "任务与重试" }).click();
  await expect(page.getByText("volcengine-simulated").first()).toBeVisible();
  await expect(page.getByText("seedance-2.0").first()).toBeVisible();
  await expect(page.getByText("task-attempt-1")).toBeVisible();
  await expect(page.getByText("provider_timeout")).toBeVisible();
  await expect(page.getByText("shot-01:attempt-1").last()).toBeVisible();
  await expect(page.getByText("费用未知 · billing unavailable")).toBeVisible();

  await page.getByRole("tab", { name: "候选与一致性" }).click();
  await expect(page.getByText("shot-01:candidate-2")).toBeVisible();
  await expect(page.getByText("aspect_ratio")).toBeVisible();
  await expect(page.getByText("first_frame_anchor_score")).toBeVisible();
  await page.getByRole("button", { name: "确认选用" }).click();
  await expect.poll(() => confirmed).toBe(true);
  expect(reviewBody).toMatchObject({
    event_type: "review_recorded",
    status: "approved",
    entity_type: "candidate",
    entity_id: "shot-01:candidate-2",
    provider: "human-workbench",
  });
  await expect(page.getByText("已选片")).toBeVisible();

  await page.getByRole("tab", { name: "配音与时间线" }).click();
  await expect(page.getByText("25 fps")).toBeVisible();
  await expect(page.getByText("clip-shot-01")).toBeVisible();

  await page.getByRole("tab", { name: "交付 QA" }).click();
  await expect(page.getByText("真实发布确认")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "批准真实发布" }),
  ).toBeVisible();
  await expect(page.getByText("personal-ip-delivery-qa-v1")).toBeVisible();
  await expect(page.getByText("d".repeat(64))).toBeVisible();

  if (screenshotDirectory) {
    await page.screenshot({
      path: `${screenshotDirectory}/video-workbench-1440x900.png`,
      fullPage: true,
    });
  }
});
