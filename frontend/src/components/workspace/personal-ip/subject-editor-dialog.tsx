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
  PersonalIPSubject,
  PersonalIPSubjectInput,
} from "@/core/personal-ip";

const EMPTY_FORM: PersonalIPSubjectInput = {
  display_name: "",
  subject_type: "creator",
  relationship: "self",
  description: "",
};

export function SubjectEditorDialog({
  open,
  subject,
  submitting,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  subject?: PersonalIPSubject | null;
  submitting: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (input: PersonalIPSubjectInput) => void;
}) {
  const [form, setForm] = useState(EMPTY_FORM);

  useEffect(() => {
    if (!open) return;
    setForm(
      subject
        ? {
            display_name: subject.display_name,
            subject_type: subject.subject_type,
            relationship: subject.relationship,
            description: subject.description,
            metadata: subject.metadata,
          }
        : EMPTY_FORM,
    );
  }, [open, subject]);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit({ ...form, display_name: form.display_name.trim() });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <form className="space-y-5" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>
              {subject ? "编辑经营主体" : "新建经营主体"}
            </DialogTitle>
            <DialogDescription>
              主体可以是个人、品牌、产品或组织；一个主体可关联多个平台账号。
            </DialogDescription>
          </DialogHeader>
          <label className="block space-y-1.5 text-sm font-medium">
            主体名称
            <Input
              required
              value={form.display_name}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  display_name: event.target.value,
                }))
              }
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1.5 text-sm font-medium">
              主体类型
              <Select
                value={form.subject_type}
                onValueChange={(
                  value: PersonalIPSubjectInput["subject_type"],
                ) =>
                  setForm((current) => ({ ...current, subject_type: value }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="creator">个人创作者</SelectItem>
                  <SelectItem value="brand">品牌</SelectItem>
                  <SelectItem value="product">产品</SelectItem>
                  <SelectItem value="organization">组织</SelectItem>
                </SelectContent>
              </Select>
            </label>
            <label className="space-y-1.5 text-sm font-medium">
              经营关系
              <Select
                value={form.relationship}
                onValueChange={(
                  value: PersonalIPSubjectInput["relationship"],
                ) =>
                  setForm((current) => ({ ...current, relationship: value }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="self">自营</SelectItem>
                  <SelectItem value="client">客户</SelectItem>
                  <SelectItem value="partner">合作方</SelectItem>
                </SelectContent>
              </Select>
            </label>
          </div>
          <label className="block space-y-1.5 text-sm font-medium">
            说明
            <Textarea
              value={form.description}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
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
            <Button
              type="submit"
              disabled={submitting || !form.display_name.trim()}
            >
              {submitting && <LoaderCircleIcon className="animate-spin" />}
              保存主体
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
