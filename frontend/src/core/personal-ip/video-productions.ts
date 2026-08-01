"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type VideoProductionStatus =
  | "draft"
  | "running"
  | "awaiting_review"
  | "blocked"
  | "completed"
  | "cancelled";

export type VideoProductionMode = "faceless_material" | "generative_cinematic";

export type PersonalIPMediaModel = {
  id: string;
  display_name: string;
  is_default: boolean;
};

export type PersonalIPMediaModelCatalog = {
  source: "live" | "fallback";
  default_image_model: string;
  default_video_model: string;
  image_models: PersonalIPMediaModel[];
  video_models: PersonalIPMediaModel[];
};

export type VideoProductionStage =
  | "intake"
  | "blueprint"
  | "assets"
  | "storyboard"
  | "generation"
  | "consistency"
  | "selection"
  | "finishing"
  | "delivery";

export type VideoArtifact = {
  ref: string;
  sha256?: string;
  size_bytes?: number;
  mime_type?: string;
  source_ref?: string;
  downloaded_at?: string;
};

export type VideoCost = {
  status?: "known" | "estimated" | "unknown";
  amount?: number;
  currency?: string;
  basis?: string;
  reason?: string;
};

export type VideoProductionEvent = {
  id: string;
  event_key?: string;
  sequence?: number;
  event_type?: string;
  stage?: VideoProductionStage;
  status?: string;
  entity_type?: string;
  entity_id?: string;
  payload?: Record<string, unknown>;
  input_refs?: string[];
  output_refs?: string[];
  provider?: string;
  model?: string | null;
  provider_task_id?: string | null;
  cost?: VideoCost;
  occurred_at?: string;
};

export type PersonalIPVideoProduction = {
  id: string;
  thread_id?: string | null;
  title: string;
  status: VideoProductionStatus;
  current_stage: VideoProductionStage;
  event_count: number;
  source_kind: "idea" | "script";
  production_mode?: VideoProductionMode | null;
  source: Record<string, unknown>;
  delivery_spec: Record<string, unknown>;
  provider_policy: Record<string, unknown>;
  budget: Record<string, unknown>;
  subject_id?: string | null;
  target_account_ids?: string[];
  created_at: string;
  updated_at: string;
};

export type VideoWorkbenchTask = {
  id: string;
  event_key?: string;
  sequence?: number;
  event_type?: string;
  stage?: VideoProductionStage;
  status?: string;
  entity_type?: string;
  entity_id?: string;
  shot_id?: string | null;
  provider?: string;
  model?: string | null;
  provider_task_id?: string | null;
  attempt?: number | null;
  retry_of?: string | null;
  cost: VideoCost;
  failure?: {
    category?: string;
    message?: string;
    retryable?: boolean;
    source?: string;
    categories?: string[];
    affected_shot_ids?: string[];
    affected_asset_ids?: string[];
  } | null;
  input_refs: string[];
  output_refs: string[];
  artifacts: VideoArtifact[];
  occurred_at?: string;
};

export type VideoWorkbenchConfirmation = {
  id: string;
  event_key: string;
  kind: "candidate_selection" | "paid_provider_call" | "real_publish";
  entity_type: string;
  entity_id: string;
  reason?: string | null;
  requested_at?: string;
};

export type VideoTimelineClip = {
  id?: string | null;
  shot_id?: string | null;
  start_sec?: number | null;
  duration_sec?: number | null;
  source_in_sec?: number | null;
  source_ref?: string | null;
  source_sha256?: string | null;
  selected_candidate_id?: string | null;
  text?: string | null;
  volume?: number | null;
  transition?: string | null;
  artifact?: VideoArtifact | null;
};

export type VideoTimelineTrack = {
  id?: string;
  type: "video" | "dialogue" | "music" | "subtitle" | "audio";
  entity_id?: string;
  status?: string;
  artifacts: VideoArtifact[];
  clips: VideoTimelineClip[];
  event_id?: string;
};

