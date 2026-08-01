"use client";

import { ShieldCheckIcon } from "lucide-react";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  type PersonalIPOperatingCockpit,
  type PersonalIPWorkflowResource,
} from "@/core/personal-ip";

type ReviewItem = Record<string, unknown> & {
  id?: string;
  status?: string;
};

type ReviewEntry = ReviewItem & {
  resource: PersonalIPWorkflowResource;
};

const REVIEW_TABS = [
  { id: "preflight", label: "预演" },
  { id: "publishing", label: "发布" },
  { id: "performance", label: "实绩" },
  { id: "retrospective", label: "复盘" },
] as const;

function text(value: unknown, fallback = "—") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function arrayLength(value: unknown) {
  return Array.isArray(value) ? value.length : 0;
}

const PLATFORM_LABELS: Record<string, string> = {
  douyin: "抖音",
  wechat_channels: "视频号",
  wechat_official: "公众号",
  xiaohongshu: "小红书",
  twitter: "X",
  instagram: "Instagram",
  youtube: "YouTube",
  tiktok: "TikTok",
};

function platformLabel(value: unknown) {
  const platform = text(value, "平台");
  return PLATFORM_LABELS[platform.toLowerCase()] ?? platform;
}

function displayTime(value: unknown, fallback: string) {
  if (typeof value !== "string" || !value.trim()) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function itemTitle(item: ReviewEntry) {
  if (item.resource === "preflights") {
    return `发布前预演 · ${arrayLength(item.target_account_ids)} 个账号`;
  }
  if (item.resource === "publish-receipts") {
    return `${platformLabel(item.platform)} · 发布结果`;
  }
  if (item.resource === "metrics") {
    return `${platformLabel(item.platform)} · 作品数据`;
  }
  if (item.resource === "platform-observations") {
    return `${platformLabel(item.platform)} · 账号数据`;
  }
  if (item.resource === "retrospectives") {
    return `${platformLabel(item.platform)} · 复盘`;
  }
  return "已记录";
}

function itemDescription(item: ReviewEntry) {
  if (item.resource === "preflights") {
    return displayTime(item.created_at, "时间未知");
  }
  if (item.resource === "publish-receipts") {
    return displayTime(item.published_at ?? item.updated_at, "等待发布结果");
  }
  if (
    item.resource === "metrics" ||
    item.resource === "platform-observations"
  ) {
    return displayTime(item.observed_at, "观测时间未知");
  }
  if (item.resource === "retrospectives") {
    return displayTime(item.created_at, "时间未知");
  }
  return "时间未知";
}

function statusLabel(status: unknown) {
  const value = typeof status === "string" ? status.toLowerCase() : "";
  if (["completed", "success", "succeeded", "confirmed"].includes(value)) {
    return "已完成";
  }
  if (["approved", "promoted", "sealed"].includes(value)) return "已验证";
  if (["failed", "error", "rejected"].includes(value)) return "未完成";
  if (["pending", "queued", "running", "proposed"].includes(value)) {
    return "进行中";
  }
  return "已记录";
}

function ReviewList({ items }: { items: ReviewEntry[] }) {
  if (items.length === 0) {
    return (
      <div className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-sm">
        暂无记录。智能体推进工作后，回执会自动出现在这里。
      </div>
    );
  }
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {items.map((item) => (
        <Card key={`${item.resource}:${String(item.id)}`} className="py-4">
          <CardContent className="flex items-start justify-between gap-4 px-4">
            <div className="min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <p className="line-clamp-2 text-sm font-medium">
                  {itemTitle(item)}
                </p>
                <Badge
                  variant={item.status === "proposed" ? "secondary" : "outline"}
                >
                  {statusLabel(item.status)}
                </Badge>
              </div>
              <p className="text-muted-foreground line-clamp-2 text-xs leading-5">
                {itemDescription(item)}
              </p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function OperatingReviewPanel({
  cockpit,
}: {
  cockpit: PersonalIPOperatingCockpit;
}) {
  const entries = useMemo(() => {
    const withResource = (
      items: Array<Record<string, unknown>>,
      resource: PersonalIPWorkflowResource,
    ): ReviewEntry[] => items.map((item) => ({ ...item, resource }));
    return {
      preflight: withResource(cockpit.recent.preflights ?? [], "preflights"),
      publishing: withResource(
        cockpit.recent.publish_receipts ?? [],
        "publish-receipts",
      ),
      performance: [
        ...withResource(cockpit.recent.metrics ?? [], "metrics"),
        ...withResource(
          cockpit.recent.platform_observations ?? [],
          "platform-observations",
        ),
      ],
      retrospective: withResource(
        cockpit.recent.retrospectives ?? [],
        "retrospectives",
      ),
    };
  }, [cockpit.recent]);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <ShieldCheckIcon className="size-5" />
          回执与学习证据
        </h2>
        <p className="text-muted-foreground text-sm">
          智能体负责执行，并根据多次真实表现持续更新可复用经验。
        </p>
      </div>
      <Tabs defaultValue="preflight">
        <TabsList className="max-w-full overflow-x-auto">
          {REVIEW_TABS.map((tab) => (
            <TabsTrigger key={tab.id} value={tab.id}>
              {tab.label}
              <Badge variant="outline" className="ml-1 px-1.5">
                {entries[tab.id].length}
              </Badge>
            </TabsTrigger>
          ))}
        </TabsList>
        {REVIEW_TABS.map((tab) => (
          <TabsContent key={tab.id} value={tab.id}>
            <ReviewList items={entries[tab.id]} />
          </TabsContent>
        ))}
      </Tabs>
    </section>
  );
}
