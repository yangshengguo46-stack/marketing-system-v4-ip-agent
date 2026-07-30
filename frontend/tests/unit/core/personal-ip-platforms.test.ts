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
    expect(
      Object.fromEntries(
        PERSONAL_IP_BROWSER_PLATFORMS.map((platform) => [
          platform.id,
          platform.startUrl,
        ]),
      ),
    ).toEqual({
      douyin: "https://creator.douyin.com/",
      wechat_channels: "https://channels.weixin.qq.com/platform",
      wechat_official: "https://mp.weixin.qq.com/",
      xiaohongshu: "https://creator.xiaohongshu.com/",
      x: "https://x.com/",
      instagram: "https://www.instagram.com/",
      youtube: "https://studio.youtube.com/",
      tiktok: "https://www.tiktok.com/tiktokstudio",
    });
  });
});
