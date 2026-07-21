import { describe, expect, it } from "@rstest/core";

import { PERSONAL_IP_BROWSER_PLATFORMS } from "@/core/personal-ip";

describe("personal IP browser platforms", () => {
  it("keeps the eight supported platforms visible in portfolio order", () => {
    expect(
      PERSONAL_IP_BROWSER_PLATFORMS.map((platform) => platform.id),
    ).toEqual([
      "douyin",
      "wechat_channels",
      "wechat_official",
      "xiaohongshu",
      "x",
      "instagram",
      "youtube",
      "tiktok",
    ]);
  });

  it("provides a secure public creator URL for every login entry", () => {
    expect(PERSONAL_IP_BROWSER_PLATFORMS).toHaveLength(8);
    for (const platform of PERSONAL_IP_BROWSER_PLATFORMS) {
      expect(platform.startUrl).toMatch(/^https:\/\//u);
      expect(platform.label.length).toBeGreaterThan(0);
    }
  });
});
