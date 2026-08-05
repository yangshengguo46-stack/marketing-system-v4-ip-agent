"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type ContentEntryRoute = "zero_start" | "benchmark";
export type ContentTruthMode = "factual" | "fictional" | "hybrid";

const CONTENT_ENTRY_PROMPTS: Record<ContentEntryRoute, string> = {
  zero_start:
    "我要从零起盘一条原创内容。请先判断当前更急的是促成成交、建立认知还是积累信任，以及对应的时间窗口；再决定这次内容应主要归因于个人、产品、品牌还是组织。信息足够时请直接推荐一个方向，不要把交流做成问卷；只追问真正影响判断的缺口。事实、推断与创作假设要分开，方向确认后再保存完整剧本版本。",
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

export type EditorialGoalPriority = "conversion" | "recognition" | "trust";
export type EditorialTimeHorizon = "urgent" | "near_term" | "long_term";
export type EditorialCarrierKind =
  | "person"
  | "product"
  | "brand"
  | "organization";
export type EditorialRouteKind =
  | "offer"
  | "proof"
  | "demonstration"
  | "explanation"
  | "semantic_story"
  | "hybrid";

export type EditorialProgramDecision = {
  contract_version: "personal-ip-editorial-program-v1";
  mission: {
    goal_priority: EditorialGoalPriority[];
    time_horizon: EditorialTimeHorizon;
    deadline_or_window: string;
    desired_action: string;
    success_signal: string;
    cost_of_delay: string;
    non_goals: string[];
    rationale: string;
  };
  audience: {
    situation: string;
    state: "user_asserted" | "hypothesized" | "unknown";
    uncertainties: string[];
  };
  attribution: {
    primary_carrier: {
      kind: EditorialCarrierKind;
      identity: string;
    };
    supporting_carriers: Array<{
      kind: EditorialCarrierKind;
      identity: string;
    }>;
    desired_association: string;
    attribution_guard: string;
    rationale: string;
  };
  differentiation: {
    statement: string;
    contrast: string;
    basis: Array<{
      claim: string;
      state: "user_asserted" | "derived" | "hypothesized";
    }>;
    reason_to_choose: string;
    reason_to_believe: string;
    sacrifice: string;
    test_signal: string;
    uncertainties: string[];
    state: "hypothesized";
  };
  editorial_spine?: {
    source_concepts: string[];
    human_theme: string;
    recurring_question: string;
    boundary: string;
  } | null;
};

export type EditorialProgramVersion = {
  id: string;
  program_id: string;
  subject_id: string | null;
  version_number: number;
  parent_program_version_id: string | null;
  title: string;
  decision: EditorialProgramDecision;
  created_at: string;
};

export type PersonalIPContentWork = {
  id: string;
  objective_id: string;
  editorial_program_version_id?: string | null;
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

export type SemanticCausalRoute = {
  association_path: string[];
  human_theme: string;
  causal_pattern: string;
  episode_tension: string;
  mission_bridge: string;
  attribution_guard: string;
};

export type DirectionSnapshot = {
  contract_version?: "personal-ip-direction-v1" | "personal-ip-direction-v2";
  route_kind?: EditorialRouteKind | null;
  semantic_route?: SemanticCausalRoute | null;
  editorial_program_digest?: string | null;
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
  editorial_program_version?: EditorialProgramVersion | null;
  breakdown_versions: PersonalIPBreakdownVersion[];
  direction_versions: PersonalIPDirectionVersion[];
  script_versions: PersonalIPScriptVersion[];
};

export type EditorialProgramProjection = {
  mission: {
    currentTask: string;
    priorityResult: string;
    timeWindow: string;
    successSignal: string;
    nonGoals: string[];
  };
  audience: {
    situation: string;
    state: "用户明确" | "待验证" | "未知";
    uncertainties: string[];
  };
  attribution: {
    carrierKind: string;
    identity: string;
    desiredAssociation: string;
  };
  differentiation: {
    statement: string;
    contrast: string;
    reasonToChoose: string;
    reasonToBelieve: string;
    sacrifice: string;
    testSignal: string;
    state: "待验证";
  };
  contentRoute: {
    kind: string;
    description: string;
  };
  editorialSpine?: {
    humanTheme: string;
    recurringQuestion: string;
  };
};

const EDITORIAL_GOAL_PRIORITY_LABELS: Record<EditorialGoalPriority, string> = {
  conversion: "成交",
  recognition: "认知",
  trust: "信任",
};

const EDITORIAL_TIME_HORIZON_LABELS: Record<EditorialTimeHorizon, string> = {
  urgent: "紧急窗口",
  near_term: "近期",
  long_term: "长期",
};

const EDITORIAL_CARRIER_KIND_LABELS: Record<EditorialCarrierKind, string> = {
  person: "个人",
  product: "产品",
  brand: "品牌",
  organization: "组织",
};

const EDITORIAL_AUDIENCE_STATE_LABELS: Record<
  EditorialProgramDecision["audience"]["state"],
  EditorialProgramProjection["audience"]["state"]
> = {
  user_asserted: "用户明确",
  hypothesized: "待验证",
  unknown: "未知",
};

const EDITORIAL_ROUTE_KIND_LABELS: Record<EditorialRouteKind, string> = {
  offer: "直接提案",
  proof: "证据建立",
  demonstration: "现场示范",
  explanation: "解释说明",
  semantic_story: "意义故事",
  hybrid: "混合路线",
};

function projectionText(value: string | null | undefined, fallback: string) {
  const trimmed = value?.trim();
  if (trimmed?.length) return trimmed;
  return fallback;
}

export function projectPersonalIPEditorialProgram(
  program: EditorialProgramVersion | null | undefined,
  direction: DirectionSnapshot | null | undefined,
): EditorialProgramProjection | undefined {
  if (!program) return undefined;

  const {
    mission,
    audience,
    attribution,
    differentiation,
    editorial_spine: spine,
  } = program.decision;
  const timeWindow = projectionText(
    mission.deadline_or_window,
    EDITORIAL_TIME_HORIZON_LABELS[mission.time_horizon] ?? "待确认",
  );
  const contentRoute = projectionText(direction?.creative_route, "待方向确认");
  const hasEditorialSpine = [
    spine?.human_theme,
    spine?.recurring_question,
  ].some((item) => Boolean(item?.trim()));
  const editorialSpine =
    hasEditorialSpine && spine
      ? {
          humanTheme: projectionText(spine.human_theme, "未记录"),
          recurringQuestion: projectionText(spine.recurring_question, "未记录"),
        }
      : undefined;

  return {
    mission: {
      currentTask: projectionText(mission.desired_action, "待确认"),
      priorityResult: mission.goal_priority
        .map((goal) => EDITORIAL_GOAL_PRIORITY_LABELS[goal] ?? "待确认")
        .join(" → "),
      timeWindow,
      successSignal: projectionText(mission.success_signal, "待确认"),
      nonGoals: mission.non_goals
        .map((item) => item.trim())
        .filter((item) => item.length > 0),
    },
    audience: {
      situation: projectionText(audience.situation, "未知"),
      state: EDITORIAL_AUDIENCE_STATE_LABELS[audience.state] ?? "未知",
      uncertainties: audience.uncertainties
        .map((item) => item.trim())
        .filter((item) => item.length > 0),
    },
    attribution: {
      carrierKind:
        EDITORIAL_CARRIER_KIND_LABELS[attribution.primary_carrier.kind] ??
        "待确认",
      identity: projectionText(attribution.primary_carrier.identity, "待确认"),
      desiredAssociation: projectionText(
        attribution.desired_association,
        "待确认",
      ),
    },
    differentiation: {
      statement: projectionText(differentiation.statement, "待确认"),
      contrast: projectionText(differentiation.contrast, "待确认"),
      reasonToChoose: projectionText(
        differentiation.reason_to_choose,
        "待确认",
      ),
      reasonToBelieve: projectionText(
        differentiation.reason_to_believe,
        "待确认",
      ),
      sacrifice: projectionText(differentiation.sacrifice, "待确认"),
      testSignal: projectionText(differentiation.test_signal, "待确认"),
      state: "待验证",
    },
    contentRoute: {
      kind: direction?.route_kind
        ? (EDITORIAL_ROUTE_KIND_LABELS[direction.route_kind] ?? "待确认")
        : "待确认",
      description: contentRoute,
    },
    ...(editorialSpine ? { editorialSpine } : {}),
  };
}

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
