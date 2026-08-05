"use client";

import {
  ArrowRightIcon,
  BookOpenTextIcon,
  ClapperboardIcon,
  DownloadIcon,
  FileSearchIcon,
  Layers3Icon,
  LoaderCircleIcon,
  MessageSquareTextIcon,
  PenLineIcon,
  RefreshCcwIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FinalArtifactContentImport } from "@/components/workspace/personal-ip/final-artifact-content-import";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import {
  type ContentEntryRoute,
  type ContentTruthMode,
  type EditorialProgramProjection,
  type PersonalIPContentLineage,
  type PersonalIPContentWork,
  type PersonalIPVideoProduction,
  type VideoProductionStage,
  type VideoProductionStatus,
  formatPersonalIPFinalArtifactSize,
  personalIPContentTaskHref,
  personalIPFinalArtifactContentURL,
  personalIPProductionTaskHref,
  projectPersonalIPEditorialProgram,
  selectPersonalIPFinalArtifact,
  selectPersonalIPFinalArtifactReceipt,
  usePersonalIPContentLineage,
  usePersonalIPContentWorks,
  usePersonalIPVideoProductions,
} from "@/core/personal-ip";
import { cn } from "@/lib/utils";

type WorkFilter = "all" | ContentEntryRoute;

const ENTRY_ROUTE_LABELS: Record<ContentEntryRoute, string> = {
  zero_start: "零起盘",
  benchmark: "对标拆解",
};

const TRUTH_MODE_LABELS: Record<ContentTruthMode, string> = {
  factual: "事实内容",
  fictional: "虚构创作",
  hybrid: "事实与虚构混合",
};

const SOURCE_KIND_LABELS: Record<
  PersonalIPContentLineage["breakdown_versions"][number]["source_kind"],
  string
> = {
  platform_content: "平台作品",
  uploaded_file: "上传文件",
  owner_material: "Owner 素材",
};

const PRODUCTION_STATUS_LABELS: Record<VideoProductionStatus, string> = {
  draft: "草稿",
  running: "制作中",
  awaiting_review: "待审核",
  blocked: "已阻塞",
  completed: "已完成",
  cancelled: "已取消",
};

const PRODUCTION_STAGE_LABELS: Record<VideoProductionStage, string> = {
  intake: "需求接收",
  blueprint: "制作蓝图",
  assets: "素材",
  storyboard: "分镜",
  generation: "生成",
  consistency: "一致性",
  selection: "选片",
  finishing: "后期",
  delivery: "交付",
};

function latestVersion<T extends { version_number: number }>(
  versions: T[],
): T | undefined {
  let latest: T | undefined;
  for (const version of versions) {
    if (!latest || version.version_number > latest.version_number) {
      latest = version;
    }
  }
  return latest;
}

