import { env } from "@/env";

export function isIPAgentTestMode(
  value = env.NEXT_PUBLIC_IP_AGENT_TEST_MODE,
): boolean {
  return value === "1" || value === "true";
}
