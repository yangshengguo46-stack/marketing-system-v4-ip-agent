"use client";

import { FileUpIcon, LoaderCircleIcon } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  type PersonalIPFinalArtifact,
  personalIPFinalArtifactContentFileError,
  useUploadPersonalIPFinalArtifactContent,
} from "@/core/personal-ip";
import { cn } from "@/lib/utils";

export function FinalArtifactContentImport({
  artifact,
  className,
}: {
  artifact: PersonalIPFinalArtifact;
  className?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [localError, setLocalError] = useState<string>();
  const upload = useUploadPersonalIPFinalArtifactContent();
  const uploadError =
    upload.error instanceof Error
      ? upload.error.message
      : upload.error
        ? "成片文件导入失败，请重试"
        : undefined;
  const error = localError ?? uploadError;

  const selectFile = (file: File) => {
    upload.reset();
    const validationError = personalIPFinalArtifactContentFileError(
      artifact,
      file,
    );
    if (validationError) {
      setLocalError(validationError);
      return;
    }
    setLocalError(undefined);
    void upload.mutateAsync({ artifact, file }).catch(() => undefined);
  };

  return (
    <div
      className={cn(
        "space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3",
        className,
      )}
      data-testid="final-artifact-content-missing"
    >
      <div className="text-xs leading-5">
        <p className="font-medium">成片回执已恢复，文件待重新导入</p>
        <p className="text-muted-foreground mt-1">
          请选择删除前单独保存的原始 {artifact.mime_type}{" "}
          文件；服务端会核对哈希、大小和类型。
        </p>
      </div>
      <input
        ref={inputRef}
        accept={artifact.mime_type}
        aria-label="选择重新导入的成片文件"
        className="hidden"
        data-testid="final-artifact-content-file-input"
        disabled={upload.isPending}
        type="file"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) selectFile(file);
        }}
      />
      <Button
        data-testid="final-artifact-content-upload"
        disabled={upload.isPending}
        size="sm"
        type="button"
        variant="outline"
        onClick={() => inputRef.current?.click()}
      >
        {upload.isPending ? (
          <LoaderCircleIcon className="animate-spin" />
        ) : (
          <FileUpIcon />
        )}
        {upload.isPending ? "正在核验并导入…" : "重新导入成片文件"}
      </Button>
      {error && (
        <p
          aria-live="polite"
          className="text-destructive text-xs leading-5"
          data-testid="final-artifact-content-error"
          role="alert"
        >
          {error}
        </p>
      )}
    </div>
  );
}
