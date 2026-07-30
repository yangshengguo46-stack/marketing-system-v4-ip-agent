import fs from "fs";
import path from "path";

import type { NextRequest } from "next/server";

const SAFE_PATH_SEGMENT = /^[^./\\\0][^/\\\0]*$/;

function isSafePathSegment(segment: string) {
  return SAFE_PATH_SEGMENT.test(segment) && segment !== "..";
}

export function resolveMockArtifactPath({
  threadId,
  artifactPath,
}: {
  threadId: string;
  artifactPath: string[];
}) {
  if (
    !isSafePathSegment(threadId) ||
    artifactPath[0] !== "mnt" ||
    artifactPath.length < 2 ||
    !artifactPath.slice(1).every(isSafePathSegment)
  ) {
    return null;
  }

  // Keep the dynamic suffix visibly anchored below the demo fixture tree.
  // Turbopack can then trace only this subtree instead of the whole project.
  const relativeArtifactPath = [threadId, ...artifactPath.slice(1)].join(
    path.sep,
  );
  const candidatePath = path.join(
    process.cwd(),
    "public/demo/threads",
    relativeArtifactPath,
  );
  if (!fs.existsSync(candidatePath)) {
    return null;
  }

  const demoRoot = fs.realpathSync(
    path.join(process.cwd(), "public/demo/threads"),
  );
  const threadRoot = fs.realpathSync(
    path.join(process.cwd(), "public/demo/threads", threadId),
  );
  const resolvedPath = fs.realpathSync(candidatePath);
  const relativeThreadRoot = path.relative(demoRoot, threadRoot);
  const relativePath = path.relative(threadRoot, resolvedPath);
  if (
    relativeThreadRoot === ".." ||
    relativeThreadRoot.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativeThreadRoot) ||
    relativePath === ".." ||
    relativePath.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativePath)
  ) {
    return null;
  }
  // Read through the statically anchored path so NFT retains the fixture-tree
  // scope; resolvedPath is used only to reject symlink escapes.
  return candidatePath;
}

export async function GET(
  request: NextRequest,
  {
    params,
  }: {
    params: Promise<{
      thread_id: string;
      artifact_path?: string[] | undefined;
    }>;
  },
) {
  const { thread_id: threadId, artifact_path: artifactPath = [] } =
    await params;
  const resolvedPath = resolveMockArtifactPath({ threadId, artifactPath });
  if (!resolvedPath) {
    return new Response("File not found", { status: 404 });
  }

  if (request.nextUrl.searchParams.get("download") === "true") {
    const headers = new Headers();
    headers.set(
      "Content-Disposition",
      `attachment; filename="${path.basename(resolvedPath)}"`,
    );
    return new Response(fs.readFileSync(resolvedPath), {
      status: 200,
      headers,
    });
  }
  if (resolvedPath.endsWith(".mp4")) {
    return new Response(fs.readFileSync(resolvedPath), {
      status: 200,
      headers: {
        "Content-Type": "video/mp4",
      },
    });
  }
  return new Response(fs.readFileSync(resolvedPath), { status: 200 });
}
