"use client";

import {
  BarChart3Icon,
  ClapperboardIcon,
  EyeIcon,
  FileCheck2Icon,
  GaugeIcon,
  LoaderCircleIcon,
  MessageSquareTextIcon,
  RefreshCcwIcon,
  UserRoundIcon,
  UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import {
  buildPersonalIPDashboardView,
  usePersonalIPAccounts,
  usePersonalIPMetrics,
  usePersonalIPPlatformObservations,
  usePersonalIPPublishReceipts,
  usePersonalIPSubjects,
  usePersonalIPVideoProductions,
} from "@/core/personal-ip";

const COMPACT_NUMBER = new Intl.NumberFormat("zh-CN", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function formatMetric(value: number | null) {
  return value === null ? "未采集" : COMPACT_NUMBER.format(value);
}

function formatObservedAt(value: string | null | undefined) {
  if (!value) return "未采集";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function FactCard({
  label,
  value,
  description,
  icon: Icon,
}: {
  label: string;
  value: string;
  description: string;
  icon: typeof EyeIcon;
}) {
  return (
    <Card className="gap-4 py-5">
      <CardHeader className="px-5">
        <div className="flex items-center justify-between gap-3">
          <CardDescription>{label}</CardDescription>
          <span className="bg-muted flex size-8 items-center justify-center rounded-lg">
            <Icon className="size-4" />
          </span>
        </div>
        <CardTitle className="font-mono text-3xl tracking-tight tabular-nums">
          {value}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-muted-foreground px-5 text-xs leading-5">
        {description}
      </CardContent>
    </Card>
  );
}

function GrowthTrend({
  trend,
}: {
  trend: ReturnType<typeof buildPersonalIPDashboardView>["trend"];
}) {
  const measuredViews = trend
    .map((item) => item.views)
    .filter((value): value is number => value !== null);
  const maximum = Math.max(...measuredViews, 1);

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3Icon className="size-4" />
          近七日观测
        </CardTitle>
        <CardDescription>
          只累计 window_total 和 delta；累计快照不计入增长。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {measuredViews.length === 0 ? (
          <div className="text-muted-foreground flex h-56 items-center justify-center rounded-xl border border-dashed text-sm">
            浏览增量未采集
          </div>
        ) : (
          <div className="grid h-60 grid-cols-7 items-end gap-2">
            {trend.map((item) => (
              <div
                key={item.date}
                className="flex h-full min-w-0 flex-col items-center justify-end gap-2"
              >
                <span className="text-muted-foreground text-[10px] tabular-nums">
                  {formatMetric(item.views)}
                </span>
                <div className="bg-muted flex h-40 w-full max-w-12 items-end overflow-hidden rounded-md">
                  {item.views !== null && (
                    <div
                      className="bg-primary w-full rounded-md"
                      style={{
                        height: Math.max(8, (item.views / maximum) * 156),
                      }}
                    />
                  )}
                </div>
                <p className="text-xs font-medium tabular-nums">{item.label}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const subjectsQuery = usePersonalIPSubjects();
  const accountsQuery = usePersonalIPAccounts();
  const metricsQuery = usePersonalIPMetrics();
  const observationsQuery = usePersonalIPPlatformObservations();
  const receiptsQuery = usePersonalIPPublishReceipts();
  const videosQuery = usePersonalIPVideoProductions();

  const accounts = useMemo(
    () => accountsQuery.data ?? [],
    [accountsQuery.data],
  );
  const dashboard = useMemo(
    () => buildPersonalIPDashboardView(metricsQuery.data ?? [], accounts),
    [accounts, metricsQuery.data],
  );
  const publishedCount = (receiptsQuery.data ?? []).filter(
    (receipt) => receipt.status === "published",
  ).length;
  const activeVideos = (videosQuery.data ?? []).filter((production) =>
    ["draft", "running", "awaiting_review", "blocked"].includes(
      production.status,
    ),
  );
  const queries = [
    subjectsQuery,
    accountsQuery,
    metricsQuery,
    observationsQuery,
    receiptsQuery,
    videosQuery,
  ];
  const isLoading = queries.some((query) => query.isLoading);
  const hasError = queries.some((query) => query.isError);

  async function refresh() {
    await Promise.all(queries.map((query) => query.refetch()));
  }

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-y-auto">
        <div className="mx-auto w-full max-w-7xl space-y-8 p-6 lg:p-10">
          <section className="flex flex-wrap items-start justify-between gap-5">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">事实看板</Badge>
                <Badge variant="outline">观测时间可追溯</Badge>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">
                账号、发布、数据和视频任务
              </h1>
              <p className="text-muted-foreground max-w-3xl text-sm leading-6">
                这里只展示已保存或已采集的事实，不判断内容潜力，不给出投流、继续或重启结论。缺失值保持“未采集”。
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={refresh} disabled={isLoading}>
                {isLoading ? (
                  <LoaderCircleIcon className="animate-spin" />
                ) : (
                  <RefreshCcwIcon />
                )}
                刷新
              </Button>
              <Button asChild>
                <Link href="/workspace/personal-ip">管理主体与账号</Link>
              </Button>
            </div>
          </section>

          <section className="bg-muted/20 rounded-2xl border p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <div className="flex items-center gap-2">
                <GaugeIcon className="text-primary size-4" />
                <span className="font-medium">指标覆盖</span>
                <span className="text-muted-foreground">
                  {dashboard.coverage.observedAccountCount}/
                  {dashboard.coverage.activeAccountCount} 个有效账号有观测
                </span>
              </div>
              <span className="text-muted-foreground text-xs">
                最近观测：
                {formatObservedAt(dashboard.coverage.latestObservedAt)}
              </span>
            </div>
            {dashboard.coverage.activeAccountCount > 0 && (
              <Progress
                className="mt-3 h-1.5"
                value={
                  (dashboard.coverage.observedAccountCount /
                    dashboard.coverage.activeAccountCount) *
                  100
                }
              />
            )}
          </section>

          {hasError && (
            <Card className="border-destructive/40 bg-destructive/5 py-4">
              <CardContent className="text-destructive text-sm">
                部分事实接口暂时无法读取；页面没有用默认值补齐缺失数据。
              </CardContent>
            </Card>
          )}

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <FactCard
              label="主体"
              value={String(subjectsQuery.data?.length ?? 0)}
              description="人、品牌、产品和组织的已保存主体。"
              icon={UserRoundIcon}
            />
            <FactCard
              label="有效平台账号"
              value={String(
                accounts.filter((account) => account.status === "active")
                  .length,
              )}
              description="当前未归档的平台账号。"
              icon={UsersIcon}
            />
            <FactCard
              label="已发布回执"
              value={String(publishedCount)}
              description="发布执行已确认成功的回执数量。"
              icon={FileCheck2Icon}
            />
            <FactCard
              label="进行中视频任务"
              value={String(activeVideos.length)}
              description="草稿、运行、待确认或受阻的视频任务。"
              icon={ClapperboardIcon}
            />
          </section>

          <section className="grid gap-4 sm:grid-cols-3">
            <FactCard
              label="近七日新增浏览"
              value={formatMetric(dashboard.totals.views)}
              description="仅来自可比增量口径。"
              icon={EyeIcon}
            />
            <FactCard
              label="近七日新增粉丝"
              value={formatMetric(dashboard.totals.followers)}
              description="仅来自明确记录的粉丝增量。"
              icon={UsersIcon}
            />
            <FactCard
              label="近七日新增互动"
              value={formatMetric(dashboard.totals.engagement)}
              description="已采集点赞、评论、收藏和分享之和。"
              icon={MessageSquareTextIcon}
            />
          </section>

          <section className="grid min-w-0 gap-4 xl:grid-cols-[1.45fr_1fr]">
            <GrowthTrend trend={dashboard.trend} />
            <Card>
              <CardHeader>
                <CardTitle>平台观测汇总</CardTitle>
                <CardDescription>
                  按平台展示最近七日已测量增量和最后观测时间。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {dashboard.platforms.length === 0 ? (
                  <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
                    未采集平台增量
                  </div>
                ) : (
                  dashboard.platforms.map((platform) => (
                    <div
                      key={platform.id}
                      className="flex items-center justify-between gap-4 rounded-xl border p-3"
                    >
                      <div>
                        <p className="text-sm font-medium">{platform.label}</p>
                        <p className="text-muted-foreground text-xs">
                          {platform.observedAccountCount} 个账号 ·{" "}
                          {formatObservedAt(platform.latestObservedAt)}
                        </p>
                      </div>
                      <div className="text-right text-xs">
                        <p>浏览 {formatMetric(platform.views)}</p>
                        <p className="text-muted-foreground">
                          粉丝 {formatMetric(platform.followers)}
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>近期作品观测</CardTitle>
                <CardDescription>
                  按观测时间排列，不进行排名、潜力或投流判断。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {dashboard.posts.length === 0 ? (
                  <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
                    未采集作品级指标
                  </div>
                ) : (
                  dashboard.posts.map((post) => (
                    <div key={post.id} className="rounded-xl border p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="min-w-0 flex-1 truncate text-sm font-medium">
                          {post.title}
                        </p>
                        <Badge variant="outline">{post.platformLabel}</Badge>
                      </div>
                      <p className="text-muted-foreground mt-1 text-xs">
                        {post.accountName} · {formatObservedAt(post.observedAt)}
                      </p>
                      <div className="mt-3 flex gap-5 text-xs">
                        <span>浏览 {formatMetric(post.views)}</span>
                        <span>互动 {formatMetric(post.engagement)}</span>
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>最近平台事实</CardTitle>
                <CardDescription>
                  creator 后台采集记录及其覆盖状态。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {(observationsQuery.data ?? []).slice(0, 8).map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between gap-4 rounded-xl border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {item.platform} · {item.dataset}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {formatObservedAt(item.observed_at)}
                      </p>
                    </div>
                    <Badge variant="outline">{item.status}</Badge>
                  </div>
                ))}
                {(observationsQuery.data ?? []).length === 0 && (
                  <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
                    未采集平台事实
                  </div>
                )}
              </CardContent>
            </Card>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>最近发布回执</CardTitle>
                <CardDescription>显示执行状态和已记录时间。</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {(receiptsQuery.data ?? []).slice(0, 8).map((receipt) => (
                  <div
                    key={receipt.id}
                    className="flex items-center justify-between gap-4 rounded-xl border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">{receipt.platform}</p>
                      <p className="text-muted-foreground text-xs">
                        {formatObservedAt(
                          receipt.published_at ?? receipt.updated_at,
                        )}
                      </p>
                    </div>
                    <Badge variant="outline">{receipt.status}</Badge>
                  </div>
                ))}
                {(receiptsQuery.data ?? []).length === 0 && (
                  <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
                    暂无发布回执
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>视频任务</CardTitle>
                <CardDescription>
                  来自不可变视频任务与事件账本。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {(videosQuery.data ?? []).slice(0, 8).map((production) => (
                  <div
                    key={production.id}
                    className="flex items-center justify-between gap-4 rounded-xl border p-3"
                  >
                    <div>
                      <p className="text-sm font-medium">{production.title}</p>
                      <p className="text-muted-foreground text-xs">
                        {production.current_stage} ·{" "}
                        {formatObservedAt(production.updated_at)}
                      </p>
                    </div>
                    <Badge variant="outline">{production.status}</Badge>
                  </div>
                ))}
                {(videosQuery.data ?? []).length === 0 && (
                  <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
                    暂无视频任务
                  </div>
                )}
                <Button variant="outline" className="w-full" asChild>
                  <Link href="/workspace/chats/new">新建视频任务</Link>
                </Button>
              </CardContent>
            </Card>
          </section>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
