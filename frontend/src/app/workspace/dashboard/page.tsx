"use client";

import {
  AlertTriangleIcon,
  ArrowUpRightIcon,
  BarChart3Icon,
  BotIcon,
  ClapperboardIcon,
  EyeIcon,
  GaugeIcon,
  LoaderCircleIcon,
  MessageSquareTextIcon,
  RefreshCcwIcon,
  RocketIcon,
  SparklesIcon,
  TrendingUpIcon,
  UserPlusIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { OperatingReviewPanel } from "@/components/workspace/personal-ip";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import {
  buildPersonalIPDashboardView,
  countCockpitPending,
  countOperationalAlerts,
  type PersonalIPOperationalAlert,
  PERSONAL_IP_OPERATING_STAGES,
  usePersonalIPAccounts,
  usePersonalIPMetrics,
  usePersonalIPOperatingCockpit,
} from "@/core/personal-ip";
import { pathOfThread } from "@/core/threads/utils";

const COMPACT_NUMBER = new Intl.NumberFormat("zh-CN", {
  notation: "compact",
  maximumFractionDigits: 1,
});
const PERCENT = new Intl.NumberFormat("zh-CN", {
  style: "percent",
  maximumFractionDigits: 1,
});

function formatMetric(value: number) {
  return COMPACT_NUMBER.format(value);
}

function formatObservedAt(value: string | null) {
  if (!value) return "尚无观测";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "观测时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function MetricCard({
  label,
  value,
  description,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number | null;
  description: string;
  icon: typeof EyeIcon;
  accent: string;
}) {
  return (
    <Card className="relative gap-4 overflow-hidden py-5">
      <div aria-hidden className={`absolute inset-x-0 top-0 h-0.5 ${accent}`} />
      <CardHeader className="px-5">
        <div className="flex items-center justify-between gap-3">
          <CardDescription>{label}</CardDescription>
          <span className="bg-muted flex size-8 items-center justify-center rounded-lg">
            <Icon className="size-4" />
          </span>
        </div>
        <CardTitle className="font-mono text-3xl tracking-tight tabular-nums">
          {value === null ? "—" : formatMetric(value)}
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
  const maxViews = Math.max(...trend.map((item) => item.views), 1);
  const hasData = trend.some(
    (item) => item.views || item.followers || item.engagement,
  );

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUpIcon className="size-4" />
          近七日增长趋势
        </CardTitle>
        <CardDescription>
          每根柱子是当天可比口径的新增浏览，底部同时标出新增粉丝。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!hasData ? (
          <div className="text-muted-foreground flex h-56 items-center justify-center rounded-xl border border-dashed text-sm">
            还没有可比增量。完成账号登录并采集两次数据后，这里会出现趋势。
          </div>
        ) : (
          <div
            className="grid h-60 grid-cols-7 items-end gap-2"
            aria-label="近七日新增浏览量"
          >
            {trend.map((item) => {
              const height = Math.max(8, (item.views / maxViews) * 156);
              return (
                <div
                  key={item.date}
                  className="flex h-full min-w-0 flex-col items-center justify-end gap-2"
                >
                  <span className="text-muted-foreground text-[10px] tabular-nums">
                    {item.views > 0 ? formatMetric(item.views) : "—"}
                  </span>
                  <div className="bg-muted flex h-40 w-full max-w-12 items-end overflow-hidden rounded-md">
                    <div
                      className="from-primary/55 to-primary w-full rounded-md bg-gradient-to-t"
                      style={{ height }}
                    />
                  </div>
                  <div className="text-center">
                    <p className="text-xs font-medium tabular-nums">
                      {item.label}
                    </p>
                    <p className="text-muted-foreground mt-0.5 text-[10px] tabular-nums">
                      +{formatMetric(item.followers)} 粉
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PlatformGrowth({
  platforms,
}: {
  platforms: ReturnType<typeof buildPersonalIPDashboardView>["platforms"];
}) {
  const maximum = Math.max(...platforms.map((item) => item.views), 1);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3Icon className="size-4" />
          平台增量
        </CardTitle>
        <CardDescription>
          相同七日窗口内，各平台新增浏览和粉丝贡献。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {platforms.length === 0 ? (
          <div className="text-muted-foreground flex h-56 items-center justify-center rounded-xl border border-dashed px-6 text-center text-sm">
            暂无平台增量，数据不会被当作 0。
          </div>
        ) : (
          platforms.slice(0, 8).map((platform, index) => (
            <div key={platform.id} className="space-y-2">
              <div className="flex items-center justify-between gap-3 text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="text-muted-foreground w-4 text-xs tabular-nums">
                    {index + 1}
                  </span>
                  <span className="truncate font-medium">{platform.label}</span>
                </div>
                <span className="font-mono text-xs tabular-nums">
                  {formatMetric(platform.views)} 浏览 · +
                  {formatMetric(platform.followers)} 粉
                </span>
              </div>
              <Progress
                value={(platform.views / maximum) * 100}
                aria-label={`${platform.label}新增浏览占比`}
              />
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

const ALERT_CATEGORY_LABELS: Record<
  PersonalIPOperationalAlert["category"],
  string
> = {
  loop: "经营闭环",
  provider: "供应商",
  cost: "成本",
};

function OperationalAlerts({
  alerts,
}: {
  alerts: PersonalIPOperationalAlert[];
}) {
  if (alerts.length === 0) return null;
  return (
    <Card className="border-amber-500/35 bg-amber-500/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangleIcon className="size-4 text-amber-600" />
          运行异常
        </CardTitle>
        <CardDescription>
          只展示可执行的闭环、供应商和成本问题，不包含密钥或供应商原始报错。
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 lg:grid-cols-2">
        {alerts.slice(0, 6).map((alert) => (
          <div
            key={alert.alert_id}
            className="bg-background flex min-w-0 items-start justify-between gap-4 rounded-xl border p-4"
          >
            <div className="min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  variant={
                    alert.severity === "blocking" ? "destructive" : "secondary"
                  }
                >
                  {alert.severity === "blocking" ? "阻塞" : "警告"}
                </Badge>
                <Badge variant="outline">
                  {ALERT_CATEGORY_LABELS[alert.category]}
                </Badge>
                {alert.provider && (
                  <span className="text-muted-foreground text-xs">
                    {alert.provider}
                  </span>
                )}
              </div>
              <p className="text-sm font-medium">{alert.title}</p>
              <p className="text-muted-foreground text-xs leading-5">
                {alert.action}
              </p>
            </div>
            <Button size="sm" variant="outline" asChild>
              <Link
                href={
                  alert.thread_id
                    ? pathOfThread(alert.thread_id)
                    : "/workspace/chats/new"
                }
              >
                处理
                <ArrowUpRightIcon />
              </Link>
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function PersonalIPDashboardPage() {
  const accountsQuery = usePersonalIPAccounts();
  const cockpitQuery = usePersonalIPOperatingCockpit();
  const metricsQuery = usePersonalIPMetrics();
  const dashboard = useMemo(
    () =>
      buildPersonalIPDashboardView(
        metricsQuery.data ?? [],
        accountsQuery.data ?? [],
        cockpitQuery.data,
      ),
    [accountsQuery.data, cockpitQuery.data, metricsQuery.data],
  );
  const cockpit = cockpitQuery.data;
  const pendingCount = countCockpitPending(cockpit);
  const operationalAlertCount = countOperationalAlerts(cockpit);
  const isLoading =
    accountsQuery.isLoading || cockpitQuery.isLoading || metricsQuery.isLoading;
  const hasError =
    accountsQuery.isError || cockpitQuery.isError || metricsQuery.isError;

  useEffect(() => {
    document.title = "工作台 - IP Agent";
  }, []);

  const refresh = () => {
    void Promise.all([
      accountsQuery.refetch(),
      cockpitQuery.refetch(),
      metricsQuery.refetch(),
    ]);
  };

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-y-auto">
        <div className="mx-auto w-full max-w-7xl space-y-8 p-6 lg:p-10">
          <section className="flex flex-wrap items-start justify-between gap-5">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">经营工作台</Badge>
                <Badge variant="outline">近 7 天实际观测</Badge>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">
                今天的增长，哪里值得继续追
              </h1>
              <p className="text-muted-foreground max-w-3xl text-sm leading-6">
                汇总全部已授权账号的新增浏览、粉丝、互动和作品表现。缺失平台保持“未采集”，不会被伪装成零。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={refresh} disabled={isLoading}>
                {isLoading ? (
                  <LoaderCircleIcon className="animate-spin" />
                ) : (
                  <RefreshCcwIcon />
                )}
                刷新数据
              </Button>
              <Button asChild>
                <Link href="/workspace/chats/new">
                  <BotIcon />
                  让智能体分析
                </Link>
              </Button>
            </div>
          </section>

          <section className="bg-muted/20 rounded-2xl border p-4 sm:p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
              <div className="flex items-center gap-2">
                <GaugeIcon className="text-primary size-4" />
                <span className="font-medium">数据覆盖</span>
                <span className="text-muted-foreground">
                  {dashboard.coverage.observedAccountCount}/
                  {dashboard.coverage.activeAccountCount} 个账号有观测
                </span>
              </div>
              <span className="text-muted-foreground text-xs">
                最近更新：
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
                aria-label="账号数据覆盖率"
              />
            )}
          </section>

          {hasError && (
            <Card className="border-destructive/40 bg-destructive/5 py-4">
              <CardContent className="text-destructive text-sm">
                部分经营数据暂时无法读取；页面只展示已经取得的真实观测。
              </CardContent>
            </Card>
          )}

          {cockpit && operationalAlertCount > 0 && (
            <OperationalAlerts alerts={cockpit.alerts.items} />
          )}

          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="新增浏览量"
              value={
                dashboard.availability.views ? dashboard.totals.views : null
              }
              description="近七天可比增量，不包含累计快照。"
              icon={EyeIcon}
              accent="bg-sky-500"
            />
            <MetricCard
              label="新增粉丝"
              value={
                dashboard.availability.followers
                  ? dashboard.totals.followers
                  : null
              }
              description="来自各平台明确标记的粉丝增量。"
              icon={UserPlusIcon}
              accent="bg-emerald-500"
            />
            <MetricCard
              label="新增互动"
              value={
                dashboard.availability.engagement
                  ? dashboard.totals.engagement
                  : null
              }
              description="点赞、评论、收藏和分享的合计。"
              icon={MessageSquareTextIcon}
              accent="bg-amber-500"
            />
            <MetricCard
              label="投流评估候选"
              value={
                dashboard.availability.paidTrafficBaseline
                  ? dashboard.totals.highPotentialPosts
                  : null
              }
              description="至少三条同平台样本后才给出候选。"
              icon={RocketIcon}
              accent="bg-violet-500"
            />
          </section>

          <section className="grid min-w-0 gap-4 xl:grid-cols-[1.55fr_1fr]">
            <GrowthTrend trend={dashboard.trend} />
            <PlatformGrowth platforms={dashboard.platforms} />
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <SparklesIcon className="size-4" />
                  近期作品表现
                </CardTitle>
                <CardDescription>
                  按作品级真实观测排序；投流只是评估入口，不会自动花钱。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {dashboard.posts.length === 0 ? (
                  <div className="text-muted-foreground rounded-xl border border-dashed p-8 text-center text-sm">
                    发布作品并回收实绩后，这里会出现高潜作品和相对基线。
                  </div>
                ) : (
                  dashboard.posts.map((post) => (
                    <div
                      key={post.id}
                      className="flex flex-wrap items-center justify-between gap-4 rounded-xl border p-4"
                    >
                      <div className="min-w-0 space-y-1.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="max-w-lg truncate text-sm font-medium">
                            {post.title}
                          </p>
                          <Badge variant="outline">{post.platformLabel}</Badge>
                          {post.opportunity === "boost_candidate" ? (
                            <Badge variant="secondary">建议评估投流</Badge>
                          ) : post.opportunity === "insufficient_baseline" ? (
                            <Badge variant="outline">样本不足</Badge>
                          ) : (
                            <Badge variant="outline">持续观察</Badge>
                          )}
                        </div>
                        <p className="text-muted-foreground text-xs">
                          {post.accountName} ·{" "}
                          {formatObservedAt(post.observedAt)}
                        </p>
                      </div>
                      <div className="flex items-center gap-5 text-right">
                        <div>
                          <p className="font-mono text-sm font-semibold tabular-nums">
                            {formatMetric(post.views)}
                          </p>
                          <p className="text-muted-foreground text-[10px]">
                            浏览
                          </p>
                        </div>
                        <div>
                          <p className="font-mono text-sm font-semibold tabular-nums">
                            {post.engagementRate === null
                              ? "—"
                              : PERCENT.format(post.engagementRate)}
                          </p>
                          <p className="text-muted-foreground text-[10px]">
                            互动率
                          </p>
                        </div>
                        {post.opportunity === "boost_candidate" && (
                          <Button size="sm" variant="outline" asChild>
                            <Link href="/workspace/chats/new">
                              评估
                              <ArrowUpRightIcon />
                            </Link>
                          </Button>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            <div className="grid gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>智能体待办</CardTitle>
                  <CardDescription>
                    当前经营闭环中需要继续推进的事项。
                  </CardDescription>
                  <CardAction>
                    <Badge variant={pendingCount > 0 ? "secondary" : "outline"}>
                      {pendingCount} 项
                    </Badge>
                  </CardAction>
                </CardHeader>
                <CardContent className="space-y-3">
                  {PERSONAL_IP_OPERATING_STAGES.map((definition) => {
                    const stage = cockpit?.stages[definition.id];
                    return (
                      <div
                        key={definition.id}
                        className="flex items-center justify-between gap-4 text-sm"
                      >
                        <span className="text-muted-foreground">
                          {definition.label}
                        </span>
                        <span className="font-mono text-xs tabular-nums">
                          {stage?.pending ?? 0} 待处理
                        </span>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>

              <Card className="bg-muted/25">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ClapperboardIcon className="size-4" />
                    视频生产
                  </CardTitle>
                  <CardDescription>
                    {cockpit?.video.active_count ?? 0} 个进行中 ·{" "}
                    {cockpit?.video.completed_count ?? 0} 个已交付
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button variant="outline" className="w-full" asChild>
                    <Link href="/workspace/chats/new">
                      新建视频任务
                      <ArrowUpRightIcon />
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            </div>
          </section>

          {cockpit && <OperatingReviewPanel cockpit={cockpit} />}
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
