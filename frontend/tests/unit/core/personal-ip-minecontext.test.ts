import { describe, expect, it } from "@rstest/core";

import { describeMineContextStatus } from "@/core/personal-ip";

describe("MineContext user-visible state", () => {
  it("distinguishes operator disablement from missing owner consent", () => {
    expect(
      describeMineContextStatus({
        operator_enabled: false,
        available: false,
        source_verified: true,
        runtime_ready: false,
        authorized: false,
        running: false,
      }),
    ).toEqual({ label: "系统未启用", action: "请管理员先启用并安装本地观察源" });

    expect(
      describeMineContextStatus({
        operator_enabled: true,
        available: true,
        source_verified: true,
        runtime_ready: true,
        authorized: false,
        running: false,
      }),
    ).toEqual({ label: "等待授权", action: "选择范围与用途后明确授权" });
  });

  it("never describes authorization as active capture", () => {
    expect(
      describeMineContextStatus({
        operator_enabled: true,
        available: true,
        source_verified: true,
        runtime_ready: true,
        authorized: true,
        running: false,
      }),
    ).toEqual({ label: "已授权，未运行", action: "需要时手动启动；不会自动恢复采集" });
  });
});
