"use client";

import { Download } from "lucide-react";
import { useCallback } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/core/i18n/hooks";
import { exportThreadAsMarkdown } from "@/core/threads/export";
import type { AgentThread } from "@/core/threads/types";

import { useThread } from "./messages/context";
import { Tooltip } from "./tooltip";

export function ExportTrigger({ threadId }: { threadId: string }) {
  const { t } = useI18n();
  const { thread } = useThread();

  const messages = thread.messages;

  const handleExport = useCallback(() => {
    if (messages.length === 0) {
      toast.error(t.conversation.noMessages);
      return;
    }
    const agentThread = {
      thread_id: threadId,
      updated_at: new Date().toISOString(),
      values: thread.values,
    } as AgentThread;

    exportThreadAsMarkdown(agentThread, messages);
    toast.success(t.common.exportSuccess);
  }, [messages, thread.values, threadId, t]);

  if (messages.length === 0) {
    return null;
  }

  return (
    <Tooltip content={t.common.export}>
      <Button
        aria-label={t.common.export}
        className="text-muted-foreground hover:text-foreground"
        variant="ghost"
        onClick={handleExport}
      >
        <Download />
        <span className="hidden sm:inline">{t.common.export}</span>
      </Button>
    </Tooltip>
  );
}
