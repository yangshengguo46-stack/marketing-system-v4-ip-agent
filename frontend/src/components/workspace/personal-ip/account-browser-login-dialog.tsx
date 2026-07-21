"use client";

import { ShieldCheckIcon } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { BrowserViewPanel } from "@/components/workspace/browser-view";
import type {
  PersonalIPAccount,
  PersonalIPBrowserPlatform,
} from "@/core/personal-ip";

export function AccountBrowserLoginDialog({
  open,
  account,
  platform,
  onOpenChange,
}: {
  open: boolean;
  account: PersonalIPAccount | null;
  platform: PersonalIPBrowserPlatform | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex w-[98vw] max-w-[98vw] flex-col gap-3 overflow-hidden p-4 sm:max-w-[98vw] 2xl:max-w-[1680px]"
        style={{ height: "min(94vh, calc(55.125vw + 8rem))" }}
      >
        <DialogHeader className="shrink-0 pr-10">
          <DialogTitle>
            {platform?.label ?? "平台"} · {account?.display_name ?? "账号登录"}
          </DialogTitle>
          <DialogDescription className="flex items-center gap-1.5">
            <ShieldCheckIcon className="size-3.5 shrink-0" />
            请本人完成扫码、验证码或双重验证；登录状态只保存在这台设备的该账号目录中。
          </DialogDescription>
        </DialogHeader>
        {account && platform && (
          <BrowserViewPanel
            accountId={account.id}
            initialUrl={platform.startUrl}
            title={`${platform.label}登录`}
            className="min-h-0 overflow-hidden rounded-lg border"
            onAccountAuthenticated={() => {
              toast.success(`${platform.label}登录成功`);
              onOpenChange(false);
            }}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
