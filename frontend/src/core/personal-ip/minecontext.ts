"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type MineContextScope =
  | "screen"
  | "files"
  | "people"
  | "projects"
  | "work_activity";
export type MineContextPurpose =
  | "persona_modeling"
  | "audience_modeling";

export type MineContextStatus = {
  operator_enabled: boolean;
  available: boolean;
  source_verified: boolean;
  source_error?: string | null;
  runtime_ready: boolean;
  authorized: boolean;
  running: boolean;
  scopes?: MineContextScope[];
  purposes?: MineContextPurpose[];
  collection_mode?: "manual" | "bounded_continuous" | null;
  retention_days?: number;
  watched_path_count?: number;
  screen_targets?: string[];
  evidence_count?: number;
  data_location?: "local_owner_isolated";
  raw_content_enters_deerflow?: false;
};

export type MineContextConsentInput = {
  scopes: MineContextScope[];
  purposes: MineContextPurpose[];
  retention_days: number;
  collection_mode: "manual" | "bounded_continuous";
  watched_paths: string[];
  recursive_file_watch: boolean;
  screen_targets: string[];
  screen_capture_interval_seconds: number;
  continuous_screen_capture_confirmed: boolean;
};

export const MINECONTEXT_QUERY_KEY = ["personal-ip", "minecontext"] as const;

async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getBackendBaseURL()}${path}`, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(payload?.detail ?? `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export function describeMineContextStatus(
  status: Pick<
    MineContextStatus,
    | "operator_enabled"
    | "available"
    | "source_verified"
    | "runtime_ready"
    | "authorized"
    | "running"
  >,
): { label: string; action: string } {
  if (!status.operator_enabled) {
    return { label: "系统未启用", action: "请管理员先启用并安装本地观察源" };
  }
  if (!status.source_verified) {
    return {
      label: "源码校验失败",
      action: "恢复已固定版本的完整源码后再使用",
    };
  }
  if (!status.runtime_ready || !status.available) {
    return { label: "等待安装", action: "请管理员从随包源码安装本地运行环境" };
  }
  if (!status.authorized) {
    return { label: "尚未开启", action: "开启后即可自动使用" };
  }
  if (!status.running) {
    return { label: "已关闭", action: "需要时可以重新开启" };
  }
  return { label: "使用中", action: "智能体正在使用本机工作上下文" };
}

export function useMineContextStatus(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: MINECONTEXT_QUERY_KEY,
    queryFn: () =>
      requestJSON<MineContextStatus>("/api/personal-ip/minecontext"),
    enabled: options.enabled ?? true,
  });
}

function useMineContextMutation<T>(mutationFn: (value: T) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: MINECONTEXT_QUERY_KEY });
    },
  });
}

export function useAuthorizeMineContext() {
  return useMineContextMutation((body: MineContextConsentInput) =>
    requestJSON("/api/personal-ip/minecontext/authorize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}
export function useEnableMineContext() {
  return useMineContextMutation((body: { retention_days: number }) =>
    requestJSON("/api/personal-ip/minecontext/enable", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}
export function useStartMineContext() {
  return useMineContextMutation(() =>
    requestJSON("/api/personal-ip/minecontext/start", { method: "POST" }),
  );
}

export function useStopMineContext() {
  return useMineContextMutation(() =>
    requestJSON("/api/personal-ip/minecontext/stop", { method: "POST" }),
  );
}

export function useRevokeMineContext() {
  return useMineContextMutation(() =>
    requestJSON("/api/personal-ip/minecontext/revoke", { method: "POST" }),
  );
}

export function useDeleteMineContextData() {
  return useMineContextMutation((scope: "evidence" | "all") =>
    requestJSON(`/api/personal-ip/minecontext/data?scope=${scope}`, {
      method: "DELETE",
    }),
  );
}
