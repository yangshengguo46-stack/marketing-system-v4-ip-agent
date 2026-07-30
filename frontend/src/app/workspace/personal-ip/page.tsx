"use client";

import { Edit3Icon, PlusIcon, UserRoundIcon } from "lucide-react";
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
  type PersonalIPBrowserPlatform,
  type PersonalIPSubject,
  type PersonalIPSubjectInput,
  PERSONAL_IP_BROWSER_PLATFORMS,
  useCreatePersonalIPAccount,
  useCreatePersonalIPSubject,
  useLogoutPersonalIPAccount,
  usePersonalIPAccounts,
  usePersonalIPSubjects,
  useUpdatePersonalIPAccount,
  useUpdatePersonalIPSubject,
} from "@/core/personal-ip";

const RELATIONSHIP_LABELS = {
  self: "自营",
  client: "客户",
  partner: "合作方",
} as const;

export default function PersonalIPPortfolioPage() {
  const accountsQuery = usePersonalIPAccounts();
  const subjectsQuery = usePersonalIPSubjects();
  const createAccount = useCreatePersonalIPAccount();
  const updateAccount = useUpdatePersonalIPAccount();
  const logoutAccount = useLogoutPersonalIPAccount();
  const createSubject = useCreatePersonalIPSubject();
  const updateSubject = useUpdatePersonalIPSubject();
  const [subjectOpen, setSubjectOpen] = useState(false);
  const [editingSubject, setEditingSubject] =
    useState<PersonalIPSubject | null>(null);
  const [loginAccount, setLoginAccount] = useState<PersonalIPAccount | null>(
    null,
  );
  const [loginPlatform, setLoginPlatform] =
    useState<PersonalIPBrowserPlatform | null>(null);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  useEffect(() => {
    document.title = "平台管理 - IP Agent";
  }, []);

  const subjects = useMemo(
    () => subjectsQuery.data ?? [],
    [subjectsQuery.data],
  );
  const accounts = useMemo(
    () => accountsQuery.data ?? [],
    [accountsQuery.data],
  );
  const subjectNames = useMemo(
    () =>
      new Map(subjects.map((subject) => [subject.id, subject.display_name])),
    [subjects],
  );

  const showError = (_error: unknown) =>
    toast.error("这次操作没有完成，请稍后重试");

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
        metadata: {
          connection_mode: "local_browser_profile",
          connection_state: "pending_login",
        },
      });
      openAccountLogin(account);
    } catch (error) {
      setConnectionError("账号暂时无法添加，请稍后重试");
      showError(error);
    }
  };

  const markAccountAuthenticated = (account: PersonalIPAccount) => {
    setConnectionError(null);
    const authenticatedMetadata = { ...account.metadata };
    delete authenticatedMetadata.logged_out_at;
    delete authenticatedMetadata.execution_ready;
    void updateAccount
      .mutateAsync({
        accountId: account.id,
        updates: {
          metadata: {
            ...authenticatedMetadata,
            connection_mode: "local_browser_profile",
            connection_state: "logged_in",
            browser_authenticated: true,
            browser_authenticated_at: new Date().toISOString(),
          },
        },
      })
      .then(() => toast.success(`${account.display_name} 已登录`))
      .catch((_error: unknown) => {
        setConnectionError("平台登录已经完成，但状态暂时没有保存，请重试");
        toast.error("登录成功，但状态保存失败；请重新读取后再试");
      });
  };

  const logoutPlatformAccount = async (account: PersonalIPAccount) => {
    try {
      setConnectionError(null);
      await logoutAccount.mutateAsync(account.id);
      toast.success(`${account.display_name} 已退出登录`);
    } catch (error) {
      setConnectionError("暂时无法退出登录，请稍后重试");
      showError(error);
    }
  };

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl space-y-8 p-6 lg:p-10">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">平台管理</h1>
            <p className="text-muted-foreground max-w-3xl text-sm leading-6">
              在这里管理经营主体和八个平台账号。增长与作品表现请前往工作台，本地上下文授权请前往设置。
            </p>
          </div>

          <PlatformConnectionsPanel
            accounts={accounts}
            subjectNames={subjectNames}
            loading={accountsQuery.isLoading}
            loadError={
              accountsQuery.isError
                ? "暂时无法读取账号，请稍后重试"
                : null
            }
            actionError={connectionError}
            actionPending={
              createAccount.isPending ||
              updateAccount.isPending ||
              logoutAccount.isPending
            }
            onAddPlatform={(platform) =>
              void createAndOpenAccountLogin(platform)
            }
            onLoginAccount={openAccountLogin}
            onLogoutAccount={(account) => void logoutPlatformAccount(account)}
            onRetry={() => {
              setConnectionError(null);
              void accountsQuery.refetch();
            }}
            onDismissError={() => setConnectionError(null)}
          />

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
