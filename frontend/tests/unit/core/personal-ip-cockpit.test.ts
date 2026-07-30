import { describe, expect, it } from "@rstest/core";

import {
  countCockpitPending,
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
        preflights_awaiting_publish: ["preflight-1"],
        published_receipts_awaiting_metrics: ["receipt-1"],
        published_receipts_awaiting_retrospective: ["receipt-1"],
      },
    } as PersonalIPOperatingCockpit;

    expect(countCockpitPending(cockpit)).toBe(4);
    expect(countCockpitPending(undefined)).toBe(0);
  });
});
