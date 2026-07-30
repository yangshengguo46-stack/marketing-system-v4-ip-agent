"use client";

import { useQuery } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import { type PersonalIPAccount } from "./accounts";
import { type PersonalIPOperatingCockpit } from "./cockpit";
import { PERSONAL_IP_BROWSER_PLATFORMS } from "./platforms";

export const PERSONAL_IP_METRICS_QUERY_KEY = [
  "personal-ip",
  "metrics",
] as const;

export type PersonalIPMetricObservation = {
  id: string;
  account_id: string;
  receipt_id: string | null;
  platform: string;
  scope: "account" | "post";
  series_key: string;
  metric_mode: "window_total" | "delta" | "snapshot";
  source: "platform_api" | "ui_tars" | "browser" | "manual";
  status: "observed" | "partial" | "unavailable";
  window_started_at: string | null;
  window_ended_at: string | null;
  observed_at: string;
  metrics: Record<string, number>;
  coverage: Record<string, unknown>;
};

export type PersonalIPDashboardView = {
  period: {
    startedAt: string;
    endedAt: string;
    days: number;
  };
  totals: {
    views: number;
    followers: number;
    engagement: number;
    highPotentialPosts: number;
  };
  availability: {
    views: boolean;
    followers: boolean;
    engagement: boolean;
    paidTrafficBaseline: boolean;
  };
  trend: Array<{
    date: string;
    label: string;
    views: number;
    followers: number;
    engagement: number;
  }>;
  platforms: Array<{
    id: string;
    label: string;
    views: number;
    followers: number;
    engagement: number;
    accountCount: number;
  }>;
  posts: Array<{
    id: string;
    title: string;
    platform: string;
    platformLabel: string;
    accountName: string;
    observedAt: string;
    views: number;
    engagement: number;
    engagementRate: number | null;
    opportunity: "boost_candidate" | "watch" | "insufficient_baseline";
  }>;
  coverage: {
    activeAccountCount: number;
    observedAccountCount: number;
    observationCount: number;
    latestObservedAt: string | null;
  };
};

const PLATFORM_LABELS = new Map(
  PERSONAL_IP_BROWSER_PLATFORMS.map((platform) => [
    platform.id,
    platform.label,
  ]),
);
const ENGAGEMENT_METRICS = ["likes", "comments", "saves", "shares"] as const;

function hasMetric(observation: PersonalIPMetricObservation, metric: string) {
  const value = observation.metrics?.[metric];
  return typeof value === "number" && Number.isFinite(value);
}

function metricValue(observation: PersonalIPMetricObservation, metric: string) {
  const value = observation.metrics?.[metric];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function engagementValue(observation: PersonalIPMetricObservation) {
  return ENGAGEMENT_METRICS.reduce(
    (total, metric) => total + metricValue(observation, metric),
    0,
  );
}

function dateValue(value: string | null | undefined) {
  const timestamp = Date.parse(value ?? "");
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function startOfUTCDay(value: Date) {
  return new Date(
    Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate()),
  );
}

function addUTCDays(value: Date, days: number) {
  return new Date(value.getTime() + days * 24 * 60 * 60 * 1000);
}

function dateKey(value: Date) {
  return value.toISOString().slice(0, 10);
}

function observationRank(observation: PersonalIPMetricObservation) {
  return [
    dateValue(observation.window_ended_at),
    dateValue(observation.observed_at),
    observation.id,
  ] as const;
}

function rankAfter(
  candidate: PersonalIPMetricObservation,
  current: PersonalIPMetricObservation,
) {
  const left = observationRank(candidate);
  const right = observationRank(current);
  if (left[0] !== right[0]) return left[0] > right[0];
  if (left[1] !== right[1]) return left[1] > right[1];
  return left[2] > right[2];
}

function deduplicateGrowthObservations(
  observations: PersonalIPMetricObservation[],
) {
  const latest = new Map<string, PersonalIPMetricObservation>();
  for (const observation of observations) {
    if (!["window_total", "delta"].includes(observation.metric_mode)) continue;
    if (observation.status === "unavailable") continue;
    if (!observation.window_started_at || !observation.window_ended_at)
      continue;
    const base = [
      observation.account_id,
      observation.scope,
      observation.series_key,
      observation.metric_mode,
      observation.window_started_at,
    ];
    if (observation.metric_mode === "delta") {
      base.push(observation.window_ended_at);
    }
    const key = base.join("|");
    const current = latest.get(key);
    if (!current || rankAfter(observation, current)) {
      latest.set(key, observation);
    }
  }
  return [...latest.values()];
}

function latestPostObservations(observations: PersonalIPMetricObservation[]) {
  const latest = new Map<string, PersonalIPMetricObservation>();
  for (const observation of observations) {
    if (observation.scope !== "post" || observation.status === "unavailable") {
      continue;
    }
    const key =
      observation.receipt_id ??
      `${observation.account_id}:${observation.series_key}`;
    const current = latest.get(key);
    if (!current || rankAfter(observation, current)) {
      latest.set(key, observation);
    }
  }
  return [...latest.values()];
}

function median(values: number[]) {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1]! + sorted[middle]!) / 2
    : sorted[middle]!;
}

