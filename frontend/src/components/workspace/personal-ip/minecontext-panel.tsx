"use client";

import {
  DatabaseIcon,
  LoaderCircleIcon,
  PlayIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
  SquareIcon,
  Trash2Icon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
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
  describeMineContextStatus,
  type MineContextPurpose,
  type MineContextScope,
  useAuthorizeMineContext,
  useDeleteMineContextData,
  useMineContextStatus,
  useRevokeMineContext,
  useStartMineContext,
  useStopMineContext,
} from "@/core/personal-ip";

const SCOPE_OPTIONS: { id: MineContextScope; label: string }[] = [
  { id: "screen", label: "屏幕摘要" },
  { id: "files", label: "指定文件夹" },
  { id: "people", label: "人物线索" },
  { id: "projects", label: "项目线索" },
  { id: "work_activity", label: "工作活动" },
];
const PURPOSE_OPTIONS: { id: MineContextPurpose; label: string }[] = [
  { id: "persona_modeling", label: "人格建模" },
  { id: "audience_modeling", label: "受众建模" },
  { id: "hllm_user_profile", label: "HLLM user_profile" },
  { id: "preflight", label: "发布前预演" },
  { id: "retrospective", label: "复盘证据" },
];

export function MineContextPanel() {
  const query = useMineContextStatus();
  const authorize = useAuthorizeMineContext();
  const start = useStartMineContext();
  const stop = useStopMineContext();
  const revoke = useRevokeMineContext();
  const remove = useDeleteMineContextData();
  const [scopes, setScopes] = useState<MineContextScope[]>([]);
  const [purposes, setPurposes] = useState<MineContextPurpose[]>([]);
  const [retentionDays, setRetentionDays] = useState(30);

  useEffect(() => {
    if (!query.data?.authorized) return;
    setScopes(query.data.scopes ?? []);
    setPurposes(query.data.purposes ?? []);
    setRetentionDays(query.data.retention_days ?? 30);
  }, [query.data]);

  const busy =
    authorize.isPending ||
    start.isPending ||
    stop.isPending ||
    revoke.isPending ||
    remove.isPending;
  const visibleError = [query.error, authorize.error, start.error, stop.error, revoke.error, remove.error].find(Boolean);
  const copy = useMemo(
    () => (query.data ? describeMineContextStatus(query.data) : null),
    [query.data],
  );
  const toggle = <T extends string>(values: T[], value: T, checked: boolean) =>
    checked ? [...values, value] : values.filter((item) => item !== value);
  const run = async (operation: () => Promise<unknown>, success: string) => {
    try {
      await operation();
      toast.success(success);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error));
    }
  };

  return (
    <section aria-labelledby="minecontext-title">
      <Card className="border-primary/15">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle id="minecontext-title" className="flex items-center gap-2">
                <DatabaseIcon className="size-4" /> 本地上下文（MineContext）
              </CardTitle>
              <CardDescription className="max-w-3xl leading-6">
                默认关闭、不会随 Gateway 自动采集。只有你明确选择的范围和用途可以启动；进入 DeerFlow/HLLM 的仅是脱敏摘要与来源时间，不含 Cookie、Token、密码、完整屏幕文字、原始文件或路径。
              </CardDescription>
            </div>
            <Badge variant={query.data?.running ? "secondary" : "outline"}>
              {query.isLoading ? "读取中" : copy?.label ?? "状态未知"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {query.isLoading ? (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <LoaderCircleIcon className="size-4 animate-spin" /> 正在读取本地观察源状态…
            </div>
          ) : query.data ? (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="bg-muted/30 rounded-lg border p-3 text-sm">
                  <ShieldCheckIcon className="text-muted-foreground mb-2 size-4" />
                  <p className="font-medium">明确授权后才运行</p>
                  <p className="text-muted-foreground mt-1 text-xs leading-5">{copy?.action}</p>
                </div>
                <div className="bg-muted/30 rounded-lg border p-3 text-sm">
                  <DatabaseIcon className="text-muted-foreground mb-2 size-4" />
                  <p className="font-medium">owner 本地隔离</p>
                  <p className="text-muted-foreground mt-1 text-xs leading-5">现有 {query.data.evidence_count ?? 0} 条边界证据；仅本机保存。</p>
                </div>
                <div className="bg-muted/30 rounded-lg border p-3 text-sm">
                  <RotateCcwIcon className="text-muted-foreground mb-2 size-4" />
                  <p className="font-medium">保留与删除可控</p>
                  <p className="text-muted-foreground mt-1 text-xs leading-5">到期自动清理，也可撤销或立即删除。</p>
                </div>
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <fieldset className="space-y-2">
                  <legend className="text-sm font-medium">允许读取的范围</legend>
                  <p className="text-muted-foreground text-xs">当前界面采用手动模式，不开启持续截图或文件夹监听。</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {SCOPE_OPTIONS.map((option) => (
                      <label key={option.id} className="flex items-center gap-2 rounded-md border p-2 text-sm">
                        <input
                          type="checkbox"
                          checked={scopes.includes(option.id)}
                          disabled={busy || query.data.running}
                          onChange={(event) => setScopes(toggle(scopes, option.id, event.target.checked))}
                        />
                        {option.label}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <fieldset className="space-y-2">
                  <legend className="text-sm font-medium">允许使用的目的</legend>
                  <p className="text-muted-foreground text-xs">预演使用本地证据时还需同时勾选 HLLM user_profile。</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {PURPOSE_OPTIONS.map((option) => (
                      <label key={option.id} className="flex items-center gap-2 rounded-md border p-2 text-sm">
                        <input
                          type="checkbox"
                          checked={purposes.includes(option.id)}
                          disabled={busy || query.data.running}
                          onChange={(event) => setPurposes(toggle(purposes, option.id, event.target.checked))}
                        />
                        {option.label}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>

              <label className="flex max-w-xs items-center gap-3 text-sm">
                <span className="font-medium">保留天数</span>
                <input
                  className="bg-background w-24 rounded-md border px-2 py-1"
                  type="number"
                  min={1}
                  max={365}
                  value={retentionDays}
                  disabled={busy || query.data.running}
                  onChange={(event) => setRetentionDays(Number(event.target.value))}
                />
              </label>

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  disabled={busy || query.data.running || scopes.length === 0 || purposes.length === 0 || !query.data.operator_enabled}
                  onClick={() => void run(() => authorize.mutateAsync({
                    scopes,
                    purposes,
                    retention_days: retentionDays,
                    collection_mode: "manual",
                    watched_paths: [],
                    recursive_file_watch: false,
                    screen_targets: [],
                    screen_capture_interval_seconds: 60,
                    continuous_screen_capture_confirmed: false,
                  }), "本地上下文授权已保存")}
                >
                  <ShieldCheckIcon /> {query.data.authorized ? "更新授权" : "明确授权"}
                </Button>
                <Button
                  disabled={busy || !query.data.available || !query.data.authorized || query.data.running}
                  onClick={() => void run(() => start.mutateAsync(undefined), "MineContext 已在本机启动")}
                >
                  <PlayIcon /> 启动
                </Button>
                <Button
                  variant="outline"
                  disabled={busy || !query.data.running}
                  onClick={() => void run(() => stop.mutateAsync(undefined), "MineContext 已停止")}
                >
                  <SquareIcon /> 停止
                </Button>
                <Button
                  variant="outline"
                  disabled={busy || !query.data.authorized}
                  onClick={() => void run(() => revoke.mutateAsync(undefined), "授权已撤销，运行时数据已清理")}
                >
                  <RotateCcwIcon /> 撤销授权
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy || (query.data.evidence_count ?? 0) === 0}
                  onClick={() => void run(() => remove.mutateAsync("evidence"), "本地摘要证据已删除")}
                >
                  <Trash2Icon /> 删除证据
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm("删除此 owner 的全部 MineContext 授权、证据和本地运行数据？")) {
                      void run(() => remove.mutateAsync("all"), "MineContext 本地数据已全部删除");
                    }
                  }}
                >
                  <Trash2Icon /> 删除全部本地数据
                </Button>
              </div>
            </>
          ) : null}

          {visibleError && (
            <Alert variant="destructive">
              <AlertTitle>本地上下文操作未完成</AlertTitle>
              <AlertDescription>{visibleError instanceof Error ? visibleError.message : String(visibleError)}</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
