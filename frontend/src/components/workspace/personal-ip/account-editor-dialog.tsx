"use client";

import { LoaderCircleIcon } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type {
  PersonalIPAccount,
  PersonalIPAccountInput,
  PersonalIPSubject,
} from "@/core/personal-ip";

const EMPTY_FORM: PersonalIPAccountInput = {
  subject_id: null,
  platform: "douyin",
  display_name: "",
  handle: null,
  avatar_url: null,
  promise_to_audience: "",
  primary_audience: "",
  content_pillars: [],
  voice_and_boundaries: [],
  business_goal: "",
};

function joinLines(values: string[]) {
  return values.join("\n");
}

function splitLines(value: string) {
  return value
    .split(/[\n,，]/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function AccountEditorDialog({
  open,
  account,
  subjects,
  submitting,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  account?: PersonalIPAccount | null;
  subjects: PersonalIPSubject[];
  submitting: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (input: PersonalIPAccountInput) => void;
}) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [pillars, setPillars] = useState("");
  const [boundaries, setBoundaries] = useState("");

  useEffect(() => {
    if (!open) return;
    const next = account
      ? {
          subject_id: account.subject_id,
          platform: account.platform,
          display_name: account.display_name,
          handle: account.handle,
          avatar_url: account.avatar_url,
          promise_to_audience: account.promise_to_audience,
          primary_audience: account.primary_audience,
          content_pillars: account.content_pillars,
          voice_and_boundaries: account.voice_and_boundaries,
          business_goal: account.business_goal,
          metadata: account.metadata,
        }
      : EMPTY_FORM;
    setForm(next);
    setPillars(joinLines(next.content_pillars));
    setBoundaries(joinLines(next.voice_and_boundaries));
  }, [account, open]);

  const setText = (
    key:
      | "platform"
      | "display_name"
      | "handle"
      | "avatar_url"
      | "promise_to_audience"
      | "primary_audience"
      | "business_goal",
    value: string,
  ) => setForm((current) => ({ ...current, [key]: value }));

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const handle = form.handle?.trim() ?? "";
    const avatarUrl = form.avatar_url?.trim() ?? "";
    onSubmit({
      ...form,
      handle: handle ? handle : null,
      avatar_url: avatarUrl ? avatarUrl : null,
      content_pillars: splitLines(pillars),
      voice_and_boundaries: splitLines(boundaries),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <form className="space-y-5" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>
              {account ? "编辑账号" : "新建个人 IP 账号"}
            </DialogTitle>
            <DialogDescription>
              这里保存的是账号经营真相。DeerFlow
              会把它注入每次运行，但不会把这些字段当成系统指令。
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm font-medium">
              经营主体
              <Select
                value={form.subject_id ?? "unassigned"}
                onValueChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    subject_id: value === "unassigned" ? null : value,
                  }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择主体" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="unassigned">暂不归属</SelectItem>
                  {subjects.map((subject) => (
                    <SelectItem key={subject.id} value={subject.id}>
                      {subject.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              平台
              <Input
                required
                value={form.platform}
                placeholder="douyin / xiaohongshu / bilibili"
                onChange={(event) => setText("platform", event.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              账号名称
              <Input
                required
                value={form.display_name}
                onChange={(event) =>
                  setText("display_name", event.target.value)
                }
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              账号 ID / handle
              <Input
                value={form.handle ?? ""}
                onChange={(event) => setText("handle", event.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              头像 URL
              <Input
                value={form.avatar_url ?? ""}
                onChange={(event) => setText("avatar_url", event.target.value)}
              />
            </label>
          </div>
          <label className="block space-y-1.5 text-sm font-medium">
            对受众的核心承诺
            <Textarea
              value={form.promise_to_audience}
              onChange={(event) =>
                setText("promise_to_audience", event.target.value)
              }
            />
          </label>
          <label className="block space-y-1.5 text-sm font-medium">
            核心受众
            <Textarea
              value={form.primary_audience}
              onChange={(event) =>
                setText("primary_audience", event.target.value)
              }
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm font-medium">
              内容支柱（每行一个）
              <Textarea
                value={pillars}
                onChange={(event) => setPillars(event.target.value)}
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              表达风格与边界（每行一个）
              <Textarea
                value={boundaries}
                onChange={(event) => setBoundaries(event.target.value)}
              />
            </label>
          </div>
          <label className="block space-y-1.5 text-sm font-medium">
            当前经营目标
            <Textarea
              value={form.business_goal}
              onChange={(event) => setText("business_goal", event.target.value)}
            />
          </label>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <LoaderCircleIcon className="animate-spin" />}
              保存账号
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
