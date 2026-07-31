import { FlaskConicalIcon } from "lucide-react";

import { isIPAgentTestMode } from "@/core/test-mode";

export function TestModeBanner() {
  if (!isIPAgentTestMode()) return null;

  return (
    <div
      role="status"
      className="border-amber-300/70 bg-amber-50 px-3 py-1.5 text-center text-xs font-medium text-amber-950 dark:border-amber-700/60 dark:bg-amber-950/70 dark:text-amber-100"
    >
      <span className="inline-flex items-center gap-1.5">
        <FlaskConicalIcon className="size-3.5" aria-hidden="true" />
        测试模式 · 会话、记忆、账号和平台登录均与正式环境隔离
      </span>
    </div>
  );
}
