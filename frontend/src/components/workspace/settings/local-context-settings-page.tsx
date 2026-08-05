"use client";

import {
  DatabaseIcon,
  LoaderCircleIcon,
  PlayIcon,
  SquareIcon,
  Trash2Icon,
} from "lucide-react";
import { useMemo } from "react";
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
  useDeleteMineContextData,
  useEnableMineContext,
  useMineContextStatus,
  useRevokeMineContext,
} from "@/core/personal-ip";

export function LocalContextSettingsPage() {
  const query = useMineContextStatus();
  const enable = useEnableMineContext();
  const revoke = useRevokeMineContext();
  const remove = useDeleteMineContextData();

  const busy = enable.isPending || revoke.isPending || remove.isPending;
  const visibleError = [
    query.error,
    enable.error,
    revoke.error,
    remove.error,
  ].find(Boolean);
  const copy = useMemo(
    () => (query.data ? describeMineContextStatus(query.data) : null),
    [query.data],
  );
  const run = async (operation: () => Promise<unknown>, success: string) => {
    try {
      await operation();
      toast.success(success);
    } catch {
      toast.error("操作没有完成，请稍后重试");
    }
  };

  return (
    <section aria-labelledby="minecontext-title">
      <Card className="border-primary/15">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle
                id="minecontext-title"
                className="flex items-center gap-2"
              >
                <DatabaseIcon className="size-4" /> 本地上下文
              </CardTitle>
              <CardDescription className="max-w-3xl leading-6">
                默认关闭。只有你明确确认后，本机才会开始有界的屏幕采集；
                登录凭据、密码和原始文件不会进入对话。默认 IP Agent
                当前不读取这些数据。
              </CardDescription>
            </div>
            <Badge variant={query.data?.running ? "secondary" : "outline"}>
              {query.isLoading ? "读取中" : (copy?.label ?? "状态未知")}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-5">
          {query.isLoading ? (
            <div className="text-muted-foreground flex items-center gap-2 text-sm">
              <LoaderCircleIcon className="size-4 animate-spin" />{" "}
              正在准备本地上下文…
            </div>
          ) : query.data ? (
            <>
              <div className="bg-muted/30 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 text-sm">
                <div>
                  <p className="font-medium">{copy?.action}</p>
                </div>
                <p className="text-muted-foreground text-xs">
                  仅本机保存 · 到期自动清理
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                {query.data.running ? (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      void run(
                        () => revoke.mutateAsync(undefined),
                        "本地上下文已关闭",
                      )
                    }
                  >
                    <SquareIcon /> 关闭本地上下文
                  </Button>
                ) : (
                  <Button
                    disabled={
                      busy ||
                      !query.data.operator_enabled ||
                      !query.data.available
                    }
                    onClick={() => {
                      if (
                        !window.confirm(
                          "开启后将在本机对所有显示器进行有界的定时采集。是否继续？",
                        )
                      ) {
                        return;
                      }
                      void run(
                        () =>
                          enable.mutateAsync({
                            retention_days: 30,
                            continuous_screen_capture_confirmed: true,
                          }),
                        "本地上下文已开启",
                      );
                    }}
                  >
                    <PlayIcon /> 开启本地上下文
                  </Button>
                )}
                <Button
                  variant="ghost"
                  disabled={
                    busy ||
                    (!query.data.authorized &&
                      (query.data.evidence_count ?? 0) === 0)
                  }
                  onClick={() => {
                    if (
                      window.confirm("清除全部本地上下文数据？清除后无法恢复。")
                    ) {
                      void run(
                        () => remove.mutateAsync("all"),
                        "本地上下文数据已全部清除",
                      );
                    }
                  }}
                >
                  <Trash2Icon /> 清除本地数据
                </Button>
              </div>
            </>
          ) : null}

          {visibleError && (
            <Alert variant="destructive">
              <AlertTitle>本地上下文操作未完成</AlertTitle>
              <AlertDescription>请稍后重试。</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
