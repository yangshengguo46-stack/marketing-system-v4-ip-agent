"use client";

import {
  BarChart3Icon,
  BrainCircuitIcon,
  ClapperboardIcon,
  Edit3Icon,
  FlaskConicalIcon,
  LoaderCircleIcon,
  PlusIcon,
  RefreshCcwIcon,
  SendIcon,
  ShieldCheckIcon,
  UserRoundIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  AccountBrowserLoginDialog,
  AccountEditorDialog,
  OperatingReviewPanel,
  PlatformConnectionsPanel,
  SubjectEditorDialog,
} from "@/components/workspace/personal-ip";
import {
  WorkspaceBody,
  WorkspaceContainer,
  WorkspaceHeader,
} from "@/components/workspace/workspace-container";
import {
  type PersonalIPAccount,
  type PersonalIPAccountInput,
  type PersonalIPBrowserPlatform,
  countCockpitPending,
  type PersonalIPSubject,
  type PersonalIPSubjectInput,
  PERSONAL_IP_BROWSER_PLATFORMS,
  PERSONAL_IP_OPERATING_STAGES,
  PERSONAL_IP_VIDEO_STAGES,
  useCreatePersonalIPAccount,
  useCreatePersonalIPSubject,
  usePersonalIPAccounts,
  usePersonalIPOperatingCockpit,
  usePersonalIPSubjects,
  useUpdatePersonalIPAccount,
  useUpdatePersonalIPSubject,
} from "@/core/personal-ip";

const OPERATING_STAGE_DETAILS = {
  modeling: {
    icon: BrainCircuitIcon,
    description: "存在哲学、人格、需求与受众假设",
  },
  preflight: {
    icon: FlaskConicalIcon,
    description: "发布前预测、变体比较与风险判断",
  },
  publishing: {
    icon: SendIcon,
    description: "每次执行都有不可变请求与尝试回执",
  },
  performance: {
    icon: BarChart3Icon,
    description: "平台实绩、内容指标与覆盖证据",
  },
  retrospective: {
    icon: RefreshCcwIcon,
    description: "预测和结果对照，等待人工复核",
  },
  evidence: {
    icon: ShieldCheckIcon,
    description: "跨样本证据经确认后进入长期模型",
  },
} as const;

const RELATIONSHIP_LABELS = {
  self: "自营",
  client: "客户",
  partner: "合作方",
} as const;

