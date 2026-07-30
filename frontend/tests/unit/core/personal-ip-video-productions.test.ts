import { describe, expect, it } from "@rstest/core";

import {
  formatVideoCost,
  isMeaningfulVideoConfirmation,
  personalIPMediaModelsPath,
  personalIPVideoArtifactPath,
  personalIPVideoWorkbenchPath,
  videoRecoveryPrompt,
} from "@/core/personal-ip";

describe("Personal-IP video workbench helpers", () => {
  it("reads the owner-facing Ark media model catalog from the gateway", () => {
    expect(personalIPMediaModelsPath()).toBe(
      "/api/personal-ip/video-productions/models",
    );
  });

  it("encodes production ids in the ledger-derived read path", () => {
    expect(personalIPVideoWorkbenchPath("video/id with space")).toBe(
      "/api/personal-ip/video-productions/video%2Fid%20with%20space/workbench",
    );
  });

  it("addresses owner-scoped media by production and immutable artifact hash", () => {
    expect(
      personalIPVideoArtifactPath("video/id with space", "a".repeat(64)),
    ).toBe(
      `/api/personal-ip/video-productions/video%2Fid%20with%20space/artifacts/${"a".repeat(64)}`,
    );
  });

  it("formats authoritative and unknown provider costs without inventing values", () => {
    expect(
      formatVideoCost({ status: "known", amount: 3.2, currency: "CNY" }),
    ).toBe("CNY 3.20");
    expect(
      formatVideoCost({ status: "unknown", reason: "billing unavailable" }),
    ).toBe("费用未知 · billing unavailable");
    expect(formatVideoCost({})).toBe("未记录费用");
  });

  it("keeps only selection, paid calls, and real publishing as confirmations", () => {
    expect(isMeaningfulVideoConfirmation("candidate_selection")).toBe(true);
    expect(isMeaningfulVideoConfirmation("paid_provider_call")).toBe(true);
    expect(isMeaningfulVideoConfirmation("real_publish")).toBe(true);
    expect(isMeaningfulVideoConfirmation("evidence_promotion")).toBe(false);
  });

  it("builds a recovery instruction that resumes from the immutable ledger", () => {
    const prompt = videoRecoveryPrompt({
      productionId: "video-production-1",
      eventKey: "shot-01:attempt-1",
      entityId: "shot-01",
    });

    expect(prompt).toContain("personal_ip_read_video_production");
    expect(prompt).toContain("video-production-1");
    expect(prompt).toContain("shot-01:attempt-1");
    expect(prompt).toContain("不要从聊天记录重建");
  });
});
