"use client";

import {
  Edit3Icon,
  PlusIcon,
  UserRoundIcon,
  UsersRoundIcon,
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
  type PersonalIPSubject,
  type PersonalIPSubjectInput,
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
                  供全平台分析和具体操作定位使用。
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
            ) : accounts.length === 0 ? (
              <Card>
                <CardContent className="text-muted-foreground text-sm">
                  还没有平台账号。
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {accounts.map((account) => (
                  <Card key={account.id} className="gap-4">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <UsersRoundIcon className="size-4" />
                        {account.display_name}
                      </CardTitle>
                      <CardDescription>
                        {account.handle || "未登记 handle"}
                      </CardDescription>
                      <CardAction>
                        <Button
                          size="icon-sm"
                          variant="ghost"
                          aria-label="编辑账号"
                          onClick={() => {
                            setEditingAccount(account);
                            setAccountOpen(true);
                          }}
                        >
                          <Edit3Icon />
                        </Button>
                      </CardAction>
                    </CardHeader>
                    <CardContent className="flex flex-wrap gap-2">
                      <Badge>{account.platform}</Badge>
                      <Badge variant="outline">
                        {account.subject_id
                          ? subjectNames.get(account.subject_id) || "未知主体"
                          : "未归属主体"}
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
    </WorkspaceContainer>
  );
}
