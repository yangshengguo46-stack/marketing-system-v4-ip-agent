import { describe, expect, it } from "@rstest/core";

import {
  type PersonalIPAccount,
  personalIPAccountConnectionState,
  summarizePersonalIPConnections,
} from "@/core/personal-ip";

function account(
  id: string,
  platform: string,
  metadata: Record<string, unknown>,
): PersonalIPAccount {
  return {
    id,
    owner_user_id: "owner-1",
    subject_id: null,
    platform,
    display_name: id,
    handle: null,
    avatar_url: null,
    promise_to_audience: "",
    primary_audience: "",
    content_pillars: [],
    voice_and_boundaries: [],
    business_goal: "",
    status: "active",
    metadata,
    created_at: "2026-07-22T00:00:00Z",
    updated_at: "2026-07-22T00:00:00Z",
  };
}

describe("personal IP connection states", () => {
  it("maps non-secret metadata to the four account states", () => {
    expect(personalIPAccountConnectionState(account("pending", "x", {}))).toBe(
      "pending_login",
    );
    expect(
      personalIPAccountConnectionState(
        account("logged", "x", { browser_authenticated: true }),
      ),
    ).toBe("logged_in");
    expect(
      personalIPAccountConnectionState(
        account("limited", "x", {
          browser_authenticated: true,
          collection_status: "partial",
        }),
      ),
    ).toBe("collection_limited");
    expect(
      personalIPAccountConnectionState(
        account("ready", "x", {
          connection_state: "logged_in",
          execution_ready: true,
        }),
      ),
    ).toBe("actionable");
  });

  it("summarizes unadded platforms separately from account states", () => {
    const summary = summarizePersonalIPConnections(
      [
        account("pending", "douyin", {}),
        account("ready", "douyin", { connection_state: "ready" }),
        account("limited", "youtube", {
          collection_restricted: true,
        }),
      ],
      ["douyin", "youtube", "tiktok"],
    );

    expect(summary).toEqual({
      platformCount: 3,
      accountCount: 3,
      notAdded: 1,
      pendingLogin: 1,
      loggedIn: 0,
      collectionLimited: 1,
      actionable: 1,
    });
  });
});