function safeCoverageTitle(observation: PersonalIPMetricObservation) {
  for (const key of ["content_title", "title", "caption"]) {
    const value = observation.coverage?.[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim().slice(0, 120);
    }
  }
  return null;
}

export function buildPersonalIPDashboardView(
  observations: PersonalIPMetricObservation[],
  accounts: PersonalIPAccount[],
  cockpit: PersonalIPOperatingCockpit | undefined,
  now = new Date(),
): PersonalIPDashboardView {
  const periodEnd = now;
  const periodStart = addUTCDays(startOfUTCDay(now), -6);
  const growth = deduplicateGrowthObservations(observations).filter(
    (observation) =>
      dateValue(observation.window_started_at) >= periodStart.getTime() &&
      dateValue(observation.window_ended_at) <= periodEnd.getTime(),
  );
  const recentPosts = latestPostObservations(observations).filter(
    (observation) =>
      dateValue(observation.observed_at) >= periodStart.getTime() &&
      dateValue(observation.observed_at) <= periodEnd.getTime(),
  );
  const accountsById = new Map(
    accounts.map((account) => [account.id, account]),
  );

  const trendMap = new Map<
    string,
    {
      date: string;
      label: string;
      views: number;
      followers: number;
      engagement: number;
    }
  >();
  for (let offset = 0; offset < 7; offset += 1) {
    const day = addUTCDays(periodStart, offset);
    const key = dateKey(day);
    trendMap.set(key, {
      date: key,
      label: `${String(day.getUTCMonth() + 1).padStart(2, "0")}/${String(
        day.getUTCDate(),
      ).padStart(2, "0")}`,
      views: 0,
      followers: 0,
      engagement: 0,
    });
  }

  const platformMap = new Map<
    string,
    {
      id: string;
      label: string;
      views: number;
      followers: number;
      engagement: number;
      accountCount: number;
    }
  >();
  const accountCounts = new Map<string, Set<string>>();

  for (const observation of growth) {
    const key = (
      observation.window_started_at ?? observation.observed_at
    ).slice(0, 10);
    const trend = trendMap.get(key);
    const views = metricValue(observation, "views");
    const followers = metricValue(observation, "followers_delta");
    const engagement = engagementValue(observation);
    if (trend) {
      trend.views += views;
      trend.followers += followers;
      trend.engagement += engagement;
    }

    const hasRelevantMetric =
      hasMetric(observation, "views") ||
      hasMetric(observation, "followers_delta") ||
      ENGAGEMENT_METRICS.some((metric) => hasMetric(observation, metric));
    if (!hasRelevantMetric) continue;

    const platform = observation.platform;
    const platformSummary = platformMap.get(platform) ?? {
      id: platform,
      label: PLATFORM_LABELS.get(platform) ?? platform,
      views: 0,
      followers: 0,
      engagement: 0,
      accountCount: 0,
    };
    platformSummary.views += views;
    platformSummary.followers += followers;
    platformSummary.engagement += engagement;
    platformMap.set(platform, platformSummary);
    const ids = accountCounts.get(platform) ?? new Set<string>();
    ids.add(observation.account_id);
    accountCounts.set(platform, ids);
  }
  for (const summary of platformMap.values()) {
    summary.accountCount = accountCounts.get(summary.id)?.size ?? 0;
  }

  const platformBaselines = new Map<
    string,
    Array<{ views: number; engagementRate: number }>
  >();
  for (const observation of recentPosts) {
    const views = metricValue(observation, "views");
    const engagementRate = views > 0 ? engagementValue(observation) / views : 0;
    const baseline = platformBaselines.get(observation.platform) ?? [];
    baseline.push({ views, engagementRate });
    platformBaselines.set(observation.platform, baseline);
  }

  const posts = recentPosts
    .map((observation) => {
      const views = metricValue(observation, "views");
      const engagement = engagementValue(observation);
      const engagementRate = views > 0 ? engagement / views : null;
      const baseline = platformBaselines.get(observation.platform) ?? [];
      const viewsMedian = median(baseline.map((item) => item.views));
      const engagementMedian = median(
        baseline.map((item) => item.engagementRate),
      );
      const opportunity =
        baseline.length < 3
          ? "insufficient_baseline"
          : views >= Math.max(1, viewsMedian * 1.5) &&
              (engagementRate ?? 0) >= engagementMedian
            ? "boost_candidate"
            : "watch";
      const account = accountsById.get(observation.account_id);
      return {
        id:
          observation.receipt_id ??
          `${observation.account_id}:${observation.series_key}`,
        title:
          safeCoverageTitle(observation) ??
          `${PLATFORM_LABELS.get(observation.platform) ?? observation.platform}近期作品`,
        platform: observation.platform,
        platformLabel:
          PLATFORM_LABELS.get(observation.platform) ?? observation.platform,
        accountName: account?.display_name ?? "未命名账号",
        observedAt: observation.observed_at,
        views,
        engagement,
        engagementRate,
        opportunity,
      } satisfies PersonalIPDashboardView["posts"][number];
    })
    .sort(
      (left, right) =>
        right.views - left.views || right.engagement - left.engagement,
    )
    .slice(0, 5);

  const availability = {
    views: growth.some((observation) => hasMetric(observation, "views")),
    followers: growth.some((observation) =>
      hasMetric(observation, "followers_delta"),
    ),
    engagement: growth.some((observation) =>
      ENGAGEMENT_METRICS.some((metric) => hasMetric(observation, metric)),
    ),
    paidTrafficBaseline: [...platformBaselines.values()].some(
      (baseline) => baseline.length >= 3,
    ),
  };
  const totals = growth.reduce(
    (result, observation) => {
      result.views += metricValue(observation, "views");
      result.followers += metricValue(observation, "followers_delta");
      result.engagement += engagementValue(observation);
      return result;
    },
    { views: 0, followers: 0, engagement: 0 },
  );
  const observedAccountIds = new Set(
    observations
      .filter((observation) => observation.status !== "unavailable")
      .map((observation) => observation.account_id),
  );
  const latestObservedAt =
    observations
      .map((observation) => observation.observed_at)
      .filter(Boolean)
      .sort()
      .at(-1) ?? null;

  return {
    period: {
      startedAt: periodStart.toISOString(),
      endedAt: periodEnd.toISOString(),
      days: 7,
    },
    totals: {
      ...totals,
      highPotentialPosts: posts.filter(
        (post) => post.opportunity === "boost_candidate",
      ).length,
    },
    availability,
    trend: [...trendMap.values()],
    platforms: [...platformMap.values()].sort(
      (left, right) =>
        right.views - left.views || right.followers - left.followers,
    ),
    posts,
    coverage: {
      activeAccountCount: cockpit?.portfolio.account_count ?? accounts.length,
      observedAccountCount: observedAccountIds.size,
      observationCount: observations.length,
      latestObservedAt,
    },
  };
}

async function requestMetrics(
  limit: number,
): Promise<PersonalIPMetricObservation[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/personal-ip/metrics?limit=${limit}`,
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as PersonalIPMetricObservation[];
}

export function usePersonalIPMetrics(limit = 500) {
  return useQuery({
    queryKey: [...PERSONAL_IP_METRICS_QUERY_KEY, limit],
    queryFn: () => requestMetrics(limit),
  });
}
