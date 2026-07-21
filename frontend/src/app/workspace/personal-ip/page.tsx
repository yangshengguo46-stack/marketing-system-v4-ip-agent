"use client";

import {
  Edit3Icon,
  Globe2Icon,
  LoaderCircleIcon,
  LogInIcon,
  PlusIcon,
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
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  AccountBrowserLoginDialog,
  AccountEditorDialog,
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
  type PersonalIPSubject,
  type PersonalIPSubjectInput,
  PERSONAL_IP_BROWSER_PLATFORMS,
  useCreatePersonalIPAccount,
  useCreatePersonalIPSubject,
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

  useEffect(() => {
    document.title = "经营组合 - IP Agent";
  }, []);

  const subjects = subjectsQuery.data ?? [];
  const accounts = accountsQuery.data ?? [];
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
        metadata: { connection_mode: "local_browser_profile" },
      });
      openAccountLogin(account);
    } catch (error) {
      showError(error);
    }
  };

  return (
    <WorkspaceContainer>
      <WorkspaceHeader />
      <WorkspaceBody className="overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl space-y-8 p-6 lg:p-10">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">经营组合</h1>
            <p className="text-muted-foreground max-w-3xl text-sm leading-6">
              这里只登记主体和平台账号。每次对话仍拥有完整智能体能力，并可统筹全部已授权账号；账号只在具体发布、采集或回执中作为目标。
            </p>
          </div>

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

          <section className="space-y-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">平台账号</h2>
                <p className="text-muted-foreground text-sm">
                  八个平台固定在这里。登录一次后，本机将按账号隔离并复用登录状态。
                </p>
              </div>
              <Button
                onClick={() => {
                  setEditingAccount(null);
                  setAccountOpen(true);
                }}
              >
                <PlusIcon /> 新建账号
              </Button>
            </div>
            {accountsQuery.isLoading ? (
              <p className="text-muted-foreground text-sm">正在读取账号…</p>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {PERSONAL_IP_BROWSER_PLATFORMS.map((platform) => {
                  const platformAccounts = accounts.filter(
                    (account) => account.platform === platform.id,
                  );
                  return (
                    <Card key={platform.id} className="gap-4">
                      <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                          <Globe2Icon className="size-4" />
                          {platform.label}
                        </CardTitle>
                        <CardDescription>
                          {platform.description}
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="grow space-y-2">
                        {platformAccounts.length === 0 ? (
                          <div className="text-muted-foreground rounded-md border border-dashed p-3 text-sm">
                            尚未添加账号
                          </div>
                        ) : (
                          platformAccounts.map((account) => (
                            <div
                              key={account.id}
                              className="flex items-center gap-2 rounded-md border p-2"
                            >
                              <button
                                type="button"
                                className="min-w-0 flex-1 text-left"
                                onClick={() => openAccountLogin(account)}
                              >
                                <span className="block truncate text-sm font-medium">
                                  {account.display_name}
                                </span>
                                <span className="text-muted-foreground block truncate text-xs">
                                  {account.handle ||
                                    (account.subject_id
                                      ? subjectNames.get(account.subject_id) ||
                                        "未知主体"
                                      : "未归属主体")}
                                </span>
                              </button>
                              <Button
                                size="icon-sm"
                                variant="ghost"
                                aria-label={`编辑${account.display_name}`}
                                onClick={() => {
                                  setEditingAccount(account);
                                  setAccountOpen(true);
                                }}
                              >
                                <Edit3Icon />
                              </Button>
                              <Button
                                size="icon-sm"
                                variant="outline"
                                aria-label={`登录${account.display_name}`}
                                onClick={() => openAccountLogin(account)}
                              >
                                <LogInIcon />
                              </Button>
                            </div>
                          ))
                        )}
                      </CardContent>
                      <CardFooter>
                        <Button
                          className="w-full"
                          variant={
                            platformAccounts.length === 0
                              ? "default"
                              : "outline"
                          }
                          disabled={createAccount.isPending}
                          onClick={() =>
                            void createAndOpenAccountLogin(platform)
                          }
                        >
                          {createAccount.isPending ? (
                            <LoaderCircleIcon className="animate-spin" />
                          ) : (
                            <LogInIcon />
                          )}
                          {platformAccounts.length === 0
                            ? "登录账号"
                            : "登录新账号"}
                        </Button>
                      </CardFooter>
                    </Card>
                  );
                })}
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
