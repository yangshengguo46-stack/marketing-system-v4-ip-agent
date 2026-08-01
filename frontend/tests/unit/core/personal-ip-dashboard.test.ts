import { describe, expect, it } from "@rstest/core";

import {
  buildPersonalIPDashboardView,
  type PersonalIPAccount,
  type PersonalIPMetricObservation,
} from "@/core/personal-ip";

const account = (id: string, platform: string): PersonalIPAccount =>
  ({
    id,
    platform,
    display_name: `${platform}账号`,
    status: "active",
    metadata: {},
  }) as PersonalIPAccount;

const metric = (
  overrides: Partial<PersonalIPMetricObservation>,
): PersonalIPMetricObservation => ({
  id: "metric-default",
  account_id: "acct-douyin",
  receipt_id: null,
  platform: "douyin",
  scope: "account",
  series_key: "daily-summary",
  metric_mode: "window_total",
  source: "browser",
  status: "observed",
  window_started_at: "2026-07-25T00:00:00Z",
  window_ended_at: "2026-07-26T00:00:00Z",
  observed_at: "2026-07-26T00:05:00Z",
  metrics: {},
  coverage: {},
  ...overrides,
});

describe("personal IP factual dashboard", () => {
  it("deduplicates replacement windows and excludes cumulative snapshots", () => {
    const view = buildPersonalIPDashboardView(
      [
        metric({
          id: "older",
          metrics: { views: 100, followers_delta: 2, likes: 5 },
        }),
        metric({
          id: "newer",
          window_ended_at: "2026-07-26T01:00:00Z",
          observed_at: "2026-07-26T01:05:00Z",
          metrics: { views: 140, followers_delta: 4, likes: 8 },
        }),
        metric({
          id: "xhs",
          account_id: "acct-xhs",
          platform: "xiaohongshu",
          series_key: "xhs-daily",
          metrics: { views: 60, followers_delta: 1, saves: 3 },
        }),
        metric({
          id: "snapshot-not-growth",
          metric_mode: "snapshot",
          metrics: { views: 99_999 },
        }),
      ],
      [account("acct-douyin", "douyin"), account("acct-xhs", "xiaohongshu")],
      new Date("2026-07-26T12:00:00Z"),
    );

    expect(view.totals).toEqual({
      views: 200,
      followers: 5,
      engagement: 11,
    });
    expect(view.platforms.map((item) => [item.id, item.views])).toEqual([
      ["douyin", 140],
      ["xiaohongshu", 60],
    ]);
    expect(view.trend.at(-2)?.views).toBe(200);
  });

  it("lists post facts by observation time without a recommendation field", () => {
    const post = (id: string, views: number, day: string) =>
      metric({
        id,
        receipt_id: `receipt-${id}`,
        scope: "post",
        series_key: `receipt:${id}`,
        metric_mode: "snapshot",
        window_started_at: null,
        window_ended_at: null,
        observed_at: `${day}T12:00:00Z`,
        metrics: { views, likes: 2 },
        coverage: { content_title: `作品 ${id}` },
      });
    const view = buildPersonalIPDashboardView(
      [post("older", 10_000, "2026-07-25"), post("newer", 10, "2026-07-26")],
      [account("acct-douyin", "douyin")],
      new Date("2026-07-26T20:00:00Z"),
    );

    expect(view.posts.map((item) => item.title)).toEqual([
      "作品 newer",
      "作品 older",
    ]);
    expect(view.posts[0]).not.toHaveProperty("opportunity");
  });

  it("keeps missing metrics distinct from an observed zero", () => {
    const missing = buildPersonalIPDashboardView(
      [metric({ metrics: {} })],
      [account("acct-douyin", "douyin")],
      new Date("2026-07-26T20:00:00Z"),
    );
    expect(missing.totals.views).toBeNull();

    const observedZero = buildPersonalIPDashboardView(
      [metric({ metrics: { views: 0 } })],
      [account("acct-douyin", "douyin")],
      new Date("2026-07-26T20:00:00Z"),
    );
    expect(observedZero.totals.views).toBe(0);
  });
});
