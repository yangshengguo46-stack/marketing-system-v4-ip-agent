import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const PRODUCTION = {
  id: "video-production-1",
  thread_id: "video-thread-1",
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

const makeWorkbench = (
  confirmed = false,
  timelineSaved = false,
  finalEditLocked = false,
) => ({
  contract_version: "personal-ip-video-workbench-v1",
  production: confirmed ? { ...PRODUCTION, status: "running" } : PRODUCTION,
  source: { kind: "script", content: PRODUCTION.source },
  domain_contracts: {},
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
    revision_id: timelineSaved ? "timeline-revision-1" : null,
    locked: finalEditLocked,
    final_edit_lock: finalEditLocked
      ? {
          contract_version: "personal-ip-video-final-edit-lock-v1",
          lock_id: "final-edit-lock-1",
          source_revision_id: "timeline-revision-1",
          source_timeline_sha256: "f".repeat(64),
        }
      : null,
    revisions: timelineSaved
      ? [
          {
            event_id: "timeline-event-1",
            revision_id: "timeline-revision-1",
            author_kind: "human",
            intent: "缩短第一镜",
            tracks: [],
            operations: [],
          },
        ]
      : [],
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

test("video workbench keeps internal evidence hidden while preserving creative control", async ({
  page,
}) => {
  const screenshotDirectory = process.env.VIDEO_WORKBENCH_SCREENSHOT_DIR;
  await page.setViewportSize({ width: 1440, height: 900 });
  mockLangGraphAPI(page);
  let confirmed = false;
  let timelineSaved = false;
  let finalEditLocked = false;
  let reviewBody: Record<string, unknown> | null = null;
  let timelineRevisionBody: Record<string, unknown> | null = null;
  let finalEditLockBody: Record<string, unknown> | null = null;

  await page.route(/\/api\/personal-ip\/video-productions(?:\?.*)?$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([PRODUCTION]),
    }),
  );
  await page.route("**/api/personal-ip/video-productions/models", (route) =>
    route.fulfill({
      status: 200,
      json: {
        source: "live",
        default_image_model: "doubao-seedream-5-0-260128",
        default_video_model: "doubao-seedance-2-0-260128",
        image_models: [
          {
            id: "doubao-seedream-5-0-260128",
            display_name: "Seedream 5.0",
            is_default: true,
          },
          {
            id: "doubao-seedream-4-5-251128",
            display_name: "Seedream 4.5",
            is_default: false,
          },
        ],
        video_models: [
          {
            id: "doubao-seedance-2-0-260128",
            display_name: "Seedance 2.0",
            is_default: true,
          },
          {
            id: "doubao-seedance-2-0-fast-260128",
            display_name: "Seedance 2.0 Fast",
            is_default: false,
          },
        ],
      },
    }),
  );
  await page.route(
    "**/api/personal-ip/video-productions/video-production-1/workbench",
    (route) =>
      route.fulfill({
        status: 200,
        json: makeWorkbench(confirmed, timelineSaved, finalEditLocked),
      }),
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
  await page.route(
    "**/api/personal-ip/video-productions/video-production-1/timeline-revisions",
    async (route) => {
      timelineRevisionBody = route.request().postDataJSON() as Record<
        string,
        unknown
      >;
      timelineSaved = true;
      await route.fulfill({
        status: 200,
        json: {
          compiled_contract: {
            contract_version: "personal-ip-video-timeline-revision-v1",
          },
          production: { ...PRODUCTION, status: "running" },
        },
      });
    },
  );
  await page.route(
    "**/api/personal-ip/video-productions/video-production-1/final-edit-lock",
    async (route) => {
      finalEditLockBody = route.request().postDataJSON() as Record<
        string,
        unknown
      >;
      finalEditLocked = true;
      await route.fulfill({
        status: 200,
        json: {
          compiled_contract: {
            contract_version: "personal-ip-video-final-edit-lock-v1",
          },
          production: { ...PRODUCTION, status: "running" },
        },
      });
    },
  );

  await page.goto("/workspace/chats/video-thread-1");

  await expect(
    page.getByText("Agent 回执验收片", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByLabel("选择制作项目")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "返回历史对话" })).toHaveAttribute(
    "href",
    "/workspace/chats",
  );
  await expect(page.getByRole("link", { name: "新建视频任务" })).toHaveAttribute(
    "href",
    "/workspace/chats/new",
  );
  await expect(page.getByText("一句话创作 · 随时人工接管")).toBeVisible();
  await expect(page.getByLabel("视频制作阶段")).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "项目与镜头" }),
  ).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "项目设定与素材" }),
  ).toBeVisible();
  await expect(page.getByLabel("制作时间线")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "设定阶段" })).toBeVisible();
  await expect(page.getByRole("button", { name: "分镜阶段" })).toBeVisible();
  await expect(page.getByRole("button", { name: "剪辑阶段" })).toBeVisible();
  await expect(page.getByRole("button", { name: "成片阶段" })).toBeVisible();
  await expect(page.getByText("当前目标 · 镜头 01")).toBeVisible();

  await page.getByRole("button", { name: "设定阶段" }).click();
  const modelPicker = page.getByRole("button", {
    name: "选择生成模型。图像：自动；视频：自动",
  });
  await expect(modelPicker).toContainText("模型自动");
  await modelPicker.click();
  await page.getByRole("menuitem", { name: /图像模型/ }).hover();
  await page.getByRole("menuitemradio", { name: "Seedream 4.5" }).click();
  await page
    .getByRole("button", { name: /选择生成模型。图像：Seedream 4.5/ })
    .click();
  await page.getByRole("menuitem", { name: /视频模型/ }).hover();
  await page.getByRole("menuitemradio", { name: "Seedance 2.0 Fast" }).click();
  await expect(
    page.getByRole("button", {
      name: "选择生成模型。图像：Seedream 4.5；视频：Seedance 2.0 Fast",
    }),
  ).toContainText("2 项已指定");
  await expect(page.getByText("原始输入、影视蓝图与生产约束")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "查看资产合同" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "查看全部项目素材" }),
  ).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("X-Amz-Credential");
  await expect(page.locator("body")).not.toContainText("user:secret");
  await expect(page.locator("body")).not.toContainText("source sha256");
  await expect(page.locator("body")).not.toContainText("shot_required");
  await page.getByRole("button", { name: "+ 新候选" }).click();
  await expect(
    page.getByLabel(
      "告诉智能体怎样生成或修改当前设定；例如：脸型不变，服装换成黑色风衣，再给我三版……",
    ),
  ).toHaveValue("");
  await expect(page.locator("body")).not.toContainText(
    "personal_ip_compile_video_asset_manifest",
  );

  await page.getByRole("button", { name: "查看角色素材" }).click();
  await expect(
    page.getByLabel(
      "告诉智能体怎样生成或修改当前设定；例如：脸型不变，服装换成黑色风衣，再给我三版……",
    ),
  ).toBeVisible();
  await expect(page.getByText("资产合同", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "分镜阶段" }).click();
  await expect(
    page.getByRole("button", {
      name: "选择生成模型。图像：Seedream 4.5；视频：Seedance 2.0 Fast",
    }),
  ).toBeVisible();
  await expect(page.getByLabel("制作时间线")).toHaveCount(0);
  await expect(page.getByText("镜头合同与连续性证据")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "检查当前候选的运动流畅度" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "检查当前候选的运动流畅度" }).click();
  await expect(
    page.getByLabel(
      "告诉智能体怎样修改当前镜头；可重生首帧、动作、运镜或整个视频候选……",
    ),
  ).toHaveValue("");
  const shotComposer = page.getByLabel(
    "告诉智能体怎样修改当前镜头；可重生首帧、动作、运镜或整个视频候选……",
  );
  const compactComposerBox = await shotComposer.boundingBox();
  expect(compactComposerBox).not.toBeNull();
  await shotComposer.fill(
    [
      "保留当前构图",
      "镜头缓慢推进",
      "加强前景细节",
      "保持远景运动",
      "维持角色一致",
      "整体使用冷蓝色调",
    ].join("\n"),
  );
  await expect
    .poll(async () => (await shotComposer.boundingBox())?.height ?? 0)
    .toBeGreaterThan((compactComposerBox?.height ?? 0) + 60);
  await shotComposer.fill(
    Array.from({ length: 20 }, (_, index) => `第 ${index + 1} 行`).join("\n"),
  );
  await expect
    .poll(async () => (await shotComposer.boundingBox())?.height ?? 999)
    .toBeLessThanOrEqual(161);
  await shotComposer.fill("");
  await expect
    .poll(async () => (await shotComposer.boundingBox())?.height ?? 999)
    .toBeLessThanOrEqual((compactComposerBox?.height ?? 28) + 1);
  await expect(page.locator("body")).not.toContainText(
    "personal_ip_interpolate_video_candidate",
  );
  await expect(page.locator("body")).not.toContainText(
    "personal_ip_run_local_generated_shot_qa",
  );
  if (screenshotDirectory) {
    await page.screenshot({
      path: `${screenshotDirectory}/video-workbench-storyboard-1440x900.png`,
      fullPage: true,
    });
  }

  await expect(page.getByRole("button", { name: "查看生成任务" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "查看候选与一致性" }),
  ).toHaveCount(0);
  await expect(page.getByText("volcengine-simulated")).toHaveCount(0);
  await expect(page.getByText("seedance-2.0")).toHaveCount(0);
  await expect(page.getByText("provider_timeout")).toHaveCount(0);
  await expect(page.getByText("shot-01:candidate-2")).toHaveCount(0);
  await expect(page.getByText("aspect_ratio")).toHaveCount(0);
  await page.getByRole("button", { name: "采用此版本" }).click();
  await expect.poll(() => confirmed).toBe(true);
  expect(reviewBody).toMatchObject({
    event_type: "review_recorded",
    status: "approved",
    entity_type: "candidate",
    entity_id: "shot-01:candidate-2",
    provider: "human-workbench",
  });
  await expect(page.getByText("已生成", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "剪辑阶段" }).click();
  await expect(page.getByText("剪辑监看")).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "项目与镜头" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("complementary", { name: "剪辑管线工具" }),
  ).toHaveCount(0);
  await expect(page.getByText("时间线轨道")).toHaveCount(0);
  await expect(page.getByLabel("制作时间线")).toHaveCount(1);
  await expect(
    page.getByLabel(
      "告诉智能体怎么调时间线，例如：把镜头 02 缩短半秒，音乐从这里淡入……",
    ),
  ).toHaveValue("");
  await page
    .getByRole("button", { name: /交给智能体补全对白\/旁白轨/ })
    .click();
  await expect(
    page.getByLabel(
      "告诉智能体怎么调时间线，例如：把镜头 02 缩短半秒，音乐从这里淡入……",
    ),
  ).toHaveValue("");
  await expect(page.locator("body")).not.toContainText("实测音频时长对齐镜头");
  await expect(
    page.getByPlaceholder("给这次手动修改写一句说明（可选）"),
  ).toHaveCount(0);
  await expect(page.getByLabel("制作时间线").getByRole("textbox")).toHaveCount(
    1,
  );
  await expect(page.getByText("25 fps", { exact: true }).first()).toBeVisible();
  await page
    .getByRole("button", { name: "时间线视频片段 镜头 01 · 回执卡推进" })
    .click();
  await expect(page.getByLabel("片段检查器")).not.toBeVisible();
  const leftTrimHandle = page.getByLabel(
    "裁切视频片段 镜头 01 · 回执卡推进左边缘",
  );
  await expect(leftTrimHandle).toBeVisible();
  await expect(
    page.getByLabel("裁切视频片段 镜头 01 · 回执卡推进右边缘"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "分割" })).not.toBeVisible();
  const leftTrimBox = await leftTrimHandle.boundingBox();
  expect(leftTrimBox).not.toBeNull();
  if (!leftTrimBox) throw new Error("left trim handle has no bounding box");
  await page.mouse.move(
    leftTrimBox.x + leftTrimBox.width / 2,
    leftTrimBox.y + leftTrimBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    leftTrimBox.x + leftTrimBox.width / 2 + 24,
    leftTrimBox.y + leftTrimBox.height / 2,
  );
  await page.mouse.up();
  await page.getByRole("button", { name: "保存 (1)" }).click();
  await expect.poll(() => timelineRevisionBody).not.toBeNull();
  const savedTimelineRevision = timelineRevisionBody as unknown as Record<
    string,
    unknown
  >;
  expect(savedTimelineRevision).toMatchObject({
    author_kind: "human",
    intent: "用户在视频工作台完成 1 项手动修改：裁切",
    fps: 25,
    strategy_confirmed: true,
  });
  expect(
    (savedTimelineRevision.operations as Array<Record<string, unknown>>)[0],
  ).toMatchObject({
    type: "trim",
    clip_id: "clip-shot-01",
  });
  expect(
    (savedTimelineRevision.tracks as Array<Record<string, unknown>>).map(
      (track) => track.type,
    ),
  ).toEqual(["video", "dialogue", "music", "subtitle"]);
  await page.getByRole("button", { name: "完成剪辑" }).click();
  await expect.poll(() => finalEditLockBody).not.toBeNull();
  expect(finalEditLockBody).toMatchObject({
    locked_by: "human",
  });
  await expect(page.getByRole("button", { name: "剪辑已完成" })).toBeVisible();

  await page.getByRole("button", { name: "成片阶段" }).click();
  await expect(
    page.getByRole("button", { name: "批准真实发布" }),
  ).not.toBeVisible();
  await expect(page.getByLabel("最终成片播放器")).toBeVisible();
  await expect(page.getByText("交付检查")).not.toBeVisible();
  await expect(page.getByText("声音正常")).not.toBeVisible();
  await expect(page.getByText("时长正确")).not.toBeVisible();
  await expect(page.getByRole("link", { name: "保存到本地" })).toBeVisible();
  await expect(page.getByRole("button", { name: "返回剪辑" })).toHaveCount(0);
  await expect(page.getByLabel("制作时间线")).toHaveCount(0);
  await expect(
    page.getByRole("complementary", { name: "项目与镜头" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("complementary", { name: "项目设定与素材" }),
  ).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText(
    "personal-ip-delivery-qa-v1",
  );
  await expect(page.locator("body")).not.toContainText("d".repeat(64));

  if (screenshotDirectory) {
    await page.screenshot({
      path: `${screenshotDirectory}/video-workbench-1440x900.png`,
      fullPage: true,
    });
  }

  await page.getByRole("link", { name: /^(新对话|New chat)$/ }).click();
  await expect(page).toHaveURL(/\/workspace\/chats\/new$/);
  await expect(
    page.getByPlaceholder(
      /告诉我账号、平台和目标|Name the account, platform, and outcome/,
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "视频生产工作台" }),
  ).toHaveCount(0);
});