function formatTimestamp(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "时间未返回";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function textOrMissing(value: string | null | undefined) {
  if (!value) return "未填写";
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : "未填写";
}

function excerpt(value: string, limit = 360) {
  const text = value.trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}…`;
}

function EntryCard({
  entryRoute,
  title,
  description,
  icon: Icon,
}: {
  entryRoute: ContentEntryRoute;
  title: string;
  description: string;
  icon: typeof SparklesIcon;
}) {
  return (
    <Card className="gap-4 py-5">
      <CardHeader className="px-5">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1.5">
            <CardTitle className="text-base">{title}</CardTitle>
            <CardDescription className="leading-5">
              {description}
            </CardDescription>
          </div>
          <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-xl">
            <Icon className="size-4" />
          </span>
        </div>
      </CardHeader>
      <CardContent className="px-5">
        <Button asChild size="sm">
          <Link href={personalIPContentTaskHref(entryRoute)}>
            开始任务
            <ArrowRightIcon />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

function StagePanel({
  title,
  subtitle,
  count,
  icon: Icon,
  testId,
  countLabel = "个版本",
  children,
}: {
  title: string;
  subtitle: string;
  count: number;
  icon: typeof FileSearchIcon;
  testId: string;
  countLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="min-w-0 gap-5" data-testid={testId}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2 text-base">
              <Icon className="text-primary size-4" />
              {title}
            </CardTitle>
            <CardDescription className="leading-5">{subtitle}</CardDescription>
          </div>
          <Badge variant="secondary">
            {count} {countLabel}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">{children}</CardContent>
    </Card>
  );
}

function MissingVersion({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-muted-foreground rounded-xl border border-dashed p-4 text-sm leading-6">
      {children}
    </div>
  );
}

function BreakdownPanel({ lineage }: { lineage: PersonalIPContentLineage }) {
  const latest = latestVersion(lineage.breakdown_versions);

  return (
    <StagePanel
      title="Breakdown"
      subtitle="来源观测、解读与限制分开保存。"
      count={lineage.breakdown_versions.length}
      icon={FileSearchIcon}
      testId="content-breakdown-board"
    >
      {!latest ? (
        <MissingVersion>服务端当前没有返回已保存的拆解版本。</MissingVersion>
      ) : (
        <>
          <div className="bg-muted/40 rounded-xl p-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">最新 v{latest.version_number}</span>
              <Badge variant="outline">
                {SOURCE_KIND_LABELS[latest.source_kind]}
              </Badge>
            </div>
            <p className="text-muted-foreground mt-2 text-xs">
              {formatTimestamp(latest.created_at)}
            </p>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="bg-muted/30 rounded-lg p-2">
              <p className="font-mono text-lg tabular-nums">
                {latest.observations.length}
              </p>
              <p className="text-muted-foreground text-[11px]">观测</p>
            </div>
            <div className="bg-muted/30 rounded-lg p-2">
              <p className="font-mono text-lg tabular-nums">
                {latest.interpretations.length}
              </p>
              <p className="text-muted-foreground text-[11px]">解读</p>
            </div>
            <div className="bg-muted/30 rounded-lg p-2">
              <p className="font-mono text-lg tabular-nums">
                {latest.limitations.length}
              </p>
              <p className="text-muted-foreground text-[11px]">限制</p>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-medium">最新观测</p>
            {latest.observations.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                该版本没有保存观测。
              </p>
            ) : (
              <ul className="space-y-2">
                {latest.observations.slice(0, 3).map((item, index) => (
                  <li
                    key={`${latest.id}-observation-${index}`}
                    className="rounded-lg border p-3 text-sm leading-6"
                  >
                    <p className="break-words">{item.observation}</p>
                    <p className="text-muted-foreground mt-1 text-[11px]">
                      {item.evidence_refs.length} 条证据引用
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {latest.interpretations.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium">最新解读</p>
              {latest.interpretations.slice(0, 2).map((item, index) => (
                <div
                  key={`${latest.id}-interpretation-${index}`}
                  className="rounded-lg border p-3 text-sm leading-6"
                >
                  <Badge className="mb-2" variant="outline">
                    {item.state === "derived" ? "派生判断" : "待验假设"}
                  </Badge>
                  <p className="break-words">{item.interpretation}</p>
                </div>
              ))}
            </div>
          )}

          {latest.limitations.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium">已记录限制</p>
              <ul className="text-muted-foreground list-disc space-y-1 pl-4 text-sm leading-6">
                {latest.limitations.slice(0, 3).map((limitation, index) => (
                  <li key={`${latest.id}-limitation-${index}`}>{limitation}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </StagePanel>
  );
}

function EditorialProgramProjectionCard({
  projection,
}: {
  projection: EditorialProgramProjection;
}) {
  return (
    <section
      className="border-primary/25 bg-primary/5 space-y-4 rounded-xl border p-3"
      data-testid="editorial-program-projection"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">当前创作判断</p>
        <Badge variant="secondary">已归纳</Badge>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <div className="bg-background/80 space-y-2 rounded-lg border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground text-[11px]">
              当前任务 / 优先结果
            </p>
            <Badge data-testid="editorial-goal-priority" variant="outline">
              {projection.mission.priorityResult}
            </Badge>
          </div>
          <p className="text-sm leading-6 break-words">
            {projection.mission.currentTask}
          </p>
          <div className="text-muted-foreground space-y-1 text-xs leading-5">
            <p>时间窗口·{projection.mission.timeWindow}</p>
            <p>成功信号·{projection.mission.successSignal}</p>
          </div>
          {projection.mission.nonGoals.length > 0 && (
            <div>
              <p className="text-muted-foreground text-[11px]">本次不做</p>
              <p className="mt-1 text-xs leading-5 break-words">
                {projection.mission.nonGoals.join("、")}
              </p>
            </div>
          )}
        </div>

        <div className="bg-background/80 space-y-2 rounded-lg border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground text-[11px]">当前受众判断</p>
            <Badge data-testid="editorial-audience-state" variant="outline">
              {projection.audience.state}
            </Badge>
          </div>
          <p className="text-sm leading-6 break-words">
            {projection.audience.situation}
          </p>
          {projection.audience.uncertainties.length > 0 && (
            <div>
              <p className="text-muted-foreground text-[11px]">仍待确认</p>
              <p className="mt-1 text-xs leading-5 break-words">
                {projection.audience.uncertainties.join("、")}
              </p>
            </div>
          )}
        </div>

        <div className="bg-background/80 space-y-2 rounded-lg border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-muted-foreground text-[11px]">归因主体</p>
            <Badge data-testid="editorial-carrier-kind" variant="outline">
              {projection.attribution.carrierKind}
            </Badge>
          </div>
          <p className="text-sm leading-6 font-medium break-words">
            {projection.attribution.identity}
          </p>
          <div>
            <p className="text-muted-foreground text-[11px]">希望建立的联想</p>
            <p className="mt-1 text-xs leading-5 break-words">
              {projection.attribution.desiredAssociation}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-background/80 space-y-3 rounded-lg border p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-muted-foreground text-[11px]">差异化假设</p>
          <Badge variant="outline">{projection.differentiation.state}</Badge>
        </div>
        <p className="text-sm leading-6 font-medium break-words">
          {projection.differentiation.statement}
        </p>
        <div className="grid gap-x-4 gap-y-2 text-xs leading-5 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <div>
            <p className="text-muted-foreground text-[11px]">相对区别</p>
            <p className="break-words">{projection.differentiation.contrast}</p>
          </div>
          <div>
            <p className="text-muted-foreground text-[11px]">选择理由</p>
            <p className="break-words">
              {projection.differentiation.reasonToChoose}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground text-[11px]">可信理由</p>
            <p className="break-words">
              {projection.differentiation.reasonToBelieve}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground text-[11px]">主动舍弃</p>
            <p className="break-words">
              {projection.differentiation.sacrifice}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground text-[11px]">验证信号</p>
            <p className="break-words">
              {projection.differentiation.testSignal}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-background/80 space-y-2 rounded-lg border p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-muted-foreground text-[11px]">内容路线</p>
          <Badge data-testid="editorial-route-kind" variant="outline">
            {projection.contentRoute.kind}
          </Badge>
        </div>
        <p className="text-sm leading-6 break-words">
          {projection.contentRoute.description}
        </p>
      </div>

      {projection.editorialSpine && (
        <div
          className="bg-background/80 space-y-2 rounded-lg border p-3"
          data-testid="editorial-spine"
        >
          <p className="text-muted-foreground text-[11px]">长期人类议题</p>
          <p className="text-sm leading-6 font-medium break-words">
            {projection.editorialSpine.humanTheme}
          </p>
          <div>
            <p className="text-muted-foreground text-[11px]">反复追问</p>
            <p className="mt-1 text-xs leading-5 break-words">
              {projection.editorialSpine.recurringQuestion}
            </p>
          </div>
        </div>
      )}
    </section>
  );
}

function WriterBrainPanel({ lineage }: { lineage: PersonalIPContentLineage }) {
  const latestDirection = latestVersion(lineage.direction_versions);
  const latestScript = latestVersion(lineage.script_versions);
  const editorialProgramProjection = projectPersonalIPEditorialProgram(
    lineage.editorial_program_version,
    latestDirection?.direction,
  );
  const totalVersions =
    lineage.direction_versions.length +
    lineage.script_versions.length +
    (lineage.editorial_program_version ? 1 : 0);

  return (
    <StagePanel
      title="Writer Brain"
      subtitle="已保存的任务判断、方向与完整剧本，不用聊天内容代替版本。"
      count={totalVersions}
      icon={BookOpenTextIcon}
      testId="content-writer-brain-board"
    >
      {!editorialProgramProjection && !latestDirection && !latestScript ? (
        <MissingVersion>
          服务端当前没有返回已保存的方向或剧本版本。
        </MissingVersion>
      ) : (
        <>
          {editorialProgramProjection && (
            <EditorialProgramProjectionCard
              projection={editorialProgramProjection}
            />
          )}

          {latestDirection ? (
            <section className="space-y-3 rounded-xl border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">
                  方向 v{latestDirection.version_number}
                </p>
                <Badge variant="outline">
                  {TRUTH_MODE_LABELS[latestDirection.direction.truth_mode]}
                </Badge>
              </div>
              <div className="space-y-2 text-sm leading-6">
                <div>
                  <p className="text-muted-foreground text-[11px]">前提</p>
                  <p className="break-words">
                    {textOrMissing(latestDirection.direction.premise)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground text-[11px]">核心张力</p>
                  <p className="break-words">
                    {textOrMissing(latestDirection.direction.core_tension)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground text-[11px]">内容承诺</p>
                  <p className="break-words">
                    {textOrMissing(latestDirection.direction.content_promise)}
                  </p>
                </div>
              </div>
              <p className="text-muted-foreground text-[11px]">
                {latestDirection.direction.claim_basis.length} 条主张依据 ·{" "}
                {formatTimestamp(latestDirection.created_at)}
              </p>
            </section>
          ) : (
            <MissingVersion>尚未保存方向版本。</MissingVersion>
          )}

          {latestScript ? (
            <section className="bg-primary/5 space-y-3 rounded-xl border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-muted-foreground text-[11px]">
                    剧本 v{latestScript.version_number}
                  </p>
                  <p className="text-sm font-medium">{latestScript.title}</p>
                </div>
                <Badge variant="secondary">
                  {TRUTH_MODE_LABELS[latestScript.story_mode]}
                </Badge>
              </div>
              <p className="text-sm leading-6 break-words whitespace-pre-wrap">
                {excerpt(latestScript.script_text)}
              </p>
              <p className="text-muted-foreground text-[11px]">
                当前仅显示节选；完整版本保存在服务端 ·{" "}
                {formatTimestamp(latestScript.created_at)}
              </p>
            </section>
          ) : (
            <MissingVersion>
              {latestDirection
                ? "方向已保存，完整剧本版本尚未返回。"
                : "尚未保存完整剧本版本。"}
            </MissingVersion>
          )}
        </>
      )}
    </StagePanel>
  );
}

type LinkedProduction = PersonalIPVideoProduction & {
  contract_version: "personal-ip-video-production-v2";
  content_work_id: string;
  script_version_id: string;
};

function FinalArtifactProjection({
  production,
}: {
  production: LinkedProduction;
}) {
  const artifactReceipt = selectPersonalIPFinalArtifactReceipt(production);
  const artifact = selectPersonalIPFinalArtifact(production);
  if (!artifactReceipt) {
    return (
      <div
        className="text-muted-foreground rounded-lg border border-dashed p-3 text-xs leading-5"
        data-testid="final-artifact-unavailable"
      >
        <p className="text-foreground font-medium">正式成片未完成</p>
        <p className="mt-1">
          只有交付阶段完成、QA 通过并返回可核验正式实体后，这里才会显示成片。
        </p>
      </div>
    );
  }

  if (!artifact) {
    return (
      <div
        className="space-y-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3"
        data-testid="final-artifact-receipt"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium">最终成片回执</p>
          <Badge
            className="border-emerald-600/30 bg-emerald-50 text-emerald-800"
            variant="outline"
          >
            <ShieldCheckIcon /> 交付 QA 已通过
          </Badge>
        </div>
        <div className="text-muted-foreground space-y-1 text-[11px]">
          <p
            data-testid="final-artifact-hash"
            title={artifactReceipt.content_sha256}
          >
            SHA-256 {artifactReceipt.content_sha256.slice(0, 12)}…
          </p>
          <p data-testid="final-artifact-size">
            {artifactReceipt.mime_type} ·{" "}
            {formatPersonalIPFinalArtifactSize(artifactReceipt.size_bytes)} ·
            交付于 {formatTimestamp(artifactReceipt.created_at)}
          </p>
        </div>
        <FinalArtifactContentImport artifact={artifactReceipt} />
      </div>
    );
  }

  const artifactUrl = personalIPFinalArtifactContentURL(artifact.id);
  return (
    <div
      className="space-y-3 rounded-xl border border-emerald-600/25 bg-emerald-500/5 p-3"
      data-testid="final-artifact"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">最终成片</p>
        <Badge
          className="border-emerald-600/30 bg-emerald-50 text-emerald-800"
          variant="outline"
        >
          <ShieldCheckIcon /> 交付 QA 已通过
        </Badge>
      </div>
      <div className="overflow-hidden rounded-lg bg-black">
        <video
          aria-label={`${production.title} 最终成片播放器`}
          className="max-h-72 w-full"
          controls
          crossOrigin="use-credentials"
          data-testid="final-artifact-player"
          playsInline
          preload="metadata"
          src={artifactUrl}
        />
      </div>
      <div className="text-muted-foreground space-y-1 text-[11px]">
        <p data-testid="final-artifact-hash" title={artifact.content_sha256}>
          SHA-256 {artifact.content_sha256.slice(0, 12)}…
        </p>
        <p data-testid="final-artifact-size">
          {artifact.mime_type} ·{" "}
          {formatPersonalIPFinalArtifactSize(artifact.size_bytes)} · 交付于{" "}
          {formatTimestamp(artifact.created_at)}
        </p>
      </div>
      <Button asChild size="sm" variant="outline">
        <a data-testid="final-artifact-download" download href={artifactUrl}>
          <DownloadIcon /> 下载成片
        </a>
      </Button>
    </div>
  );
}

function ProductionPanel({
  lineage,
  productions,
  isLoading,
  isError,
  onRetry,
}: {
  lineage: PersonalIPContentLineage;
  productions: PersonalIPVideoProduction[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
}) {
  const latestScript = latestVersion(lineage.script_versions);
  const scriptVersionsById = new Map(
    lineage.script_versions.map((version) => [version.id, version]),
  );
  const linkedProductions = productions
    .filter((production): production is LinkedProduction => {
      return (
        production.contract_version === "personal-ip-video-production-v2" &&
        production.content_work_id === lineage.content_work.id &&
        typeof production.script_version_id === "string" &&
        scriptVersionsById.has(production.script_version_id)
      );
    })
    .sort(
      (left, right) =>
        new Date(right.updated_at).getTime() -
        new Date(left.updated_at).getTime(),
    );

  return (
    <StagePanel
      title="Production"
      subtitle="制作只认服务端的正式绑定，不按标题、时间或任务推测。"
      count={linkedProductions.length}
      countLabel="个制作"
      icon={ClapperboardIcon}
      testId="content-production-board"
    >
      {isLoading ? (
        <div className="text-muted-foreground flex items-center gap-2 rounded-xl border border-dashed p-4 text-sm">
          <LoaderCircleIcon className="size-4 animate-spin" />
          正在读取制作绑定…
        </div>
      ) : isError ? (
        <div className="border-destructive/40 bg-destructive/5 space-y-3 rounded-xl border p-4">
          <p className="text-destructive text-sm leading-6">
            暂时无法读取制作记录，因此不能判断这个作品是否已绑定 Production。
          </p>
          <Button size="sm" variant="outline" onClick={onRetry}>
            重试
          </Button>
        </div>
      ) : linkedProductions.length === 0 ? (
        <>
          <div className="space-y-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium">制作绑定</p>
              <Badge data-testid="production-binding-status" variant="outline">
                未绑定 Production
              </Badge>
            </div>
            <p className="text-muted-foreground text-sm leading-6">
              {latestScript
                ? `剧本 v${latestScript.version_number} 已保存，但服务端没有返回同时绑定该作品与正式剧本版本的制作记录。`
                : "当前还没有已保存的完整剧本，也没有正式制作绑定。"}
            </p>
            {latestScript && (
              <Button asChild size="sm">
                <Link
                  data-testid="start-linked-production"
                  href={personalIPProductionTaskHref(
                    lineage.content_work.id,
                    latestScript.id,
                  )}
                >
                  从正式剧本启动制作
                  <ArrowRightIcon />
                </Link>
              </Button>
            )}
          </div>
          <div className="text-muted-foreground rounded-xl border border-dashed p-4 text-sm leading-6">
            入口只携带服务端作品与剧本版本标识；Agent
            会重新读取并校验关系，页面不会从聊天内容或既有视频任务猜测绑定。
          </div>
        </>
      ) : (
        <>
          <div className="border-primary/30 bg-primary/5 space-y-2 rounded-xl border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium">制作绑定</p>
              <Badge data-testid="production-binding-status">
                已绑定 Production
              </Badge>
            </div>
            <p className="text-muted-foreground text-sm leading-6">
              下列制作均由服务端同时绑定到当前内容作品和谱系中的正式剧本版本。
            </p>
          </div>
          <div className="space-y-3">
            {linkedProductions.map((production) => {
              const scriptVersion = scriptVersionsById.get(
                production.script_version_id,
              );
              return (
                <section
                  key={production.id}
                  className="space-y-3 rounded-xl border p-3"
                  data-testid="linked-production"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-medium break-words">
                        {production.title}
                      </p>
                      <p className="text-muted-foreground mt-1 text-[11px]">
                        正式剧本 v{scriptVersion?.version_number} · 更新于{" "}
                        {formatTimestamp(production.updated_at)}
                      </p>
                      <p
                        className="text-muted-foreground mt-1 text-[11px]"
                        data-testid="production-event-count"
                      >
                        {production.event_count} 条不可变制作回执
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge variant="secondary">
                        {PRODUCTION_STATUS_LABELS[production.status]}
                      </Badge>
                      <Badge variant="outline">
                        {PRODUCTION_STAGE_LABELS[production.current_stage]}
                      </Badge>
                    </div>
                  </div>
                  <FinalArtifactProjection production={production} />
                  {production.thread_id ? (
                    <Button asChild size="sm" variant="outline">
                      <Link
                        data-testid="linked-production-task"
                        href={`/workspace/chats/${encodeURIComponent(production.thread_id)}`}
                      >
                        <MessageSquareTextIcon />
                        打开制作任务
                      </Link>
                    </Button>
                  ) : (
                    <Badge variant="outline">未关联 Agent 任务</Badge>
                  )}
                </section>
              );
            })}
          </div>
        </>
      )}
    </StagePanel>
  );
}

function ContentWorkHeader({ work }: { work: PersonalIPContentWork }) {
  return (
    <section className="space-y-5 rounded-2xl border p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">
              {ENTRY_ROUTE_LABELS[work.entry_route]}
            </Badge>
            <Badge variant="outline">
              {work.status === "active" ? "进行中" : "已归档"}
            </Badge>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight break-words">
            {work.title}
          </h2>
          <p className="text-muted-foreground text-xs">
            最后更新：{formatTimestamp(work.updated_at)}
          </p>
        </div>
        {work.thread_id ? (
          <Button asChild variant="outline">
            <Link
              data-testid="content-linked-task"
              href={`/workspace/chats/${encodeURIComponent(work.thread_id)}`}
            >
              <MessageSquareTextIcon />
              打开关联任务
            </Link>
          </Button>
        ) : (
          <Badge data-testid="content-unlinked-task" variant="outline">
            未关联 Agent 任务
          </Badge>
        )}
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="bg-muted/30 rounded-xl p-3">
          <p className="text-muted-foreground text-[11px]">希望促成的变化</p>
          <p className="mt-1 text-sm leading-6 break-words">
            {textOrMissing(work.objective.desired_change)}
          </p>
        </div>
        <div className="bg-muted/30 rounded-xl p-3">
          <p className="text-muted-foreground text-[11px]">受众处境</p>
          <p className="mt-1 text-sm leading-6 break-words">
            {textOrMissing(work.objective.audience_situation)}
          </p>
        </div>
        <div className="bg-muted/30 rounded-xl p-3">
          <p className="text-muted-foreground text-[11px]">业务背景</p>
          <p className="mt-1 text-sm leading-6 break-words">
            {textOrMissing(work.objective.business_context)}
          </p>
        </div>
        <div className="bg-muted/30 rounded-xl p-3">
          <p className="text-muted-foreground text-[11px]">约束</p>
          <p className="mt-1 text-sm leading-6 break-words">
            {work.objective.constraints.length > 0
              ? work.objective.constraints.join("、")
              : "未记录约束"}
          </p>
        </div>
      </div>

      <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
        <span>服务端目标标识</span>
        {work.objective_id ? (
          <code
            className="bg-muted max-w-full rounded px-1.5 py-0.5 break-all"
            data-testid="content-objective-id"
          >
            {work.objective_id}
          </code>
        ) : (
          <span data-testid="content-objective-id-missing">未返回</span>
        )}
      </div>
    </section>
  );
}

export default function PersonalIPContentPage() {
  const worksQuery = usePersonalIPContentWorks();
  const [filter, setFilter] = useState<WorkFilter>("all");
  const [requestedWorkId, setRequestedWorkId] = useState<string | null>(null);

  useEffect(() => {
    document.title = "内容主线 - IP Agent";
  }, []);

  const activeWorks = useMemo(
    () => (worksQuery.data ?? []).filter((work) => work.status === "active"),
    [worksQuery.data],
  );
  const filteredWorks = useMemo(
    () =>
      filter === "all"
        ? activeWorks
        : activeWorks.filter((work) => work.entry_route === filter),
    [activeWorks, filter],
  );
  const selectedWorkId = useMemo(() => {
    if (
      requestedWorkId &&
      filteredWorks.some((work) => work.id === requestedWorkId)
    ) {
      return requestedWorkId;
    }
    return filteredWorks[0]?.id ?? null;
  }, [filteredWorks, requestedWorkId]);
  const selectedSummary = activeWorks.find(
    (work) => work.id === selectedWorkId,
  );
  const lineageQuery = usePersonalIPContentLineage(selectedWorkId);
  const productionsQuery = usePersonalIPVideoProductions({
    contentWorkId: selectedWorkId,
    enabled: Boolean(selectedWorkId),
  });
  const selectedWork = lineageQuery.data?.content_work ?? selectedSummary;
  const isRefreshing =
    worksQuery.isFetching ||
    lineageQuery.isFetching ||
    productionsQuery.isFetching;

  const zeroStartCount = activeWorks.filter(
    (work) => work.entry_route === "zero_start",
  ).length;
  const benchmarkCount = activeWorks.filter(
    (work) => work.entry_route === "benchmark",
  ).length;

  const refresh = async () => {
    await Promise.all([
      worksQuery.refetch(),
      selectedWorkId ? lineageQuery.refetch() : Promise.resolve(),
      selectedWorkId ? productionsQuery.refetch() : Promise.resolve(),
    ]);
  };

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-y-auto">
        <div className="mx-auto w-full max-w-[1600px] space-y-8 p-6 lg:p-10">
          <section className="flex flex-wrap items-start justify-between gap-5">
            <div className="max-w-3xl space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">内容主线</Badge>
                <Badge variant="outline">服务端版本为准</Badge>
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">
                Breakdown → Writer Brain → Production
              </h1>
              <p className="text-muted-foreground text-sm leading-6">
                一个内容作品贯穿拆解、方向和剧本版本。页面只展示已保存的事实；制作没有正式绑定时，始终显示未绑定。
              </p>
            </div>
            <Button
              disabled={isRefreshing}
              variant="outline"
              onClick={() => void refresh()}
            >
              {isRefreshing ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <RefreshCcwIcon />
              )}
              刷新
            </Button>
          </section>

          <section className="space-y-3" aria-labelledby="content-entry-title">
            <div>
              <h2 id="content-entry-title" className="text-lg font-semibold">
                开始一个 Agent 任务
              </h2>
              <p className="text-muted-foreground mt-1 text-sm leading-6">
                入口只预填任务说明；内容作品、目标标识和任务绑定由服务端在保存时产生。
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <EntryCard
                entryRoute="zero_start"
                title="零起盘"
                description="从受众处境、想促成的变化和业务约束开始，形成原创方向与完整剧本。"
                icon={SparklesIcon}
              />
              <EntryCard
                entryRoute="benchmark"
                title="对标拆解"
                description="从精确作品链接或上传文件出发，先保存来源绑定的拆解，再发展原创内容。"
                icon={FileSearchIcon}
              />
            </div>
          </section>

          {worksQuery.isError ? (
            <Card className="border-destructive/40 bg-destructive/5">
              <CardContent className="space-y-3 text-sm">
                <p className="text-destructive">
                  暂时无法读取已保存的内容作品；页面没有使用默认数据补齐。
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void refresh()}
                >
                  重试
                </Button>
              </CardContent>
            </Card>
          ) : (
            <section className="grid min-w-0 gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
              <Card className="h-fit min-w-0 gap-4 lg:sticky lg:top-6">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Layers3Icon className="size-4" />
                    内容作品
                  </CardTitle>
                  <CardDescription>
                    仅显示服务端返回的活跃作品。
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div
                    className="flex flex-wrap gap-1"
                    role="group"
                    aria-label="内容作品筛选"
                  >
                    {(
                      [
                        ["all", `全部 ${activeWorks.length}`],
                        ["zero_start", `零起盘 ${zeroStartCount}`],
                        ["benchmark", `对标 ${benchmarkCount}`],
                      ] as const
                    ).map(([value, label]) => (
                      <Button
                        key={value}
                        aria-pressed={filter === value}
                        size="sm"
                        variant={filter === value ? "secondary" : "ghost"}
                        onClick={() => setFilter(value)}
                      >
                        {label}
                      </Button>
                    ))}
                  </div>

                  {worksQuery.isLoading ? (
                    <div className="text-muted-foreground flex items-center gap-2 py-6 text-sm">
                      <LoaderCircleIcon className="size-4 animate-spin" />
                      正在读取内容作品…
                    </div>
                  ) : filteredWorks.length === 0 ? (
                    <div className="text-muted-foreground rounded-xl border border-dashed p-4 text-sm leading-6">
                      {activeWorks.length === 0
                        ? "还没有已保存的活跃内容作品。"
                        : "当前筛选下没有内容作品。"}
                    </div>
                  ) : (
                    <div className="max-h-[540px] space-y-2 overflow-y-auto pr-1">
                      {filteredWorks.map((work) => (
                        <button
                          key={work.id}
                          type="button"
                          aria-pressed={work.id === selectedWorkId}
                          className={cn(
                            "hover:bg-muted/60 w-full rounded-xl border p-3 text-left transition-colors",
                            work.id === selectedWorkId &&
                              "border-primary/40 bg-primary/5",
                          )}
                          onClick={() => setRequestedWorkId(work.id)}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <p className="min-w-0 text-sm font-medium break-words">
                              {work.title}
                            </p>
                            <Badge className="shrink-0" variant="outline">
                              {ENTRY_ROUTE_LABELS[work.entry_route]}
                            </Badge>
                          </div>
                          <p className="text-muted-foreground mt-2 line-clamp-2 text-xs leading-5">
                            {textOrMissing(work.objective.desired_change)}
                          </p>
                          <p className="text-muted-foreground mt-2 text-[10px]">
                            {formatTimestamp(work.updated_at)}
                          </p>
                        </button>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <div className="min-w-0 space-y-5">
                {!selectedWorkId ? (
                  <Card>
                    <CardContent className="text-muted-foreground flex min-h-56 items-center justify-center text-center text-sm leading-6">
                      选择一个已保存作品查看完整谱系，或从上方入口开始新任务。
                    </CardContent>
                  </Card>
                ) : lineageQuery.isLoading ? (
                  <Card>
                    <CardContent className="text-muted-foreground flex min-h-56 items-center justify-center gap-2 text-sm">
                      <LoaderCircleIcon className="size-4 animate-spin" />
                      正在读取版本谱系…
                    </CardContent>
                  </Card>
                ) : lineageQuery.isError || !lineageQuery.data ? (
                  <Card className="border-destructive/40 bg-destructive/5">
                    <CardContent className="space-y-3 text-sm">
                      <p className="text-destructive">
                        暂时无法读取这个作品的版本谱系。
                      </p>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void lineageQuery.refetch()}
                      >
                        重试
                      </Button>
                    </CardContent>
                  </Card>
                ) : (
                  <>
                    {selectedWork && <ContentWorkHeader work={selectedWork} />}
                    <div className="grid min-w-0 gap-5 xl:grid-cols-3">
                      <BreakdownPanel lineage={lineageQuery.data} />
                      <WriterBrainPanel lineage={lineageQuery.data} />
                      <ProductionPanel
                        lineage={lineageQuery.data}
                        productions={productionsQuery.data ?? []}
                        isLoading={productionsQuery.isLoading}
                        isError={productionsQuery.isError}
                        onRetry={() => void productionsQuery.refetch()}
                      />
                    </div>
                  </>
                )}
              </div>
            </section>
          )}

          <section className="text-muted-foreground flex items-center gap-2 border-t pt-5 text-xs leading-5">
            <PenLineIcon className="size-3.5 shrink-0" />
            聊天是交互入口，服务端内容作品与不可变版本才是这条主线的事实来源。
          </section>
        </div>
      </WorkspaceBody>
    </WorkspaceContainer>
  );
}