export type VideoTimelineRevision = {
  event_id?: string;
  event_key?: string;
  revision_id?: string | null;
  base_revision_id?: string | null;
  author_kind?: "human" | "agent" | null;
  intent?: string | null;
  sha256?: string | null;
  tracks: Array<Record<string, unknown>>;
  operations: Array<Record<string, unknown>>;
  occurred_at?: string | null;
};

export type PersonalIPVideoWorkbench = {
  contract_version: "personal-ip-video-workbench-v1";
  production_mode?: VideoProductionMode | null;
  production: PersonalIPVideoProduction;
  source: { kind: "idea" | "script"; content: Record<string, unknown> };
  stage_summary: Array<{
    id: VideoProductionStage;
    label: string;
    ledger_state:
      | "not_started"
      | "recorded"
      | "current"
      | "attention"
      | "complete";
    event_count: number;
    latest_event?: VideoProductionEvent | null;
  }>;
  domain_contracts: {
    plan?: Record<string, unknown> | null;
    asset_manifest?: Record<string, unknown> | null;
    storyboard?: Record<string, unknown> | null;
    narration?: Record<string, unknown> | null;
    material_selection?: Record<string, unknown> | null;
    narration_timing?: Record<string, unknown> | null;
    continuity?: Record<string, unknown> | null;
    assembly?: Record<string, unknown> | null;
    timeline_revision?: Record<string, unknown> | null;
    final_edit_lock?: Record<string, unknown> | null;
  };
  blueprint: {
    events: VideoProductionEvent[];
    artifacts: VideoArtifact[];
    contract?: Record<string, unknown> | null;
  };
  assets: Array<{
    entity_type: string;
    id: string;
    name?: string | null;
    status?: string;
    version?: number | string | null;
    source_sha256?: string | null;
    source_ref?: string | null;
    license?: string | null;
    allowed_for_use?: boolean | null;
    generation_route?: string | null;
    projection_mode?: string | null;
    coverage?: Record<string, unknown> | null;
    lineage?: Record<string, unknown> | null;
    latest_event?: VideoProductionEvent | null;
    artifacts: VideoArtifact[];
    event_ids: string[];
  }>;
  storyboard: {
    events: VideoProductionEvent[];
    shot_count: number;
    artifacts: VideoArtifact[];
    contract?: Record<string, unknown> | null;
  };
  shots: Array<{
    id: string;
    spec: {
      order?: number | null;
      title?: string | null;
      scene_id?: string | null;
      duration_seconds?: number | null;
      first_frame?: string | null;
      last_frame?: string | null;
      motion?: string | null;
      preserve_elements?: string[];
      change_elements?: string[];
      dialogue?: string | null;
      camera?: unknown;
      action?: string | null;
      narration_text?: string | null;
      visual_subject?: string | null;
      visual_query?: string | null;
      composition_strategy?: string | null;
      claim_evidence_refs?: string[];
      pass_criteria?: string[];
    };
    task_ids: string[];
    candidate_ids: string[];
    selected_candidate_id?: string | null;
  }>;
  tasks: VideoWorkbenchTask[];
  candidates: Array<{
    id: string;
    shot_id?: string | null;
    status?: string;
    selected: boolean;
    selection?: VideoProductionEvent | null;
    consistency?: Record<string, unknown> | null;
    quality?: Record<string, unknown> | null;
    review?: VideoProductionEvent | null;
    artifacts: VideoArtifact[];
    task_ids: string[];
    event_ids: string[];
  }>;
  continuity: {
    ledger?: Record<string, unknown> | null;
    bridges: Array<{
      event_id?: string;
      event_key?: string;
      candidate_id?: string | null;
      bridge_id?: string;
      from_shot_id?: string;
      to_shot_id?: string;
      inherited_state_sha256?: string;
      preserve_facts?: unknown[];
      cut_kind?: string;
      axis_relation?: string;
      [key: string]: unknown;
    }>;
    recovery_scopes: Array<{
      event_id?: string;
      event_key?: string;
      entity_id?: string;
      source?: string | null;
      categories: string[];
      affected_shot_ids: string[];
      affected_asset_ids: string[];
      retryable?: boolean | null;
    }>;
  };
  confirmations: VideoWorkbenchConfirmation[];
  timeline: {
    events: VideoProductionEvent[];
    fps?: number | null;
    duration_sec?: number | null;
    tracks: VideoTimelineTrack[];
    revision_id?: string | null;
    revisions: VideoTimelineRevision[];
    locked?: boolean;
    final_edit_lock?: Record<string, unknown> | null;
  };
  delivery: {
    qa_events: VideoProductionEvent[];
    current_qa_event?: VideoProductionEvent | null;
    delivery_events: VideoProductionEvent[];
    qa_passed?: boolean | null;
    qa_stale?: boolean;
    qa_stale_reason?: string | null;
    artifacts: VideoArtifact[];
  };
  events: VideoProductionEvent[];
};

