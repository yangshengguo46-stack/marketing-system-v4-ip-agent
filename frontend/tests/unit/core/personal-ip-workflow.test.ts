import { describe, expect, it } from "@rstest/core";

import { personalIPWorkflowResourcePath } from "@/core/personal-ip";

describe("personal IP workflow review", () => {
  it("builds an owner-scoped API path and escapes the resource id", () => {
    expect(
      personalIPWorkflowResourcePath("retrospectives", "review/with space"),
    ).toBe("/api/personal-ip/retrospectives/review%2Fwith%20space");
  });
});
