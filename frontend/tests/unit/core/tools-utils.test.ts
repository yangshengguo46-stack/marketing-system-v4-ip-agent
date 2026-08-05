import { describe, expect, it } from "@rstest/core";

import { enUS } from "@/core/i18n/locales/en-US";
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

  it("makes a long complete video analysis visibly distinct from generic thinking", () => {
    const label = explainToolCall(
      {
        name: "ip_evidence_inspect_reference_videos",
        args: { references: ["opaque-reference"] },
      },
      zhCN,
    );

    expect(label).toBe(
      "正在完整拆解视频：转写、画面文字、场景与故事线可能需要数分钟…",
    );
    expect(label).not.toContain("ip_evidence");
  });

  it("describes persisted content work without exposing tool names", () => {
    const label = explainToolCall({ name: "ip_content_write", args: {} }, zhCN);

    expect(label).toBe("正在生成并保存完整脚本版本…");
    expect(label).not.toContain("ip_content");
  });

  it("describes formal-script Production startup without exposing the tool name", () => {
    const toolCall = {
      name: "ip_content_start_production",
      args: { content_work_id: "work-1", script_version_id: "script-1" },
    };

    const zhLabel = explainToolCall(toolCall, zhCN);
    const enLabel = explainToolCall(toolCall, enUS);

    expect(zhLabel).toBe("正在从正式剧本启动制作…");
    expect(enLabel).toBe("Starting production from the formal script…");
    expect(zhLabel).not.toContain("ip_content");
    expect(enLabel).not.toContain("ip_content");
  });
});
