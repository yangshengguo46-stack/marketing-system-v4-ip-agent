"use client";

import {
  AlertCircleIcon,
  CheckCircle2Icon,
  Globe2Icon,
  LoaderCircleIcon,
  LogInIcon,
  LogOutIcon,
  PlusIcon,
  RefreshCcwIcon,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  type PersonalIPAccount,
  type PersonalIPBrowserPlatform,
  PERSONAL_IP_BROWSER_PLATFORMS,
  PERSONAL_IP_CONNECTION_STATE_COPY,
  type PersonalIPConnectionState,
  personalIPAccountConnectionState,
} from "@/core/personal-ip";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<PersonalIPConnectionState, string> = {
  not_added: "border-border bg-background text-muted-foreground",
  pending_login:
    "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
  logged_in:
    "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200",
  collection_limited:
    "border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-900 dark:bg-orange-950/40 dark:text-orange-200",
  actionable:
    "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200",
};

function ConnectionBadge({ state }: { state: PersonalIPConnectionState }) {
  const copy = PERSONAL_IP_CONNECTION_STATE_COPY[state];
  return (
    <Badge
      variant="outline"
      className={cn("font-medium", STATUS_STYLES[state])}
      data-connection-state={state}
    >
      {state === "actionable" || state === "logged_in" ? (
        <CheckCircle2Icon />
      ) : state === "collection_limited" ? (
        <AlertCircleIcon />
      ) : (
        <span className="size-1.5 rounded-full bg-current" />
      )}
      {copy.label}
    </Badge>
  );
}

export function PlatformConnectionsPanel({
  accounts,
  subjectNames,
  loading,
  loadError,
  actionError,
  actionPending,
  onAddPlatform,
  onLoginAccount,
  onLogoutAccount,
  onRetry,
  onDismissError,
}: {
  accounts: PersonalIPAccount[];
  subjectNames: Map<string, string>;
  loading: boolean;
  loadError: string | null;
  actionError: string | null;
  actionPending: boolean;
  onAddPlatform: (platform: PersonalIPBrowserPlatform) => void;
  onLoginAccount: (account: PersonalIPAccount) => void;
  onLogoutAccount: (account: PersonalIPAccount) => void;
  onRetry: () => void;
  onDismissError: () => void;
}) {
  const visibleError = loadError ?? actionError;

  return (
    <section className="space-y-5" aria-label="平台账号">
      {visibleError && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>连接状态没有更新</AlertTitle>
          <AlertDescription>
            <p>{visibleError}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={onRetry}>
                <RefreshCcwIcon /> 重新读取
              </Button>
              {actionError && (
                <Button size="sm" variant="ghost" onClick={onDismissError}>
                  知道了
                </Button>
              )}
            </div>
          </AlertDescription>
        </Alert>
      )}

      {loading ? (
        <Card>
          <CardContent className="text-muted-foreground flex items-center gap-2 text-sm">
            <LoaderCircleIcon className="size-4 animate-spin" />
            正在读取八个平台的连接状态…
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {PERSONAL_IP_BROWSER_PLATFORMS.map((platform) => {
            const platformAccounts = accounts.filter(
              (account) => account.platform === platform.id,
            );
            return (
              <Card
                key={platform.id}
                className="gap-0 overflow-hidden py-0"
                data-platform={platform.id}
              >
                <CardHeader className="bg-muted/20 gap-2 border-b px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Globe2Icon className="size-4" />
                      {platform.label}
                    </CardTitle>
                    {loadError ? (
                      <Badge variant="outline">状态未知</Badge>
                    ) : platformAccounts.length === 0 ? (
                      <ConnectionBadge state="not_added" />
                    ) : (
                      <Badge variant="outline">
                        {platformAccounts.length} 个账号
                      </Badge>
                    )}
                  </div>
                  <CardDescription>{platform.description}</CardDescription>
                </CardHeader>
                <CardContent className="grow space-y-3 p-4">
                  {loadError ? (
                    <div className="text-muted-foreground rounded-lg border border-dashed p-3 text-sm leading-6">
                      重新读取后显示账号和连接状态。
                    </div>
                  ) : platformAccounts.length === 0 ? (
                    <div className="text-muted-foreground rounded-lg border border-dashed p-3 text-sm leading-6">
                      尚未添加账号。
                    </div>
                  ) : (
                    platformAccounts.map((account) => {
                      const connectionState =
                        personalIPAccountConnectionState(account);
                      const copy =
                        PERSONAL_IP_CONNECTION_STATE_COPY[connectionState];
                      const isLoggedIn = connectionState !== "pending_login";
                      return (
                        <div
                          key={account.id}
                          className="space-y-3 rounded-lg border p-3"
                          data-account-state={connectionState}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium">
                                {account.display_name}
                              </p>
                              <p className="text-muted-foreground mt-0.5 truncate text-xs">
                                {account.handle ??
                                  (account.subject_id
                                    ? (subjectNames.get(account.subject_id) ??
                                      "未知主体")
                                    : "未归属主体")}
                              </p>
                            </div>
                            <ConnectionBadge state={connectionState} />
                          </div>
                          <p className="text-muted-foreground text-xs leading-5">
                            {copy.description}
                          </p>
                          <Button
                            size="sm"
                            className="w-full"
                            variant={isLoggedIn ? "outline" : "default"}
                            disabled={actionPending}
                            onClick={() =>
                              isLoggedIn
                                ? onLogoutAccount(account)
                                : onLoginAccount(account)
                            }
                          >
                            {actionPending ? (
                              <LoaderCircleIcon className="animate-spin" />
                            ) : isLoggedIn ? (
                              <LogOutIcon />
                            ) : (
                              <LogInIcon />
                            )}
                            {copy.action}
                          </Button>
                        </div>
                      );
                    })
                  )}
                </CardContent>
                <CardFooter className="border-t p-4">
                  <Button
                    className="w-full"
                    variant={
                      platformAccounts.length === 0 ? "default" : "outline"
                    }
                    disabled={actionPending || Boolean(loadError)}
                    onClick={() => onAddPlatform(platform)}
                  >
                    {actionPending ? (
                      <LoaderCircleIcon className="animate-spin" />
                    ) : platformAccounts.length === 0 ? (
                      <LogInIcon />
                    ) : (
                      <PlusIcon />
                    )}
                    {platformAccounts.length === 0
                      ? "登录"
                      : "登录另一个账号"}
                  </Button>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}