export const PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY = [
  "personal-ip",
  "video-productions",
] as const;
export const PERSONAL_IP_MEDIA_MODELS_QUERY_KEY = [
  "personal-ip",
  "media-models",
] as const;

export function personalIPMediaModelsPath() {
  return "/api/personal-ip/video-productions/models";
}

export function personalIPVideoWorkbenchPath(productionId: string) {
  return `/api/personal-ip/video-productions/${encodeURIComponent(productionId)}/workbench`;
}

export function personalIPVideoArtifactPath(
  productionId: string,
  artifactSha256: string,
) {
  return `/api/personal-ip/video-productions/${encodeURIComponent(productionId)}/artifacts/${encodeURIComponent(artifactSha256)}`;
}

export function personalIPVideoArtifactURL(
  productionId: string,
  artifactSha256: string,
) {
  return `${getBackendBaseURL()}${personalIPVideoArtifactPath(productionId, artifactSha256)}`;
}

export function isMeaningfulVideoConfirmation(kind: string) {
  return ["candidate_selection", "paid_provider_call", "real_publish"].includes(
    kind,
  );
}

export function formatVideoCost(cost: VideoCost) {
  if (cost.status === "unknown") {
    return `费用未知${cost.reason ? ` · ${cost.reason}` : ""}`;
  }
  if (
    (cost.status === "known" || cost.status === "estimated") &&
    typeof cost.amount === "number" &&
    cost.currency
  ) {
    return `${cost.status === "estimated" ? "约 " : ""}${cost.currency} ${cost.amount.toFixed(2)}`;
  }
  return "未记录费用";
}

export function videoRecoveryPrompt({
  productionId,
  eventKey,
  entityId,
}: {
  productionId: string;
  eventKey: string;
  entityId: string;
}) {
  return `请使用 personal_ip_read_video_production 读取制作 ${productionId} 的不可变事件账本，定位失败事件 ${eventKey}（实体 ${entityId}），在校验输入和既有输出哈希后创建新的 retry event_key，并通过 personal_ip_record_video_production_event 继续推进。不要从聊天记录重建，也不要覆盖失败回执。`;
}

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

function normalizeOptionalThreadId(value: string | null | undefined) {
  const normalized = value?.trim();
  if (!normalized) return null;
  return normalized;
}

export function usePersonalIPVideoProductions(options?: {
  threadId?: string | null;
  enabled?: boolean;
}) {
  const threadId = normalizeOptionalThreadId(options?.threadId);
  return useQuery({
    queryKey: [...PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY, { threadId }],
    enabled: options?.enabled ?? true,
    queryFn: () =>
      requestJSON<PersonalIPVideoProduction[]>(
        `/api/personal-ip/video-productions?limit=200${
          threadId ? `&thread_id=${encodeURIComponent(threadId)}` : ""
        }`,
      ),
  });
}

export function useBindVideoProductionThread(productionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (threadId: string) => {
      if (!productionId) throw new Error("未选择视频制作");
      return bindPersonalIPVideoProductionThread(productionId, threadId);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY,
      }),
  });
}

