import { describe, expect, it } from "@rstest/core";

import {
  isInternalSkillToolCall,
  stripSkillSelectorForDisplay,
} from "@/core/skills/visibility";

describe("skill implementation visibility", () => {
  it("recognizes skill tools and skill paths as internal", () => {
    expect(isInternalSkillToolCall("skill_manage", {})).toBe(true);
    expect(
      isInternalSkillToolCall("read_file", {
        path: "/mnt/skills/video-pattern/SKILL.md",
      }),
    ).toBe(true);
    expect(
      isInternalSkillToolCall("bash", {
        description: "Run production QA",
        command: "python /mnt/user-data/run_qa.py",
      }),
    ).toBe(false);
  });

  it("keeps the request while removing an explicit skill selector", () => {
    expect(
      stripSkillSelectorForDisplay("/video-pattern improve this edit"),
    ).toBe("improve this edit");
    expect(stripSkillSelectorForDisplay("improve this edit")).toBe(
      "improve this edit",
    );
  });
});
