import { describe, expect, it } from "@rstest/core";

import {
  countCockpitPending,
  countOperationalAlerts,
  type PersonalIPOperatingCockpit,
  PERSONAL_IP_OPERATING_STAGES,
  PERSONAL_IP_VIDEO_STAGES,
} from "@/core/personal-ip";

describe("personal IP operating cockpit", () => {
  it("keeps the product-owned calibration loop in order", () => {
    expect(PERSONAL_IP_OPERATING_STAGES.map((stage) => stage.id)).toEqual([
      "modeling",
      "preflight",
      "publishing",
      "performance",
      "retrospective",
      "evidence",
    ]);
    expect(PERSONAL_IP_OPERATING_STAGES[0].label).toBe(
      "影响力方向与商业验证",
    );
  });

  it("keeps the full script-to-delivery video pipeline in order", () => {
    expect(PERSONAL_IP_VIDEO_STAGES.map((stage) => stage.id)).toEqual([
      "intake",
      "blueprint",
      "assets",
      "storyboard",
      "generation",
      "consistency",
      "selection",
      "finishing",
      "delivery",
    ]);
  });

  it("counts every explicit queue without treating missing data as zero", () => {
    const cockpit = {
      queues: {
        subjects_needing_strategy_validation: ["subject-1"],
        subjects_needing_differentiation_validation: ["subject-1"],
        preflights_awaiting_publish: ["preflight-1"],
        published_receipts_awaiting_metrics: ["receipt-1"],
        published_receipts_awaiting_retrospective: ["receipt-1"],
      },
    } as unknown as PersonalIPOperatingCockpit;

    expect(countCockpitPending(cockpit)).toBe(5);
    expect(countCockpitPending(undefined)).toBe(0);
  });

  it("counts only explicit operational alerts", () => {
    const cockpit = {
      alerts: {
        summary: {
          total: 3,
          blocking: 2,
          warning: 1,
          by_category: { loop: 1, provider: 1, cost: 1 },
        },
        items: [],
      },
    } as unknown as PersonalIPOperatingCockpit;

    expect(countOperationalAlerts(cockpit)).toBe(3);
    expect(countOperationalAlerts(undefined)).toBe(0);
  });
});