export function bindPersonalIPVideoProductionThread(
  productionId: string,
  threadId: string,
) {
  return requestJSON<PersonalIPVideoProduction>(
    `/api/personal-ip/video-productions/${encodeURIComponent(productionId)}/thread`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ thread_id: threadId }),
    },
  );
}

export function ensurePersonalIPVideoTaskThread(
  productionId: string,
  threadId: string,
  title: string,
) {
  return requestJSON<{ thread_id: string }>("/api/threads", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      thread_id: threadId,
      assistant_id: "ip-agent",
      metadata: {
        title,
        task_type: "video_production",
        video_production_id: productionId,
      },
    }),
  });
}

export function usePersonalIPMediaModelCatalog() {
  return useQuery({
    queryKey: PERSONAL_IP_MEDIA_MODELS_QUERY_KEY,
    queryFn: () =>
      requestJSON<PersonalIPMediaModelCatalog>(personalIPMediaModelsPath()),
    staleTime: 15 * 60 * 1000,
  });
}

export function usePersonalIPVideoWorkbench(productionId: string | null) {
  return useQuery({
    queryKey: [...PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY, productionId],
    queryFn: () =>
      requestJSON<PersonalIPVideoWorkbench>(
        personalIPVideoWorkbenchPath(productionId ?? ""),
      ),
    enabled: Boolean(productionId),
  });
}

export function useRecordVideoConfirmation(productionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      confirmation,
      decision,
    }: {
      confirmation: VideoWorkbenchConfirmation;
      decision: "approved" | "rejected";
    }) => {
      if (!productionId) throw new Error("未选择视频制作");
      return requestJSON<PersonalIPVideoProduction>(
        `/api/personal-ip/video-productions/${encodeURIComponent(productionId)}/events`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_key: `workbench-review:${confirmation.event_key}:${decision}`,
            event_type: "review_recorded",
            status: decision,
            entity_type: confirmation.entity_type,
            entity_id: confirmation.entity_id,
            payload: {
              contract_version: "personal-ip-video-review-v1",
              review_kind: confirmation.kind,
              request_event_key: confirmation.event_key,
              decision,
            },
            input_refs: [`event://${confirmation.event_key}`],
            output_refs: [],
            provider: "human-workbench",
            model: null,
            provider_task_id: null,
            cost: {
              status: "known",
              amount: 0,
              currency: "CNY",
              basis: "human confirmation",
            },
          }),
        },
      );
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY,
        }),
      ]);
    },
  });
}

export type SaveVideoTimelineRevisionInput = {
  revision_id: string;
  base_revision_id?: string | null;
  author_kind: "human" | "agent";
  intent: string;
  fps: number;
  tracks: Array<Record<string, unknown>>;
  operations: Array<Record<string, unknown>>;
  strategy_confirmed?: boolean;
};

export function useSaveVideoTimelineRevision(productionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: SaveVideoTimelineRevisionInput) => {
      if (!productionId) throw new Error("未选择视频制作");
      const eventKey = `timeline-revision:${input.revision_id}`;
      return requestJSON<{
        compiled_contract: Record<string, unknown>;
        production: PersonalIPVideoProduction;
      }>(
        `/api/personal-ip/video-productions/${encodeURIComponent(productionId)}/timeline-revisions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...input,
            event_key: eventKey,
            strategy_confirmed: input.strategy_confirmed ?? true,
          }),
        },
      );
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY,
        }),
      ]);
    },
  });
}

export function useLockVideoFinalEdit(productionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ lockId, note }: { lockId: string; note: string }) => {
      if (!productionId) throw new Error("未选择视频制作");
      return requestJSON<{
        compiled_contract: Record<string, unknown>;
        production: PersonalIPVideoProduction;
      }>(
        `/api/personal-ip/video-productions/${encodeURIComponent(productionId)}/final-edit-lock`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event_key: `final-edit-lock:${lockId}`,
            lock_id: lockId,
            locked_by: "human",
            note,
          }),
        },
      );
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY,
        }),
      ]);
    },
  });
}
