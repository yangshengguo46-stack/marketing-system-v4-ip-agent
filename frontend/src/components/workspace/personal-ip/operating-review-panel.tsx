"use client";

import { EyeIcon, LoaderCircleIcon, ShieldCheckIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  type PersonalIPOperatingCockpit,
  type PersonalIPWorkflowResource,
  usePersonalIPWorkflowDetail,
} from "@/core/personal-ip";

type ReviewItem = Record<string, unknown> & {
  id?: string;
  status?: string;
};

type ReviewEntry = ReviewItem & {
  resource: PersonalIPWorkflowResource;
};

type DetailTarget = {
  resource: PersonalIPWorkflowResource;
  id: string;
  title: string;
} | null;

const REVIEW_TABS = [
  { id: "preflight", label: "预演" },
  { id: "publishing", label: "发布" },
  { id: "performance", label: "实绩" },
  { id: "retrospective", label: "复盘" },
  { id: "evidence", label: "证据晋级" },
] as const;

function text(value: unknown, fallback = "—") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function arrayLength(value: unknown) {
  return Array.isArray(value) ? value.length : 0;
}

function number(value: unknown, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function itemTitle(item: ReviewEntry) {
  if (item.resource === "preflights") {
    return `${text(item.provider, "模型预演")} · ${arrayLength(item.target_account_ids)} 个目标账号`;
  }
  if (item.resource === "publish-receipts") {
    return `${text(item.platform, "平台")} · ${text(item.executor, "执行器")}`;
  }
  if (item.resource === "metrics") {
    return `${text(item.platform, "平台")} · ${text(item.scope, "指标")}`;
  }
  if (item.resource === "platform-observations") {
    return `${text(item.platform, "平台")} · ${text(item.dataset, "经营数据")}`;
  }
  if (item.resource === "retrospectives") {
    return `${text(item.platform, "平台")} · ${text(item.horizon, "复盘")}`;
  }
  return text(item.claim, "已晋级证据");
}

function itemDescription(item: ReviewEntry) {
  if (item.resource === "preflights") {
    return `${text(item.model_version, "模型版本未知")} · ${text(item.created_at, "时间未知")}`;
  }
  if (item.resource === "publish-receipts") {
    return `${number(item.attempt_count)} 次执行 · ${text(item.published_at ?? item.updated_at, "尚未发布")}`;
  }
  if (
    item.resource === "metrics" ||
    item.resource === "platform-observations"
  ) {
    return text(item.observed_at, "观测时间未知");
  }
  if (item.resource === "retrospectives") {
    return `${text(item.comparison_state, "未比较")} · ${text(item.created_at, "时间未知")}`;
  }
  return `${arrayLength(item.retrospective_ids)} 份复盘证据 · 最低支持 ${number(item.minimum_support, 3)}`;
}

function ReviewList({
  items,
  onDetail,
}: {
  items: ReviewEntry[];
  onDetail: (item: ReviewEntry) => void;
}) {
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
                  {text(item.status, "已记录")}
                </Badge>
              </div>
              <p className="text-muted-foreground line-clamp-2 text-xs leading-5">
                {itemDescription(item)}
              </p>
            </div>
            <div className="flex shrink-0 gap-1">
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="查看完整证据"
                onClick={() => onDetail(item)}
              >
                <EyeIcon />
              </Button>
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
  const [detail, setDetail] = useState<DetailTarget>(null);
  const detailQuery = usePersonalIPWorkflowDetail(
    detail?.resource ?? "preflights",
    detail?.id ?? null,
  );

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
      evidence: withResource(
        cockpit.recent.evidence_promotions ?? [],
        "evidence-promotions",
      ),
    };
  }, [cockpit.recent]);

  const openDetail = (item: ReviewEntry) => {
    if (!item.id) return;
    setDetail({
      resource: item.resource,
      id: item.id,
      title: itemTitle(item),
    });
  };

  return (
    <>
      <section className="space-y-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <ShieldCheckIcon className="size-5" />
            回执与学习证据
          </h2>
          <p className="text-muted-foreground text-sm">
            智能体负责执行，并按跨样本规则自动晋级；你可以在这里读取完整回执和依据。
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
              <ReviewList items={entries[tab.id]} onDetail={openDetail} />
            </TabsContent>
          ))}
        </Tabs>
      </section>

      <Dialog
        open={Boolean(detail)}
        onOpenChange={(open) => !open && setDetail(null)}
      >
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{detail?.title ?? "完整经营证据"}</DialogTitle>
            <DialogDescription>
              读取的是当前用户拥有的不可变请求、回执和证据快照。
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="h-[min(65vh,680px)] rounded-md border">
            {detailQuery.isLoading ? (
              <div className="text-muted-foreground flex items-center gap-2 p-5 text-sm">
                <LoaderCircleIcon className="size-4 animate-spin" />
                正在读取完整证据…
              </div>
            ) : detailQuery.isError ? (
              <p className="text-destructive p-5 text-sm">
                {detailQuery.error instanceof Error
                  ? detailQuery.error.message
                  : "读取失败"}
              </p>
            ) : (
              <pre className="overflow-auto p-5 text-xs leading-5 break-words whitespace-pre-wrap">
                {JSON.stringify(detailQuery.data ?? {}, null, 2)}
              </pre>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
}
