"use client";

import { useMineContextStatus } from "@/core/personal-ip";

export function LocalContextBootstrap({
  disabled = false,
}: {
  disabled?: boolean;
}) {
  useMineContextStatus({ enabled: !disabled });
  return null;
}
