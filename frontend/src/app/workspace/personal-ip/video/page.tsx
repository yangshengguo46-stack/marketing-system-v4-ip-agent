"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircleIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import {
  bindPersonalIPVideoProductionThread,
  ensurePersonalIPVideoTaskThread,
  usePersonalIPVideoProductions,
} from "@/core/personal-ip";
import { INFINITE_THREADS_QUERY_KEY_PREFIX } from "@/core/threads/hooks";
import { pathOfThread } from "@/core/threads/utils";

export default function LegacyVideoWorkbenchRedirect() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const productions = usePersonalIPVideoProductions();
  const started = useRef(false);

  useEffect(() => {
    if (started.current || productions.isLoading || productions.isFetching) {
      return;
    }
    started.current = true;
    const migrate = async () => {
      let destinationThreadId: string | null = null;
      for (const production of productions.data ?? []) {
        const storedThreadId = window.localStorage.getItem(
          `ip-agent:video-workbench-thread:${production.id}`,
        );
        const threadId = production.thread_id ?? storedThreadId;
        if (!threadId) continue;
        try {
          await ensurePersonalIPVideoTaskThread(
            production.id,
            threadId,
            production.title,
          );
          if (!production.thread_id) {
            await bindPersonalIPVideoProductionThread(
              production.id,
              threadId,
            );
          }
          destinationThreadId ??= threadId;
        } catch {
          // One stale legacy mapping must not block the remaining migrations.
        }
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["threads", "search"] }),
        queryClient.invalidateQueries({
          queryKey: INFINITE_THREADS_QUERY_KEY_PREFIX,
        }),
      ]);
      router.replace(
        destinationThreadId
          ? pathOfThread(destinationThreadId)
          : "/workspace/chats/new",
      );
    };
    void migrate();
  }, [
    productions.data,
    productions.isFetching,
    productions.isLoading,
    queryClient,
    router,
  ]);

  return (
    <div className="flex h-screen items-center justify-center gap-2 text-sm text-muted-foreground">
      <LoaderCircleIcon className="size-4 animate-spin" />
      正在把视频项目迁入历史任务…
    </div>
  );
}
