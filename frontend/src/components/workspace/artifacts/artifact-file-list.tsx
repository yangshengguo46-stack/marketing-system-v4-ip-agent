import { DownloadIcon } from "lucide-react";
import { useCallback, useMemo } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  isCustomerVisibleArtifact,
  urlOfArtifact,
} from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import {
  getFileExtensionDisplayName,
  getFileIcon,
  getFileName,
} from "@/core/utils/files";
import { cn } from "@/lib/utils";

import { useArtifacts } from "./context";

export function ArtifactFileList({
  className,
  files,
  threadId,
}: {
  className?: string;
  files: string[];
  threadId: string;
}) {
  const { t } = useI18n();
  const { select: selectArtifact, setOpen } = useArtifacts();
  const visibleFiles = useMemo(
    () => files.filter(isCustomerVisibleArtifact),
    [files],
  );

  const handleClick = useCallback(
    (filepath: string) => {
      selectArtifact(filepath);
      setOpen(true);
    },
    [selectArtifact, setOpen],
  );

  if (visibleFiles.length === 0) return null;

  return (
    <ul className={cn("flex w-full flex-col gap-4", className)}>
      {visibleFiles.map((file) => (
        <Card
          key={file}
          className="relative cursor-pointer p-3"
          onClick={() => handleClick(file)}
        >
          <CardHeader className="grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 pr-2 pl-1">
            <CardTitle className="relative min-w-0 pl-8 leading-tight [overflow-wrap:anywhere] break-words">
              <div className="min-w-0">{getFileName(file)}</div>
              <div className="absolute top-2 -left-0.5">
                {getFileIcon(file, "size-6")}
              </div>
            </CardTitle>
            <CardDescription className="min-w-0 pl-8 text-xs">
              {getFileExtensionDisplayName(file)} file
            </CardDescription>
            <CardAction className="row-span-1 self-center">
              <Button variant="ghost" asChild>
                <a
                  href={urlOfArtifact({
                    filepath: file,
                    threadId: threadId,
                    download: true,
                  })}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  <DownloadIcon className="size-4" />
                  {t.common.download}
                </a>
              </Button>
            </CardAction>
          </CardHeader>
        </Card>
      ))}
    </ul>
  );
}
