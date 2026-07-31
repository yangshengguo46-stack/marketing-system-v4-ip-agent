import { describe, expect, it } from "@rstest/core";

import { isIPAgentTestMode } from "@/core/test-mode";

describe("isIPAgentTestMode", () => {
  it("accepts only explicit local test-mode flags", () => {
    expect(isIPAgentTestMode("1")).toBe(true);
    expect(isIPAgentTestMode("true")).toBe(true);
    expect(isIPAgentTestMode("0")).toBe(false);
    expect(isIPAgentTestMode("false")).toBe(false);
    expect(isIPAgentTestMode(undefined)).toBe(false);
  });
});
