"use client";

import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  BotIcon,
  BoxesIcon,
  CheckCircle2Icon,
  ChevronRightIcon,
  CircleDollarSignIcon,
  ClapperboardIcon,
  ClipboardCopyIcon,
  FilmIcon,
  GaugeIcon,
  ImageIcon,
  Layers3Icon,
  LoaderCircleIcon,
  MessageSquareTextIcon,
  Music2Icon,
  PackageCheckIcon,
  RefreshCcwIcon,
  SearchIcon,
  ShieldCheckIcon,
  SparklesIcon,
  VideoIcon,
  XCircleIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import {
  type PersonalIPVideoProduction,
  type PersonalIPVideoWorkbench,
  type VideoArtifact,
  type VideoProductionStatus,
  type VideoWorkbenchConfirmation,
  type VideoWorkbenchTask,
  formatVideoCost,
  usePersonalIPVideoProductions,
  usePersonalIPVideoWorkbench,
  useRecordVideoConfirmation,
  videoRecoveryPrompt,
} from "@/core/personal-ip";
import { cn } from "@/lib/utils";

const STATUS_LABELS: Record<VideoProductionStatus, string> = {
  draft: "待启动",
  running: "制作中",
  awaiting_review: "待确认",
  blocked: "受阻",
  completed: "已交付",
  cancelled: "已取消",
};

const ENTITY_LABELS: Record<string, string> = {
  character: "角色",
  scene: "场景",
  prop: "道具",
  shot: "镜头",
  candidate: "候选片段",
  audio: "音频",
  timeline: "时间线",
  delivery: "交付",
  production: "制作",
};

const EVENT_LABELS: Record<string, string> = {
  blueprint_sealed: "蓝图已封存",
  asset_registered: "资产已登记",
  asset_generation_requested: "资产生成中",
  asset_generation_completed: "资产已生成",
  asset_generation_failed: "资产生成失败",
  storyboard_sealed: "分镜已封存",
  shot_generation_requested: "镜头生成中",
  shot_generation_completed: "镜头候选已生成",
  shot_generation_failed: "镜头生成失败",
  consistency_checked: "一致性已检查",
  candidate_selected: "候选已选用",
  review_requested: "等待确认",
  review_recorded: "确认已记录",
  voice_generated: "配音已生成",
  voice_generation_requested: "配音生成中",
  media_processing_requested: "媒体处理中",
  media_processing_completed: "媒体处理完成",
  media_processing_failed: "媒体处理失败",
  edit_completed: "剪辑完成",
  delivery_qa_completed: "交付 QA 完成",
  delivery_completed: "交付完成",
};

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

function ProjectButton({
  production,
  selected,
  onClick,
}: {
  production: PersonalIPVideoProduction;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group w-full rounded-xl border p-3 text-left transition",
        selected
          ? "border-primary/35 bg-primary/[0.06] shadow-sm"
          : "bg-card hover:border-primary/20 hover:bg-muted/45",
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border",
            selected ? "bg-primary text-primary-foreground" : "bg-muted",
          )}
        >
          <FilmIcon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <p className="line-clamp-2 flex-1 text-sm leading-5 font-medium">
              {production.title}
            </p>
            <ChevronRightIcon className="text-muted-foreground mt-0.5 size-4 shrink-0 transition group-hover:translate-x-0.5" />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <Badge variant={statusBadge(production.status)}>
              {STATUS_LABELS[production.status]}
            </Badge>
            <span className="text-muted-foreground text-[11px]">
              {production.event_count} 条事件
            </span>
          </div>
          <p className="text-muted-foreground mt-2 text-[11px]">
            更新于 {formatTime(production.updated_at)}
          </p>
        </div>
      </div>
    </button>
  );
}

