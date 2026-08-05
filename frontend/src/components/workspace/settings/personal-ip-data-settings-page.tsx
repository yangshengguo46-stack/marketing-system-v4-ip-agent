"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  DownloadIcon,
  FileUpIcon,
  LoaderCircleIcon,
  ShieldAlertIcon,
  Trash2Icon,
} from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  deleteAllPersonalIPData,
  exportPersonalIPBackup,
  type PersonalIPBackup,
  type PersonalIPDeletePreview,
  previewPersonalIPDelete,
  restorePersonalIPBackup,
} from "@/core/personal-ip";

function isBackup(value: unknown): value is PersonalIPBackup {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<PersonalIPBackup>;
  return (
    candidate.schema_version === "personal-ip-owner-backup-v1" &&
    Array.isArray(candidate.datasets) &&
    typeof candidate.verification?.data_digest === "string" &&
    typeof candidate.verification?.manifest_digest === "string"
  );
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : "操作没有完成，请稍后重试";
}

export function PersonalIPDataSettingsPage() {
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<
    "export" | "restore" | "preview" | "delete"
  >();
  const [preview, setPreview] = useState<PersonalIPDeletePreview>();
  const [phrase, setPhrase] = useState("");
  const [backupAcknowledged, setBackupAcknowledged] = useState(false);

  const refreshPersonalIP = async () => {
    await queryClient.invalidateQueries({ queryKey: ["personal-ip"] });
  };

  const exportBackup = async () => {
    setBusy("export");
    try {
      const backup = await exportPersonalIPBackup();
      const blob = new Blob([JSON.stringify(backup, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `personal-ip-backup-${backup.exported_at.slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      toast.success("个人 IP 数据备份已导出");
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(undefined);
    }
  };

  const restoreBackup = async (file: File) => {
    setBusy("restore");
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!isBackup(parsed)) {
        throw new Error("请选择有效的 Personal‑IP 备份文件");
      }
      const receipt = await restorePersonalIPBackup(parsed);
      if (!receipt.verified) {
        throw new Error("服务端没有完成恢复校验");
      }
      await refreshPersonalIP();
      toast.success("备份已恢复；平台账号需要重新登录授权");
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(undefined);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const prepareDelete = async () => {
    setBusy("preview");
    try {
      setPreview(await previewPersonalIPDelete());
      setPhrase("");
      setBackupAcknowledged(false);
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(undefined);
    }
  };

  const deleteEverything = async () => {
    if (!preview) return;
    setBusy("delete");
    try {
      await deleteAllPersonalIPData({
        schema_version: "personal-ip-destructive-delete-confirmation-v1",
        owner_user_id: preview.owner_user_id,
        state_digest: preview.state_digest,
        confirmation_phrase: phrase,
        backup_acknowledged: true,
        delete_local_context: true,
      });
      setPreview(undefined);
      setPhrase("");
      setBackupAcknowledged(false);
      await refreshPersonalIP();
      toast.success("全部 Personal‑IP 数据已永久删除");
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(undefined);
    }
  };

  const loading = busy !== undefined;
  const deleteReady =
    Boolean(preview) &&
    backupAcknowledged &&
    phrase === preview?.confirmation_phrase;

  return (
    <section aria-labelledby="personal-ip-data-title" className="space-y-5">
      <Card className="border-primary/15">
        <CardHeader>
          <CardTitle
            id="personal-ip-data-title"
            className="flex items-center gap-2"
          >
            <DownloadIcon className="size-4" /> 数据与备份
          </CardTitle>
          <CardDescription className="max-w-3xl leading-6">
            导出经营主体、账号、发布回执、指标与平台观测、平台连接外壳和视频制作账本。备份不含密码、Cookie、平台访问令牌、一次性授权状态或付费调用准入记录。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <ShieldAlertIcon />
            <AlertTitle>恢复后需要重新登录平台</AlertTitle>
            <AlertDescription>
              为避免凭证泄露，平台授权不会进入备份。恢复只允许在当前 Personal‑IP
              数据为空时执行，并会逐表校验备份摘要。
            </AlertDescription>
          </Alert>
          <div className="flex flex-wrap gap-2">
            <Button disabled={loading} onClick={() => void exportBackup()}>
              {busy === "export" ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <DownloadIcon />
              )}
              导出完整备份
            </Button>
            <Button
              variant="outline"
              disabled={loading}
              onClick={() => fileInput.current?.click()}
            >
              {busy === "restore" ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <FileUpIcon />
              )}
              从备份恢复
            </Button>
            <input
              ref={fileInput}
              className="hidden"
              type="file"
              accept="application/json,.json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void restoreBackup(file);
              }}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-destructive flex items-center gap-2">
            <Trash2Icon className="size-4" /> 永久删除
          </CardTitle>
          <CardDescription className="leading-6">
            删除所有 Personal‑IP
            业务数据、加密平台凭证、未完成授权状态和本地上下文。此操作无法撤销。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!preview ? (
            <Button
              variant="destructive"
              disabled={loading}
              onClick={() => void prepareDelete()}
            >
              {busy === "preview" ? (
                <LoaderCircleIcon className="animate-spin" />
              ) : (
                <Trash2Icon />
              )}
              准备永久删除
            </Button>
          ) : (
            <div className="border-destructive/40 bg-destructive/5 space-y-4 rounded-lg border p-4">
              <p className="text-sm font-medium">
                将永久删除 {preview.total_records}{" "}
                条数据库记录及全部本地上下文。
              </p>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={backupAcknowledged}
                  onChange={(event) =>
                    setBackupAcknowledged(event.target.checked)
                  }
                />
                <span>我已导出所需备份，或确认不需要备份。</span>
              </label>
              <label className="block space-y-2 text-sm">
                <span>
                  输入确认语句：
                  <strong>{preview.confirmation_phrase}</strong>
                </span>
                <Input
                  autoComplete="off"
                  value={phrase}
                  onChange={(event) => setPhrase(event.target.value)}
                />
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="destructive"
                  disabled={!deleteReady || loading}
                  onClick={() => void deleteEverything()}
                >
                  {busy === "delete" ? (
                    <LoaderCircleIcon className="animate-spin" />
                  ) : (
                    <Trash2Icon />
                  )}
                  永久删除全部数据
                </Button>
                <Button
                  variant="outline"
                  disabled={loading}
                  onClick={() => setPreview(undefined)}
                >
                  取消
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
