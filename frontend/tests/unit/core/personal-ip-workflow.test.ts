import { describe, expect, it } from "@rstest/core";

import { personalIPWorkflowResourcePath } from "@/core/personal-ip";

describe("personal IP workflow review", () => {
  it("builds an owner-scoped API path and escapes the resource id", () => {
    expect(
      personalIPWorkflowResourcePath(
        "evidence-promotions",
        "promotion/with space",
      ),
    ).toBe("/api/personal-ip/evidence-promotions/promotion%2Fwith%20space");
  });
});
