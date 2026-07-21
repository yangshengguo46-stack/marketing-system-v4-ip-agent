export type PersonalIPBrowserPlatform = {
  id: string;
  label: string;
  startUrl: string;
  description: string;
};

export const PERSONAL_IP_BROWSER_PLATFORMS: readonly PersonalIPBrowserPlatform[] =
  [
    {
      id: "douyin",
      label: "抖音",
      startUrl: "https://creator.douyin.com/",
      description: "创作者中心",
    },
    {
      id: "wechat_channels",
      label: "视频号",
      startUrl: "https://channels.weixin.qq.com/platform",
      description: "视频号助手",
    },
    {
      id: "wechat_official",
      label: "公众号",
      startUrl: "https://mp.weixin.qq.com/",
      description: "微信公众平台",
    },
    {
      id: "xiaohongshu",
      label: "小红书",
      startUrl: "https://creator.xiaohongshu.com/",
      description: "创作服务平台",
    },
    {
      id: "x",
      label: "X",
      startUrl: "https://x.com/",
      description: "账号主页",
    },
    {
      id: "instagram",
      label: "Instagram",
      startUrl: "https://www.instagram.com/",
      description: "账号主页",
    },
    {
      id: "youtube",
      label: "YouTube",
      startUrl: "https://studio.youtube.com/",
      description: "YouTube Studio",
    },
    {
      id: "tiktok",
      label: "TikTok",
      startUrl: "https://www.tiktok.com/tiktokstudio",
      description: "TikTok Studio",
    },
  ];
