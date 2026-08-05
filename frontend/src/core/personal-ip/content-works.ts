"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type ContentEntryRoute = "zero_start" | "benchmark";
export type ContentTruthMode = "factual" | "fictional" | "hybrid";

const CONTENT_ENTRY_PROMPTS: Record<ContentEntryRoute, string> = {
  zero_start:
    "我要从零起盘一条原创内容。请先和我确认希望促成的变化、受众处境、业务背景和约束；事实、推断与创作假设要分开，方向确认后再保存完整剧本版本。",
  benchmark:
    "我要从一个明确的对标作品开始做原创内容。请先让我提供精确作品链接或上传文件，完成来源绑定的拆解；将可观测事实、解读和创作假设分开，再由我确认方向并保存完整剧本版本。",
};

export function personalIPContentTaskHref(
  entryRoute: ContentEntryRoute,
): string {
  return `/workspace/chats/new?${new URLSearchParams({
    content_entry: entryRoute,
  })}`;
}

export function personalIPContentEntryPrompt(
  entryRoute: string | null | undefined,
): string | undefined {
  if (entryRoute !== "zero_start" && entryRoute !== "benchmark") {
    return undefined;
  }
  return CONTENT_ENTRY_PROMPTS[entryRoute];
}

export function personalIPProductionTaskHref(
  contentWorkId: string,
  scriptVersionId: string,
): string {
  return `/workspace/chats/new?${new URLSearchParams({
    production_content_work_id: contentWorkId,
    production_script_version_id: scriptVersionId,
  })}`;
}

export function personalIPProductionEntryPrompt(
  contentWorkId: string | null | undefined,
  scriptVersionId: string | null | undefined,
): string | undefined {
  const workId = contentWorkId?.trim();
  const versionId = scriptVersionId?.trim();
  if (!workId || !versionId || workId.length > 64 || versionId.length > 64) {
    return undefined;
  }
  return `请从服务端已保存的内容作品 ${workId} 中，以正式剧本版本 ${versionId} 启动一次制作。请先读取并校验这两个服务端标识的 Owner 归属与版本关系；不要从聊天文本重建剧本，也不要使用未绑定的制作任务。`;
}

export type ContentObjective = {
  desired_change: string;
  audience_situation: string;
  business_context: string;
  constraints: string[];
};

export type PersonalIPContentWork = {
  id: string;
  objective_id: string;
  thread_id: string | null;
  subject_id?: string | null;
  title: string;
  entry_route: ContentEntryRoute;
  objective: ContentObjective;
  status: "active" | "archived";
  created_by_run_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type BreakdownObservation = {
  observation: string;
  evidence_refs: string[];
};

export type BreakdownInterpretation = {
  interpretation: string;
  state: "derived" | "hypothesized";
  based_on_observations: number[];
};

export type PersonalIPBreakdownVersion = {
  id: string;
  content_work_id: string;
  version_number: number;
  source_kind: "platform_content" | "uploaded_file" | "owner_material";
  source_identity: Record<string, unknown>;
  source_digest?: string | null;
  observations: BreakdownObservation[];
  interpretations: BreakdownInterpretation[];
  limitations: string[];
  created_at: string;
};

export type ClaimBasis = {
  claim: string;
  state: string;
  usage: string;
  evidence_refs: string[];
};

export type DirectionSnapshot = {
  premise: string;
  audience_situation: string;
  core_tension: string;
  content_promise: string;
  creative_route: string;
  rationale: string;
  truth_mode: ContentTruthMode;
  business_relevance?: string;
  claim_basis: ClaimBasis[];
};

export type PersonalIPDirectionVersion = {
  id: string;
  content_work_id: string;
  version_number: number;
  parent_direction_version_id?: string | null;
  breakdown_version_ids: string[];
  objective_snapshot: ContentObjective;
  direction: DirectionSnapshot;
  created_at: string;
};

export type PersonalIPScriptVersion = {
  id: string;
  content_work_id: string;
  direction_version_id: string;
  version_number: number;
  parent_script_version_id?: string | null;
  title: string;
  story_mode: ContentTruthMode;
  script_text: string;
  claim_basis: ClaimBasis[];
  creative_elements: Array<{
    element: string;
    kind: "fictional" | "composite" | "dramatic_device";
    disclosure: string;
  }>;
  locked_story?: string | null;
  locked_story_digest?: string | null;
  production_notes: Record<string, unknown>;
  created_at: string;
};

export type PersonalIPContentLineage = {
  content_work: PersonalIPContentWork;
  breakdown_versions: PersonalIPBreakdownVersion[];
  direction_versions: PersonalIPDirectionVersion[];
  script_versions: PersonalIPScriptVersion[];
};

export const PERSONAL_IP_CONTENT_WORKS_QUERY_KEY = [
  "personal-ip",
  "content-works",
] as const;

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

export function usePersonalIPContentWorks(includeArchived = false) {
  return useQuery({
    queryKey: [...PERSONAL_IP_CONTENT_WORKS_QUERY_KEY, { includeArchived }],
    queryFn: () =>
      requestJSON<PersonalIPContentWork[]>(
        `/api/personal-ip/content-works?limit=200${
          includeArchived ? "&include_archived=true" : ""
        }`,
      ),
  });
}

export function usePersonalIPContentLineage(contentWorkId: string | null) {
  return useQuery({
    queryKey: [...PERSONAL_IP_CONTENT_WORKS_QUERY_KEY, contentWorkId],
    enabled: Boolean(contentWorkId),
    queryFn: () =>
      requestJSON<PersonalIPContentLineage>(
        `/api/personal-ip/content-works/${encodeURIComponent(contentWorkId ?? "")}`,
      ),
  });
}

export function useArchivePersonalIPContentWork() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contentWorkId: string) =>
      requestJSON<PersonalIPContentWork>(
        `/api/personal-ip/content-works/${encodeURIComponent(contentWorkId)}/archive`,
        { method: "POST" },
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: PERSONAL_IP_CONTENT_WORKS_QUERY_KEY,
      }),
  });
}
