"use client";

import {
  AlertCircleIcon,
  CheckCircle2Icon,
  LoaderCircleIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  BrowserViewPanel,
  type BrowserPresentationMode,
  type BrowserStreamStatus,
} from "@/components/workspace/browser-view";
import type {
  PersonalIPAccount,
  PersonalIPBrowserPlatform,
} from "@/core/personal-ip";
import { cn } from "@/lib/utils";

export function AccountBrowserLoginDialog({
  open,
  account,
  platform,
  onAuthenticated,
  onOpenChange,
}: {
  open: boolean;
  account: PersonalIPAccount | null;
  platform: PersonalIPBrowserPlatform | null;
  onAuthenticated: (account: PersonalIPAccount) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const [streamStatus, setStreamStatus] = useState<BrowserStreamStatus>("idle");
  const [presentationMode, setPresentationMode] =
    useState<BrowserPresentationMode>("pending");

  useEffect(() => {
    if (open) {
      setStreamStatus("idle");
      setPresentationMode("pending");
    }
  }, [account?.id, open]);

  const embeddedStream = presentationMode === "embedded_stream";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "gap-3 overflow-hidden p-4",
          embeddedStream
            ? "w-[98vw] max-w-[98vw] sm:max-w-[98vw] 2xl:max-w-[1680px]"
            : "w-[calc(100vw-2rem)] max-w-lg sm:max-w-lg",
        )}
      >
        <DialogHeader className="shrink-0 pr-10">
          <DialogTitle>
            {platform?.label ?? "平台"} · {account?.display_name ?? "账号登录"}
          </DialogTitle>
          <DialogDescription className="flex items-start gap-1.5 leading-5">
            <ShieldCheckIcon className="size-3.5 shrink-0" />
            <span>
              请本人完成扫码、验证码或双重验证。登录状态只保存在这个账号的独立浏览器中；无需公司统一认证，Cookie、Token、密码不会提供给智能体。
            </span>
          </DialogDescription>
        </DialogHeader>
        {embeddedStream && (
          <div
            className="bg-muted/35 flex min-h-9 shrink-0 items-center justify-between gap-3 rounded-lg border px-3 py-2 text-xs"
            aria-live="polite"
          >
            <div className="flex items-center gap-2">
              {streamStatus === "open" ? (
                <CheckCircle2Icon className="size-4 text-emerald-600" />
              ) : streamStatus === "closed" ? (
                <AlertCircleIcon className="text-destructive size-4" />
              ) : (
                <LoaderCircleIcon className="text-muted-foreground size-4 animate-spin" />
              )}
              <span>
                {streamStatus === "open"
                  ? "远程登录窗口已连接；登录成功后窗口会自动关闭。"
                  : streamStatus === "closed"
                    ? "登录窗口已断开，请关闭后重新登录。"
                    : "正在连接远程登录窗口…"}
              </span>
            </div>
          </div>
        )}
        {account && platform && (
          <div
            className={cn(
              "min-h-0 w-full overflow-hidden rounded-lg",
              embeddedStream
                ? "aspect-video max-h-[calc(94vh-8.5rem)] border"
                : "min-h-36",
            )}
          >
            <BrowserViewPanel
              key={account.id}
              accountId={account.id}
              initialUrl={platform.startUrl}
              title={`${platform.label}登录`}
              className="min-h-0 overflow-hidden"
              onAccountAuthenticated={() => {
                onAuthenticated(account);
                onOpenChange(false);
              }}
              onPresentationModeChange={setPresentationMode}
              onStreamStatusChange={setStreamStatus}
              onClose={() => onOpenChange(false)}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
