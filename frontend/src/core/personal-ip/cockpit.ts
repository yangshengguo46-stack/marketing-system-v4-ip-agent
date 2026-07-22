"use client";

import { useQuery } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export const PERSONAL_IP_COCKPIT_QUERY_KEY = [
  "personal-ip",
  "operating-cockpit",
] as const;

export const PERSONAL_IP_OPERATING_STAGES = [
  { id: "modeling", label: "人格 / 粉丝建模" },
  { id: "preflight", label: "发布前预演" },
  { id: "publishing", label: "发布回执" },
  { id: "performance", label: "实绩回收" },
  { id: "retrospective", label: "复盘校准" },
  { id: "evidence", label: "证据晋级" },
] as const;

export const PERSONAL_IP_VIDEO_STAGES = [
  { id: "intake", label: "剧本理解" },
  { id: "blueprint", label: "影视蓝图" },
  { id: "assets", label: "资产建档" },
  { id: "storyboard", label: "分镜" },
  { id: "generation", label: "逐镜生成" },
  { id: "consistency", label: "一致性检查" },
  { id: "selection", label: "选片 / 审批" },
  { id: "finishing", label: "配音剪辑" },
  { id: "delivery", label: "交付" },
] as const;

export type PersonalIPOperatingStageId =
  (typeof PERSONAL_IP_OPERATING_STAGES)[number]["id"];

export type PersonalIPOperatingStage = {
  state: "empty" | "needs_attention" | "ready";
  total: number;
  pending: number;
  [key: string]: number | string;
};

export type PersonalIPOperatingCockpit = {
  contract_version: "personal-ip-operating-cockpit-v1";
  generated_at: string;
  portfolio: {
    subject_count: number;
    account_count: number;
    platform_count: number;
    platforms: string[];
  };
  stages: Record<PersonalIPOperatingStageId, PersonalIPOperatingStage>;
  queues: {
    accounts_needing_model_input: string[];
    preflights_awaiting_publish: string[];
    published_receipts_awaiting_metrics: string[];
    published_receipts_awaiting_retrospective: string[];
    evidence_awaiting_decision: string[];
  };
  recent: Record<string, Array<Record<string, unknown>>>;
  video: {
    contract_version: "personal-ip-video-production-v1";
    production_count: number;
    active_count: number;
    completed_count: number;
    blocked_production_ids: string[];
    awaiting_review_production_ids: string[];
    stages: Record<(typeof PERSONAL_IP_VIDEO_STAGES)[number]["id"], number>;
    recent: Array<Record<string, unknown>>;
  };
  coverage: {
    history_limit: number;
    possibly_truncated: string[];
  };
};

export function countCockpitPending(
  cockpit: PersonalIPOperatingCockpit | undefined,
) {
  if (!cockpit) return 0;
  return Object.values(cockpit.queues).reduce(
    (total, queue) => total + queue.length,
    0,
  );
}

async function requestCockpit(): Promise<PersonalIPOperatingCockpit> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/personal-ip/cockpit`,
  );
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as PersonalIPOperatingCockpit;
}

export function usePersonalIPOperatingCockpit() {
  return useQuery({
    queryKey: PERSONAL_IP_COCKPIT_QUERY_KEY,
    queryFn: requestCockpit,
  });
}
