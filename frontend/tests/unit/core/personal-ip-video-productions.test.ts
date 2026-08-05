import { describe, expect, it } from "@rstest/core";

import {
  type PersonalIPVideoProduction,
  formatPersonalIPFinalArtifactSize,
  formatVideoCost,
  isMeaningfulVideoConfirmation,
  personalIPFinalArtifactContentFileError,
  personalIPFinalArtifactContentPath,
  personalIPMediaModelsPath,
  personalIPVideoArtifactPath,
  personalIPVideoWorkbenchPath,
  selectPersonalIPFinalArtifact,
  selectPersonalIPFinalArtifactReceipt,
  videoRecoveryPrompt,
} from "@/core/personal-ip";

const finalArtifact = {
  id: "final-artifact-1",
  contract_version: "personal-ip-final-artifact-v1" as const,
  production_id: "video-production-1",
  content_sha256: "a".repeat(64),
  size_bytes: 2_621_440,
  mime_type: "video/mp4",
  artifact_digest: "b".repeat(64),
  content_available: true,
  created_at: "2026-08-05T10:00:00Z",
};

const completedProduction: PersonalIPVideoProduction = {
  id: "video-production-1",
  contract_version: "personal-ip-video-production-v2",
  thread_id: "production-thread-1",
  content_work_id: "content-work-1",
  script_version_id: "script-1",
  title: "正式剧本制作",
  status: "completed",
  current_stage: "delivery",
  event_count: 12,
  final_artifact: finalArtifact,
  source_kind: "script",
  source: {},
  delivery_spec: {},
  provider_policy: {},
  budget: {},
  created_at: "2026-08-05T09:00:00Z",
  updated_at: "2026-08-05T10:00:00Z",
};

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

  it("addresses a formal Artifact by its server identity without hash scanning", () => {
    expect(personalIPFinalArtifactContentPath("artifact/id with space")).toBe(
      "/api/personal-ip/artifacts/artifact%2Fid%20with%20space/content",
    );
  });

  it("selects only a completed delivery with a valid formal Artifact", () => {
    expect(selectPersonalIPFinalArtifact(completedProduction)).toEqual(
      finalArtifact,
    );
    expect(formatPersonalIPFinalArtifactSize(finalArtifact.size_bytes)).toBe(
      "2.5 MB",
    );
    expect(formatPersonalIPFinalArtifactSize(512)).toBe("1 KB");
  });

  it("preserves a restored receipt while withholding unavailable content", () => {
    const unavailableArtifact = {
      ...finalArtifact,
      content_available: false,
    };
    const restoredProduction = {
      ...completedProduction,
      final_artifact: unavailableArtifact,
    };

    expect(selectPersonalIPFinalArtifactReceipt(restoredProduction)).toEqual(
      unavailableArtifact,
    );
    expect(selectPersonalIPFinalArtifact(restoredProduction)).toBeNull();
  });

  it("validates a replacement file against the formal receipt before upload", () => {
    expect(
      personalIPFinalArtifactContentFileError(finalArtifact, {
        type: "video/mp4",
        size: finalArtifact.size_bytes,
      }),
    ).toBeNull();
    expect(
      personalIPFinalArtifactContentFileError(finalArtifact, {
        type: "text/plain",
        size: finalArtifact.size_bytes,
      }),
    ).toBe("请选择视频文件（video/*）");
    expect(
      personalIPFinalArtifactContentFileError(finalArtifact, {
        type: "video/webm",
        size: finalArtifact.size_bytes,
      }),
    ).toContain("文件类型不匹配");
    expect(
      personalIPFinalArtifactContentFileError(finalArtifact, {
        type: "video/mp4",
        size: 0,
      }),
    ).toBe("不能导入空的视频文件");
    expect(
      personalIPFinalArtifactContentFileError(finalArtifact, {
        type: "video/mp4",
        size: 1,
      }),
    ).toContain("文件大小不匹配");
  });

  it("never promotes a preview, stale shape, or mismatched Artifact", () => {
    expect(
      selectPersonalIPFinalArtifact({
        ...completedProduction,
        status: "awaiting_review",
      }),
    ).toBeNull();
    expect(
      selectPersonalIPFinalArtifactReceipt({
        ...completedProduction,
        final_artifact: {
          ...finalArtifact,
          content_available: undefined as unknown as boolean,
        },
      }),
    ).toBeNull();
    expect(
      selectPersonalIPFinalArtifact({
        ...completedProduction,
        current_stage: "finishing",
      }),
    ).toBeNull();
    expect(
      selectPersonalIPFinalArtifact({
        ...completedProduction,
        final_artifact: {
          ...finalArtifact,
          production_id: "another-production",
        },
      }),
    ).toBeNull();
    expect(
      selectPersonalIPFinalArtifact({
        ...completedProduction,
        final_artifact: {
          ...finalArtifact,
          content_sha256: "not-a-sha256",
        },
      }),
    ).toBeNull();
    expect(
      selectPersonalIPFinalArtifact({
        ...completedProduction,
        final_artifact: {
          ...finalArtifact,
          mime_type: "application/json",
        },
      }),
    ).toBeNull();
    expect(
      selectPersonalIPFinalArtifact({
        ...completedProduction,
        final_artifact: null,
      }),
    ).toBeNull();
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
