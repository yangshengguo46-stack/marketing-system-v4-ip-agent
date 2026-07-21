import { afterEach, expect, rs, test } from "@rstest/core";

import {
  DEFAULT_LOCAL_SETTINGS,
  getLocalSettings,
  getThreadModelName,
  saveLocalSettings,
  saveThreadModelName,
} from "@/core/settings/local";

afterEach(() => {
  rs.unstubAllGlobals();
});

test("defaults token usage to header total plus per-turn breakdown", () => {
  expect(DEFAULT_LOCAL_SETTINGS.tokenUsage).toEqual({
    headerTotal: true,
    inlineMode: "per_turn",
  });
});

test("falls back when localStorage access is blocked", () => {
  rs.stubGlobal("window", {
    get localStorage() {
      throw new DOMException("Blocked", "SecurityError");
    },
  });

  expect(getLocalSettings()).toEqual(DEFAULT_LOCAL_SETTINGS);
  expect(getThreadModelName("thread-1")).toBeUndefined();
  expect(() => saveLocalSettings(DEFAULT_LOCAL_SETTINGS)).not.toThrow();
  expect(() => saveThreadModelName("thread-1", "model-1")).not.toThrow();
});

test("restores the selected personal-IP account from local settings", () => {
  rs.stubGlobal("window", {
    localStorage: {
      getItem: () =>
        JSON.stringify({ context: { personal_ip_account_id: "acct-1" } }),
    },
  });

  expect(getLocalSettings().context.personal_ip_account_id).toBe("acct-1");
});
