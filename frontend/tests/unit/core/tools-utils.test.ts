import { describe, expect, it } from "@rstest/core";

import { zhCN } from "@/core/i18n/locales/zh-CN";
import { explainToolCall } from "@/core/tools/utils";

describe("explainToolCall", () => {
  it("shows customer-facing progress for live account collection", () => {
    expect(
      explainToolCall(
        {
          name: "personal_ip_collect_browser_page",
          args: { account_id: "opaque-account-id" },
        },
        zhCN,
      ),
    ).toBe("正在读取账号的最新数据…");
  });

  it("summarizes portfolio work without exposing implementation names", () => {
    const label = explainToolCall(
      {
        name: "personal_ip_collect_browser_portfolio_today",
        args: {},
      },
      zhCN,
    );

    expect(label).toBe("正在同步各平台的最新数据…");
    expect(label).not.toContain("personal_ip");
  });
});
