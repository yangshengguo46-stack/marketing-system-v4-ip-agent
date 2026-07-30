"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

export default function AgentsLayout({ children: _children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    const match = /\/workspace\/agents\/[^/]+\/chats\/([^/]+)/.exec(pathname);
    router.replace(
      match?.[1]
        ? `/workspace/chats/${encodeURIComponent(decodeURIComponent(match[1]))}`
        : "/workspace/chats/new",
    );
  }, [pathname, router]);

  return null;
}
