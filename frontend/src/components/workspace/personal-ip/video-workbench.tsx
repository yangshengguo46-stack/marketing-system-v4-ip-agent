"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  BotIcon,
  BoxesIcon,
  CheckCircle2Icon,
  ChevronRightIcon,
  CircleDollarSignIcon,
  CopyIcon,
  DownloadIcon,
  FilmIcon,
  GaugeIcon,
  GripVerticalIcon,
  ImageIcon,
  Layers3Icon,
  LoaderCircleIcon,
  MessageSquareTextIcon,
  Music2Icon,
  PackageCheckIcon,
  RefreshCcwIcon,
  SaveIcon,
  ScissorsIcon,
  SendIcon,
  ShieldCheckIcon,
  SparklesIcon,
  Trash2Icon,
  Undo2Icon,
  Volume2Icon,
  XCircleIcon,
} from "lucide-react";
import Link from "next/link";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import { visibleAssistantContent } from "@/core/messages/utils";
import {
  type PersonalIPVideoWorkbench,
  type VideoArtifact,
  type VideoTimelineClip,
  type VideoTimelineTrack,
  type VideoWorkbenchConfirmation,
  type VideoWorkbenchTask,
  PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY,
  formatVideoCost,
  personalIPVideoArtifactURL,
  useBindVideoProductionThread,
  usePersonalIPVideoProductions,
  usePersonalIPMediaModelCatalog,
  usePersonalIPVideoWorkbench,
  useLockVideoFinalEdit,
  useRecordVideoConfirmation,
  useSaveVideoTimelineRevision,
} from "@/core/personal-ip";
import { useLocalSettings } from "@/core/settings";
import { useThreadStream } from "@/core/threads/hooks";
import { textOfMessage } from "@/core/threads/utils";
import { cn } from "@/lib/utils";

const EXECUTION_STATUS_LABELS: Record<string, string> = {
  awaiting_review: "待确认",
  blocked: "需要处理",
  cancelled: "已取消",
  completed: "已完成",
  failed: "生成失败",
  pending: "等待中",
  queued: "等待中",
  running: "生成中",
  succeeded: "已生成",
};

const ENTITY_LABELS: Record<string, string> = {
  character: "角色",
  scene: "场景",
  prop: "道具",
  image: "设定图",
  shot: "镜头",
  candidate: "候选片段",
  audio: "音频",
  timeline: "时间线",
  delivery: "交付",
  production: "制作",
};

const DELIVERY_CHECK_LABELS: Record<string, string> = {
  audio: "声音正常",
  black_frames: "无异常黑帧",
  decode: "视频可完整播放",
  duration: "时长正确",
  fps: "帧率符合要求",
  freeze_frames: "无异常卡帧",
  resolution: "画面尺寸正确",
  subtitles: "字幕时间正确",
};

const EVENT_LABELS: Record<string, string> = {
  video_plan_compiled: "生产方案已编译",
  blueprint_sealed: "蓝图已封存",
  asset_manifest_compiled: "资产合同已编译",
  asset_registered: "资产已登记",
  asset_generation_requested: "资产生成中",
  asset_generation_completed: "资产已生成",
  asset_generation_failed: "资产生成失败",
  storyboard_sealed: "分镜已封存",
  storyboard_compiled: "分镜合同已编译",
  material_selection_compiled: "逐镜素材已锁定",
  continuity_compiled: "连续性账本已编译",
  generated_shot_qa_compiled: "逐镜 QA 已计算",
  shot_generation_requested: "镜头生成中",
  shot_generation_completed: "镜头候选已生成",
  shot_generation_failed: "镜头生成失败",
  consistency_checked: "一致性已检查",
  candidate_selected: "候选已选用",
  review_requested: "等待确认",
  review_recorded: "确认已记录",
  voice_generated: "配音已生成",
  narration_contract_compiled: "旁白合同已编译",
  narration_timing_compiled: "旁白时长与回执已对账",
  voice_generation_requested: "配音生成中",
  media_processing_requested: "媒体处理中",
  media_processing_completed: "媒体处理完成",
  media_processing_failed: "媒体处理失败",
  edit_completed: "剪辑完成",
  assembly_admitted: "选中片段已准入时间线",
  timeline_revision_compiled: "时间线修订已封存",
  final_edit_locked: "最终剪辑已锁定",
  delivery_qa_completed: "交付 QA 完成",
  delivery_completed: "交付完成",
};

type WorkbenchView =
  | "overview"
  | "storyboard"
  | "tasks"
  | "candidates"
  | "timeline"
  | "delivery"
  | "receipts";

const SHOW_INLINE_TIMELINE_TOOLBAR = false;

const DIRECTOR_STAGES: Array<{
  id: string;
  label: string;
  view: WorkbenchView;
  views: WorkbenchView[];
  ledgerStages: string[];
}> = [
  {
    id: "setup",
    label: "设定",
    view: "overview",
    views: ["overview"],
    ledgerStages: ["intake", "blueprint", "assets"],
  },
  {
    id: "storyboard",
    label: "分镜",
    view: "storyboard",
    views: ["storyboard"],
    ledgerStages: ["storyboard", "generation", "consistency", "selection"],
  },
  {
    id: "edit",
    label: "剪辑",
    view: "timeline",
    views: ["timeline"],
    ledgerStages: ["finishing"],
  },
  {
    id: "delivery",
    label: "成片",
    view: "delivery",
    views: ["delivery"],
    ledgerStages: ["delivery"],
  },
];

function statusBadge(status: string | undefined) {
  if (status === "failed" || status === "blocked" || status === "rejected") {
    return "destructive" as const;
  }
  if (status === "awaiting_review") return "secondary" as const;
  if (
    status === "succeeded" ||
    status === "completed" ||
    status === "approved"
  ) {
    return "outline" as const;
  }
  return "secondary" as const;
}

function formatTime(value: string | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function safeRef(ref: string) {
  const clean = ref.split("?")[0]?.split("#")[0] ?? ref;
  try {
    const parsed = new URL(clean);
    if (parsed.username || parsed.password) {
      parsed.username = "";
      parsed.password = "";
    }
    return parsed.toString();
  } catch {
    return clean;
  }
}

function shortRef(ref: string) {
  const clean = safeRef(ref);
  const parts = clean.split("/").filter(Boolean);
  return parts.at(-1) ?? clean;
}

function jsonText(value: unknown) {
  return JSON.stringify(value, null, 2);
}

function objectValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function EmptyPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-muted-foreground flex min-h-36 items-center justify-center rounded-xl border border-dashed p-6 text-center text-sm">
      {children}
    </div>
  );
}

