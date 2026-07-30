import type { ScheduleValue } from "@/components/workspace/scheduled-task-schedule-input";

export type RecipeTitleKey = "trending" | "news" | "issues" | "weekly";

export type Recipe = {
  id: string;
  icon: string;
  titleKey: RecipeTitleKey;
  prompt: string;
  schedule: ScheduleValue;
};

// Front-end-only starter recipes. The schedule's timezone is left empty so the
// ScheduleInput falls back to the browser-detected timezone when applied.
export const RECIPES: Recipe[] = [
  {
    id: "trending",
    icon: "🔥",
    titleKey: "trending",
    prompt:
      "每天汇总全部已登录平台账号的新增浏览、粉丝、互动和作品表现，明确标出未采集平台，并告诉我最值得继续追的一个增长机会。",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * *" },
      timezone: "",
    },
  },
  {
    id: "news",
    icon: "📰",
    titleKey: "news",
    prompt:
      "每天结合当前账号定位、受众和近期表现扫描热点，给出最多 5 个值得做的选题，并说明为什么适合这个账号。",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * *" },
      timezone: "",
    },
  },
  {
    id: "issues",
    icon: "🏷️",
    titleKey: "issues",
    prompt:
      "每天回收近期已发布作品的真实数据，和发布前预演及账号基线对照；发现异常增长或明显下滑时直接告诉我。",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * *" },
      timezone: "",
    },
  },
  {
    id: "weekly",
    icon: "📅",
    titleKey: "weekly",
    prompt:
      "每周复盘全部平台的增长、粉丝反馈和作品表现，更新可复用经验，并给出下周最值得做的三件事。",
    schedule: {
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * 1" },
      timezone: "",
    },
  },
];
