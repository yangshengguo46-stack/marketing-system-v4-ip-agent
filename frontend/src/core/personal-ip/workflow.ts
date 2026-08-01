"use client";

import { useQuery } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type PersonalIPWorkflowResource =
  | "publish-receipts"
  | "metrics"
  | "platform-observations";

async function readError(response: Response): Promise<string> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string;
  } | null;
  return payload?.detail ?? `Request failed (${response.status})`;
}

export function personalIPWorkflowResourcePath(
  resource: PersonalIPWorkflowResource,
  id: string,
) {
  return `/api/personal-ip/${resource}/${encodeURIComponent(id)}`;
}

async function requestWorkflowDetail(
  resource: PersonalIPWorkflowResource,
  id: string,
): Promise<Record<string, unknown>> {
  const response = await fetch(
    `${getBackendBaseURL()}${personalIPWorkflowResourcePath(resource, id)}`,
  );
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as Record<string, unknown>;
}

export function usePersonalIPWorkflowDetail(
  resource: PersonalIPWorkflowResource,
  id: string | null,
) {
  return useQuery({
    queryKey: ["personal-ip", "workflow-detail", resource, id],
    queryFn: () => requestWorkflowDetail(resource, id ?? ""),
    enabled: Boolean(id),
  });
}
