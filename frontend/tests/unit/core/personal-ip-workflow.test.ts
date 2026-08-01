import { describe, expect, it } from "@rstest/core";

import { personalIPWorkflowResourcePath } from "@/core/personal-ip";

describe("personal IP retained workflow detail", () => {
  it("builds an owner-scoped publish receipt path and escapes the id", () => {
    expect(
      personalIPWorkflowResourcePath("publish-receipts", "receipt/with space"),
    ).toBe("/api/personal-ip/publish-receipts/receipt%2Fwith%20space");
  });
});
