import { describe, expect, it } from "@rstest/core";

import {
  personalIPContentEntryPrompt,
  personalIPContentTaskHref,
  personalIPProductionEntryPrompt,
  personalIPProductionTaskHref,
} from "@/core/personal-ip";

describe("Personal-IP content task entries", () => {
  it("builds bounded zero-start and benchmark task routes", () => {
    expect(personalIPContentTaskHref("zero_start")).toBe(
      "/workspace/chats/new?content_entry=zero_start",
    );
    expect(personalIPContentTaskHref("benchmark")).toBe(
      "/workspace/chats/new?content_entry=benchmark",
    );
  });

  it("prefills only the two active entry routes", () => {
    expect(personalIPContentEntryPrompt("zero_start")).toContain("从零起盘");
    expect(personalIPContentEntryPrompt("benchmark")).toContain("对标作品");
    expect(personalIPContentEntryPrompt("account_history")).toBeUndefined();
    expect(personalIPContentEntryPrompt(null)).toBeUndefined();
  });

  it("starts Production only from bounded server work and script identifiers", () => {
    expect(personalIPProductionTaskHref("work/server", "script 1")).toBe(
      "/workspace/chats/new?production_content_work_id=work%2Fserver&production_script_version_id=script+1",
    );
    expect(
      personalIPProductionEntryPrompt("content-work-1", "script-1"),
    ).toContain("内容作品 content-work-1");
    expect(
      personalIPProductionEntryPrompt("content-work-1", "script-1"),
    ).toContain("正式剧本版本 script-1");
    expect(personalIPProductionEntryPrompt("", "script-1")).toBeUndefined();
    expect(
      personalIPProductionEntryPrompt("content-work-1", null),
    ).toBeUndefined();
    expect(
      personalIPProductionEntryPrompt("w".repeat(65), "script-1"),
    ).toBeUndefined();
  });
});
