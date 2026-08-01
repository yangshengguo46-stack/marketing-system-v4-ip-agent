"use client";

import { useQuery } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import { type PersonalIPAccount } from "./accounts";
import { PERSONAL_IP_BROWSER_PLATFORMS } from "./platforms";

export const PERSONAL_IP_METRICS_QUERY_KEY = [
  "personal-ip",
  "metrics",
] as const;
export const PERSONAL_IP_PLATFORM_OBSERVATIONS_QUERY_KEY = [
  "personal-ip",
  "platform-observations",
] as const;
export const PERSONAL_IP_PUBLISH_RECEIPTS_QUERY_KEY = [
  "personal-ip",
  "publish-receipts",
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

export type PersonalIPPlatformObservation = {
  id: string;
  account_id: string;
  subject_id: string | null;
  platform: string;
  dataset: string;
  source: string;
  status: "observed" | "partial" | "unavailable";
  observed_at: string;
  summary: Record<string, unknown>;
  coverage: Record<string, unknown>;
};

export type PersonalIPPublishReceipt = {
  id: string;
  account_id: string;
  subject_id: string | null;
  platform: string;
  executor: string;
  status:
    | "planned"
    | "pending"
    | "published"
    | "failed"
    | "unknown"
    | "deleted";
  external_url: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PersonalIPDashboardView = {
  period: { startedAt: string; endedAt: string; days: number };
  totals: {
    views: number | null;
    followers: number | null;
    engagement: number | null;
  };
  trend: Array<{
    date: string;
    label: string;
    views: number | null;
    followers: number | null;
    engagement: number | null;
  }>;
  platforms: Array<{
    id: string;
    label: string;
    views: number | null;
    followers: number | null;
    engagement: number | null;
    observedAccountCount: number;
    latestObservedAt: string;
  }>;
  posts: Array<{
    id: string;
    title: string;
    platform: string;
    platformLabel: string;
    accountName: string;
    observedAt: string;
    views: number | null;
    engagement: number | null;
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

function numericMetric(
  observation: PersonalIPMetricObservation,
  metric: string,
) {
  const value = observation.metrics?.[metric];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function engagementMetric(observation: PersonalIPMetricObservation) {
  const values = ENGAGEMENT_METRICS.map((metric) =>
    numericMetric(observation, metric),
  );
  const measured = values.filter((value): value is number => value !== null);
  return measured.length
    ? measured.reduce((sum, value) => sum + value, 0)
    : null;
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
  return new Date(value.getTime() + days * 86_400_000);
}

function dateKey(value: Date) {
  return value.toISOString().slice(0, 10);
}

function rankAfter(
  candidate: PersonalIPMetricObservation,
  current: PersonalIPMetricObservation,
) {
  return (
    dateValue(candidate.window_ended_at ?? candidate.observed_at) >
      dateValue(current.window_ended_at ?? current.observed_at) ||
    (dateValue(candidate.window_ended_at ?? candidate.observed_at) ===
      dateValue(current.window_ended_at ?? current.observed_at) &&
      candidate.id > current.id)
  );
}

function deduplicateGrowth(observations: PersonalIPMetricObservation[]) {
  const latest = new Map<string, PersonalIPMetricObservation>();
  for (const observation of observations) {
    if (!["window_total", "delta"].includes(observation.metric_mode)) continue;
    if (observation.status === "unavailable") continue;
    if (!observation.window_started_at || !observation.window_ended_at)
      continue;
    const key = [
      observation.account_id,
      observation.scope,
      observation.series_key,
      observation.metric_mode,
      observation.window_started_at,
      observation.metric_mode === "delta" ? observation.window_ended_at : "",
    ].join("|");
    const current = latest.get(key);
    if (!current || rankAfter(observation, current))
      latest.set(key, observation);
  }
  return [...latest.values()];
}

function latestPosts(observations: PersonalIPMetricObservation[]) {
  const latest = new Map<string, PersonalIPMetricObservation>();
  for (const observation of observations) {
    if (observation.scope !== "post" || observation.status === "unavailable")
      continue;
    const key =
      observation.receipt_id ??
      `${observation.account_id}:${observation.series_key}`;
    const current = latest.get(key);
    if (!current || rankAfter(observation, current))
      latest.set(key, observation);
  }
  return [...latest.values()];
}

function coverageTitle(observation: PersonalIPMetricObservation) {
  for (const key of ["content_title", "title", "caption"]) {
    const value = observation.coverage?.[key];
    if (typeof value === "string" && value.trim())
      return value.trim().slice(0, 120);
  }
  return null;
}

function addMeasured(current: number | null, value: number | null) {
  if (value === null) return current;
  return (current ?? 0) + value;
}

export function buildPersonalIPDashboardView(
  observations: PersonalIPMetricObservation[],
  accounts: PersonalIPAccount[],
  now = new Date(),
): PersonalIPDashboardView {
  const periodEnd = now;
  const periodStart = addUTCDays(startOfUTCDay(now), -6);
  const growth = deduplicateGrowth(observations).filter(
    (observation) =>
      dateValue(observation.window_started_at) >= periodStart.getTime() &&
      dateValue(observation.window_ended_at) <= periodEnd.getTime(),
  );
  const posts = latestPosts(observations)
    .filter(
      (observation) =>
        dateValue(observation.observed_at) >= periodStart.getTime() &&
        dateValue(observation.observed_at) <= periodEnd.getTime(),
    )
    .sort(
      (left, right) =>
        dateValue(right.observed_at) - dateValue(left.observed_at),
    );

  const accountsById = new Map(
    accounts.map((account) => [account.id, account]),
  );
  const trend: PersonalIPDashboardView["trend"] = Array.from(
    { length: 7 },
    (_, offset) => {
      const day = addUTCDays(periodStart, offset);
      return {
        date: dateKey(day),
        label: `${String(day.getUTCMonth() + 1).padStart(2, "0")}/${String(
          day.getUTCDate(),
        ).padStart(2, "0")}`,
        views: null,
        followers: null,
        engagement: null,
      };
    },
  );
  const trendByDate = new Map(trend.map((item) => [item.date, item]));
  const platformMap = new Map<
    string,
    PersonalIPDashboardView["platforms"][number] & { accountIds: Set<string> }
  >();

  let totalViews: number | null = null;
  let totalFollowers: number | null = null;
  let totalEngagement: number | null = null;

  for (const observation of growth) {
    const views = numericMetric(observation, "views");
    const followers = numericMetric(observation, "followers_delta");
    const engagement = engagementMetric(observation);
    totalViews = addMeasured(totalViews, views);
    totalFollowers = addMeasured(totalFollowers, followers);
    totalEngagement = addMeasured(totalEngagement, engagement);

    const day = trendByDate.get(observation.window_started_at!.slice(0, 10));
    if (day) {
      day.views = addMeasured(day.views, views);
      day.followers = addMeasured(day.followers, followers);
      day.engagement = addMeasured(day.engagement, engagement);
    }

    if (views === null && followers === null && engagement === null) continue;
    const current = platformMap.get(observation.platform) ?? {
      id: observation.platform,
      label: PLATFORM_LABELS.get(observation.platform) ?? observation.platform,
      views: null,
      followers: null,
      engagement: null,
      observedAccountCount: 0,
      latestObservedAt: observation.observed_at,
      accountIds: new Set<string>(),
    };
    current.views = addMeasured(current.views, views);
    current.followers = addMeasured(current.followers, followers);
    current.engagement = addMeasured(current.engagement, engagement);
    current.accountIds.add(observation.account_id);
    if (
      dateValue(observation.observed_at) > dateValue(current.latestObservedAt)
    ) {
      current.latestObservedAt = observation.observed_at;
    }
    platformMap.set(observation.platform, current);
  }

  const platforms = [...platformMap.values()]
    .map(({ accountIds, ...item }) => ({
      ...item,
      observedAccountCount: accountIds.size,
    }))
    .sort(
      (left, right) =>
        dateValue(right.latestObservedAt) - dateValue(left.latestObservedAt),
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
      views: totalViews,
      followers: totalFollowers,
      engagement: totalEngagement,
    },
    trend,
    platforms,
    posts: posts.slice(0, 8).map((observation) => ({
      id:
        observation.receipt_id ??
        `${observation.account_id}:${observation.series_key}`,
      title:
        coverageTitle(observation) ??
        `${PLATFORM_LABELS.get(observation.platform) ?? observation.platform}作品`,
      platform: observation.platform,
      platformLabel:
        PLATFORM_LABELS.get(observation.platform) ?? observation.platform,
      accountName:
        accountsById.get(observation.account_id)?.display_name ?? "未命名账号",
      observedAt: observation.observed_at,
      views: numericMetric(observation, "views"),
      engagement: engagementMetric(observation),
    })),
    coverage: {
      activeAccountCount: accounts.filter(
        (account) => account.status === "active",
      ).length,
      observedAccountCount: observedAccountIds.size,
      observationCount: observations.length,
      latestObservedAt,
    },
  };
}

async function requestJSON<T>(path: string): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${path}`);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function usePersonalIPMetrics(limit = 500) {
  return useQuery({
    queryKey: [...PERSONAL_IP_METRICS_QUERY_KEY, limit],
    queryFn: () =>
      requestJSON<PersonalIPMetricObservation[]>(
        `/api/personal-ip/metrics?limit=${limit}`,
      ),
  });
}

export function usePersonalIPPlatformObservations(limit = 100) {
  return useQuery({
    queryKey: [...PERSONAL_IP_PLATFORM_OBSERVATIONS_QUERY_KEY, limit],
    queryFn: () =>
      requestJSON<PersonalIPPlatformObservation[]>(
        `/api/personal-ip/platform-observations?limit=${limit}`,
      ),
  });
}

export function usePersonalIPPublishReceipts(limit = 100) {
  return useQuery({
    queryKey: [...PERSONAL_IP_PUBLISH_RECEIPTS_QUERY_KEY, limit],
    queryFn: () =>
      requestJSON<PersonalIPPublishReceipt[]>(
        `/api/personal-ip/publish-receipts?limit=${limit}`,
      ),
  });
}
