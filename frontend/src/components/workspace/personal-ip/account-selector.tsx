"use client";

import {
  CheckIcon,
  ChevronsUpDownIcon,
  PlusIcon,
  UsersIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  useBindPersonalIPAccount,
  useCreatePersonalIPAccount,
  usePersonalIPAccounts,
  type PersonalIPAccountInput,
} from "@/core/personal-ip";

import { AccountEditorDialog } from "./account-editor-dialog";

export function AccountSelector({
  value,
  threadId,
  disabled,
  onChange,
}: {
  value?: string;
  threadId?: string;
  disabled?: boolean;
  onChange: (accountId: string) => void;
}) {
  const accounts = usePersonalIPAccounts();
  const createAccount = useCreatePersonalIPAccount();
  const bindAccount = useBindPersonalIPAccount();
  const [createOpen, setCreateOpen] = useState(false);
  const selected = accounts.data?.find((account) => account.id === value);

  const selectAccount = async (accountId: string) => {
    try {
      if (threadId) {
        await bindAccount.mutateAsync({ threadId, accountId });
      }
      onChange(accountId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "账号切换失败");
    }
  };

  const create = async (input: PersonalIPAccountInput) => {
    try {
      const account = await createAccount.mutateAsync(input);
      setCreateOpen(false);
      await selectAccount(account.id);
      toast.success("账号已创建并设为当前账号");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "账号创建失败");
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="max-w-56 gap-2"
            disabled={disabled ? true : accounts.isLoading}
          >
            <UsersIcon className="size-4" />
            <span className="truncate">
              {selected?.display_name ??
                (value ? "账号不可用" : "选择经营账号")}
            </span>
            <ChevronsUpDownIcon className="size-3.5 opacity-60" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>当前任务属于哪个账号</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {accounts.data?.map((account) => (
            <DropdownMenuItem
              key={account.id}
              className="flex items-center gap-2"
              onSelect={() => void selectAccount(account.id)}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">
                  {account.display_name}
                </div>
                <div className="text-muted-foreground truncate text-xs">
                  {account.platform}
                  {account.handle ? ` · ${account.handle}` : ""}
                </div>
              </div>
              {account.id === value && <CheckIcon className="size-4" />}
            </DropdownMenuItem>
          ))}
          {!accounts.data?.length && (
            <div className="text-muted-foreground px-2 py-4 text-center text-xs">
              还没有账号，先建一个。
            </div>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCreateOpen(true)}>
            <PlusIcon />
            新建账号
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AccountEditorDialog
        open={createOpen}
        submitting={createAccount.isPending}
        onOpenChange={setCreateOpen}
        onSubmit={(input) => void create(input)}
      />
    </>
  );
}