export default function PersonalIPPortfolioPage() {
  const accountsQuery = usePersonalIPAccounts();
  const subjectsQuery = usePersonalIPSubjects();
  const cockpitQuery = usePersonalIPOperatingCockpit();
  const createAccount = useCreatePersonalIPAccount();
  const updateAccount = useUpdatePersonalIPAccount();
  const createSubject = useCreatePersonalIPSubject();
  const updateSubject = useUpdatePersonalIPSubject();
  const [accountOpen, setAccountOpen] = useState(false);
  const [subjectOpen, setSubjectOpen] = useState(false);
  const [editingAccount, setEditingAccount] =
    useState<PersonalIPAccount | null>(null);
  const [editingSubject, setEditingSubject] =
    useState<PersonalIPSubject | null>(null);
  const [loginAccount, setLoginAccount] = useState<PersonalIPAccount | null>(
    null,
  );
  const [loginPlatform, setLoginPlatform] =
    useState<PersonalIPBrowserPlatform | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "经营组合 - IP Agent";
  }, []);

  const subjects = useMemo(
    () => subjectsQuery.data ?? [],
    [subjectsQuery.data],
  );
  const accounts = useMemo(
    () => accountsQuery.data ?? [],
    [accountsQuery.data],
  );
  const cockpit = cockpitQuery.data;
  const pendingCount = countCockpitPending(cockpit);
  const subjectNames = useMemo(
    () =>
      new Map(subjects.map((subject) => [subject.id, subject.display_name])),
    [subjects],
  );

  const showError = (error: unknown) =>
    toast.error(error instanceof Error ? error.message : String(error));

  const submitSubject = async (input: PersonalIPSubjectInput) => {
    try {
      if (editingSubject) {
        await updateSubject.mutateAsync({
          subjectId: editingSubject.id,
          updates: input,
        });
      } else {
        await createSubject.mutateAsync(input);
      }
      setSubjectOpen(false);
      toast.success("经营主体已保存");
    } catch (error) {
      showError(error);
    }
  };

  const submitAccount = async (input: PersonalIPAccountInput) => {
    try {
      setConnectionError(null);
      if (editingAccount) {
        await updateAccount.mutateAsync({
          accountId: editingAccount.id,
          updates: input,
        });
      } else {
        await createAccount.mutateAsync(input);
      }
      setAccountOpen(false);
      toast.success("平台账号已保存");
    } catch (error) {
      setConnectionError(
        error instanceof Error ? error.message : String(error),
      );
      showError(error);
    }
  };

  const openAccountLogin = (account: PersonalIPAccount) => {
    const platform = PERSONAL_IP_BROWSER_PLATFORMS.find(
      (candidate) => candidate.id === account.platform,
    );
    if (!platform) {
      toast.error("这个平台还没有浏览器登录入口");
      return;
    }
    setLoginAccount(account);
    setLoginPlatform(platform);
  };

  const createAndOpenAccountLogin = async (
    platform: PersonalIPBrowserPlatform,
  ) => {
    const platformAccountCount = accounts.filter(
      (account) => account.platform === platform.id,
    ).length;
    try {
      setConnectionError(null);
      const account = await createAccount.mutateAsync({
        subject_id: null,
        platform: platform.id,
        display_name:
          platformAccountCount === 0
            ? `${platform.label}账号`
            : `${platform.label}账号 ${platformAccountCount + 1}`,
        handle: null,
        avatar_url: null,
        promise_to_audience: "",
        primary_audience: "",
        content_pillars: [],
        voice_and_boundaries: [],
        business_goal: "",
        metadata: {
          connection_mode: "local_browser_profile",
          connection_state: "pending_login",
        },
      });
      openAccountLogin(account);
    } catch (error) {
      setConnectionError(
        error instanceof Error ? error.message : String(error),
      );
      showError(error);
    }
  };

  const markAccountAuthenticated = (account: PersonalIPAccount) => {
    setConnectionError(null);
    void updateAccount
      .mutateAsync({
        accountId: account.id,
        updates: {
          metadata: {
            ...account.metadata,
            connection_mode: "local_browser_profile",
            connection_state: "logged_in",
            browser_authenticated: true,
            browser_authenticated_at: new Date().toISOString(),
          },
        },
      })
      .then(() => toast.success(`${account.display_name} 已登录`))
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        setConnectionError(
          `平台登录已经完成，但连接状态暂时没有保存：${message}`,
        );
        toast.error("登录成功，但状态保存失败；请重新读取后再试");
      });
  };

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl space-y-8 p-6 lg:p-10">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">IP Agent 经营总台账</h1>
            <p className="text-muted-foreground max-w-3xl text-sm leading-6">
              先连接账号，再让同一场会话统筹全部已授权平台。账号只在具体采集、发布或回执中作为操作目标，不会缩小整场会话的经营范围。
            </p>
          </div>

          <PlatformConnectionsPanel
            accounts={accounts}
            subjectNames={subjectNames}
            loading={accountsQuery.isLoading}
            loadError={
              accountsQuery.isError
                ? accountsQuery.error instanceof Error
                  ? accountsQuery.error.message
                  : "无法读取账号连接状态"
                : null
            }
            actionError={connectionError}
            actionPending={createAccount.isPending || updateAccount.isPending}
            onAddPlatform={(platform) =>
              void createAndOpenAccountLogin(platform)
            }
            onOpenAccount={openAccountLogin}
            onEditAccount={(account) => {
              setEditingAccount(account);
              setAccountOpen(true);
            }}
            onRetry={() => {
              setConnectionError(null);
              void accountsQuery.refetch();
            }}
            onDismissError={() => setConnectionError(null)}
          />

          <section className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">经营主线</h2>
                <p className="text-muted-foreground text-sm">
                  DeerFlow 负责执行，这六步保存个人 IP 真正需要积累的业务状态。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">
                  {cockpit?.portfolio.subject_count ?? subjects.length} 个主体
                </Badge>
                <Badge variant="outline">
                  {cockpit?.portfolio.account_count ?? accounts.length} 个账号
                </Badge>
                <Badge variant={pendingCount > 0 ? "secondary" : "outline"}>
                  {pendingCount > 0 ? `${pendingCount} 项待推进` : "当前无待办"}
                </Badge>
              </div>
            </div>

            {cockpitQuery.isLoading ? (
              <Card>
                <CardContent className="text-muted-foreground flex items-center gap-2 text-sm">
                  <LoaderCircleIcon className="size-4 animate-spin" />
                  正在汇总经营闭环…
                </CardContent>
              </Card>
            ) : cockpitQuery.isError || !cockpit ? (
              <Card>
                <CardContent className="text-destructive text-sm">
                  经营闭环暂时无法读取，账号管理仍可正常使用。
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
                {PERSONAL_IP_OPERATING_STAGES.map((definition, index) => {
                  const stage = cockpit.stages[definition.id];
                  const details = OPERATING_STAGE_DETAILS[definition.id];
                  const Icon = details.icon;
                  return (
                    <Card key={definition.id} className="gap-3 py-4">
                      <CardHeader className="gap-3 px-4">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-muted-foreground text-xs tabular-nums">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <Icon className="text-muted-foreground size-4" />
                        </div>
                        <CardTitle className="text-sm leading-5">
                          {definition.label}
                        </CardTitle>
                        <CardDescription className="text-xs leading-5">
                          {details.description}
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="flex items-center justify-between px-4">
                        <span className="text-lg font-semibold tabular-nums">
                          {stage.total}
                        </span>
                        <Badge
                          variant={stage.pending > 0 ? "secondary" : "outline"}
                        >
                          {stage.pending > 0
                            ? `${stage.pending} 待处理`
                            : stage.total > 0
                              ? "已接通"
                              : "待开始"}
                        </Badge>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </section>

          <section className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <ClapperboardIcon className="size-5" />
                  影视生产线
                </h2>
                <p className="text-muted-foreground text-sm">
                  生成模型可以替换，蓝图、资产、镜头、失败重试、成本和交付回执留在同一条生产线上。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">
                  {cockpit?.video.production_count ?? 0} 个项目
                </Badge>
                <Badge variant="outline">
                  {cockpit?.video.completed_count ?? 0} 已交付
                </Badge>
                {(cockpit?.video.blocked_production_ids.length ?? 0) > 0 && (
                  <Badge variant="secondary">
                    {cockpit?.video.blocked_production_ids.length} 个受阻
                  </Badge>
                )}
              </div>
            </div>
            <Card>
              <CardContent className="grid gap-2 sm:grid-cols-3 xl:grid-cols-9">
                {PERSONAL_IP_VIDEO_STAGES.map((stage, index) => (
                  <div
                    key={stage.id}
                    className="bg-muted/35 rounded-lg border px-3 py-3"
                  >
                    <div className="text-muted-foreground flex items-center justify-between text-[11px] tabular-nums">
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <span>{cockpit?.video.stages[stage.id] ?? 0}</span>
                    </div>
                    <p className="mt-2 text-xs leading-5 font-medium">
                      {stage.label}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </section>

          {cockpit && <OperatingReviewPanel cockpit={cockpit} />}

          <section className="space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">经营主体</h2>
                <p className="text-muted-foreground text-sm">
                  你自己、客户、品牌或组织。
                </p>
              </div>
              <Button
                onClick={() => {
                  setEditingSubject(null);
                  setSubjectOpen(true);
                }}
              >
                <PlusIcon /> 新建主体
              </Button>
            </div>
            {subjectsQuery.isLoading ? (
              <p className="text-muted-foreground text-sm">正在读取主体…</p>
            ) : subjects.length === 0 ? (
              <Card>
                <CardContent className="text-muted-foreground text-sm">
                  还没有经营主体。
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {subjects.map((subject) => (
                  <Card key={subject.id} className="gap-4">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <UserRoundIcon className="size-4" />
                        {subject.display_name}
                      </CardTitle>
                      <CardDescription>
                        {subject.description || "暂无说明"}
                      </CardDescription>
                      <CardAction>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label="编辑主体"
                          onClick={() => {
                            setEditingSubject(subject);
                            setSubjectOpen(true);
                          }}
                        >
                          <Edit3Icon />
                        </Button>
                      </CardAction>
                    </CardHeader>
                    <CardContent className="flex flex-wrap gap-2">
                      <Badge variant="secondary">
                        {RELATIONSHIP_LABELS[subject.relationship]}
                      </Badge>
                      <Badge variant="outline">
                        {
                          accounts.filter(
                            (account) => account.subject_id === subject.id,
                          ).length
                        }{" "}
                        个账号
                      </Badge>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </section>
        </div>
      </WorkspaceBody>

      <SubjectEditorDialog
        open={subjectOpen}
        subject={editingSubject}
        submitting={createSubject.isPending || updateSubject.isPending}
        onOpenChange={setSubjectOpen}
        onSubmit={submitSubject}
      />
      <AccountEditorDialog
        open={accountOpen}
        account={editingAccount}
        subjects={subjects}
        submitting={createAccount.isPending || updateAccount.isPending}
        onOpenChange={setAccountOpen}
        onSubmit={submitAccount}
      />
      <AccountBrowserLoginDialog
        open={Boolean(loginAccount && loginPlatform)}
        account={loginAccount}
        platform={loginPlatform}
        onAuthenticated={markAccountAuthenticated}
        onOpenChange={(open) => {
          if (!open) {
            setLoginAccount(null);
            setLoginPlatform(null);
          }
        }}
      />
    </WorkspaceContainer>
  );
}
