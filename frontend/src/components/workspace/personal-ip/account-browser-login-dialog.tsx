"use client";

import {
  AlertCircleIcon,
  CheckCircle2Icon,
  LoaderCircleIcon,
  RefreshCcwIcon,
  ShieldCheckIcon,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  BrowserViewPanel,
  type BrowserStreamStatus,
} from "@/components/workspace/browser-view";
import type {
  PersonalIPAccount,
  PersonalIPBrowserPlatform,
} from "@/core/personal-ip";

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
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (open) {
      setStreamStatus("idle");
      setRetryKey(0);
    }
  }, [account?.id, open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[98vw] max-w-[98vw] gap-3 overflow-hidden p-4 sm:max-w-[98vw] 2xl:max-w-[1680px]">
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
                ? "浏览器已连接，请在下方完成平台登录；成功后窗口会自动关闭。"
                : streamStatus === "closed"
                  ? "连接中断。可以立即重新连接，已保存的账号登录状态不会被清除。"
                  : "正在打开该账号的独立浏览器…"}
            </span>
          </div>
          {streamStatus === "closed" && (
            <Button
              size="sm"
              variant="outline"
              className="shrink-0"
              onClick={() => {
                setStreamStatus("connecting");
                setRetryKey((value) => value + 1);
              }}
            >
              <RefreshCcwIcon /> 重新连接
            </Button>
          )}
        </div>
        {account && platform && (
          <div className="aspect-video max-h-[calc(94vh-8.5rem)] min-h-0 w-full overflow-hidden rounded-lg border">
            <BrowserViewPanel
              key={`${account.id}:${retryKey}`}
              accountId={account.id}
              initialUrl={platform.startUrl}
              title={`${platform.label}登录`}
              className="min-h-0 overflow-hidden"
              onAccountAuthenticated={() => {
                onAuthenticated(account);
                onOpenChange(false);
              }}
              onStreamStatusChange={setStreamStatus}
              onClose={() => onOpenChange(false)}
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
