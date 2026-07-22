"use client";

import {
  AlertCircleIcon,
  CheckCircle2Icon,
  DatabaseIcon,
  Edit3Icon,
  Globe2Icon,
  KeyRoundIcon,
  LoaderCircleIcon,
  LockKeyholeIcon,
  LogInIcon,
  PlusIcon,
  RefreshCcwIcon,
  ShieldCheckIcon,
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
  summarizePersonalIPConnections,
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

function nextStepText(
  summary: ReturnType<typeof summarizePersonalIPConnections>,
) {
  if (summary.pendingLogin > 0) {
    return `继续完成 ${summary.pendingLogin} 个账号的本人登录。扫码、验证码和 MFA 都由你操作。`;
  }
  if (summary.collectionLimited > 0) {
    return `打开 ${summary.collectionLimited} 个受限账号，检查登录是否过期以及平台的数据权限提示。`;
  }
  if (summary.loggedIn > 0) {
    return "登录已确认。回到同一场会话，让 IP Agent 先读取账号、内容和经营数据。";
  }
  if (summary.notAdded > 0) {
    return "选择你最常用的平台，点击“添加并登录”。无需先配置公司统一认证。";
  }
  return "账号均可执行。继续在同一场会话里安排跨平台分析、创作和经过确认的操作。";
}

export function PlatformConnectionsPanel({
  accounts,
  subjectNames,
  loading,
  loadError,
  actionError,
  actionPending,
  onAddPlatform,
  onOpenAccount,
  onEditAccount,
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
  onOpenAccount: (account: PersonalIPAccount) => void;
  onEditAccount: (account: PersonalIPAccount) => void;
  onRetry: () => void;
  onDismissError: () => void;
}) {
  const platformIds = PERSONAL_IP_BROWSER_PLATFORMS.map(
    (platform) => platform.id,
  );
  const summary = summarizePersonalIPConnections(accounts, platformIds);
  const visibleError = loadError ?? actionError;

  return (
    <section className="space-y-5" aria-labelledby="platform-connections-title">
      <Card className="border-primary/20 overflow-hidden py-0">
        <CardContent className="grid gap-6 p-5 lg:grid-cols-[1.15fr_0.85fr] lg:p-7">
          <div className="space-y-4">
            <Badge variant="secondary">首次使用从这里开始</Badge>
            <div className="space-y-2">
              <h2
                id="platform-connections-title"
                className="text-xl font-semibold tracking-tight sm:text-2xl"
              >
                连接你要经营的平台
              </h2>
              <p className="text-muted-foreground max-w-2xl text-sm leading-6">
                不需要公司统一认证。按平台手动点击“添加并登录”，由你本人在独立浏览器窗口完成扫码、验证码或双重验证；一场会话可以继续统筹全部账号。
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="bg-muted/35 rounded-lg border p-3">
                <KeyRoundIcon className="text-muted-foreground mb-2 size-4" />
                <p className="text-sm font-medium">你亲自登录</p>
                <p className="text-muted-foreground mt-1 text-xs leading-5">
                  密码、扫码、验证码和 MFA 都由你操作。
                </p>
              </div>
              <div className="bg-muted/35 rounded-lg border p-3">
                <DatabaseIcon className="text-muted-foreground mb-2 size-4" />
                <p className="text-sm font-medium">深度读取业务数据</p>
                <p className="text-muted-foreground mt-1 text-xs leading-5">
                  获授权后可读取内容、指标、受众、评论和回执。
                </p>
              </div>
              <div className="bg-muted/35 rounded-lg border p-3">
                <LockKeyholeIcon className="text-muted-foreground mb-2 size-4" />
                <p className="text-sm font-medium">凭据不进入智能体</p>
                <p className="text-muted-foreground mt-1 text-xs leading-5">
                  Cookie、Token、密码和浏览器目录不会暴露给智能体。
                </p>
              </div>
            </div>
          </div>

          <div className="bg-muted/25 flex flex-col justify-between gap-5 rounded-xl border p-4 sm:p-5">
            <div className="space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold">连接状态摘要</p>
                  <p className="text-muted-foreground mt-1 text-xs">
                    {loadError
                      ? "暂时无法读取账号状态"
                      : `${summary.platformCount} 个平台 · ${summary.accountCount} 个账号`}
                  </p>
                </div>
                <ShieldCheckIcon className="text-muted-foreground size-5" />
              </div>
              <div className="flex flex-wrap gap-2" aria-label="连接状态摘要">
                <ConnectionBadge state="not_added" />
                <span className="text-sm tabular-nums">
                  {loadError ? "—" : summary.notAdded}
                </span>
                <ConnectionBadge state="pending_login" />
                <span className="text-sm tabular-nums">
                  {loadError ? "—" : summary.pendingLogin}
                </span>
                <ConnectionBadge state="logged_in" />
                <span className="text-sm tabular-nums">
                  {loadError ? "—" : summary.loggedIn}
                </span>
                <ConnectionBadge state="collection_limited" />
                <span className="text-sm tabular-nums">
                  {loadError ? "—" : summary.collectionLimited}
                </span>
                <ConnectionBadge state="actionable" />
                <span className="text-sm tabular-nums">
                  {loadError ? "—" : summary.actionable}
                </span>
              </div>
            </div>
            <div className="border-primary/15 bg-background rounded-lg border p-4">
              <p className="text-xs font-semibold tracking-wide">下一步</p>
              <p className="text-muted-foreground mt-1 text-sm leading-6">
                {loadError
                  ? "先重新读取连接状态，再继续添加账号，避免重复创建。"
                  : nextStepText(summary)}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

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
                      尚未添加账号。创建后会使用该账号独立的浏览器登录状态。
                    </div>
                  ) : (
                    platformAccounts.map((account) => {
                      const connectionState =
                        personalIPAccountConnectionState(account);
                      const copy =
                        PERSONAL_IP_CONNECTION_STATE_COPY[connectionState];
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
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              className="min-w-0 flex-1"
                              variant={
                                connectionState === "pending_login"
                                  ? "default"
                                  : "outline"
                              }
                              onClick={() => onOpenAccount(account)}
                            >
                              <LogInIcon /> {copy.action}
                            </Button>
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              aria-label={`编辑${account.display_name}`}
                              onClick={() => onEditAccount(account)}
                            >
                              <Edit3Icon />
                            </Button>
                          </div>
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
                      ? "添加并登录"
                      : "添加另一个账号"}
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