function ArtifactList({
  artifacts,
  compact = false,
}: {
  artifacts: VideoArtifact[];
  compact?: boolean;
}) {
  if (artifacts.length === 0)
    return <span className="text-muted-foreground text-xs">无产物</span>;
  return (
    <div className="space-y-2">
      {artifacts.map((artifact) => {
        const displayRef = safeRef(artifact.ref);
        return (
          <div
            key={artifact.ref}
            className={cn(
              "bg-background/70 rounded-lg border",
              compact ? "px-3 py-2" : "p-3",
            )}
          >
            <div className="flex min-w-0 items-center gap-2">
              <PackageCheckIcon className="size-4 shrink-0 text-emerald-600" />
              <span className="truncate text-xs font-medium" title={displayRef}>
                {shortRef(displayRef)}
              </span>
              {artifact.mime_type && (
                <Badge
                  variant="outline"
                  className="ml-auto max-w-36 truncate text-[10px]"
                >
                  {artifact.mime_type}
                </Badge>
              )}
            </div>
            <p
              className="text-muted-foreground mt-1 truncate font-mono text-[10px]"
              title={displayRef}
            >
              {displayRef}
            </p>
            {artifact.sha256 && (
              <div className="mt-2 flex items-start gap-2">
                <span className="text-muted-foreground pt-0.5 text-[10px] uppercase">
                  sha256
                </span>
                <code className="text-[10px] leading-4 break-all">
                  {artifact.sha256}
                </code>
              </div>
            )}
            {typeof artifact.size_bytes === "number" && (
              <p className="text-muted-foreground mt-1 text-[10px] tabular-nums">
                {artifact.size_bytes.toLocaleString()} bytes
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Snapshot({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="min-w-0 rounded-xl border bg-black/[0.025] dark:bg-white/[0.025]">
      <div className="text-muted-foreground border-b px-4 py-2 text-[11px] font-medium tracking-wide uppercase">
        {title}
      </div>
      <pre className="max-h-64 overflow-auto p-4 text-xs leading-5 whitespace-pre-wrap">
        {jsonText(value)}
      </pre>
    </div>
  );
}

function StageRail({
  workbench,
  activeView,
  onSelect,
}: {
  workbench?: PersonalIPVideoWorkbench;
  activeView: WorkbenchView;
  onSelect: (view: WorkbenchView) => void;
}) {
  return (
    <ScrollArea className="w-full" aria-label="视频制作阶段">
      <nav className="flex min-w-[360px] items-center justify-center px-2">
        {DIRECTOR_STAGES.map((stage, index) => {
          const ledgerStages = (workbench?.stage_summary ?? []).filter((item) =>
            stage.ledgerStages.includes(item.id),
          );
          const attention = ledgerStages.some(
            (item) => item.ledger_state === "attention",
          );
          const active = ledgerStages.some(
            (item) => item.ledger_state === "current",
          );
          const recorded =
            ledgerStages.length > 0 &&
            ledgerStages.every((item) =>
              ["complete", "recorded"].includes(item.ledger_state),
            );
          const selected = stage.views.includes(activeView);
          return (
            <div key={stage.id} className="relative flex min-w-0 flex-1">
              {index < DIRECTOR_STAGES.length - 1 && (
                <div className="absolute top-3.5 left-[62%] h-px w-[76%] bg-[#d7d0c5]" />
              )}
              <button
                type="button"
                aria-label={`${stage.label}阶段`}
                onClick={() => onSelect(stage.view)}
                className={cn(
                  "relative z-10 flex min-w-0 flex-1 flex-col items-center gap-1.5 rounded-lg px-1 py-1 text-[#8d867c] transition hover:bg-white/60 hover:text-[#24211d]",
                  attention && "text-amber-700",
                  active && "font-bold",
                  recorded && "text-[#397461]",
                  selected && "text-[#ad3f2d]",
                )}
              >
                <span
                  className={cn(
                    "flex size-7 items-center justify-center rounded-full border border-[#d9d2c8] bg-[#faf8f2] text-[9px] font-semibold tabular-nums",
                    recorded && "border-[#397461]/25 bg-[#397461]/10",
                    attention && "border-amber-500/40 bg-amber-500/10",
                    selected &&
                      "border-[#e25f45] bg-[#e25f45] text-white shadow-[0_0_0_4px_rgba(226,95,69,0.1)]",
                  )}
                >
                  {recorded ? (
                    <CheckCircle2Icon className="size-3.5" />
                  ) : (
                    index + 1
                  )}
                </span>
                <span className="max-w-full truncate text-[9px] font-semibold">
                  {stage.label}
                </span>
              </button>
            </div>
          );
        })}
      </nav>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
}

function ConfirmationCard({
  confirmation,
  pending,
  onDecision,
}: {
  confirmation: VideoWorkbenchConfirmation;
  pending: boolean;
  onDecision: (decision: "approved" | "rejected") => void;
}) {
  const selection = confirmation.kind === "candidate_selection";
  const publishing = confirmation.kind === "real_publish";
  const title = selection
    ? "候选选片确认"
    : publishing
      ? "真实发布确认"
      : "真实付费调用确认";
  const approveLabel = selection
    ? "确认选用"
    : publishing
      ? "批准真实发布"
      : "批准真实付费调用";
  return (
    <div className="rounded-xl border border-amber-400/50 bg-amber-500/[0.07] p-4">
      <div className="flex items-start gap-3">
        {selection || publishing ? (
          <ShieldCheckIcon className="mt-0.5 size-5 text-amber-700 dark:text-amber-300" />
        ) : (
          <CircleDollarSignIcon className="mt-0.5 size-5 text-amber-700 dark:text-amber-300" />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{title}</p>
          <p className="text-muted-foreground mt-1 text-xs leading-5">
            {confirmation.reason ??
              "这一步会产生实际费用或外部影响，需要你确认后继续。"}
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={pending}
          onClick={() => onDecision("rejected")}
        >
          <XCircleIcon /> 拒绝
        </Button>
        <Button
          size="sm"
          disabled={pending}
          onClick={() => onDecision("approved")}
        >
          {pending ? (
            <LoaderCircleIcon className="animate-spin" />
          ) : (
            <CheckCircle2Icon />
          )}
          {approveLabel}
        </Button>
      </div>
    </div>
  );
}

function TaskCard({ task }: { task: VideoWorkbenchTask }) {
  const failed = task.status === "failed";
  return (
    <Card className={cn("gap-4 py-4", failed && "border-destructive/35")}>
      <CardHeader className="gap-3 px-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-sm">
                {EVENT_LABELS[task.event_type ?? ""] ?? task.event_type}
              </CardTitle>
              <Badge variant={statusBadge(task.status)}>
                {task.status ?? "unknown"}
              </Badge>
              {typeof task.attempt === "number" && (
                <Badge variant="outline">第 {task.attempt} 次</Badge>
              )}
            </div>
            <p className="text-muted-foreground mt-1 text-xs">
              {ENTITY_LABELS[task.entity_type ?? ""] ?? task.entity_type} ·{" "}
              {task.entity_id}
            </p>
          </div>
          <span className="text-muted-foreground text-[11px]">
            {formatTime(task.occurred_at)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 px-4">
        <div className="grid gap-2 text-xs sm:grid-cols-2 xl:grid-cols-4">
          <EvidenceField label="Provider" value={task.provider} />
          <EvidenceField label="Model" value={task.model ?? "—"} />
          <EvidenceField
            label="Task ID"
            value={task.provider_task_id ?? "—"}
            mono
          />
          <EvidenceField label="Cost" value={formatVideoCost(task.cost)} />
        </div>
        {task.retry_of && (
          <div className="flex items-center gap-2 rounded-lg border bg-blue-500/[0.05] px-3 py-2 text-xs">
            <RefreshCcwIcon className="size-4 text-blue-600" />
            <span className="text-muted-foreground">retry_of</span>
            <code className="break-all">{task.retry_of}</code>
          </div>
        )}
        {task.failure && (
          <div className="border-destructive/25 bg-destructive/[0.05] rounded-lg border px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <AlertTriangleIcon className="text-destructive size-4" />
              <code className="text-xs font-semibold">
                {task.failure.category ?? "uncategorized"}
              </code>
              <Badge
                variant={task.failure.retryable ? "secondary" : "destructive"}
              >
                {task.failure.retryable ? "可重试" : "不可重试"}
              </Badge>
            </div>
            {task.failure.message && (
              <p className="text-muted-foreground mt-2 text-xs">
                {task.failure.message}
              </p>
            )}
            {(Boolean(task.failure.source) ||
              (task.failure.affected_shot_ids?.length ?? 0) > 0 ||
              (task.failure.affected_asset_ids?.length ?? 0) > 0) && (
              <div className="text-muted-foreground mt-2 flex flex-wrap gap-2 text-[11px]">
                {task.failure.source && (
                  <Badge variant="outline">来源 {task.failure.source}</Badge>
                )}
                {task.failure.affected_shot_ids?.map((shotId) => (
                  <Badge key={shotId} variant="outline">
                    仅恢复 {shotId}
                  </Badge>
                ))}
                {task.failure.affected_asset_ids?.map((assetId) => (
                  <Badge key={assetId} variant="outline">
                    资产 {assetId}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
        {task.artifacts.length > 0 && (
          <ArtifactList artifacts={task.artifacts} compact />
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <code className="text-muted-foreground text-[10px] break-all">
            {task.event_key}
          </code>
          {failed && task.failure?.retryable && (
            <Badge variant="outline">可让智能体重试</Badge>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function EvidenceField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="bg-muted/40 min-w-0 rounded-lg border px-3 py-2">
      <p className="text-muted-foreground text-[10px] uppercase">{label}</p>
      <p
        className={cn("mt-1 truncate", mono && "font-mono")}
        title={typeof value === "string" ? value : undefined}
      >
        {value}
      </p>
    </div>
  );
}

type SetupPreviewItem = {
  key: string;
  asset: PersonalIPVideoWorkbench["assets"][number];
  artifact?: VideoArtifact;
  artifactIndex: number;
};

type WorkbenchQuickAction = {
  id: string;
  userText: string;
  internalInstruction: string;
};

function workbenchQuickAction(
  userText: string,
  internalInstruction: string,
): WorkbenchQuickAction {
  return {
    id: crypto.randomUUID(),
    userText,
    internalInstruction,
  };
}

function isImageArtifact(artifact: VideoArtifact) {
  if (artifact.mime_type?.startsWith("image/")) return true;
  return /\.(?:avif|gif|jpe?g|png|webp)$/i.test(safeRef(artifact.ref));
}

function setupPreviewItems(
  workbench: PersonalIPVideoWorkbench,
): SetupPreviewItem[] {
  return workbench.assets
    .filter(
      (asset) =>
        ["character", "scene", "prop", "image"].includes(asset.entity_type) ||
        asset.artifacts.some(isImageArtifact),
    )
    .flatMap((asset) => {
      const imageArtifacts = asset.artifacts.filter(isImageArtifact);
      const artifacts =
        imageArtifacts.length > 0 ? imageArtifacts : asset.artifacts;
      if (artifacts.length === 0) {
        return [
          {
            key: `${asset.entity_type}:${asset.id}:pending`,
            asset,
            artifactIndex: 0,
          },
        ];
      }
      return artifacts.map((artifact, artifactIndex) => ({
        key: `${asset.entity_type}:${asset.id}:${artifact.ref}`,
        asset,
        artifact,
        artifactIndex,
      }));
    });
}

function setupTargetLabel(item: SetupPreviewItem | undefined) {
  if (!item) return "本项目缺失的角色、场景和道具";
  return friendlyAssetName(item.asset);
}

function rawNameLooksInternal(value: string) {
  return (
    /\.(?:avif|gif|jpe?g|png|webp|mov|mp4)$/i.test(value) ||
    /^(?:shot[-_])?s?\d{1,3}[-_]/i.test(value) ||
    value.split(/[-_]/).length >= 4
  );
}

function friendlyAssetName(asset: SetupPreviewItem["asset"]) {
  const entityLabel = ENTITY_LABELS[asset.entity_type] ?? "素材";
  const raw = asset.name ?? asset.id;
  if (!raw || rawNameLooksInternal(raw)) {
    const order = /(?:^|[-_])s?(\d{1,3})(?:[-_.]|$)/i.exec(raw ?? "")?.[1];
    return order
      ? `${entityLabel} ${String(Number(order)).padStart(2, "0")}`
      : entityLabel;
  }
  return raw;
}

function friendlyShotName(
  workbench: PersonalIPVideoWorkbench,
  shotId: string | null | undefined,
) {
  const index = workbench.shots.findIndex((item) => item.id === shotId);
  const shot = index >= 0 ? workbench.shots[index] : undefined;
  const order = String(shot?.spec.order ?? Math.max(1, index + 1)).padStart(
    2,
    "0",
  );
  const title = shot?.spec.title;
  return title && !rawNameLooksInternal(title)
    ? `镜头 ${order} · ${title}`
    : `镜头 ${order}`;
}

function visibleTimelineClipText(
  workbench: PersonalIPVideoWorkbench,
  clip: EditableTimelineClip,
) {
  const text = clip.text?.trim();
  return text && !rawNameLooksInternal(text)
    ? text
    : friendlyShotName(workbench, clip.shot_id);
}

function setupArtifactIdentity(item: SetupPreviewItem | undefined) {
  if (!item?.artifact) return "尚未生成候选图";
  return `候选图 ${safeRef(item.artifact.ref)}${
    item.artifact.sha256 ? `（sha256=${item.artifact.sha256}）` : ""
  }`;
}

function setupAdoptAction(item: SetupPreviewItem) {
  const targetLabel = setupTargetLabel(item);
  return workbenchQuickAction(
    `采用这张${targetLabel}设定图`,
    `采用${targetLabel}的${setupArtifactIdentity(item)}作为当前正式设定。保留其他候选版本；校验使用权和回执后，用 personal_ip_compile_video_asset_manifest 更新同一制作的资产合同。`,
  );
}

function setupLibraryAction(item: SetupPreviewItem) {
  const targetLabel = setupTargetLabel(item);
  return workbenchQuickAction(
    `把这张${targetLabel}设定图加入素材库`,
    `把${targetLabel}的${setupArtifactIdentity(item)}加入当前用户的可复用素材库，并保留它与本制作、生成回执和使用权证据的关联。如果当前只有项目级资产账本，不要伪造跨项目保存成功；先完成本项目资产登记并明确返回缺失的用户级素材库能力。`,
  );
}

function setupNewVersionAction(item: SetupPreviewItem) {
  const targetLabel = setupTargetLabel(item);
  return workbenchQuickAction(
    `为${targetLabel}生成一个新版本`,
    `为${targetLabel}生成新的设定候选版本。${
      item.artifact ? `把${setupArtifactIdentity(item)}仅作为上一版参考，` : ""
    }先询问或根据用户的下一句话确定要保留和修改的元素；使用 Seedream，保留旧版本，并把每张新图及标准执行回执写回同一视频账本。`,
  );
}

function OverviewTab({
  workbench,
  selectedPreviewKey,
  onSelectPreview,
  command,
  onCommandChange,
  quickAction,
  onQuickAction,
  onQuickActionConsumed,
}: {
  workbench: PersonalIPVideoWorkbench;
  selectedPreviewKey: string | null;
  onSelectPreview: (key: string) => void;
  command: string;
  onCommandChange: (value: string) => void;
  quickAction: WorkbenchQuickAction | null;
  onQuickAction: (action: WorkbenchQuickAction) => void;
  onQuickActionConsumed: (id: string) => void;
}) {
  const previewItems = setupPreviewItems(workbench);
  const selectedPreview =
    previewItems.find((item) => item.key === selectedPreviewKey) ??
    previewItems[0];
  const selectedAsset = selectedPreview?.asset;
  const selectedArtifact = selectedPreview?.artifact;
  const previewRef = displayableMediaRef(
    selectedArtifact,
    workbench.production.id,
  );
  const selectedAssetVersions = selectedAsset
    ? previewItems.filter(
        (item) =>
          item.asset.entity_type === selectedAsset.entity_type &&
          item.asset.id === selectedAsset.id,
      )
    : [];

  const targetLabel = setupTargetLabel(selectedPreview);

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-3.5">
      <section className="overflow-hidden rounded-xl border border-[#3f352b]/14 bg-[#ebe3d6] shadow-[0_18px_50px_-38px_rgba(45,30,20,0.8)]">
        <div className="relative aspect-video min-h-[200px] overflow-hidden bg-[radial-gradient(circle_at_62%_24%,rgba(223,155,110,0.42),transparent_18%),radial-gradient(circle_at_35%_38%,rgba(98,127,126,0.3),transparent_28%),linear-gradient(145deg,#c9c1b5,#876f64_62%,#594b45)] xl:min-h-[280px]">
          {previewRef ? (
            <div
              className="size-full bg-contain bg-center bg-no-repeat"
              style={{ backgroundImage: `url(${JSON.stringify(previewRef)})` }}
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/10 px-8 text-center text-white">
              <div className="flex size-16 items-center justify-center rounded-full border border-white/25 bg-black/20 backdrop-blur">
                <ImageIcon className="size-7" />
              </div>
              <p className="mt-4 text-lg font-semibold">
                {selectedAsset?.name ?? "还没有设定候选图"}
              </p>
              <p className="mt-2 max-w-lg text-xs leading-5 text-white/70">
                描述你想要的角色、场景或道具。智能体会生成首批候选，每一版都保留在左侧。
              </p>
            </div>
          )}
          <div className="absolute top-3 left-3 flex items-center gap-2 rounded-md border border-white/20 bg-black/35 px-2 py-1 text-[10px] text-white backdrop-blur">
            <ImageIcon className="size-3" />
            {selectedAsset
              ? (ENTITY_LABELS[selectedAsset.entity_type] ??
                selectedAsset.entity_type)
              : "设定图"}
          </div>
        </div>
        <div className="flex min-h-11 flex-wrap items-center gap-2 border-t border-[#3f352b]/10 bg-[#faf8f2] px-3 py-2 text-[10px] text-[#79736a]">
          <span className="font-semibold text-[#24211d]">
            {selectedAsset ? friendlyAssetName(selectedAsset) : "等待生成"}
          </span>
          {selectedAsset?.status && (
            <Badge
              variant={statusBadge(selectedAsset.status)}
              className="text-[9px]"
            >
              {EXECUTION_STATUS_LABELS[selectedAsset.status] ?? "处理中"}
            </Badge>
          )}
        </div>
      </section>

      <section className="grid grid-cols-[72px_1fr] items-center gap-3">
        <span className="pl-1 text-xs font-semibold">候选版本</span>
        <div className="flex min-w-0 gap-2 overflow-x-auto pb-1">
          {selectedAssetVersions.length === 0 ? (
            <button
              type="button"
              onClick={() =>
                onQuickAction(
                  workbenchQuickAction(
                    "生成第一批角色、场景和道具设定图",
                    "读取当前视频的剧本和影视蓝图，列出缺失的角色、场景、道具设定，并用 Seedream 逐类生成首批候选图。每张图必须生成标准回执并写回同一视频资产账本；先从最影响人物和视觉一致性的设定开始。",
                  ),
                )
              }
              className="flex h-12 min-w-44 items-center justify-center rounded-lg border border-dashed border-[#3f352b]/20 bg-white/35 text-[10px] text-[#645b51]"
            >
              + 生成第一批设定图
            </button>
          ) : (
            selectedAssetVersions.map((item, index) => {
              const versionRef = displayableMediaRef(
                item.artifact,
                workbench.production.id,
              );
              return (
                <button
                  type="button"
                  key={item.key}
                  aria-label={`预览设定候选 V${index + 1}`}
                  onClick={() => onSelectPreview(item.key)}
                  className={cn(
                    "relative h-12 min-w-24 overflow-hidden rounded-lg border bg-gradient-to-br from-[#574d47] to-[#b68b73] text-left text-white",
                    item.key === selectedPreview?.key
                      ? "border-[#e25f45] ring-2 ring-[#e25f45]/15"
                      : "border-[#3f352b]/15",
                  )}
                  style={
                    versionRef
                      ? {
                          backgroundImage: `linear-gradient(0deg,rgba(0,0,0,.25),rgba(0,0,0,0)),url(${JSON.stringify(versionRef)})`,
                          backgroundPosition: "center",
                          backgroundSize: "cover",
                        }
                      : undefined
                  }
                >
                  <span className="absolute right-1.5 bottom-1 text-[9px] font-semibold">
                    V{index + 1}
                  </span>
                </button>
              );
            })
          )}
          <button
            type="button"
            onClick={() =>
              onQuickAction(
                workbenchQuickAction(
                  `为${targetLabel}生成一个新候选`,
                  `为${targetLabel}新增一个设定候选版本。保留现有版本，不要覆盖；生成完成后把图片和标准执行回执写回同一视频账本。`,
                ),
              )
            }
            className="flex h-12 min-w-32 items-center justify-center rounded-lg border border-dashed border-[#3f352b]/20 bg-white/35 text-[10px] text-[#645b51]"
          >
            + 新候选
          </button>
        </div>
      </section>

      <section className="mt-auto shrink-0 px-1 pb-1">
        <div className="px-1 pb-2 text-[10px]">
          <span className="font-semibold text-[#d9573e]">
            当前目标 · {targetLabel}
          </span>
        </div>
        <WorkbenchAgentCommand
          workbench={workbench}
          target="setup"
          assetId={selectedAsset?.id}
          assetType={selectedAsset?.entity_type}
          artifactRef={selectedArtifact?.ref}
          command={command}
          onCommandChange={onCommandChange}
          quickAction={quickAction}
          onQuickActionConsumed={onQuickActionConsumed}
          placeholder="告诉智能体怎样生成或修改当前设定；例如：脸型不变，服装换成黑色风衣，再给我三版……"
        />
      </section>
    </div>
  );
}

function TasksTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  if (workbench.tasks.length === 0)
    return <EmptyPanel>还没有 provider 任务回执。</EmptyPanel>;
  return (
    <div className="space-y-3">
      {workbench.tasks.map((task) => (
        <TaskCard key={task.id} task={task} />
      ))}
    </div>
  );
}

function CandidatesTab({
  workbench,
  reviewPending,
  onDecision,
}: {
  workbench: PersonalIPVideoWorkbench;
  reviewPending: boolean;
  onDecision: (
    confirmation: VideoWorkbenchConfirmation,
    decision: "approved" | "rejected",
  ) => void;
}) {
  const paidConfirmations = workbench.confirmations.filter(
    (item) => item.kind === "paid_provider_call",
  );
  return (
    <div className="space-y-4">
      {paidConfirmations.map((confirmation) => (
        <ConfirmationCard
          key={confirmation.id}
          confirmation={confirmation}
          pending={reviewPending}
          onDecision={(decision) => onDecision(confirmation, decision)}
        />
      ))}
      {workbench.candidates.length === 0 ? (
        <EmptyPanel>逐镜生成完成后，候选片段会在这里并排比较。</EmptyPanel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {workbench.candidates.map((candidate) => {
            const confirmation = workbench.confirmations.find(
              (item) =>
                item.kind === "candidate_selection" &&
                item.entity_id === candidate.id,
            );
            const checks = candidate.consistency?.checks;
            const checkEntries =
              checks && typeof checks === "object"
                ? Object.entries(checks)
                : [];
            const qualityEntries = candidate.quality
              ? Object.entries(candidate.quality).filter(
                  ([, value]) =>
                    typeof value === "boolean" || typeof value === "number",
                )
              : [];
            return (
              <Card
                key={candidate.id}
                className={cn(
                  "gap-4",
                  candidate.selected && "border-emerald-500/40",
                )}
              >
                <CardHeader>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <CardTitle
                        className="truncate text-sm"
                        title={candidate.id}
                      >
                        {candidate.id}
                      </CardTitle>
                      <p className="text-muted-foreground mt-1 text-xs">
                        镜头 {candidate.shot_id ?? "未关联"}
                      </p>
                    </div>
                    {candidate.selected ? (
                      <Badge className="bg-emerald-600">
                        <CheckCircle2Icon /> 已选片
                      </Badge>
                    ) : (
                      <Badge variant="outline">候选</Badge>
                    )}
                  </div>
                  {qualityEntries.length > 0 && (
                    <div>
                      <p className="text-muted-foreground mb-2 text-[11px] font-medium uppercase">
                        自动 QA
                      </p>
                      <div className="grid grid-cols-2 gap-2">
                        {qualityEntries.map(([key, value]) => (
                          <EvidenceField
                            key={key}
                            label={key}
                            value={
                              typeof value === "boolean"
                                ? value
                                  ? "PASS"
                                  : "FAIL"
                                : String(value)
                            }
                          />
                        ))}
                      </div>
                    </div>
                  )}
                </CardHeader>
                <CardContent className="space-y-4">
                  <ArtifactList artifacts={candidate.artifacts} compact />
                  <div>
                    <p className="text-muted-foreground mb-2 text-[11px] font-medium uppercase">
                      一致性
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {checkEntries.length === 0 ? (
                        <Badge variant="secondary">未检查</Badge>
                      ) : (
                        checkEntries.map(([key, raw]) => {
                          const passed =
                            typeof raw === "boolean"
                              ? raw
                              : Boolean((raw as { passed?: boolean })?.passed);
                          return (
                            <Badge
                              key={key}
                              variant={passed ? "outline" : "destructive"}
                            >
                              {passed ? <CheckCircle2Icon /> : <XCircleIcon />}{" "}
                              {key}
                            </Badge>
                          );
                        })
                      )}
                    </div>
                  </div>
                  {confirmation && (
                    <ConfirmationCard
                      confirmation={confirmation}
                      pending={reviewPending}
                      onDecision={(decision) =>
                        onDecision(confirmation, decision)
                      }
                    />
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

type WorkbenchConversationRuntime = Pick<
  ReturnType<typeof useThreadStream>,
  "thread" | "sendMessage"
> & {
  threadId: string;
  imageModel: string;
  videoModel: string;
  imageModels: Array<{ id: string; display_name: string }>;
  videoModels: Array<{ id: string; display_name: string }>;
  setImageModel: (model: string) => void;
  setVideoModel: (model: string) => void;
};

const WorkbenchConversationContext =
  createContext<WorkbenchConversationRuntime | null>(null);
const AUTO_MEDIA_MODEL = "auto";

function WorkbenchConversationProvider({
  workbench,
  taskThreadId,
  children,
}: {
  workbench: PersonalIPVideoWorkbench;
  taskThreadId?: string;
  children: React.ReactNode;
}) {
  const queryClient = useQueryClient();
  const [localSettings] = useLocalSettings();
  const [threadId, setThreadId] = useState(taskThreadId ?? "");
  const [isNewThread, setIsNewThread] = useState(!taskThreadId);
  const [imageModel, setImageModel] = useState(AUTO_MEDIA_MODEL);
  const [videoModel, setVideoModel] = useState(AUTO_MEDIA_MODEL);
  const modelCatalog = usePersonalIPMediaModelCatalog();
  const bindThread = useBindVideoProductionThread(workbench.production.id);
  const bindAttempted = useRef(new Set<string>());
  const storageKey = `ip-agent:video-workbench-thread:${workbench.production.id}`;
  const modelStorageKey = `ip-agent:video-workbench-models:${workbench.production.id}`;

  useEffect(() => {
    if (taskThreadId) {
      setThreadId(taskThreadId);
      setIsNewThread(false);
      return;
    }
    const restored = window.localStorage.getItem(storageKey);
    if (restored) {
      setThreadId(restored);
      setIsNewThread(false);
      return;
    }
    setThreadId(crypto.randomUUID());
    setIsNewThread(true);
  }, [storageKey, taskThreadId]);

  useEffect(() => {
    if (
      !threadId ||
      workbench.production.thread_id === threadId ||
      bindAttempted.current.has(threadId)
    ) {
      return;
    }
    bindAttempted.current.add(threadId);
    bindThread.mutate(threadId);
  }, [bindThread, threadId, workbench.production.thread_id]);

  useEffect(() => {
    const restored = window.localStorage.getItem(modelStorageKey);
    if (!restored) return;
    try {
      const parsed = JSON.parse(restored) as {
        imageModel?: string;
        videoModel?: string;
      };
      setImageModel(parsed.imageModel ?? AUTO_MEDIA_MODEL);
      setVideoModel(parsed.videoModel ?? AUTO_MEDIA_MODEL);
    } catch {
      setImageModel(AUTO_MEDIA_MODEL);
      setVideoModel(AUTO_MEDIA_MODEL);
    }
  }, [modelStorageKey]);

  useEffect(() => {
    window.localStorage.setItem(
      modelStorageKey,
      JSON.stringify({ imageModel, videoModel }),
    );
  }, [imageModel, modelStorageKey, videoModel]);

  useEffect(() => {
    if (!modelCatalog.data) return;
    if (
      imageModel !== AUTO_MEDIA_MODEL &&
      !modelCatalog.data.image_models.some((model) => model.id === imageModel)
    ) {
      setImageModel(AUTO_MEDIA_MODEL);
    }
    if (
      videoModel !== AUTO_MEDIA_MODEL &&
      !modelCatalog.data.video_models.some((model) => model.id === videoModel)
    ) {
      setVideoModel(AUTO_MEDIA_MODEL);
    }
  }, [imageModel, modelCatalog.data, videoModel]);

  const { thread, sendMessage } = useThreadStream({
    threadId: isNewThread ? undefined : threadId || undefined,
    displayThreadId: threadId || undefined,
    assistantId: "ip-agent",
    context: { ...localSettings.context, agent_name: "ip-agent" },
    onStart: (createdThreadId) => {
      setThreadId(createdThreadId);
      setIsNewThread(false);
      window.localStorage.setItem(storageKey, createdThreadId);
    },
    onFinish: () => {
      void queryClient.invalidateQueries({
        queryKey: PERSONAL_IP_VIDEO_PRODUCTIONS_QUERY_KEY,
      });
    },
  });

  return (
    <WorkbenchConversationContext.Provider
      value={{
        threadId,
        thread,
        sendMessage,
        imageModel,
        videoModel,
        imageModels: modelCatalog.data?.image_models ?? [],
        videoModels: modelCatalog.data?.video_models ?? [],
        setImageModel,
        setVideoModel,
      }}
    >
      {children}
    </WorkbenchConversationContext.Provider>
  );
}

function WorkbenchConversationBoundary({
  workbench,
  taskThreadId,
  children,
}: {
  workbench?: PersonalIPVideoWorkbench;
  taskThreadId?: string;
  children: React.ReactNode;
}) {
  if (!workbench) return <>{children}</>;
  return (
    <WorkbenchConversationProvider
      key={workbench.production.id}
      workbench={workbench}
      taskThreadId={taskThreadId}
    >
      {children}
    </WorkbenchConversationProvider>
  );
}

function WorkbenchAgentCommand({
  workbench,
  shotId,
  candidateId,
  assetId,
  assetType,
  artifactRef,
  target = shotId ? "shot" : "timeline",
  command,
  onCommandChange,
  quickAction,
  onQuickActionConsumed,
  placeholder,
}: {
  workbench: PersonalIPVideoWorkbench;
  shotId?: string | null;
  candidateId?: string | null;
  assetId?: string | null;
  assetType?: string | null;
  artifactRef?: string | null;
  target?: "setup" | "shot" | "timeline";
  command: string;
  onCommandChange: (value: string) => void;
  quickAction?: WorkbenchQuickAction | null;
  onQuickActionConsumed?: (id: string) => void;
  placeholder: string;
}) {
  const conversation = useContext(WorkbenchConversationContext);
  if (!conversation) {
    throw new Error("Video workbench conversation is unavailable");
  }
  const {
    threadId,
    thread,
    sendMessage,
    imageModel,
    videoModel,
    imageModels,
    videoModels,
    setImageModel,
    setVideoModel,
  } = conversation;
  const submittedQuickActions = useRef(new Set<string>());
  const imageModelName =
    imageModel === AUTO_MEDIA_MODEL
      ? "自动"
      : (imageModels.find((model) => model.id === imageModel)?.display_name ??
        "已选择");
  const videoModelName =
    videoModel === AUTO_MEDIA_MODEL
      ? "自动"
      : (videoModels.find((model) => model.id === videoModel)?.display_name ??
        "已选择");
  const selectedModelCount = [imageModel, videoModel].filter(
    (model) => model !== AUTO_MEDIA_MODEL,
  ).length;
  const modelSummary =
    selectedModelCount === 0
      ? "自动"
      : selectedModelCount === 1
        ? imageModel !== AUTO_MEDIA_MODEL
          ? imageModelName
          : videoModelName
        : "2 项已指定";

  const visibleMessages = thread.messages
    .filter(
      (message) =>
        message.type !== "tool" &&
        (message.additional_kwargs as { hide_from_ui?: boolean } | undefined)
          ?.hide_from_ui !== true &&
        Boolean(textOfMessage(message)?.trim()),
    )
    .slice(-4);

  const submitText = useCallback(
    async (
      textValue: string,
      internalInstruction?: string,
      restoreOnFailure = false,
    ) => {
      const text = textValue.trim();
      if (!text || !threadId || thread.isLoading) return;
      const contextText = [
        "【视频工作台操作上下文】",
        `production_id=${workbench.production.id}`,
        `production_mode=${workbench.production_mode ?? "unknown"}`,
        `target=${target}`,
        `preferred_image_model=${imageModel}`,
        `preferred_video_model=${videoModel}`,
        "preferred_*_model=auto 时沿用当前默认模型；如果是具体模型 ID，相关生成必须向 image-generation 或 video-generation 脚本传入完全相同的 --model 参数。不得擅自改用其他生成模型；调用回执必须记录实际模型。",
        "不得在面向用户的回复里复述本上下文、技能名、工具函数名、内部合同名或执行提示词；只报告进度、结果和需要用户决定的事项。",
        shotId ? `shot_id=${shotId}` : null,
        candidateId ? `selected_candidate_id=${candidateId}` : null,
        assetType ? `asset_type=${assetType}` : null,
        assetId ? `asset_id=${assetId}` : null,
        artifactRef ? `selected_artifact_ref=${safeRef(artifactRef)}` : null,
        target === "setup"
          ? "这是设定资产工作面，不是会话权限边界。先读取现有不可变视频账本。用户没有参考图时，使用 image-generation Skill 和 Seedream 生成角色、场景或道具设定图；每次生成必须保留旧版本、产出 personal-ip-media-execution-v1 回执，并通过 personal_ip_ingest_media_execution 写回同一 production。只有用户明确采用后才更新资产合同，禁止用聊天文本假装图片已经入账。"
          : target === "shot"
            ? "这是本次操作目标，不是会话权限边界。先读取现有不可变视频账本；若重生图片或视频，必须创建新候选版本，禁止覆盖旧候选。"
            : "先读取现有不可变视频账本；把自然语言编辑编译为 personal_ip_compile_video_timeline_revision，同用户手动编辑共用一份完整时间线快照，禁止另建状态。",
        internalInstruction
          ? `【仅供智能体执行的动作要求】\n${internalInstruction}`
          : null,
      ]
        .filter(Boolean)
        .join("\n");
      const hiddenContext: Message = {
        type: "human",
        content: [{ type: "text", text: contextText }],
        additional_kwargs: {
          hide_from_ui: true,
          video_workbench_context: true,
        },
      } as Message;
      onCommandChange("");
      try {
        await sendMessage(
          threadId,
          { text, files: [] },
          {
            agent_name: "ip-agent",
            video_production_id: workbench.production.id,
            video_shot_id: shotId ?? undefined,
            video_candidate_id: candidateId ?? undefined,
          },
          {
            additionalInputMessages: [hiddenContext],
            additionalKwargs: {
              video_workbench_visible_message: true,
              video_production_id: workbench.production.id,
              video_shot_id: shotId ?? null,
              video_candidate_id: candidateId ?? null,
            },
          },
        );
      } catch {
        if (restoreOnFailure) onCommandChange(text);
        toast.error("操作没有发送成功，请稍后重试");
      }
    },
    [
      candidateId,
      artifactRef,
      assetId,
      assetType,
      imageModel,
      onCommandChange,
      sendMessage,
      shotId,
      target,
      thread.isLoading,
      threadId,
      videoModel,
      workbench.production.id,
      workbench.production_mode,
    ],
  );

  const submit = useCallback(async () => {
    const text = command.trim();
    if (!text) return;
    await submitText(text, undefined, true);
  }, [command, submitText]);

  useEffect(() => {
    if (
      !quickAction ||
      !threadId ||
      thread.isLoading ||
      submittedQuickActions.current.has(quickAction.id)
    ) {
      return;
    }
    submittedQuickActions.current.add(quickAction.id);
    onQuickActionConsumed?.(quickAction.id);
    void submitText(
      quickAction.userText,
      quickAction.internalInstruction,
      false,
    );
  }, [
    onQuickActionConsumed,
    quickAction,
    submitText,
    thread.isLoading,
    threadId,
  ]);

  return (
    <div className="space-y-2">
      {visibleMessages.length > 0 && (
        <div className="max-h-32 space-y-1.5 overflow-y-auto rounded-lg border border-[#3f352b]/8 bg-white/45 p-2">
          {visibleMessages.map((message, index) => (
            <div
              key={message.id ?? `${message.type}:${index}`}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-[10px] leading-4",
                message.type === "human"
                  ? "ml-8 bg-[#efe3d8] text-[#5f4b41]"
                  : "mr-8 bg-[#e5ece7] text-[#40584b]",
              )}
            >
              {message.type === "ai"
                ? visibleAssistantContent(textOfMessage(message) ?? "", "zh-CN")
                : textOfMessage(message)}
            </div>
          ))}
        </div>
      )}
      <div className="rounded-[22px] border border-[#3f352b]/12 bg-white px-4 pt-3 pb-2.5 shadow-[0_8px_24px_-22px_rgba(45,30,20,0.7)]">
        <textarea
          value={command}
          onChange={(event) => onCommandChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          rows={1}
          aria-label={placeholder}
          placeholder={placeholder}
          className="field-sizing-content max-h-40 min-h-16 w-full resize-none overflow-y-auto bg-transparent text-sm leading-6 outline-none placeholder:text-[#aaa39a]"
        />
        <div className="mt-1.5 flex items-center justify-between gap-3">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={`选择生成模型。图像：${imageModelName}；视频：${videoModelName}`}
                className="inline-flex h-8 max-w-60 items-center gap-1.5 rounded-lg px-2 text-xs text-[#6f685f] transition-colors hover:bg-[#3f352b]/5 hover:text-[#302c27] focus-visible:ring-2 focus-visible:ring-[#5d806e]/25 focus-visible:outline-none"
              >
                <SparklesIcon className="size-3.5 text-[#8a796d]" />
                <span className="font-medium">模型</span>
                <span className="truncate text-[#938b81]">{modelSummary}</span>
                <ChevronRightIcon className="size-3 rotate-90 opacity-40" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              side="top"
              align="start"
              sideOffset={8}
              className="w-64 rounded-xl border-[#3f352b]/10 bg-[#fffdf8] p-1.5 shadow-xl"
            >
              <DropdownMenuSub>
                <DropdownMenuSubTrigger className="rounded-lg px-2.5 py-2 text-xs">
                  <ImageIcon className="size-3.5" />
                  <span>图像模型</span>
                  <span className="ml-auto max-w-28 truncate text-[10px] font-normal text-[#8a8177]">
                    {imageModelName}
                  </span>
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="max-h-80 w-64 overflow-y-auto rounded-xl border-[#3f352b]/10 bg-[#fffdf8] p-1.5 shadow-xl">
                  <DropdownMenuRadioGroup
                    value={imageModel}
                    onValueChange={setImageModel}
                  >
                    <DropdownMenuRadioItem
                      value={AUTO_MEDIA_MODEL}
                      className="rounded-lg py-2 text-xs"
                    >
                      自动选择
                    </DropdownMenuRadioItem>
                    {imageModels.map((model) => (
                      <DropdownMenuRadioItem
                        key={model.id}
                        value={model.id}
                        className="rounded-lg py-2 text-xs"
                      >
                        {model.display_name}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger className="rounded-lg px-2.5 py-2 text-xs">
                  <FilmIcon className="size-3.5" />
                  <span>视频模型</span>
                  <span className="ml-auto max-w-28 truncate text-[10px] font-normal text-[#8a8177]">
                    {videoModelName}
                  </span>
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent className="max-h-80 w-64 overflow-y-auto rounded-xl border-[#3f352b]/10 bg-[#fffdf8] p-1.5 shadow-xl">
                  <DropdownMenuRadioGroup
                    value={videoModel}
                    onValueChange={setVideoModel}
                  >
                    <DropdownMenuRadioItem
                      value={AUTO_MEDIA_MODEL}
                      className="rounded-lg py-2 text-xs"
                    >
                      自动选择
                    </DropdownMenuRadioItem>
                    {videoModels.map((model) => (
                      <DropdownMenuRadioItem
                        key={model.id}
                        value={model.id}
                        className="rounded-lg py-2 text-xs"
                      >
                        {model.display_name}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            type="button"
            size="icon"
            disabled={!command.trim() || !threadId || thread.isLoading}
            onClick={() => void submit()}
            className="size-9 shrink-0 rounded-full bg-[#24211d] text-white hover:bg-[#0e0d0b] disabled:bg-[#d9d3ca] disabled:text-white"
            aria-label="发送给视频智能体"
          >
            {thread.isLoading ? (
              <LoaderCircleIcon className="animate-spin" />
            ) : (
              <SendIcon />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

type EditableTimelineClip = Omit<
  VideoTimelineClip,
  "id" | "start_sec" | "duration_sec" | "source_in_sec"
> & {
  id: string;
  start_sec: number;
  duration_sec: number;
  source_in_sec: number;
};

type EditableTimelineTrack = {
  id: string;
  type: "video" | "dialogue" | "music" | "subtitle";
  clips: EditableTimelineClip[];
};

const TIMELINE_TRACK_ORDER: EditableTimelineTrack["type"][] = [
  "video",
  "dialogue",
  "music",
  "subtitle",
];

function normalizedTrackType(
  track: VideoTimelineTrack,
): EditableTimelineTrack["type"] {
  if (track.type === "audio") {
    return /music|bgm/i.test(track.id ?? "") ? "music" : "dialogue";
  }
  return track.type;
}

function reflowTimelineClips(clips: EditableTimelineClip[]) {
  let elapsed = 0;
  return clips.map((clip) => {
    const next = { ...clip, start_sec: Number(elapsed.toFixed(3)) };
    elapsed += clip.duration_sec;
    return next;
  });
}

function buildEditableTimeline(
  workbench: PersonalIPVideoWorkbench,
): EditableTimelineTrack[] {
  const byType = new Map<
    EditableTimelineTrack["type"],
    EditableTimelineClip[]
  >();
  for (const track of workbench.timeline.tracks) {
    const type = normalizedTrackType(track);
    const existing = byType.get(type) ?? [];
    existing.push(
      ...track.clips.map((clip, index) => ({
        ...clip,
        id: clip.id ?? `${type}:${clip.shot_id ?? index + 1}`,
        start_sec: clip.start_sec ?? 0,
        duration_sec: Math.max(clip.duration_sec ?? 1, 0.1),
        source_in_sec: clip.source_in_sec ?? 0,
        volume: clip.volume ?? 1,
        transition: clip.transition ?? "none",
      })),
    );
    byType.set(type, existing);
  }
  if ((byType.get("video")?.length ?? 0) === 0) {
    byType.set(
      "video",
      reflowTimelineClips(
        workbench.shots.map((shot, index) => ({
          id: `video:${shot.id}`,
          shot_id: shot.id,
          start_sec: index,
          duration_sec: Math.max(shot.spec.duration_seconds ?? 1, 0.1),
          source_in_sec: 0,
          selected_candidate_id: shot.selected_candidate_id,
          volume: 1,
          transition: "none",
        })),
      ),
    );
  }
  if ((byType.get("dialogue")?.length ?? 0) === 0) {
    byType.set(
      "dialogue",
      reflowTimelineClips(
        workbench.shots.flatMap((shot) => {
          const text = shot.spec.dialogue ?? shot.spec.narration_text;
          return text
            ? [
                {
                  id: `dialogue:${shot.id}`,
                  shot_id: shot.id,
                  start_sec: 0,
                  duration_sec: Math.max(shot.spec.duration_seconds ?? 1, 0.1),
                  source_in_sec: 0,
                  text,
                  volume: 1,
                  transition: "none",
                },
              ]
            : [];
        }),
      ),
    );
  }
  if ((byType.get("subtitle")?.length ?? 0) === 0) {
    byType.set(
      "subtitle",
      reflowTimelineClips(
        workbench.shots.map((shot) => ({
          id: `subtitle:${shot.id}`,
          shot_id: shot.id,
          start_sec: 0,
          duration_sec: Math.max(shot.spec.duration_seconds ?? 1, 0.1),
          source_in_sec: 0,
          text:
            shot.spec.narration_text ??
            shot.spec.dialogue ??
            shot.spec.title ??
            shot.id,
          volume: 1,
          transition: "none",
        })),
      ),
    );
  }
  return TIMELINE_TRACK_ORDER.map((type) => ({
    id: type,
    type,
    clips: (byType.get(type) ?? []).sort(
      (left, right) => left.start_sec - right.start_sec,
    ),
  }));
}

function timelineTrackPayload(track: EditableTimelineTrack) {
  return {
    id: track.id,
    type: track.type,
    clips: track.clips.map((clip) => ({
      id: clip.id,
      shot_id: clip.shot_id ?? null,
      start_sec: clip.start_sec,
      duration_sec: clip.duration_sec,
      source_in_sec: clip.source_in_sec,
      source_ref: clip.source_ref ?? clip.artifact?.ref ?? null,
      source_sha256: clip.source_sha256 ?? clip.artifact?.sha256 ?? null,
      selected_candidate_id: clip.selected_candidate_id ?? null,
      text: clip.text ?? null,
      volume: clip.volume ?? 1,
      transition: clip.transition ?? "none",
    })),
  };
}

const TIMELINE_OPERATION_LABELS: Record<string, string> = {
  move: "移动",
  trim: "裁切",
  split: "分割",
  duplicate: "复制",
  delete: "删除",
  replace_candidate: "替换候选",
  change_volume: "调整音量",
  edit_caption: "修改字幕或对白",
  add_transition: "调整转场",
  restore_revision: "恢复历史版本",
};

function describeTimelineOperations(
  operations: Array<Record<string, unknown>>,
) {
  const labels = [
    ...new Set(
      operations.map((operation) => {
        const type =
          typeof operation.type === "string" ? operation.type : "unknown";
        return TIMELINE_OPERATION_LABELS[type] ?? "其他调整";
      }),
    ),
  ];
  return `用户在视频工作台完成 ${operations.length} 项手动修改：${labels.join("、")}`;
}

function TimelineEditor({
  workbench,
  compact = false,
  onOpen,
  agentCommand,
  onAgentCommandChange,
  quickAction,
  onQuickAction,
  onQuickActionConsumed,
}: {
  workbench: PersonalIPVideoWorkbench;
  compact?: boolean;
  onOpen?: () => void;
  agentCommand: string;
  onAgentCommandChange: (value: string) => void;
  quickAction: WorkbenchQuickAction | null;
  onQuickAction: (action: WorkbenchQuickAction) => void;
  onQuickActionConsumed: (id: string) => void;
}) {
  const saveRevision = useSaveVideoTimelineRevision(workbench.production.id);
  const lockFinalEdit = useLockVideoFinalEdit(workbench.production.id);
  const [tracks, setTracks] = useState<EditableTimelineTrack[]>(() =>
    buildEditableTimeline(workbench),
  );
  const [selected, setSelected] = useState<{
    trackId: string;
    clipId: string;
  } | null>(null);
  const [operations, setOperations] = useState<Array<Record<string, unknown>>>(
    [],
  );
  const [dragged, setDragged] = useState<{
    trackId: string;
    clipId: string;
  } | null>(null);

  useEffect(() => {
    setTracks(buildEditableTimeline(workbench));
    setOperations([]);
    setSelected(null);
  }, [workbench]);

  const recordOperation = useCallback((operation: Record<string, unknown>) => {
    setOperations((current) => [
      ...current,
      { id: `edit-${crypto.randomUUID()}`, ...operation },
    ]);
  }, []);

  const updateSelectedClip = useCallback(
    (
      updater: (clip: EditableTimelineClip) => EditableTimelineClip | null,
      operation: Record<string, unknown>,
      options?: { reflow?: boolean },
    ) => {
      if (!selected) return;
      setTracks((current) =>
        current.map((track) => {
          if (track.id !== selected.trackId) return track;
          const next = track.clips.flatMap((clip) => {
            if (clip.id !== selected.clipId) return [clip];
            const updated = updater(clip);
            return updated ? [updated] : [];
          });
          return {
            ...track,
            clips: options?.reflow ? reflowTimelineClips(next) : next,
          };
        }),
      );
      recordOperation({ clip_id: selected.clipId, ...operation });
    },
    [recordOperation, selected],
  );

  const moveSelected = useCallback(
    (direction: -1 | 1) => {
      if (!selected) return;
      const track = tracks.find((item) => item.id === selected.trackId);
      if (!track) return;
      const index = track.clips.findIndex(
        (clip) => clip.id === selected.clipId,
      );
      const target = index + direction;
      if (index < 0 || target < 0 || target >= track.clips.length) return;
      const clips = [...track.clips];
      const [clip] = clips.splice(index, 1);
      clips.splice(target, 0, clip!);
      const reflowed = reflowTimelineClips(clips);
      const moved = reflowed.find((item) => item.id === selected.clipId);
      setTracks((current) =>
        current.map((item) =>
          item.id === selected.trackId ? { ...item, clips: reflowed } : item,
        ),
      );
      recordOperation({
        type: "move",
        clip_id: selected.clipId,
        track_id: selected.trackId,
        start_sec: moved?.start_sec ?? 0,
      });
    },
    [recordOperation, selected, tracks],
  );

  const splitSelected = useCallback(() => {
    if (!selected) return;
    const track = tracks.find((item) => item.id === selected.trackId);
    const selectedClip = track?.clips.find(
      (clip) => clip.id === selected.clipId,
    );
    if (!track || !selectedClip || selectedClip.duration_sec < 0.4) return;
    const splitAt = Number((selectedClip.duration_sec / 2).toFixed(3));
    const newClipId = `${selectedClip.id}:split:${crypto.randomUUID().slice(0, 8)}`;
    setTracks((current) =>
      current.map((item) => {
        if (item.id !== selected.trackId) return item;
        const next = item.clips.flatMap((clip) => {
          if (clip.id !== selected.clipId) {
            return [clip];
          }
          return [
            { ...clip, duration_sec: splitAt },
            {
              ...clip,
              id: newClipId,
              source_in_sec: clip.source_in_sec + splitAt,
              duration_sec: Number((clip.duration_sec - splitAt).toFixed(3)),
            },
          ];
        });
        return { ...item, clips: reflowTimelineClips(next) };
      }),
    );
    recordOperation({
      type: "split",
      clip_id: selected.clipId,
      new_clip_id: newClipId,
      at_sec: splitAt,
    });
  }, [recordOperation, selected, tracks]);

  const duplicateSelected = useCallback(() => {
    if (!selected) return;
    const newClipId = `${selected.clipId}:copy:${crypto.randomUUID().slice(0, 8)}`;
    setTracks((current) =>
      current.map((track) => {
        if (track.id !== selected.trackId) return track;
        const next = track.clips.flatMap((clip) =>
          clip.id === selected.clipId
            ? [clip, { ...clip, id: newClipId }]
            : [clip],
        );
        return { ...track, clips: reflowTimelineClips(next) };
      }),
    );
    recordOperation({
      type: "duplicate",
      clip_id: selected.clipId,
      new_clip_id: newClipId,
    });
  }, [recordOperation, selected]);

  const dropClip = useCallback(
    (targetTrackId: string, targetClipId: string) => {
      if (dragged?.trackId !== targetTrackId) return;
      const track = tracks.find((item) => item.id === targetTrackId);
      if (!track) return;
      const from = track.clips.findIndex((clip) => clip.id === dragged.clipId);
      const to = track.clips.findIndex((clip) => clip.id === targetClipId);
      if (from < 0 || to < 0 || from === to) return;
      const clips = [...track.clips];
      const [clip] = clips.splice(from, 1);
      clips.splice(to, 0, clip!);
      const reflowed = reflowTimelineClips(clips);
      const moved = reflowed.find((item) => item.id === dragged.clipId);
      setTracks((current) =>
        current.map((item) =>
          item.id === targetTrackId ? { ...item, clips: reflowed } : item,
        ),
      );
      recordOperation({
        type: "move",
        clip_id: dragged.clipId,
        track_id: targetTrackId,
        start_sec: moved?.start_sec ?? 0,
      });
      setSelected({ trackId: targetTrackId, clipId: dragged.clipId });
      setDragged(null);
    },
    [dragged, recordOperation, tracks],
  );

  const selectedClip = selected
    ? tracks
        .find((track) => track.id === selected.trackId)
        ?.clips.find((clip) => clip.id === selected.clipId)
    : null;
  const selectedTrack = selected
    ? tracks.find((track) => track.id === selected.trackId)
    : null;
  const selectedClipCandidates = selectedClip?.shot_id
    ? workbench.candidates.filter(
        (candidate) => candidate.shot_id === selectedClip.shot_id,
      )
    : [];
  const timelineDuration = Math.max(
    workbench.timeline.duration_sec ?? 0,
    ...tracks.flatMap((track) =>
      track.clips.map((clip) => clip.start_sec + clip.duration_sec),
    ),
    1,
  );
  const rulerMarks = Array.from({ length: 6 }, (_, index) => {
    const seconds = (timelineDuration / 5) * index;
    const minutes = Math.floor(seconds / 60);
    const remaining = Math.floor(seconds % 60);
    return `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
  });
  const beginTrimDrag = useCallback(
    (
      event: React.PointerEvent<HTMLElement>,
      trackId: string,
      clipId: string,
      edge: "start" | "end",
    ) => {
      event.preventDefault();
      event.stopPropagation();
      const track = tracks.find((item) => item.id === trackId);
      const clip = track?.clips.find((item) => item.id === clipId);
      if (!track || !clip) return;

      const lane = event.currentTarget.closest("[data-timeline-lane]");
      const laneWidth =
        lane instanceof HTMLElement ? Math.max(lane.clientWidth, 1) : 1;
      const pointerStart = event.clientX;
      const initialSourceIn = clip.source_in_sec;
      const initialDuration = clip.duration_sec;
      let finalSourceIn = initialSourceIn;
      let finalDuration = initialDuration;

      const move = (pointerEvent: PointerEvent) => {
        const deltaSeconds =
          ((pointerEvent.clientX - pointerStart) / laneWidth) *
          timelineDuration;
        if (edge === "start") {
          const boundedDelta = Math.min(
            Math.max(deltaSeconds, -initialSourceIn),
            initialDuration - 0.1,
          );
          finalSourceIn = Number((initialSourceIn + boundedDelta).toFixed(3));
          finalDuration = Number((initialDuration - boundedDelta).toFixed(3));
        } else {
          finalDuration = Math.max(
            Number((initialDuration + deltaSeconds).toFixed(3)),
            0.1,
          );
        }
        setTracks((current) =>
          current.map((item) => {
            if (item.id !== trackId) return item;
            const clips = item.clips.map((currentClip) =>
              currentClip.id === clipId
                ? {
                    ...currentClip,
                    source_in_sec: finalSourceIn,
                    duration_sec: finalDuration,
                  }
                : currentClip,
            );
            return { ...item, clips: reflowTimelineClips(clips) };
          }),
        );
      };
      const finish = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", finish);
        window.removeEventListener("pointercancel", finish);
        document.body.style.cursor = "";
        if (
          finalSourceIn !== initialSourceIn ||
          finalDuration !== initialDuration
        ) {
          recordOperation({
            type: "trim",
            clip_id: clipId,
            source_in_sec: finalSourceIn,
            duration_sec: finalDuration,
          });
        }
      };

      setSelected({ trackId, clipId });
      document.body.style.cursor = "ew-resize";
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", finish);
      window.addEventListener("pointercancel", finish);
    },
    [recordOperation, timelineDuration, tracks],
  );
  const previousRevision =
    workbench.timeline.revisions.length > 1
      ? workbench.timeline.revisions.at(-2)
      : null;

  const restoreRevision = useCallback(
    (revision: PersonalIPVideoWorkbench["timeline"]["revisions"][number]) => {
      if (!revision.revision_id) return;
      const rawWorkbench = {
        ...workbench,
        timeline: {
          ...workbench.timeline,
          tracks: revision.tracks as VideoTimelineTrack[],
        },
      };
      setTracks(buildEditableTimeline(rawWorkbench));
      setOperations([
        {
          id: `edit-${crypto.randomUUID()}`,
          type: "restore_revision",
          revision_id: revision.revision_id,
          clip_id: null,
        },
      ]);
    },
    [workbench],
  );

  const restorePrevious = useCallback(() => {
    if (!previousRevision) return;
    restoreRevision(previousRevision);
  }, [previousRevision, restoreRevision]);

  const save = useCallback(async () => {
    if (operations.length === 0) {
      toast.message("还没有需要保存的剪辑修改");
      return;
    }
    const revisionId = `timeline-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
    try {
      await saveRevision.mutateAsync({
        revision_id: revisionId,
        base_revision_id: workbench.timeline.revision_id ?? null,
        author_kind: "human",
        intent: describeTimelineOperations(operations),
        fps: workbench.timeline.fps ?? 24,
        tracks: tracks.map(timelineTrackPayload),
        operations,
        strategy_confirmed: true,
      });
      toast.success("剪辑修改已保存");
      setOperations([]);
    } catch {
      toast.error("时间线暂时无法保存，请重试");
    }
  }, [
    operations,
    saveRevision,
    tracks,
    workbench.timeline.fps,
    workbench.timeline.revision_id,
  ]);

  const lockEdit = useCallback(async () => {
    if (!workbench.timeline.revision_id) {
      toast.message("请先保存当前剪辑");
      return;
    }
    if (operations.length > 0) {
      toast.message("当前还有未保存修改，请先保存");
      return;
    }
    const lockId = `final-edit-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
    try {
      await lockFinalEdit.mutateAsync({
        lockId,
        note: `锁定时间线修订 ${workbench.timeline.revision_id}，进入最终渲染与交付 QA`,
      });
      toast.success("剪辑已完成，可以生成成片");
    } catch {
      toast.error("暂时无法完成剪辑，请重试");
    }
  }, [lockFinalEdit, operations.length, workbench.timeline.revision_id]);

  return (
    <div className={cn("space-y-3", compact && "space-y-2")}>
      {SHOW_INLINE_TIMELINE_TOOLBAR && !compact && (
        <div className="flex min-h-10 flex-wrap items-center gap-1.5 rounded-lg border border-[#3f352b]/10 bg-[#faf8f3] px-2 py-1.5">
          {selectedClip ? (
            <>
              <span className="mr-1 max-w-48 truncate px-1 text-[10px] font-semibold">
                {selectedClip.text ?? selectedClip.shot_id ?? selectedClip.id}
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[9px]"
                onClick={splitSelected}
              >
                <ScissorsIcon /> 分割
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[9px]"
                onClick={duplicateSelected}
              >
                <CopyIcon /> 复制
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  updateSelectedClip(
                    () => null,
                    { type: "delete" },
                    { reflow: true },
                  )
                }
                className="text-destructive h-7 px-2 text-[9px]"
              >
                <Trash2Icon /> 删除
              </Button>
              <Separator orientation="vertical" className="mx-1 h-5" />
              {selectedClipCandidates.length > 0 && (
                <select
                  aria-label="替换镜头候选"
                  value={selectedClip.selected_candidate_id ?? ""}
                  onChange={(event) => {
                    const candidate = selectedClipCandidates.find(
                      (item) => item.id === event.target.value,
                    );
                    if (!candidate) return;
                    const artifact =
                      candidate.artifacts.find((item) =>
                        item.mime_type?.startsWith("video/"),
                      ) ?? candidate.artifacts[0];
                    updateSelectedClip(
                      (clip) => ({
                        ...clip,
                        selected_candidate_id: candidate.id,
                        source_ref: artifact?.ref ?? clip.source_ref,
                        source_sha256: artifact?.sha256 ?? clip.source_sha256,
                        artifact: artifact ?? clip.artifact,
                      }),
                      {
                        type: "replace_candidate",
                        candidate_id: candidate.id,
                      },
                    );
                  }}
                  className="h-7 rounded-md border border-[#3f352b]/10 bg-white px-2 text-[9px]"
                >
                  <option value="">选择版本</option>
                  {selectedClipCandidates.map((candidate, index) => (
                    <option key={candidate.id} value={candidate.id}>
                      版本 {index + 1}
                    </option>
                  ))}
                </select>
              )}
              <select
                aria-label="片段转场"
                value={selectedClip.transition ?? "none"}
                onChange={(event) => {
                  const transition = event.target.value;
                  updateSelectedClip((clip) => ({ ...clip, transition }), {
                    type: "add_transition",
                    transition,
                  });
                }}
                className="h-7 rounded-md border border-[#3f352b]/10 bg-white px-2 text-[9px]"
              >
                <option value="none">无转场</option>
                <option value="hard_cut">硬切</option>
                <option value="crossfade">叠化</option>
                <option value="dip_to_black">淡黑</option>
              </select>
              <label className="ml-auto flex h-7 items-center gap-1.5 rounded-md px-2 text-[9px] text-[#79736a]">
                <Volume2Icon className="size-3" />
                <input
                  aria-label="片段音量"
                  type="range"
                  min="0"
                  max="4"
                  step="0.05"
                  value={selectedClip.volume ?? 1}
                  onChange={(event) => {
                    const volume = Number(event.target.value);
                    updateSelectedClip((clip) => ({ ...clip, volume }), {
                      type: "change_volume",
                      volume,
                    });
                  }}
                  className="w-20"
                />
              </label>
              {selectedClip.text != null && (
                <input
                  value={selectedClip.text}
                  onChange={(event) => {
                    const text = event.target.value;
                    if (!text.trim()) return;
                    updateSelectedClip((clip) => ({ ...clip, text }), {
                      type: "edit_caption",
                      text,
                    });
                  }}
                  aria-label="编辑字幕或对白"
                  className="h-7 min-w-44 flex-1 rounded-md border border-[#3f352b]/10 bg-white px-2 text-[9px] outline-none"
                />
              )}
            </>
          ) : (
            <span className="px-2 text-[9px] text-[#8d867c]">
              选择片段后可分割、复制、删除或更换版本；拖动片段边缘即可裁切。
            </span>
          )}
        </div>
      )}
      <div className="relative overflow-hidden rounded-xl border border-[#3f352b]/10 bg-[#ebe7df]">
        <div
          className={cn(
            "ml-[74px] grid grid-cols-6 items-center border-b border-[#3f352b]/8 bg-[#f7f4ee] px-3 text-[#8c857b]",
            compact ? "h-5 text-[7px]" : "h-8 text-[9px]",
          )}
        >
          {rulerMarks.map((time, index) => (
            <span key={`${time}-${index}`}>{time}</span>
          ))}
        </div>
        {tracks.map((track) => (
          <div
            key={track.id}
            className="grid grid-cols-[74px_1fr] items-stretch border-b border-[#3f352b]/8 last:border-b-0"
          >
            <div
              className={cn(
                "flex items-center gap-2 border-r border-[#3f352b]/8 bg-[#f7f4ee] px-2.5 text-[#645b51]",
                compact ? "text-[9px]" : "py-2.5 text-[11px]",
              )}
            >
              {track.type === "video" ? (
                <FilmIcon className="size-3" />
              ) : track.type === "dialogue" ? (
                <MessageSquareTextIcon className="size-3" />
              ) : track.type === "music" ? (
                <Music2Icon className="size-3" />
              ) : (
                <Layers3Icon className="size-3" />
              )}
              <span>
                {
                  {
                    video: "视频",
                    dialogue: "对白",
                    music: "音乐",
                    subtitle: "字幕",
                  }[track.type]
                }
                {!compact && (
                  <small className="mt-0.5 block text-[8px] text-[#9b9389]">
                    {track.clips.length} 段
                  </small>
                )}
              </span>
            </div>
            <div
              data-timeline-lane={track.id}
              className={cn(
                "flex gap-1 overflow-x-auto p-1",
                compact ? "min-h-8" : "min-h-14 items-stretch p-1.5",
              )}
            >
              {track.clips.length === 0 ? (
                <button
                  type="button"
                  onClick={() =>
                    onQuickAction(
                      {
                        video: workbenchQuickAction(
                          "补全画面轨",
                          "检查当前已选镜头候选并组装一版可编辑的视频粗剪轨道。",
                        ),
                        dialogue: workbenchQuickAction(
                          "补全对白和旁白轨",
                          "检查当前脚本并生成或整理对白/旁白音轨，使用实测音频时长对齐镜头。",
                        ),
                        music: workbenchQuickAction(
                          "补全配乐轨",
                          "为当前作品选择权利清晰的配乐，设计入点、出点、音量和对白避让并加入音乐轨。",
                        ),
                        subtitle: workbenchQuickAction(
                          "补全字幕轨",
                          "根据当前对白或旁白生成并校准字幕轨，使用最终输出时间线坐标。",
                        ),
                      }[track.type],
                    )
                  }
                  className="m-0.5 flex-1 rounded-lg border border-dashed border-[#3f352b]/12 bg-white/25 px-3 py-1 text-left text-[9px] text-[#928b82] transition hover:border-[#c95038]/25 hover:bg-white/65 hover:text-[#a45b48]"
                >
                  + 交给智能体补全
                  {track.type === "video"
                    ? "画面"
                    : track.type === "dialogue"
                      ? "对白/旁白"
                      : track.type === "music"
                        ? "配乐"
                        : "字幕"}
                  轨
                </button>
              ) : (
                track.clips.map((clip) => {
                  const active =
                    selected?.trackId === track.id &&
                    selected.clipId === clip.id;
                  return (
                    <div
                      key={clip.id}
                      role="button"
                      tabIndex={0}
                      aria-label={`时间线${
                        {
                          video: "视频",
                          dialogue: "对白",
                          music: "音乐",
                          subtitle: "字幕",
                        }[track.type]
                      }片段 ${friendlyShotName(workbench, clip.shot_id)}`}
                      draggable
                      onDragStart={() =>
                        setDragged({ trackId: track.id, clipId: clip.id })
                      }
                      onDragOver={(event) => event.preventDefault()}
                      onDrop={() => dropClip(track.id, clip.id)}
                      onClick={() =>
                        setSelected({ trackId: track.id, clipId: clip.id })
                      }
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelected({ trackId: track.id, clipId: clip.id });
                        }
                      }}
                      className={cn(
                        "group relative flex min-w-20 cursor-pointer items-center gap-1 truncate rounded-md border px-2 text-left shadow-sm transition",
                        compact ? "py-1 text-[8px]" : "py-2.5 text-[10px]",
                        track.type === "video" &&
                          "border-[#2e3f45] bg-[#354950] text-white",
                        track.type === "dialogue" &&
                          "border-[#afc4b4] bg-[#dce8df] text-[#466152]",
                        track.type === "music" &&
                          "border-[#b4c2d3] bg-[#dce4ee] text-[#4f6685]",
                        track.type === "subtitle" &&
                          "border-[#d4c09d] bg-[#eee5d4] text-[#74654f]",
                        active &&
                          "border-[#ef6b48] ring-2 ring-[#ef6b48]/35 ring-offset-1",
                      )}
                      style={{ flexGrow: Math.max(clip.duration_sec, 1) }}
                      title={`${friendlyShotName(workbench, clip.shot_id)} · ${clip.duration_sec}s`}
                    >
                      {!compact && (
                        <>
                          <span
                            role="separator"
                            aria-label={`裁切${
                              {
                                video: "视频",
                                dialogue: "对白",
                                music: "音乐",
                                subtitle: "字幕",
                              }[track.type]
                            }片段 ${friendlyShotName(workbench, clip.shot_id)}左边缘`}
                            draggable={false}
                            onPointerDown={(event) =>
                              beginTrimDrag(event, track.id, clip.id, "start")
                            }
                            className={cn(
                              "absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize rounded-l border-l-2 border-transparent transition hover:border-white/80",
                              active
                                ? "opacity-100"
                                : "opacity-0 group-hover:opacity-100",
                            )}
                          />
                          <span
                            role="separator"
                            aria-label={`裁切${
                              {
                                video: "视频",
                                dialogue: "对白",
                                music: "音乐",
                                subtitle: "字幕",
                              }[track.type]
                            }片段 ${friendlyShotName(workbench, clip.shot_id)}右边缘`}
                            draggable={false}
                            onPointerDown={(event) =>
                              beginTrimDrag(event, track.id, clip.id, "end")
                            }
                            className={cn(
                              "absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize rounded-r border-r-2 border-transparent transition hover:border-white/80",
                              active
                                ? "opacity-100"
                                : "opacity-0 group-hover:opacity-100",
                            )}
                          />
                        </>
                      )}
                      <GripVerticalIcon className="size-2.5 shrink-0 opacity-50" />
                      <span className="truncate">
                        {visibleTimelineClipText(workbench, clip)}
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        ))}
      </div>

      {selectedClip && compact && (
        <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-[#3f352b]/10 bg-white/55 p-2 text-[9px]">
          <span className="mr-1 max-w-40 truncate font-semibold">
            {visibleTimelineClipText(workbench, selectedClip)}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="h-6 px-2 text-[9px]"
            onClick={() => moveSelected(-1)}
          >
            ← 前移
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-6 px-2 text-[9px]"
            onClick={() => moveSelected(1)}
          >
            后移 →
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-6 px-2 text-[9px]"
            onClick={splitSelected}
          >
            <ScissorsIcon /> 分割
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              updateSelectedClip(
                () => null,
                { type: "delete" },
                { reflow: true },
              )
            }
            className="text-destructive ml-auto h-6 px-2 text-[9px]"
          >
            <Trash2Icon /> 删除
          </Button>
        </div>
      )}

      {!compact && selectedClip && (
        <section
          aria-label="片段检查器"
          className="hidden rounded-xl border border-[#3f352b]/10 bg-[#faf8f3] p-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2">
              <span className="rounded-md bg-[#24211d] px-2 py-1 text-[9px] text-white">
                {
                  {
                    video: "视频",
                    dialogue: "对白",
                    music: "音乐",
                    subtitle: "字幕",
                  }[selectedTrack?.type ?? "video"]
                }
              </span>
              <p className="max-w-80 truncate text-[11px] font-semibold">
                {selectedClip.text ?? selectedClip.shot_id ?? selectedClip.id}
              </p>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[9px]"
                onClick={() => moveSelected(-1)}
              >
                ← 前移
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[9px]"
                onClick={() => moveSelected(1)}
              >
                后移 →
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[9px]"
                onClick={splitSelected}
              >
                <ScissorsIcon /> 分割
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[9px]"
                onClick={duplicateSelected}
              >
                <CopyIcon /> 复制
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  updateSelectedClip(
                    () => null,
                    { type: "delete" },
                    { reflow: true },
                  )
                }
                className="text-destructive h-7 px-2 text-[9px]"
              >
                <Trash2Icon /> 删除
              </Button>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 border-t border-[#3f352b]/8 pt-3 md:grid-cols-4 xl:grid-cols-7">
            <label className="text-[9px] text-[#79736a]">
              位置
              <input
                aria-label="片段时间线位置"
                type="number"
                min="0"
                step="0.1"
                value={selectedClip.start_sec}
                onChange={(event) => {
                  const start = Math.max(Number(event.target.value), 0);
                  updateSelectedClip(
                    (clip) => ({ ...clip, start_sec: start }),
                    {
                      type: "move",
                      track_id: selectedTrack?.id ?? "video",
                      start_sec: start,
                    },
                  );
                }}
                className="mt-1 h-8 w-full rounded-md border border-[#3f352b]/12 bg-white px-2 text-[10px] text-[#24211d] outline-none"
              />
            </label>
            <label className="text-[9px] text-[#79736a]">
              入点
              <input
                aria-label="片段源片入点"
                type="number"
                min="0"
                step="0.1"
                value={selectedClip.source_in_sec}
                onChange={(event) => {
                  const sourceIn = Math.max(Number(event.target.value), 0);
                  updateSelectedClip(
                    (clip) => ({ ...clip, source_in_sec: sourceIn }),
                    {
                      type: "trim",
                      source_in_sec: sourceIn,
                      duration_sec: selectedClip.duration_sec,
                    },
                  );
                }}
                className="mt-1 h-8 w-full rounded-md border border-[#3f352b]/12 bg-white px-2 text-[10px] text-[#24211d] outline-none"
              />
            </label>
            <label className="text-[9px] text-[#79736a]">
              时长
              <input
                aria-label="片段持续时长"
                type="number"
                min="0.1"
                step="0.1"
                value={selectedClip.duration_sec}
                onChange={(event) => {
                  const duration = Math.max(Number(event.target.value), 0.1);
                  updateSelectedClip(
                    (clip) => ({ ...clip, duration_sec: duration }),
                    {
                      type: "trim",
                      source_in_sec: selectedClip.source_in_sec,
                      duration_sec: duration,
                    },
                    { reflow: true },
                  );
                }}
                className="mt-1 h-8 w-full rounded-md border border-[#3f352b]/12 bg-white px-2 text-[10px] text-[#24211d] outline-none"
              />
            </label>
            <div className="flex items-end gap-1">
              <Button
                variant="outline"
                size="sm"
                className="h-8 flex-1 px-1 text-[9px]"
                onClick={() => {
                  const duration = Math.max(
                    Number((selectedClip.duration_sec - 0.5).toFixed(3)),
                    0.1,
                  );
                  updateSelectedClip(
                    (clip) => ({ ...clip, duration_sec: duration }),
                    {
                      type: "trim",
                      source_in_sec: selectedClip.source_in_sec,
                      duration_sec: duration,
                    },
                    { reflow: true },
                  );
                }}
              >
                -0.5s
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8 flex-1 px-1 text-[9px]"
                onClick={() => {
                  const duration = Number(
                    (selectedClip.duration_sec + 0.5).toFixed(3),
                  );
                  updateSelectedClip(
                    (clip) => ({ ...clip, duration_sec: duration }),
                    {
                      type: "trim",
                      source_in_sec: selectedClip.source_in_sec,
                      duration_sec: duration,
                    },
                    { reflow: true },
                  );
                }}
              >
                +0.5s
              </Button>
            </div>
            <label className="text-[9px] text-[#79736a]">
              音量
              <span className="mt-1 flex h-8 items-center gap-2 rounded-md border border-[#3f352b]/12 bg-white px-2">
                <Volume2Icon className="size-3" />
                <input
                  aria-label="片段音量"
                  type="range"
                  min="0"
                  max="4"
                  step="0.05"
                  value={selectedClip.volume ?? 1}
                  onChange={(event) => {
                    const volume = Number(event.target.value);
                    updateSelectedClip((clip) => ({ ...clip, volume }), {
                      type: "change_volume",
                      volume,
                    });
                  }}
                  className="min-w-0 flex-1"
                />
              </span>
            </label>
            <label className="text-[9px] text-[#79736a]">
              转场
              <select
                aria-label="片段转场"
                value={selectedClip.transition ?? "none"}
                onChange={(event) => {
                  const transition = event.target.value;
                  updateSelectedClip((clip) => ({ ...clip, transition }), {
                    type: "add_transition",
                    transition,
                  });
                }}
                className="mt-1 h-8 w-full rounded-md border border-[#3f352b]/12 bg-white px-2 text-[10px] text-[#24211d]"
              >
                <option value="none">无</option>
                <option value="hard_cut">硬切</option>
                <option value="crossfade">叠化</option>
                <option value="dip_to_black">淡黑</option>
              </select>
            </label>
            {selectedClipCandidates.length > 0 && (
              <label className="text-[9px] text-[#79736a]">
                版本
                <select
                  aria-label="替换镜头候选"
                  value={selectedClip.selected_candidate_id ?? ""}
                  onChange={(event) => {
                    const candidate = selectedClipCandidates.find(
                      (item) => item.id === event.target.value,
                    );
                    if (!candidate) return;
                    const artifact =
                      candidate.artifacts.find((item) =>
                        item.mime_type?.startsWith("video/"),
                      ) ?? candidate.artifacts[0];
                    updateSelectedClip(
                      (clip) => ({
                        ...clip,
                        selected_candidate_id: candidate.id,
                        source_ref: artifact?.ref ?? clip.source_ref,
                        source_sha256: artifact?.sha256 ?? clip.source_sha256,
                        artifact: artifact ?? clip.artifact,
                      }),
                      {
                        type: "replace_candidate",
                        candidate_id: candidate.id,
                      },
                    );
                  }}
                  className="mt-1 h-8 w-full rounded-md border border-[#3f352b]/12 bg-white px-2 text-[10px] text-[#24211d]"
                >
                  <option value="">选择</option>
                  {selectedClipCandidates.map((candidate, index) => (
                    <option key={candidate.id} value={candidate.id}>
                      V{index + 1}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {selectedClip.text != null && (
            <textarea
              value={selectedClip.text}
              onChange={(event) => {
                const text = event.target.value;
                if (!text.trim()) return;
                updateSelectedClip((clip) => ({ ...clip, text }), {
                  type: "edit_caption",
                  text,
                });
              }}
              aria-label="编辑字幕或对白"
              rows={1}
              className="mt-2 w-full resize-none rounded-md border border-[#3f352b]/12 bg-white px-3 py-2 text-[10px] text-[#24211d] outline-none focus:border-[#ef6b48]/50"
            />
          )}
        </section>
      )}

      {!compact && !selectedClip && (
        <div className="hidden rounded-xl border border-dashed border-[#3f352b]/12 bg-white/30 px-4 py-3 text-center text-[9px] text-[#79736a]">
          选择任意画面、对白、音乐或字幕片段后，这里会打开精确检查器。
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {previousRevision && (
          <Button variant="outline" size="sm" onClick={restorePrevious}>
            <Undo2Icon /> 回退上一版
          </Button>
        )}
        {workbench.timeline.revisions.length > 0 && (
          <select
            aria-label="恢复历史时间线修订"
            defaultValue=""
            onChange={(event) => {
              const revision = workbench.timeline.revisions.find(
                (item) => item.revision_id === event.target.value,
              );
              if (revision) restoreRevision(revision);
              event.currentTarget.value = "";
            }}
            className="h-9 rounded-md border border-[#3f352b]/10 bg-white/70 px-3 text-[10px]"
          >
            <option value="">恢复任一历史版本…</option>
            {workbench.timeline.revisions.map((revision, index) => (
              <option
                key={revision.revision_id ?? revision.event_id}
                value={revision.revision_id ?? ""}
              >
                版本 {index + 1} ·{" "}
                {revision.author_kind === "agent" ? "智能体" : "手动修改"}
              </option>
            ))}
          </select>
        )}
        <Button
          size="sm"
          disabled={operations.length === 0 || saveRevision.isPending}
          onClick={() => void save()}
          className="bg-[#d85e42] hover:bg-[#bf4e35]"
        >
          {saveRevision.isPending ? (
            <LoaderCircleIcon className="animate-spin" />
          ) : (
            <SaveIcon />
          )}
          保存{operations.length > 0 ? ` (${operations.length})` : ""}
        </Button>
        {!compact && (
          <Button
            variant={workbench.timeline.locked ? "outline" : "default"}
            size="sm"
            disabled={
              !workbench.timeline.revision_id ||
              operations.length > 0 ||
              workbench.timeline.locked === true ||
              lockFinalEdit.isPending
            }
            onClick={() => void lockEdit()}
            className={cn(
              !workbench.timeline.locked && "bg-[#5d806e] hover:bg-[#496d5b]",
            )}
          >
            {lockFinalEdit.isPending ? (
              <LoaderCircleIcon className="animate-spin" />
            ) : (
              <ShieldCheckIcon />
            )}
            {workbench.timeline.locked ? "剪辑已完成" : "完成剪辑"}
          </Button>
        )}
        {compact && onOpen && (
          <Button variant="outline" size="sm" onClick={onOpen}>
            完整剪辑台
          </Button>
        )}
      </div>

      {!compact && (
        <WorkbenchAgentCommand
          workbench={workbench}
          command={agentCommand}
          onCommandChange={onAgentCommandChange}
          quickAction={quickAction}
          onQuickActionConsumed={onQuickActionConsumed}
          placeholder="告诉智能体怎么调时间线，例如：把镜头 02 缩短半秒，音乐从这里淡入……"
        />
      )}
    </div>
  );
}

function TimelineTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  const previewArtifact = [...workbench.delivery.artifacts]
    .reverse()
    .find((artifact) => artifact.mime_type?.startsWith("video/"));
  const previewRef = displayableMediaRef(
    previewArtifact,
    workbench.production.id,
  );
  return (
    <div className="space-y-4">
      <Card className="gap-4 overflow-hidden border-[#3f352b]/14 bg-[#faf8f2]/75">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <FilmIcon className="size-4" /> 剪辑监看
            </CardTitle>
            <div className="flex gap-2">
              {workbench.timeline.fps != null && (
                <Badge variant="outline">{workbench.timeline.fps} fps</Badge>
              )}
              {workbench.timeline.duration_sec != null && (
                <Badge variant="outline">
                  {workbench.timeline.duration_sec}s
                </Badge>
              )}
              <Badge
                variant={workbench.timeline.locked ? "outline" : "secondary"}
              >
                {workbench.timeline.locked ? "剪辑已完成" : "剪辑中"}
              </Badge>
            </div>
          </div>
          <CardDescription>
            画面、节奏、声音和字幕都可以继续调整。
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="relative flex min-h-64 items-center justify-center overflow-hidden rounded-xl bg-[#111] shadow-inner">
            {previewArtifact && previewRef ? (
              <video
                aria-label="剪辑监看播放器"
                className="max-h-[46vh] max-w-full"
                controls
                crossOrigin="use-credentials"
                playsInline
                preload="metadata"
                src={previewRef}
              />
            ) : (
              <div className="max-w-sm px-8 text-center text-xs leading-6 text-white/65">
                <FilmIcon className="mx-auto mb-3 size-7 text-white/45" />
                完成剪辑后，可在这里预览。
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function displayableMediaRef(
  artifact: VideoArtifact | undefined,
  productionId?: string,
) {
  if (!artifact) return null;
  const ref = safeRef(artifact.ref);
  const inferredMediaRef =
    /\.(?:avif|gif|jpe?g|png|webp|m4a|mp3|wav|mov|mp4|webm)$/i.test(ref);
  if (
    productionId &&
    artifact.sha256 &&
    (artifact.mime_type?.match(/^(?:video|audio|image)\//) || inferredMediaRef)
  ) {
    return personalIPVideoArtifactURL(productionId, artifact.sha256);
  }
  return ref.startsWith("https://") ||
    ref.startsWith("http://") ||
    ref.startsWith("/")
    ? ref
    : null;
}

function ShotWorkbench({
  workbench,
  selectedShotId,
  reviewPending,
  onDecision,
}: {
  workbench: PersonalIPVideoWorkbench;
  selectedShotId: string | null;
  reviewPending: boolean;
  onDecision: (
    confirmation: VideoWorkbenchConfirmation,
    decision: "approved" | "rejected",
  ) => void;
}) {
  const [shotCommand, setShotCommand] = useState("");
  const [shotQuickAction, setShotQuickAction] =
    useState<WorkbenchQuickAction | null>(null);
  const [previewCandidateId, setPreviewCandidateId] = useState<string | null>(
    null,
  );
  const selectedShot =
    workbench.shots.find((shot) => shot.id === selectedShotId) ??
    workbench.shots[0];
  const candidates = workbench.candidates.filter(
    (candidate) => candidate.shot_id === selectedShot?.id,
  );
  const selectedCandidate =
    candidates.find((candidate) => candidate.id === previewCandidateId) ??
    candidates.find((candidate) => candidate.selected) ??
    candidates[0];
  const selectionConfirmation = workbench.confirmations.find(
    (item) =>
      item.kind === "candidate_selection" &&
      item.entity_id === selectedCandidate?.id,
  );
  const previewArtifact =
    selectedCandidate?.artifacts.find((artifact) =>
      artifact.mime_type?.startsWith("video/"),
    ) ?? selectedCandidate?.artifacts[0];
  const previewRef = displayableMediaRef(
    previewArtifact,
    workbench.production.id,
  );
  const isVideo = previewArtifact?.mime_type?.startsWith("video/") === true;
  const spec = selectedShot?.spec;
  const qualityEvidence = objectValue(selectedCandidate?.quality?.evidence);
  const motionCadence = objectValue(qualityEvidence?.motion_cadence);
  const interpolationRecommended =
    selectedCandidate?.quality?.interpolation_recommended === true ||
    motionCadence?.interpolation_recommended === true;
  const targetPlaybackFps =
    typeof motionCadence?.target_playback_fps === "number"
      ? motionCadence.target_playback_fps
      : 48;

  if (!selectedShot) {
    return (
      <div className="p-5">
        <EmptyPanel>分镜编译后，这里会出现镜头工作面。</EmptyPanel>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-3.5">
      <section className="overflow-hidden rounded-xl border border-[#3f352b]/14 bg-[#ebe3d6] shadow-[0_18px_50px_-38px_rgba(45,30,20,0.8)]">
        <div className="relative aspect-video min-h-[200px] overflow-hidden bg-[radial-gradient(circle_at_62%_24%,rgba(234,141,92,0.7),transparent_18%),radial-gradient(circle_at_35%_38%,rgba(89,120,126,0.55),transparent_28%),linear-gradient(145deg,#10232d,#543c38_62%,#c46b48)] xl:min-h-[280px]">
          {previewRef && isVideo ? (
            <video
              className="size-full object-cover"
              controls
              preload="metadata"
              src={previewRef}
            />
          ) : previewRef ? (
            <div
              className="size-full bg-cover bg-center"
              style={{ backgroundImage: `url(${JSON.stringify(previewRef)})` }}
            />
          ) : (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/10 text-center text-white">
              <div className="flex size-16 items-center justify-center rounded-full border border-white/25 bg-black/20 backdrop-blur">
                <FilmIcon className="size-7" />
              </div>
              <p className="mt-4 text-lg font-semibold">
                {friendlyShotName(workbench, selectedShot.id)}
              </p>
              <p className="mt-2 max-w-lg px-8 text-xs leading-5 text-white/65">
                {spec?.visual_subject ??
                  spec?.first_frame ??
                  "候选画面生成后将在这里直接预览"}
              </p>
            </div>
          )}
          <div className="absolute top-3 left-3 rounded-md border border-white/20 bg-black/35 px-2 py-1 text-[10px] text-white backdrop-blur">
            镜头 {String(spec?.order ?? 1).padStart(2, "0")}
          </div>
        </div>
        <div className="flex h-10 items-center gap-3 border-t border-[#3f352b]/10 bg-[#faf8f2] px-3 text-[10px] text-[#79736a]">
          <FilmIcon className="size-3.5 text-[#24211d]" />
          <span className="font-medium text-[#24211d]">
            {spec?.duration_seconds ?? "—"}s
          </span>
          <span>·</span>
          <span>
            {selectedCandidate?.status
              ? (EXECUTION_STATUS_LABELS[selectedCandidate.status] ?? "处理中")
              : "等待生成"}
          </span>
          {motionCadence && (
            <>
              <span>·</span>
              <span>
                运动节奏{" "}
                {motionCadence.risk === "high"
                  ? "高风险"
                  : motionCadence.risk === "medium"
                    ? "需关注"
                    : "正常"}
              </span>
            </>
          )}
          {interpolationRecommended && (
            <Badge className="bg-amber-600 text-[9px]">建议流畅增强</Badge>
          )}
          <Badge variant="outline" className="ml-auto text-[9px]">
            {typeof workbench.production.delivery_spec.aspect_ratio === "string"
              ? workbench.production.delivery_spec.aspect_ratio
              : "16:9"}
          </Badge>
        </div>
      </section>

      <section className="grid grid-cols-[72px_1fr] items-center gap-3">
        <span className="pl-1 text-xs font-semibold">版本</span>
        <div className="flex min-w-0 gap-2 overflow-x-auto pb-1">
          {candidates.length === 0 ? (
            <div className="flex h-12 min-w-36 items-center justify-center rounded-lg border border-dashed border-[#3f352b]/15 text-[10px] text-[#79736a]">
              等待生成候选
            </div>
          ) : (
            candidates.map((candidate, index) => (
              <button
                type="button"
                key={candidate.id}
                aria-label={`预览候选版本 V${index + 1}`}
                onClick={() => setPreviewCandidateId(candidate.id)}
                className={cn(
                  "relative h-12 min-w-24 overflow-hidden rounded-lg border bg-gradient-to-br from-[#1c3038] to-[#9b624f] p-2 text-left text-white",
                  candidate.id === selectedCandidate?.id
                    ? "border-[#e25f45] ring-2 ring-[#e25f45]/15"
                    : "border-[#3f352b]/15",
                )}
              >
                <span className="absolute right-1.5 bottom-1 text-[9px] font-semibold">
                  V{index + 1}
                </span>
                {candidate.selected && (
                  <CheckCircle2Icon className="size-3 text-[#b7e0c9]" />
                )}
              </button>
            ))
          )}
          <button
            type="button"
            onClick={() =>
              setShotQuickAction(
                workbenchQuickAction(
                  `为镜头 ${String(spec?.order ?? 1).padStart(2, "0")} 生成一个新版本`,
                  `为镜头 ${selectedShot.id} 生成一个新的候选版本。先说明准备修改哪些画面、动作或运镜；保留现有版本，不要覆盖。`,
                ),
              )
            }
            aria-label="生成当前镜头的新版本"
            className="flex h-12 min-w-32 items-center justify-center rounded-lg border border-dashed border-[#3f352b]/20 bg-white/35 text-[10px] text-[#645b51]"
          >
            + 生成新版本
          </button>
          {selectedCandidate && isVideo && (
            <button
              type="button"
              onClick={() =>
                setShotQuickAction(
                  workbenchQuickAction(
                    interpolationRecommended
                      ? `为镜头 ${String(spec?.order ?? 1).padStart(2, "0")} 生成流畅版本`
                      : `检查镜头 ${String(spec?.order ?? 1).padStart(2, "0")} 的运动流畅度`,
                    `检查镜头 ${selectedShot.id} 的候选 ${selectedCandidate.id} 是否存在运动卡顿。先调用 personal_ip_run_local_generated_shot_qa，按连续运动评估并把 target_playback_fps 设为 ${targetPlaybackFps}；只有 QA 明确建议 motion_interpolation 时，才调用 personal_ip_interpolate_video_candidate 生成一个新的 ${targetPlaybackFps}fps 候选。保留原片，不覆盖；新候选完成后重新 QA，等待用户对比选片。`,
                  ),
                )
              }
              aria-label="检查当前候选的运动流畅度"
              className={cn(
                "flex h-12 min-w-28 items-center justify-center gap-1 rounded-lg border px-3 text-[10px]",
                interpolationRecommended
                  ? "border-amber-500/50 bg-amber-50 text-amber-800"
                  : "border-[#3f352b]/20 bg-white/35 text-[#645b51]",
              )}
            >
              <GaugeIcon className="size-3.5" />
              {interpolationRecommended ? "生成流畅版" : "检查流畅度"}
            </button>
          )}
          {selectedCandidate &&
            !selectedCandidate.selected &&
            selectionConfirmation && (
              <button
                type="button"
                disabled={reviewPending}
                onClick={() => onDecision(selectionConfirmation, "approved")}
                className="flex h-12 min-w-28 items-center justify-center gap-1 rounded-lg bg-[#397461] px-3 text-[10px] font-semibold text-white transition hover:bg-[#2f6553] disabled:opacity-50"
              >
                {reviewPending ? (
                  <LoaderCircleIcon className="size-3.5 animate-spin" />
                ) : (
                  <CheckCircle2Icon className="size-3.5" />
                )}
                采用此版本
              </button>
            )}
        </div>
      </section>

      <section className="mt-auto shrink-0 px-1 pb-1">
        <div className="px-1 pb-2 text-[10px]">
          <span className="font-semibold text-[#d9573e]">
            当前目标 · 镜头 {String(spec?.order ?? 1).padStart(2, "0")}
          </span>
        </div>
        <WorkbenchAgentCommand
          workbench={workbench}
          shotId={selectedShot.id}
          candidateId={selectedCandidate?.id}
          command={shotCommand}
          onCommandChange={setShotCommand}
          quickAction={shotQuickAction}
          onQuickActionConsumed={(id) =>
            setShotQuickAction((current) =>
              current?.id === id ? null : current,
            )
          }
          placeholder="告诉智能体怎样修改当前镜头；可重生首帧、动作、运镜或整个视频候选……"
        />
      </section>
    </div>
  );
}

function EmptyDirectorCanvas({
  loading,
  failed,
}: {
  loading: boolean;
  failed: boolean;
}) {
  return (
    <div className="flex min-h-full flex-col gap-3 p-3.5">
      <section className="overflow-hidden rounded-xl border border-[#3f352b]/14 bg-[#ebe3d6] shadow-[0_18px_50px_-38px_rgba(45,30,20,0.8)]">
        <div className="relative aspect-video min-h-[200px] overflow-hidden bg-[radial-gradient(circle_at_60%_24%,rgba(231,153,108,0.3),transparent_22%),radial-gradient(circle_at_32%_42%,rgba(104,132,128,0.22),transparent_30%),linear-gradient(145deg,#ebe3d8,#d9d1c4_62%,#c7b8a7)] xl:min-h-[280px]">
          <div className="absolute inset-0 flex flex-col items-center justify-center text-center text-[#514b44]">
            <div className="flex size-14 items-center justify-center rounded-full border border-white/60 bg-white/35 backdrop-blur">
              {loading ? (
                <LoaderCircleIcon className="size-6 animate-spin" />
              ) : (
                <FilmIcon className="size-6" />
              )}
            </div>
            <p className="mt-4 text-sm font-semibold">
              {loading
                ? "正在读取视频项目"
                : failed
                  ? "视频项目暂时不可用"
                  : "还没有视频制作"}
            </p>
            <p className="mt-1.5 max-w-sm px-6 text-[10px] leading-5 text-[#7f786f]">
              在对话中给出剧本、选题或一句话目标，智能体会创建项目并把首个分镜放到这里。
            </p>
          </div>
        </div>
        <div className="flex h-10 items-center gap-3 border-t border-[#3f352b]/10 bg-[#faf8f2] px-3 text-[10px] text-[#79736a]">
          <FilmIcon className="size-3.5" />
          <span>等待镜头</span>
          <Badge variant="outline" className="ml-auto text-[9px]">
            16:9
          </Badge>
        </div>
      </section>

      <section className="grid grid-cols-[54px_1fr] items-center gap-3 xl:grid-cols-[72px_1fr]">
        <span className="pl-1 text-xs font-semibold">版本</span>
        <div className="flex h-12 items-center rounded-lg border border-dashed border-[#3f352b]/15 px-4 text-[10px] text-[#8d867c]">
          候选版本会按镜头归档在这里
        </div>
      </section>

      <section className="rounded-xl border border-[#3f352b]/12 bg-[#faf8f2]/80 p-2.5">
        <div className="flex items-center gap-2 rounded-lg border border-[#3f352b]/10 bg-white/70 px-3 py-2">
          <p className="min-w-0 flex-1 truncate text-xs text-[#8d867c]">
            告诉智能体你想制作什么视频……
          </p>
          <Button
            asChild
            size="icon-sm"
            className="bg-[#5d806e] hover:bg-[#496d5b]"
          >
            <Link href="/workspace/chats" aria-label="创建视频项目">
              <BotIcon />
            </Link>
          </Button>
        </div>
      </section>
    </div>
  );
}

function EmptyTimelineDock() {
  const rows = [
    ["video", "视频"],
    ["dialogue", "对白"],
    ["music", "音乐"],
    ["subtitle", "字幕"],
  ] as const;
  return (
    <section
      aria-label="制作时间线"
      className="relative shrink-0 border-t border-[#3f352b]/14 bg-[#f8f4ec] px-3 py-2.5 text-[#24211d]"
    >
      <div className="mb-1.5 flex items-center gap-2 px-1">
        <Layers3Icon className="size-3.5 text-[#c95038]" />
        <span className="text-[8px] font-bold tracking-[0.16em] text-[#a45b48]">
          TIMELINE
        </span>
        <span className="text-[9px] text-[#79736a]">等待开始制作</span>
      </div>
      <div className="overflow-hidden rounded-lg border border-[#3f352b]/10 bg-white/35">
        <div className="ml-[54px] grid h-5 grid-cols-5 items-center border-b border-[#3f352b]/8 px-2 text-[7px] text-[#8c857b]">
          {["00:00", "00:03", "00:06", "00:09", "00:12"].map((time) => (
            <span key={time}>{time}</span>
          ))}
        </div>
        {rows.map(([id, label]) => (
          <div
            key={id}
            className="grid grid-cols-[54px_1fr] border-b border-[#3f352b]/8 last:border-b-0"
          >
            <div className="flex items-center gap-1 border-r border-[#3f352b]/8 px-2 py-1.5 text-[8px] text-[#645b51]">
              {id === "video" ? (
                <FilmIcon className="size-3" />
              ) : id === "dialogue" ? (
                <MessageSquareTextIcon className="size-3" />
              ) : (
                <Music2Icon className="size-3" />
              )}
              {label}
            </div>
            <div className="m-1 h-4 rounded border border-dashed border-[#3f352b]/8 bg-white/25" />
          </div>
        ))}
      </div>
    </section>
  );
}

function CompactTimelineDock({
  workbench,
  onOpen,
  expanded,
  agentCommand,
  onAgentCommandChange,
  quickAction,
  onQuickAction,
  onQuickActionConsumed,
}: {
  workbench: PersonalIPVideoWorkbench;
  onOpen: () => void;
  expanded: boolean;
  agentCommand: string;
  onAgentCommandChange: (value: string) => void;
  quickAction: WorkbenchQuickAction | null;
  onQuickAction: (action: WorkbenchQuickAction) => void;
  onQuickActionConsumed: (id: string) => void;
}) {
  return (
    <section
      aria-label="制作时间线"
      className={cn(
        "relative shrink-0 border-t border-[#3f352b]/14 bg-[#f8f4ec] px-3 py-2.5 text-[#24211d]",
        expanded && "max-h-[52vh] overflow-y-auto",
      )}
    >
      <div className="mb-1.5 flex items-center justify-between gap-3 px-1">
        <div className="flex items-center gap-2">
          <Layers3Icon className="size-3.5 text-[#c95038]" />
          <span className="text-[8px] font-bold tracking-[0.16em] text-[#a45b48]">
            {expanded ? "剪辑时间线" : "TIMELINE"}
          </span>
          {(workbench.timeline.duration_sec != null ||
            workbench.timeline.fps != null) && (
            <span className="text-[9px] text-[#79736a]">
              {workbench.timeline.duration_sec != null
                ? `${workbench.timeline.duration_sec}s`
                : null}
              {workbench.timeline.duration_sec != null &&
              workbench.timeline.fps != null
                ? " · "
                : null}
              {workbench.timeline.fps != null
                ? `${workbench.timeline.fps} fps`
                : null}
            </span>
          )}
        </div>
        {!expanded && (
          <span className="text-[9px] text-[#79736a]">
            可选中、拖动、裁切并保存
          </span>
        )}
      </div>
      <TimelineEditor
        workbench={workbench}
        compact={!expanded}
        onOpen={expanded ? undefined : onOpen}
        agentCommand={agentCommand}
        onAgentCommandChange={onAgentCommandChange}
        quickAction={quickAction}
        onQuickAction={onQuickAction}
        onQuickActionConsumed={onQuickActionConsumed}
      />
    </section>
  );
}

function ReferenceSidebar({
  workbench,
  onOpen,
}: {
  workbench: PersonalIPVideoWorkbench;
  onOpen: (view: WorkbenchView) => void;
}) {
  const referenceItems = [
    {
      id: "character",
      label: "角色",
      asset: workbench.assets.find(
        (asset) => asset.entity_type === "character",
      ),
      tone: "from-[#887266] to-[#d6c0ac]",
    },
    {
      id: "scene",
      label: "场景",
      asset: workbench.assets.find((asset) => asset.entity_type === "scene"),
      tone: "from-[#172d39] to-[#a55c42]",
    },
    {
      id: "prop",
      label: "道具",
      asset: workbench.assets.find((asset) => asset.entity_type === "prop"),
      tone: "from-[#3f3b34] to-[#a28d6b]",
    },
    {
      id: "audio",
      label: "声音",
      asset: undefined,
      tone: "from-[#e2ded4] to-[#b8c5b5]",
    },
  ];
  return (
    <aside
      aria-label="项目设定与素材"
      className="flex min-h-0 flex-col border-l border-[#3f352b]/12 bg-[#faf8f2]/90"
    >
      <div className="flex items-center justify-between border-b border-[#3f352b]/10 px-4 py-3.5">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">项目素材</h2>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2.5 p-3">
          {referenceItems.map((item) => {
            const artifact = item.asset?.artifacts[0];
            const mediaRef = displayableMediaRef(
              artifact,
              workbench.production.id,
            );
            const ready =
              item.id === "audio"
                ? Boolean(workbench.domain_contracts.narration_timing)
                : item.asset?.allowed_for_use === true ||
                  item.asset?.status === "succeeded";
            return (
              <button
                key={item.id}
                type="button"
                aria-label={`查看${item.label}素材`}
                onClick={() =>
                  onOpen(item.id === "audio" ? "timeline" : "overview")
                }
                className="group grid h-[96px] w-full grid-cols-[minmax(0,1.1fr)_0.9fr] items-center gap-2 rounded-xl border border-[#3f352b]/11 bg-white/55 p-2 text-left transition hover:border-[#c95038]/25 hover:bg-white xl:h-[112px] xl:grid-cols-[minmax(0,1.25fr)_0.75fr] xl:gap-3"
              >
                <span
                  className={cn(
                    "relative size-full min-h-0 overflow-hidden rounded-lg bg-gradient-to-br",
                    item.tone,
                  )}
                  style={
                    mediaRef
                      ? {
                          backgroundImage: `url(${JSON.stringify(mediaRef)})`,
                          backgroundPosition: "center",
                          backgroundSize: "cover",
                        }
                      : undefined
                  }
                >
                  {!mediaRef && item.id === "audio" && (
                    <span className="absolute inset-0 flex items-center justify-center gap-1 opacity-55">
                      {[16, 30, 22, 42, 28, 36, 18, 32, 24].map(
                        (height, index) => (
                          <i
                            key={index}
                            className="w-1 rounded-full bg-[#397461]"
                            style={{ height }}
                          />
                        ),
                      )}
                    </span>
                  )}
                  {!mediaRef && item.id !== "audio" && (
                    <span className="absolute inset-0 flex items-center justify-center text-white/75">
                      {item.id === "character" ? (
                        <SparklesIcon className="size-6" />
                      ) : item.id === "scene" ? (
                        <ImageIcon className="size-6" />
                      ) : (
                        <BoxesIcon className="size-6" />
                      )}
                    </span>
                  )}
                </span>
                <span className="flex min-w-0 items-center justify-between gap-2 pr-1">
                  <span>
                    <strong className="block text-sm">{item.label}</strong>
                    <small className="mt-1 block max-w-24 truncate text-[9px] text-[#79736a]">
                      {item.asset
                        ? friendlyAssetName(item.asset)
                        : ready
                          ? "已准备"
                          : "未添加"}
                    </small>
                  </span>
                  {ready ? (
                    <CheckCircle2Icon className="size-5 shrink-0 text-[#4f7d62]" />
                  ) : (
                    <ChevronRightIcon className="size-4 shrink-0 text-[#9a9389]" />
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </ScrollArea>
      <div className="border-t border-[#3f352b]/10 p-3">
        <Button
          asChild
          className="h-12 w-full bg-[#ef5f3f] text-base hover:bg-[#d94d31]"
        >
          <Link href="/workspace/chats">
            <BotIcon /> 继续创作
          </Link>
        </Button>
        {workbench.confirmations.length > 0 && (
          <p className="mt-2 text-center text-[9px] text-amber-700">
            当前有 {workbench.confirmations.length} 个关键确认待处理
          </p>
        )}
      </div>
    </aside>
  );
}

function EmptyReferenceSidebar() {
  const items = [
    ["角色", SparklesIcon, "from-[#887266] to-[#d6c0ac]"],
    ["场景", ImageIcon, "from-[#172d39] to-[#a55c42]"],
    ["道具", BoxesIcon, "from-[#3f3b34] to-[#a28d6b]"],
    ["声音", Music2Icon, "from-[#e2ded4] to-[#b8c5b5]"],
  ] as const;
  return (
    <aside
      aria-label="项目设定与素材"
      className="flex min-h-0 flex-col border-l border-[#3f352b]/12 bg-[#faf8f2]/90"
    >
      <div className="border-b border-[#3f352b]/10 px-4 py-3.5">
        <h2 className="text-sm font-semibold tracking-tight">项目素材</h2>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2.5 p-3">
          {items.map(([label, Icon, tone]) => (
            <div
              key={label}
              className="grid h-[84px] grid-cols-[minmax(0,1.1fr)_0.9fr] items-center gap-2 rounded-xl border border-[#3f352b]/11 bg-white/45 p-2 xl:h-[100px]"
            >
              <span
                className={cn(
                  "flex size-full items-center justify-center rounded-lg bg-gradient-to-br text-white/70",
                  tone,
                )}
              >
                <Icon className="size-5" />
              </span>
              <span>
                <strong className="block text-xs">{label}</strong>
                <small className="mt-1 block text-[8px] text-[#8d867c]">
                  未添加
                </small>
              </span>
            </div>
          ))}
        </div>
      </ScrollArea>
      <div className="border-t border-[#3f352b]/10 p-3">
        <Button
          asChild
          className="h-11 w-full bg-[#ef5f3f] text-sm hover:bg-[#d94d31]"
        >
          <Link href="/workspace/chats">
            <BotIcon /> 开始创作
          </Link>
        </Button>
      </div>
    </aside>
  );
}

function DeliveryTab({
  workbench,
  reviewPending,
  onDecision,
}: {
  workbench: PersonalIPVideoWorkbench;
  reviewPending: boolean;
  onDecision: (
    confirmation: VideoWorkbenchConfirmation,
    decision: "approved" | "rejected",
  ) => void;
}) {
  const currentQa =
    workbench.delivery.current_qa_event ??
    [...workbench.delivery.qa_events].reverse().find(Boolean);
  const payload = currentQa?.payload ?? {};
  const payloadArtifact =
    payload.artifact &&
    typeof payload.artifact === "object" &&
    typeof (payload.artifact as Record<string, unknown>).ref === "string"
      ? (payload.artifact as VideoArtifact)
      : undefined;
  const currentArtifact =
    payloadArtifact ??
    workbench.delivery.artifacts.find(
      (artifact) =>
        currentQa?.output_refs?.includes(artifact.ref) &&
        artifact.mime_type?.startsWith("video/"),
    ) ??
    [...workbench.delivery.artifacts]
      .reverse()
      .find((artifact) => artifact.mime_type?.startsWith("video/"));
  const playbackRef = displayableMediaRef(
    currentArtifact,
    workbench.production.id,
  );
  const checks = payload.checks;
  const checkEntries =
    checks && typeof checks === "object" ? Object.entries(checks) : [];
  const publishConfirmations = workbench.confirmations.filter(
    (item) => item.kind === "real_publish",
  );
  const passedChecks = checkEntries.filter(([, raw]) => {
    const detail =
      raw && typeof raw === "object"
        ? (raw as Record<string, unknown>)
        : { passed: raw };
    return detail.passed === true;
  }).length;
  const fileSize =
    typeof currentArtifact?.size_bytes === "number"
      ? currentArtifact.size_bytes >= 1024 * 1024
        ? `${(currentArtifact.size_bytes / 1024 / 1024).toFixed(1)} MB`
        : `${Math.max(1, Math.round(currentArtifact.size_bytes / 1024))} KB`
      : null;
  return (
    <div className="mx-auto w-full max-w-[1440px] space-y-4">
      <section className="overflow-hidden rounded-[28px] border border-[#3f352b]/12 bg-[#f9f6ef] shadow-[0_18px_50px_-38px_rgba(49,41,33,0.45)]">
        <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <div>
            <p className="flex items-center gap-2 text-base font-semibold">
              <FilmIcon className="size-4 text-[#c95038]" />
              {currentArtifact ? "最终成片" : "成片尚未完成"}
            </p>
            <p className="mt-1 text-[10px] text-[#79736a]">
              {currentArtifact
                ? "播放确认后即可保存到本地。"
                : "完成剪辑后，成片会出现在这里。"}
            </p>
          </div>
          <Badge
            variant={
              workbench.delivery.qa_passed
                ? "outline"
                : currentArtifact
                  ? "secondary"
                  : "outline"
            }
            className={cn(
              "hidden",
              workbench.delivery.qa_passed &&
                "border-emerald-600/30 bg-emerald-50 text-emerald-800",
            )}
          >
            {workbench.delivery.qa_passed ? (
              <CheckCircle2Icon />
            ) : currentArtifact ? (
              <LoaderCircleIcon />
            ) : (
              <FilmIcon />
            )}
            {workbench.delivery.qa_passed
              ? "检查通过"
              : currentArtifact
                ? "等待检查"
                : "尚未生成"}
          </Badge>
        </header>

        <div className="flex min-h-[440px] items-center justify-center bg-[#171614] xl:min-h-[560px]">
          {currentArtifact && playbackRef ? (
            <div className="flex size-full items-center justify-center p-3">
              <video
                aria-label="最终成片播放器"
                className="max-h-[68vh] max-w-full rounded-xl"
                controls
                crossOrigin="use-credentials"
                playsInline
                preload="metadata"
                src={playbackRef}
              />
            </div>
          ) : (
            <div className="flex max-w-sm flex-col items-center px-6 text-center text-white">
              <span className="mb-4 flex size-16 items-center justify-center rounded-full border border-white/15 bg-white/8">
                <FilmIcon className="size-7 text-white/75" />
              </span>
              <strong className="text-lg">还没有可播放的成片</strong>
            </div>
          )}
        </div>

        {currentArtifact && playbackRef && (
          <footer className="flex justify-end border-t border-[#3f352b]/10 px-5 py-4">
            <Button asChild className="ml-auto bg-[#ef5f3f] hover:bg-[#d94d31]">
              <a href={playbackRef} download>
                <DownloadIcon /> 保存到本地
              </a>
            </Button>
          </footer>
        )}
      </section>

      <div className="hidden gap-4 md:grid-cols-2">
        <Card
          className={cn(
            "gap-3 border-[#3f352b]/12 bg-white/60",
            workbench.delivery.qa_passed
              ? "border-emerald-500/40"
              : currentArtifact
                ? "border-amber-500/40"
                : "",
          )}
        >
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheckIcon className="size-4" /> 交付检查
              </CardTitle>
              <Badge
                variant={workbench.delivery.qa_passed ? "outline" : "secondary"}
              >
                {workbench.delivery.qa_passed ? (
                  <CheckCircle2Icon />
                ) : (
                  <AlertTriangleIcon />
                )}
                {workbench.delivery.qa_passed
                  ? "已通过"
                  : workbench.delivery.qa_passed === false
                    ? "需要处理"
                    : "等待检查"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {workbench.delivery.qa_stale && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-900">
                剪辑在上次检查后有修改，需要重新生成并检查成片。
              </div>
            )}
            {checkEntries.length > 0 ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {checkEntries.map(([key, raw]) => {
                  const detail =
                    raw && typeof raw === "object"
                      ? (raw as Record<string, unknown>)
                      : { passed: raw };
                  const passed = detail.passed === true;
                  return (
                    <div
                      key={key}
                      className="flex items-center justify-between gap-3 rounded-lg border border-[#3f352b]/10 bg-white/70 px-3 py-2 text-xs"
                    >
                      <span>{DELIVERY_CHECK_LABELS[key] ?? "媒体检查"}</span>
                      <Badge variant={passed ? "outline" : "destructive"}>
                        {passed ? "通过" : "未通过"}
                      </Badge>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm leading-6 text-[#79736a]">
                成片生成后，智能体会自动检查播放、画面、声音、字幕和交付规格。
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="gap-3 border-[#3f352b]/12 bg-white/60">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <PackageCheckIcon className="size-4" /> 成片文件
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {currentArtifact ? (
              <>
                <div className="flex items-center justify-between gap-3 rounded-xl border border-[#3f352b]/10 bg-white/70 p-3">
                  <div className="min-w-0">
                    <strong className="block truncate text-sm">
                      {shortRef(currentArtifact.ref)}
                    </strong>
                    <span className="mt-1 block text-[10px] text-[#79736a]">
                      {currentArtifact.mime_type ?? "视频文件"}
                      {fileSize ? ` · ${fileSize}` : ""}
                    </span>
                  </div>
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-emerald-50 text-emerald-700">
                    <CheckCircle2Icon className="size-4" />
                  </span>
                </div>
                <p className="text-xs text-[#79736a]">
                  {passedChecks}/{checkEntries.length || "—"} 项检查通过
                </p>
              </>
            ) : (
              <p className="text-sm leading-6 text-[#79736a]">
                当前没有交付文件。完成最终剪辑后，成片会出现在这里。
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="hidden">
        {publishConfirmations.map((confirmation) => (
          <ConfirmationCard
            key={confirmation.id}
            confirmation={confirmation}
            pending={reviewPending}
            onDecision={(decision) => onDecision(confirmation, decision)}
          />
        ))}
      </div>
    </div>
  );
}

function ReceiptsTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  if (workbench.events.length === 0)
    return <EmptyPanel>账本中还没有制作事件。</EmptyPanel>;
  return (
    <div className="space-y-2">
      {workbench.events.map((event) => (
        <details key={event.id} className="group bg-card rounded-xl border">
          <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3">
            <span className="text-muted-foreground w-7 text-[11px] tabular-nums">
              #{event.sequence}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm font-medium">
              {EVENT_LABELS[event.event_type ?? ""] ?? event.event_type}
            </span>
            <Badge variant={statusBadge(event.status)}>{event.status}</Badge>
            <code className="text-muted-foreground hidden max-w-48 truncate text-[10px] xl:block">
              {event.provider_task_id}
            </code>
            <ChevronRightIcon className="text-muted-foreground size-4 transition group-open:rotate-90" />
          </summary>
          <Separator />
          <div className="grid gap-3 p-4 lg:grid-cols-2">
            <Snapshot
              title="Receipt metadata"
              value={{
                event_key: event.event_key,
                event_type: event.event_type,
                entity_type: event.entity_type,
                entity_id: event.entity_id,
                provider: event.provider,
                model: event.model,
                provider_task_id: event.provider_task_id,
                cost: event.cost,
                occurred_at: event.occurred_at,
              }}
            />
            <Snapshot
              title="Payload / refs"
              value={{
                payload: event.payload,
                input_refs: event.input_refs,
                output_refs: event.output_refs,
              }}
            />
          </div>
        </details>
      ))}
    </div>
  );
}

function WorkbenchViewSwitch({
  activeView,
  onSelect,
}: {
  activeView: WorkbenchView;
  onSelect: (view: WorkbenchView) => void;
}) {
  const options: ReadonlyArray<readonly [WorkbenchView, string]> | null = [
    "tasks",
    "candidates",
  ].includes(activeView)
    ? [
        ["storyboard", "镜头工作面"],
        ["tasks", "生成任务"],
        ["candidates", "候选与一致性"],
      ]
    : null;

  if (!options) return null;
  return (
    <div className="sticky top-0 z-20 flex h-11 items-center gap-1 border-b border-[#3f352b]/10 bg-[#f7f3ec]/95 px-5 backdrop-blur">
      {options.map(([view, label]) => (
        <button
          key={view}
          type="button"
          aria-label={`查看${label}`}
          onClick={() => onSelect(view)}
          className={cn(
            "rounded-lg px-3 py-1.5 text-[10px] font-semibold transition",
            activeView === view
              ? "bg-[#24211d] text-white"
              : "text-[#79736a] hover:bg-white/70 hover:text-[#24211d]",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function WorkbenchDetail({
  workbench,
  activeView,
  onActiveViewChange,
  selectedShotId,
  selectedSetupPreviewKey,
  onSelectSetupPreview,
  setupCommand,
  onSetupCommandChange,
  setupQuickAction,
  onSetupQuickAction,
  onSetupQuickActionConsumed,
}: {
  workbench: PersonalIPVideoWorkbench;
  activeView: WorkbenchView;
  onActiveViewChange: (view: WorkbenchView) => void;
  selectedShotId: string | null;
  selectedSetupPreviewKey: string | null;
  onSelectSetupPreview: (key: string) => void;
  setupCommand: string;
  onSetupCommandChange: (value: string) => void;
  setupQuickAction: WorkbenchQuickAction | null;
  onSetupQuickAction: (action: WorkbenchQuickAction) => void;
  onSetupQuickActionConsumed: (id: string) => void;
}) {
  const reviewMutation = useRecordVideoConfirmation(workbench.production.id);
  const decide = (
    confirmation: VideoWorkbenchConfirmation,
    decision: "approved" | "rejected",
  ) => {
    void reviewMutation
      .mutateAsync({ confirmation, decision })
      .then(() =>
        toast.success(
          decision === "approved" ? "确认已写入生产账本" : "拒绝已写入生产账本",
        ),
      )
      .catch(() => toast.error("这次确认没有保存，请重试"));
  };
  return (
    <Tabs
      value={activeView}
      onValueChange={(value) => onActiveViewChange(value as WorkbenchView)}
      className="h-full min-h-0 min-w-0"
    >
      <WorkbenchViewSwitch
        activeView={activeView}
        onSelect={onActiveViewChange}
      />
      <TabsContent value="overview" className="h-full min-h-0">
        <OverviewTab
          workbench={workbench}
          selectedPreviewKey={selectedSetupPreviewKey}
          onSelectPreview={onSelectSetupPreview}
          command={setupCommand}
          onCommandChange={onSetupCommandChange}
          quickAction={setupQuickAction}
          onQuickAction={onSetupQuickAction}
          onQuickActionConsumed={onSetupQuickActionConsumed}
        />
      </TabsContent>
      <TabsContent value="storyboard" className="h-full min-h-0">
        <ShotWorkbench
          workbench={workbench}
          selectedShotId={selectedShotId}
          reviewPending={reviewMutation.isPending}
          onDecision={decide}
        />
      </TabsContent>
      <TabsContent value="tasks" className="p-5">
        <TasksTab workbench={workbench} />
      </TabsContent>
      <TabsContent value="candidates" className="p-5">
        <CandidatesTab
          workbench={workbench}
          reviewPending={reviewMutation.isPending}
          onDecision={decide}
        />
      </TabsContent>
      <TabsContent value="timeline" className="p-5">
        <TimelineTab workbench={workbench} />
      </TabsContent>
      <TabsContent value="delivery" className="p-5">
        <DeliveryTab
          workbench={workbench}
          reviewPending={reviewMutation.isPending}
          onDecision={decide}
        />
      </TabsContent>
      <TabsContent value="receipts" className="p-5">
        <ReceiptsTab workbench={workbench} />
      </TabsContent>
    </Tabs>
  );
}

export function PersonalIPVideoWorkbench({
  productionId,
  threadId: taskThreadId,
  embedded = false,
}: {
  productionId?: string;
  threadId?: string;
  embedded?: boolean;
} = {}) {
  const productionsQuery = usePersonalIPVideoProductions();
  const productions = useMemo(
    () =>
      (productionsQuery.data ?? []).filter(
        (production) =>
          !/^agent receipt acceptance$/i.test(production.title.trim()),
      ),
    [productionsQuery.data],
  );
  const [selectedId, setSelectedId] = useState<string | null>(
    productionId ?? null,
  );
  const [activeView, setActiveView] = useState<WorkbenchView>("storyboard");
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [selectedSetupPreviewKey, setSelectedSetupPreviewKey] = useState<
    string | null
  >(null);
  const [setupCommand, setSetupCommand] = useState("");
  const [setupQuickAction, setSetupQuickAction] =
    useState<WorkbenchQuickAction | null>(null);
  const [timelineCommand, setTimelineCommand] = useState("");
  const [timelineQuickAction, setTimelineQuickAction] =
    useState<WorkbenchQuickAction | null>(null);

  useEffect(() => {
    document.title = "视频生产工作台 - IP Agent";
  }, []);
  useEffect(() => {
    if (productionId) {
      if (selectedId !== productionId) setSelectedId(productionId);
      return;
    }
    if (!selectedId && productions[0]) setSelectedId(productions[0].id);
    if (
      selectedId &&
      productions.length > 0 &&
      !productions.some((item) => item.id === selectedId)
    ) {
      setSelectedId(productions[0]?.id ?? null);
    }
  }, [productionId, productions, selectedId]);

  const workbenchQuery = usePersonalIPVideoWorkbench(selectedId);
  const workbench = workbenchQuery.data;
  const setupItems = useMemo(
    () => (workbench ? setupPreviewItems(workbench) : []),
    [workbench],
  );
  const setupStageActive = activeView === "overview";
  const editStageActive = activeView === "timeline";
  const deliveryStageActive = activeView === "delivery";
  const immersiveStageActive = editStageActive || deliveryStageActive;
  useEffect(() => {
    if (!workbench?.shots.length) {
      setSelectedShotId(null);
      return;
    }
    if (!workbench.shots.some((shot) => shot.id === selectedShotId)) {
      setSelectedShotId(workbench.shots[0]?.id ?? null);
    }
  }, [selectedShotId, workbench]);
  useEffect(() => {
    if (!setupItems.length) {
      setSelectedSetupPreviewKey(null);
      setSetupCommand("");
      setSetupQuickAction(null);
      return;
    }
    if (!setupItems.some((item) => item.key === selectedSetupPreviewKey)) {
      setSelectedSetupPreviewKey(setupItems[0]?.key ?? null);
      setSetupCommand("");
      setSetupQuickAction(null);
    }
  }, [selectedSetupPreviewKey, setupItems]);
  const selectSetupPreview = (key: string) => {
    setSelectedSetupPreviewKey(key);
    setSetupCommand("");
    setSetupQuickAction(null);
    setActiveView("overview");
  };
  const selectProduction = (productionId: string) => {
    setSelectedId(productionId);
    setSelectedShotId(null);
    setSelectedSetupPreviewKey(null);
    setSetupCommand("");
    setSetupQuickAction(null);
    setTimelineCommand("");
    setTimelineQuickAction(null);
    setActiveView("storyboard");
  };

  return (
    <WorkspaceContainer>
      {!embedded && <WorkspaceHeader />}
      <WorkspaceBody className="overflow-auto bg-[#f3efe7]">
        <div className="flex h-full w-full min-w-0 flex-col text-[#24211d]">
          <header className="grid h-[78px] shrink-0 grid-cols-[170px_minmax(0,1fr)_150px] items-center border-b border-[#3f352b]/12 bg-[#faf8f2]/90 px-3 backdrop-blur-xl xl:grid-cols-[280px_minmax(0,1fr)_310px] xl:px-4">
            <div className="flex min-w-0 items-center gap-2">
              <Link
                href={embedded ? "/workspace/chats" : "/workspace/personal-ip"}
                aria-label={embedded ? "返回历史对话" : "返回平台管理"}
                className="flex size-8 shrink-0 items-center justify-center rounded-lg text-[#79736a] transition hover:bg-[#3f352b]/5 hover:text-[#24211d]"
              >
                <ArrowLeftIcon className="size-4" />
              </Link>
              <div className="min-w-0 flex-1">
                <h1 className="sr-only">视频生产工作台</h1>
                {embedded ? (
                  <p className="truncate text-lg font-semibold tracking-tight">
                    {workbench?.production.title ?? "视频创作任务"}
                  </p>
                ) : (
                  <select
                    aria-label="选择制作项目"
                    value={selectedId ?? ""}
                    onChange={(event) => selectProduction(event.target.value)}
                    className="w-full truncate border-0 bg-transparent text-lg font-semibold tracking-tight outline-none"
                  >
                    {productions.length === 0 && (
                      <option value="">视频生产工作台</option>
                    )}
                    {productions.map((production) => (
                      <option key={production.id} value={production.id}>
                        {production.title}
                      </option>
                    ))}
                  </select>
                )}
                <p className="truncate text-[8px] font-semibold text-[#397461]">
                  一句话创作 · 随时人工接管
                </p>
              </div>
            </div>

            <div className="min-w-0 px-3">
              <StageRail
                workbench={workbench}
                activeView={activeView}
                onSelect={setActiveView}
              />
            </div>

            <div />
          </header>

          <div
            className={cn(
              "grid min-h-0 flex-1",
              immersiveStageActive
                ? "grid-cols-[minmax(0,1fr)]"
                : "grid-cols-[160px_minmax(0,1fr)_200px] xl:grid-cols-[230px_minmax(520px,1fr)_290px]",
            )}
          >
            {!immersiveStageActive && (
              <aside
                aria-label={setupStageActive ? "设定图候选" : "项目与镜头"}
                className="flex min-h-0 flex-col border-r border-[#3f352b]/12 bg-[#faf8f2]/60"
              >
                <div className="flex h-12 items-center justify-between border-b border-[#3f352b]/10 px-3">
                  <Button
                    size="icon-sm"
                    variant="outline"
                    aria-label={setupStageActive ? "设定图列表" : "镜头列表"}
                    className="border-[#3f352b]/12 bg-white/55"
                  >
                    {setupStageActive ? <ImageIcon /> : <Layers3Icon />}
                  </Button>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-[#79736a]">
                      {setupStageActive
                        ? `${setupItems.filter((item) => item.artifact).length} 张`
                        : `${workbench?.shots.length ?? 0} 镜`}
                    </span>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      aria-label="刷新制作列表"
                      onClick={() => void productionsQuery.refetch()}
                    >
                      <RefreshCcwIcon
                        className={cn(
                          productionsQuery.isFetching && "animate-spin",
                        )}
                      />
                    </Button>
                    <Button
                      asChild={!setupStageActive}
                      size="icon-sm"
                      variant="outline"
                      className="border-[#3f352b]/12 bg-white/55"
                      aria-label={
                        setupStageActive ? "生成新设定图" : "新增视频制作"
                      }
                      onClick={
                        setupStageActive
                          ? () => setActiveView("overview")
                          : undefined
                      }
                    >
                      {setupStageActive ? (
                        <span className="text-lg leading-none">+</span>
                      ) : (
                        <Link
                          href="/workspace/chats/new"
                          aria-label="新建视频任务"
                        >
                          <span className="text-lg leading-none">+</span>
                        </Link>
                      )}
                    </Button>
                  </div>
                </div>
                <ScrollArea className="min-h-0 flex-1">
                  <div className="space-y-2 p-2.5">
                    {setupStageActive ? (
                      setupItems.length === 0 ? (
                        <button
                          type="button"
                          onClick={() => setActiveView("overview")}
                          className="w-full rounded-xl border border-dashed border-[#3f352b]/15 p-4 text-center text-[10px] text-[#79736a]"
                        >
                          还没有设定图
                          <span className="mt-1 block font-semibold text-[#a45b48]">
                            去和智能体生成第一批
                          </span>
                        </button>
                      ) : (
                        setupItems.map((item, index) => {
                          const mediaRef = displayableMediaRef(
                            item.artifact,
                            workbench?.production.id,
                          );
                          const isSelected =
                            item.key === selectedSetupPreviewKey;
                          return (
                            <div
                              key={item.key}
                              className={cn(
                                "group/setup-thumb grid h-[72px] w-full grid-cols-[66px_minmax(0,1fr)] items-center gap-1.5 rounded-xl border p-1.5 text-left transition xl:h-[82px] xl:grid-cols-[94px_minmax(0,1fr)] xl:gap-2",
                                isSelected
                                  ? "border-[#ef6b48] bg-[#fff6ee] shadow-[0_8px_22px_-18px_rgba(180,74,43,0.8)]"
                                  : "border-[#3f352b]/10 bg-white/45 hover:bg-white/75",
                              )}
                            >
                              <span className="relative size-full min-h-0">
                                <button
                                  type="button"
                                  aria-label={`查看${
                                    ENTITY_LABELS[item.asset.entity_type] ??
                                    "素材"
                                  }设定 ${friendlyAssetName(item.asset)} V${
                                    item.artifactIndex + 1
                                  }`}
                                  onClick={() => selectSetupPreview(item.key)}
                                  className={cn(
                                    "relative size-full overflow-hidden rounded-lg bg-gradient-to-br",
                                    index % 4 === 0 &&
                                      "from-[#57473f] to-[#c49a7e]",
                                    index % 4 === 1 &&
                                      "from-[#1d3440] to-[#8398a2]",
                                    index % 4 === 2 &&
                                      "from-[#4d2b3f] to-[#c0786c]",
                                    index % 4 === 3 &&
                                      "from-[#29423d] to-[#93a28c]",
                                  )}
                                  style={
                                    mediaRef
                                      ? {
                                          backgroundImage: `url(${JSON.stringify(mediaRef)})`,
                                          backgroundPosition: "center",
                                          backgroundSize: "cover",
                                        }
                                      : undefined
                                  }
                                >
                                  <i
                                    className={cn(
                                      "absolute top-1 left-1 rounded px-1 py-0.5 text-[8px] text-white not-italic",
                                      isSelected
                                        ? "bg-[#ef6b48]"
                                        : "bg-black/45",
                                    )}
                                  >
                                    V{item.artifactIndex + 1}
                                  </i>
                                  {!mediaRef && (
                                    <span className="absolute inset-0 flex items-center justify-center text-white/70">
                                      <ImageIcon className="size-5" />
                                    </span>
                                  )}
                                </button>
                                <span className="pointer-events-none absolute inset-x-1 bottom-1 z-10 grid translate-y-1 grid-cols-3 gap-0.5 opacity-0 transition duration-150 group-focus-within/setup-thumb:pointer-events-auto group-focus-within/setup-thumb:translate-y-0 group-focus-within/setup-thumb:opacity-100 group-hover/setup-thumb:pointer-events-auto group-hover/setup-thumb:translate-y-0 group-hover/setup-thumb:opacity-100">
                                  <button
                                    type="button"
                                    disabled={!item.artifact}
                                    title="采用此图"
                                    aria-label={`采用 ${friendlyAssetName(item.asset)}`}
                                    onClick={() => {
                                      setSelectedSetupPreviewKey(item.key);
                                      setActiveView("overview");
                                      setSetupQuickAction(
                                        setupAdoptAction(item),
                                      );
                                    }}
                                    className="h-5 rounded bg-black/65 text-[7px] font-semibold text-white backdrop-blur hover:bg-[#397461] disabled:opacity-40"
                                  >
                                    采用
                                  </button>
                                  <button
                                    type="button"
                                    disabled={!item.artifact}
                                    title="加入素材库"
                                    aria-label={`将 ${friendlyAssetName(item.asset)} 加入素材库`}
                                    onClick={() => {
                                      setSelectedSetupPreviewKey(item.key);
                                      setActiveView("overview");
                                      setSetupQuickAction(
                                        setupLibraryAction(item),
                                      );
                                    }}
                                    className="h-5 rounded bg-black/65 text-[7px] font-semibold text-white backdrop-blur hover:bg-[#397461] disabled:opacity-40"
                                  >
                                    入库
                                  </button>
                                  <button
                                    type="button"
                                    title="生成新版本"
                                    aria-label={`为 ${friendlyAssetName(item.asset)} 生成新版本`}
                                    onClick={() => {
                                      setSelectedSetupPreviewKey(item.key);
                                      setActiveView("overview");
                                      setSetupQuickAction(
                                        setupNewVersionAction(item),
                                      );
                                    }}
                                    className="h-5 rounded bg-black/65 text-[7px] font-semibold text-white backdrop-blur hover:bg-[#a94d3a]"
                                  >
                                    新版
                                  </button>
                                </span>
                              </span>
                              <button
                                type="button"
                                onClick={() => selectSetupPreview(item.key)}
                                className="min-w-0 px-1 text-left"
                              >
                                <strong className="block truncate text-[11px]">
                                  {friendlyAssetName(item.asset)}
                                </strong>
                                <small className="mt-1 block truncate text-[9px] text-[#79736a]">
                                  {ENTITY_LABELS[item.asset.entity_type] ??
                                    "素材"}{" "}
                                  · {item.artifact ? "已生成" : "等待生成"}
                                </small>
                              </button>
                            </div>
                          );
                        })
                      )
                    ) : !workbench || workbench.shots.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-[#3f352b]/15 p-4 text-center text-[10px] text-[#79736a]">
                        分镜生成后会显示在这里
                      </div>
                    ) : (
                      workbench.shots.map((shot, index) => {
                        const candidate =
                          workbench.candidates.find(
                            (item) => item.shot_id === shot.id && item.selected,
                          ) ??
                          workbench.candidates.find(
                            (item) => item.shot_id === shot.id,
                          );
                        const mediaRef = displayableMediaRef(
                          candidate?.artifacts[0],
                          workbench.production.id,
                        );
                        const isSelected = shot.id === selectedShotId;
                        return (
                          <button
                            key={shot.id}
                            type="button"
                            aria-label={`查看${friendlyShotName(workbench, shot.id)}`}
                            onClick={() => {
                              setSelectedShotId(shot.id);
                              setActiveView("storyboard");
                            }}
                            className={cn(
                              "group grid h-[72px] w-full grid-cols-[66px_minmax(0,1fr)] items-center gap-1.5 rounded-xl border p-1.5 text-left transition xl:h-[82px] xl:grid-cols-[94px_minmax(0,1fr)] xl:gap-2",
                              isSelected
                                ? "border-[#ef6b48] bg-[#fff6ee] shadow-[0_8px_22px_-18px_rgba(180,74,43,0.8)]"
                                : "border-[#3f352b]/10 bg-white/45 hover:bg-white/75",
                            )}
                          >
                            <span
                              className={cn(
                                "relative size-full overflow-hidden rounded-lg bg-gradient-to-br",
                                index % 4 === 0 &&
                                  "from-[#182a3b] to-[#80504d]",
                                index % 4 === 1 &&
                                  "from-[#14243a] to-[#718494]",
                                index % 4 === 2 &&
                                  "from-[#392137] to-[#bb675d]",
                                index % 4 === 3 &&
                                  "from-[#183832] to-[#839278]",
                              )}
                              style={
                                mediaRef
                                  ? {
                                      backgroundImage: `url(${JSON.stringify(mediaRef)})`,
                                      backgroundPosition: "center",
                                      backgroundSize: "cover",
                                    }
                                  : undefined
                              }
                            >
                              <i
                                className={cn(
                                  "absolute top-1 left-1 rounded px-1 py-0.5 text-[8px] text-white not-italic",
                                  isSelected ? "bg-[#ef6b48]" : "bg-black/45",
                                )}
                              >
                                {String(shot.spec.order ?? index + 1).padStart(
                                  2,
                                  "0",
                                )}
                              </i>
                            </span>
                            <span className="min-w-0 px-1">
                              <strong className="block truncate text-[11px]">
                                {friendlyShotName(workbench, shot.id)}
                              </strong>
                              <small className="mt-1 block truncate text-[9px] text-[#79736a]">
                                {shot.spec.duration_seconds ?? "—"}s ·{" "}
                                {shot.candidate_ids.length} 个候选
                              </small>
                            </span>
                          </button>
                        );
                      })
                    )}
                  </div>
                </ScrollArea>
              </aside>
            )}

            <WorkbenchConversationBoundary
              workbench={workbench}
              taskThreadId={taskThreadId}
            >
              <main className="flex min-h-0 min-w-0 flex-col bg-[#f7f3ec]">
                <div className="min-h-0 flex-1 overflow-y-auto">
                  {!selectedId ? (
                    <EmptyDirectorCanvas
                      loading={productionsQuery.isLoading}
                      failed={productionsQuery.isError}
                    />
                  ) : workbenchQuery.isLoading ? (
                    <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-[#79736a]">
                      <LoaderCircleIcon className="size-5 animate-spin" />{" "}
                      正在打开视频项目…
                    </div>
                  ) : workbenchQuery.isError || !workbenchQuery.data ? (
                    <div className="p-5">
                      <EmptyPanel>
                        视频项目暂时无法打开，请稍后重试。
                      </EmptyPanel>
                    </div>
                  ) : (
                    <WorkbenchDetail
                      workbench={workbenchQuery.data}
                      activeView={activeView}
                      onActiveViewChange={setActiveView}
                      selectedShotId={selectedShotId}
                      selectedSetupPreviewKey={selectedSetupPreviewKey}
                      onSelectSetupPreview={selectSetupPreview}
                      setupCommand={setupCommand}
                      onSetupCommandChange={setSetupCommand}
                      setupQuickAction={setupQuickAction}
                      onSetupQuickAction={setSetupQuickAction}
                      onSetupQuickActionConsumed={(id) =>
                        setSetupQuickAction((current) =>
                          current?.id === id ? null : current,
                        )
                      }
                    />
                  )}
                </div>
                {editStageActive ? (
                  workbench ? (
                    <CompactTimelineDock
                      workbench={workbench}
                      onOpen={() => setActiveView("timeline")}
                      expanded
                      agentCommand={timelineCommand}
                      onAgentCommandChange={setTimelineCommand}
                      quickAction={timelineQuickAction}
                      onQuickAction={setTimelineQuickAction}
                      onQuickActionConsumed={(id) =>
                        setTimelineQuickAction((current) =>
                          current?.id === id ? null : current,
                        )
                      }
                    />
                  ) : (
                    <EmptyTimelineDock />
                  )
                ) : null}
              </main>
            </WorkbenchConversationBoundary>

            {!immersiveStageActive &&
              (workbench ? (
                <ReferenceSidebar
                  workbench={workbench}
                  onOpen={setActiveView}
                />
              ) : (
                <EmptyReferenceSidebar />
              ))}
          </div>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}

export default function PersonalIPVideoWorkbenchPage() {
  return <PersonalIPVideoWorkbench />;
}