function StageRail({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  return (
    <ScrollArea className="w-full">
      <div className="grid min-w-[900px] grid-cols-9 gap-2 pb-2">
        {workbench.stage_summary.map((stage, index) => {
          const attention = stage.ledger_state === "attention";
          const active = stage.ledger_state === "current";
          const recorded = ["complete", "recorded"].includes(
            stage.ledger_state,
          );
          return (
            <div key={stage.id} className="relative">
              {index < workbench.stage_summary.length - 1 && (
                <div className="bg-border absolute top-4 left-[58%] h-px w-[88%]" />
              )}
              <div
                className={cn(
                  "relative rounded-xl border px-3 py-3",
                  attention && "border-amber-400/60 bg-amber-500/[0.08]",
                  active && "border-primary/40 bg-primary/[0.06]",
                  recorded && "bg-muted/45",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      "flex size-7 items-center justify-center rounded-full border text-[10px] font-semibold tabular-nums",
                      recorded &&
                        "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
                      attention &&
                        "border-amber-500/40 text-amber-700 dark:text-amber-300",
                    )}
                  >
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="text-muted-foreground text-[10px] tabular-nums">
                    {stage.event_count}
                  </span>
                </div>
                <p className="mt-2 text-xs font-medium">{stage.label}</p>
              </div>
            </div>
          );
        })}
      </div>
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
              "DeerFlow 已暂停在需要用户承担实际选择或费用的检查点。"}
          </p>
          <p className="text-muted-foreground mt-2 font-mono text-[10px]">
            {confirmation.event_key}
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

function TaskCard({
  task,
  productionId,
}: {
  task: VideoWorkbenchTask;
  productionId: string;
}) {
  const failed = task.status === "failed";
  const copyRecovery = async () => {
    const prompt = videoRecoveryPrompt({
      productionId,
      eventKey: task.event_key ?? task.id,
      entityId: task.entity_id ?? "unknown",
    });
    await navigator.clipboard.writeText(prompt);
    toast.success("恢复指令已复制，可交给 DeerFlow 继续执行");
  };
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
            <Button
              size="sm"
              variant="outline"
              onClick={() => void copyRecovery()}
            >
              <ClipboardCopyIcon /> 复制恢复指令
            </Button>
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

function OverviewTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  const sourceText = Object.values(workbench.source.content).find(
    (value) => typeof value === "string",
  );
  return (
    <div className="grid gap-4 xl:grid-cols-[1.3fr_1fr]">
      <div className="space-y-4">
        <Card className="gap-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <MessageSquareTextIcon className="size-4" />
              {workbench.source.kind === "script" ? "原始剧本" : "创意输入"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-7 whitespace-pre-wrap">
              {typeof sourceText === "string"
                ? sourceText
                : jsonText(workbench.source.content)}
            </p>
          </CardContent>
        </Card>
        <Card className="gap-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <SparklesIcon className="size-4" /> 影视蓝图
            </CardTitle>
          </CardHeader>
          <CardContent>
            {workbench.blueprint.artifacts.length > 0 ? (
              <ArtifactList artifacts={workbench.blueprint.artifacts} />
            ) : (
              <EmptyPanel>蓝图事件尚未进入账本。</EmptyPanel>
            )}
          </CardContent>
        </Card>
      </div>
      <div className="space-y-4">
        <Snapshot
          title="Delivery spec"
          value={workbench.production.delivery_spec}
        />
        <Snapshot
          title="Provider policy"
          value={workbench.production.provider_policy}
        />
        <Snapshot
          title="Budget / approval gate"
          value={workbench.production.budget}
        />
      </div>
    </div>
  );
}

function AssetsTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  if (workbench.assets.length === 0)
    return <EmptyPanel>角色、场景和道具资产尚未写入账本。</EmptyPanel>;
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {workbench.assets.map((asset) => (
        <Card key={`${asset.entity_type}:${asset.id}`} className="gap-4 py-4">
          <CardHeader className="px-4">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                {asset.entity_type === "character" ? (
                  <SparklesIcon className="size-4" />
                ) : asset.entity_type === "scene" ? (
                  <ImageIcon className="size-4" />
                ) : (
                  <BoxesIcon className="size-4" />
                )}
                <CardTitle className="truncate text-sm">{asset.id}</CardTitle>
              </div>
              <Badge variant={statusBadge(asset.status)}>{asset.status}</Badge>
            </div>
            <p className="text-muted-foreground text-xs">
              {ENTITY_LABELS[asset.entity_type]}
            </p>
          </CardHeader>
          <CardContent className="px-4">
            <ArtifactList artifacts={asset.artifacts} compact />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function StoryboardTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">
          {workbench.storyboard.shot_count} 个分镜
        </Badge>
        <Badge variant="outline">{workbench.candidates.length} 个候选</Badge>
        <Badge variant="outline">
          {workbench.tasks.filter((task) => task.shot_id).length} 条逐镜任务
        </Badge>
      </div>
      {workbench.storyboard.artifacts.length > 0 && (
        <ArtifactList artifacts={workbench.storyboard.artifacts} compact />
      )}
      {workbench.shots.length === 0 ? (
        <EmptyPanel>分镜已可封存，但尚未解析出镜头实体。</EmptyPanel>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {workbench.shots.map((shot, index) => (
            <Card key={shot.id} className="gap-3 py-4">
              <CardHeader className="px-4">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-sm">
                    镜头 {String(index + 1).padStart(2, "0")}
                  </CardTitle>
                  <VideoIcon className="text-muted-foreground size-4" />
                </div>
                <code className="text-muted-foreground text-[11px]">
                  {shot.id}
                </code>
              </CardHeader>
              <CardContent className="grid grid-cols-3 gap-2 px-4 text-center">
                <EvidenceField label="任务" value={shot.task_ids.length} />
                <EvidenceField label="候选" value={shot.candidate_ids.length} />
                <EvidenceField
                  label="选片"
                  value={shot.selected_candidate_id ? "已选" : "待定"}
                />
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function TasksTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  if (workbench.tasks.length === 0)
    return <EmptyPanel>还没有 provider 任务回执。</EmptyPanel>;
  return (
    <div className="space-y-3">
      {workbench.tasks.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          productionId={workbench.production.id}
        />
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

function TimelineTab({ workbench }: { workbench: PersonalIPVideoWorkbench }) {
  const finishingTasks = workbench.tasks.filter(
    (task) => task.stage === "finishing",
  );
  return (
    <div className="space-y-5">
      <Card className="gap-4">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers3Icon className="size-4" /> 时间线轨道
          </CardTitle>
        </CardHeader>
        <CardContent>
          {workbench.timeline.tracks.length === 0 ? (
            <EmptyPanel>配音、片段与剪辑回执会组成只读时间线。</EmptyPanel>
          ) : (
            <div className="overflow-hidden rounded-xl border">
              {(["video", "audio"] as const).map((type) => {
                const tracks = workbench.timeline.tracks.filter(
                  (track) => track.type === type,
                );
                return (
                  <div
                    key={type}
                    className="grid grid-cols-[96px_1fr] border-b last:border-b-0"
                  >
                    <div className="bg-muted/50 flex items-center gap-2 border-r px-3 py-4 text-xs font-medium">
                      {type === "video" ? (
                        <FilmIcon className="size-4" />
                      ) : (
                        <Music2Icon className="size-4" />
                      )}
                      {type === "video" ? "视频" : "音频"}
                    </div>
                    <div className="flex min-h-16 flex-wrap items-center gap-2 p-3">
                      {tracks.length === 0 ? (
                        <span className="text-muted-foreground text-xs">
                          暂无轨道片段
                        </span>
                      ) : (
                        tracks.map((track) => (
                          <div
                            key={track.event_id}
                            className="bg-primary/[0.06] min-w-40 rounded-lg border px-3 py-2"
                          >
                            <p className="truncate text-xs font-medium">
                              {track.entity_id}
                            </p>
                            <p className="text-muted-foreground mt-1 text-[10px]">
                              {track.status} · {track.artifacts.length} 个产物
                            </p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
      <div className="space-y-3">
        {finishingTasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            productionId={workbench.production.id}
          />
        ))}
      </div>
    </div>
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
  const latestQa = workbench.delivery.qa_events.at(-1);
  const payload = latestQa?.payload ?? {};
  const checks = payload.checks;
  const checkEntries =
    checks && typeof checks === "object" ? Object.entries(checks) : [];
  const publishConfirmations = workbench.confirmations.filter(
    (item) => item.kind === "real_publish",
  );
  return (
    <div className="space-y-4">
      {publishConfirmations.map((confirmation) => (
        <ConfirmationCard
          key={confirmation.id}
          confirmation={confirmation}
          pending={reviewPending}
          onDecision={(decision) => onDecision(confirmation, decision)}
        />
      ))}
      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card
          className={cn(
            "gap-4",
            workbench.delivery.qa_passed
              ? "border-emerald-500/40"
              : "border-amber-500/40",
          )}
        >
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <GaugeIcon className="size-4" /> 交付 QA
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
                  ? "通过"
                  : workbench.delivery.qa_passed === false
                    ? "未通过"
                    : "未执行"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <code className="bg-muted block rounded-lg border px-3 py-2 text-xs">
              {typeof payload.contract_version === "string"
                ? payload.contract_version
                : "personal-ip-delivery-qa-v1"}
            </code>
            <div className="space-y-2">
              {checkEntries.map(([key, raw]) => {
                const detail =
                  raw && typeof raw === "object"
                    ? (raw as Record<string, unknown>)
                    : { passed: raw };
                const passed = detail.passed === true;
                return (
                  <div
                    key={key}
                    className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-xs"
                  >
                    <span>{key}</span>
                    <Badge variant={passed ? "outline" : "destructive"}>
                      {passed ? "通过" : "未通过"}
                    </Badge>
                  </div>
                );
              })}
            </div>
            <p className="text-muted-foreground text-xs">
              只有成功 QA 覆盖完全相同的 output refs 后，账本才允许写入
              delivery_completed。
            </p>
          </CardContent>
        </Card>
        <Card className="gap-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <PackageCheckIcon className="size-4" /> 交付产物
            </CardTitle>
          </CardHeader>
          <CardContent>
            {workbench.delivery.artifacts.length > 0 ? (
              <ArtifactList artifacts={workbench.delivery.artifacts} />
            ) : (
              <EmptyPanel>最终成片尚未进入交付回执。</EmptyPanel>
            )}
          </CardContent>
        </Card>
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

function WorkbenchDetail({
  workbench,
}: {
  workbench: PersonalIPVideoWorkbench;
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
      .catch((error: unknown) =>
        toast.error(error instanceof Error ? error.message : String(error)),
      );
  };
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold tracking-tight">
              {workbench.production.title}
            </h2>
            <Badge variant={statusBadge(workbench.production.status)}>
              {STATUS_LABELS[workbench.production.status]}
            </Badge>
          </div>
          <p className="text-muted-foreground mt-2 font-mono text-[11px]">
            {workbench.production.id}
          </p>
        </div>
        <Button asChild>
          <Link href="/workspace/chats">
            <BotIcon /> 回到 DeerFlow 推进
          </Link>
        </Button>
      </div>

      <StageRail workbench={workbench} />

      <Tabs defaultValue="overview" className="min-w-0">
        <ScrollArea className="w-full border-b">
          <TabsList variant="line" className="h-11 min-w-max justify-start">
            <TabsTrigger value="overview">总览</TabsTrigger>
            <TabsTrigger value="assets">资产</TabsTrigger>
            <TabsTrigger value="storyboard">分镜</TabsTrigger>
            <TabsTrigger value="tasks">任务与重试</TabsTrigger>
            <TabsTrigger value="candidates">候选与一致性</TabsTrigger>
            <TabsTrigger value="timeline">配音与时间线</TabsTrigger>
            <TabsTrigger value="delivery">交付 QA</TabsTrigger>
            <TabsTrigger value="receipts">回执明细</TabsTrigger>
          </TabsList>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>
        <TabsContent value="overview" className="pt-4">
          <OverviewTab workbench={workbench} />
        </TabsContent>
        <TabsContent value="assets" className="pt-4">
          <AssetsTab workbench={workbench} />
        </TabsContent>
        <TabsContent value="storyboard" className="pt-4">
          <StoryboardTab workbench={workbench} />
        </TabsContent>
        <TabsContent value="tasks" className="pt-4">
          <TasksTab workbench={workbench} />
        </TabsContent>
        <TabsContent value="candidates" className="pt-4">
          <CandidatesTab
            workbench={workbench}
            reviewPending={reviewMutation.isPending}
            onDecision={decide}
          />
        </TabsContent>
        <TabsContent value="timeline" className="pt-4">
          <TimelineTab workbench={workbench} />
        </TabsContent>
        <TabsContent value="delivery" className="pt-4">
          <DeliveryTab
            workbench={workbench}
            reviewPending={reviewMutation.isPending}
            onDecision={decide}
          />
        </TabsContent>
        <TabsContent value="receipts" className="pt-4">
          <ReceiptsTab workbench={workbench} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function PersonalIPVideoWorkbenchPage() {
  const productionsQuery = usePersonalIPVideoProductions();
  const productions = useMemo(
    () => productionsQuery.data ?? [],
    [productionsQuery.data],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    document.title = "视频生产工作台 - IP Agent";
  }, []);
  useEffect(() => {
    if (!selectedId && productions[0]) setSelectedId(productions[0].id);
    if (
      selectedId &&
      productions.length > 0 &&
      !productions.some((item) => item.id === selectedId)
    ) {
      setSelectedId(productions[0]?.id ?? null);
    }
  }, [productions, selectedId]);

  const workbenchQuery = usePersonalIPVideoWorkbench(selectedId);
  const filtered = productions.filter((production) =>
    production.title
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  );

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-hidden">
        <div className="flex h-full w-full flex-col bg-[radial-gradient(circle_at_top_right,rgba(59,130,246,0.08),transparent_28%),radial-gradient(circle_at_bottom_left,rgba(16,185,129,0.06),transparent_25%)]">
          <div className="bg-background/75 border-b px-5 py-5 backdrop-blur lg:px-8">
            <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-start justify-between gap-4">
              <div>
                <Link
                  href="/workspace/personal-ip"
                  className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
                >
                  <ArrowLeftIcon className="size-3.5" /> 返回经营组合
                </Link>
                <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-tight">
                  <ClapperboardIcon className="size-6" /> 视频生产工作台
                </h1>
                <p className="text-muted-foreground mt-2 max-w-3xl text-sm leading-6">
                  项目、资产、镜头、失败重试、选片、时间线与交付 QA
                  全部从同一条不可变事件账本读取；创建和推进仍由 DeerFlow
                  对话完成。
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">
                  <ShieldCheckIcon /> 账本派生 · 不创建第二套状态
                </Badge>
                <Badge variant="outline">
                  <CircleDollarSignIcon /> 真实付费需确认
                </Badge>
              </div>
            </div>
          </div>

          <div className="mx-auto grid min-h-0 w-full max-w-[1600px] flex-1 grid-cols-1 lg:grid-cols-[300px_minmax(0,1fr)]">
            <aside className="bg-background/70 flex min-h-0 flex-col border-r backdrop-blur">
              <div className="space-y-3 border-b p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold">制作列表</p>
                    <p className="text-muted-foreground mt-0.5 text-[11px]">
                      {productions.length} 个项目
                    </p>
                  </div>
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
                </div>
                <div className="relative">
                  <SearchIcon className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
                  <Input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="搜索制作"
                    className="pl-9"
                  />
                </div>
              </div>
              <ScrollArea className="min-h-0 flex-1">
                <div className="space-y-2 p-3">
                  {productionsQuery.isLoading ? (
                    <div className="text-muted-foreground flex items-center justify-center gap-2 py-12 text-sm">
                      <LoaderCircleIcon className="size-4 animate-spin" />{" "}
                      正在读取账本…
                    </div>
                  ) : productionsQuery.isError ? (
                    <EmptyPanel>制作列表暂时无法读取。</EmptyPanel>
                  ) : filtered.length === 0 ? (
                    <EmptyPanel>
                      {productions.length === 0
                        ? "还没有视频制作。请在 DeerFlow 对话中创建第一条 production。"
                        : "没有匹配的制作。"}
                    </EmptyPanel>
                  ) : (
                    filtered.map((production) => (
                      <ProjectButton
                        key={production.id}
                        production={production}
                        selected={production.id === selectedId}
                        onClick={() => setSelectedId(production.id)}
                      />
                    ))
                  )}
                </div>
              </ScrollArea>
            </aside>

            <main className="min-h-0 min-w-0 overflow-y-auto">
              <div className="mx-auto w-full max-w-[1280px] p-5 lg:p-7 xl:p-8">
                {!selectedId ? (
                  <EmptyPanel>从左侧选择一个视频制作。</EmptyPanel>
                ) : workbenchQuery.isLoading ? (
                  <div className="text-muted-foreground flex min-h-72 items-center justify-center gap-2 text-sm">
                    <LoaderCircleIcon className="size-5 animate-spin" />{" "}
                    正在折叠制作事件…
                  </div>
                ) : workbenchQuery.isError || !workbenchQuery.data ? (
                  <EmptyPanel>
                    工作台读模型暂时不可用；原始账本没有被修改。
                  </EmptyPanel>
                ) : (
                  <WorkbenchDetail workbench={workbenchQuery.data} />
                )}
              </div>
            </main>
          </div>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
