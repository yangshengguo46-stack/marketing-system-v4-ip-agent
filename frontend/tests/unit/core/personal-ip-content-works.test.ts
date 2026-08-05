import { describe, expect, it } from "@rstest/core";

import {
  type DirectionSnapshot,
  type EditorialProgramVersion,
  personalIPContentEntryPrompt,
  personalIPContentTaskHref,
  personalIPProductionEntryPrompt,
  personalIPProductionTaskHref,
  projectPersonalIPEditorialProgram,
} from "@/core/personal-ip";

describe("Personal-IP content task entries", () => {
  it("builds bounded zero-start and benchmark task routes", () => {
    expect(personalIPContentTaskHref("zero_start")).toBe(
      "/workspace/chats/new?content_entry=zero_start",
    );
    expect(personalIPContentTaskHref("benchmark")).toBe(
      "/workspace/chats/new?content_entry=benchmark",
    );
  });

  it("prefills only the two active entry routes", () => {
    const zeroStartPrompt = personalIPContentEntryPrompt("zero_start");
    expect(zeroStartPrompt).toContain("从零起盘");
    expect(zeroStartPrompt).toContain("成交、建立认知还是积累信任");
    expect(zeroStartPrompt).toContain("个人、产品、品牌还是组织");
    expect(zeroStartPrompt).toContain("信息足够时请直接推荐");
    expect(zeroStartPrompt).toContain("不要把交流做成问卷");
    expect(personalIPContentEntryPrompt("benchmark")).toContain("对标作品");
    expect(personalIPContentEntryPrompt("account_history")).toBeUndefined();
    expect(personalIPContentEntryPrompt(null)).toBeUndefined();
  });

  it("starts Production only from bounded server work and script identifiers", () => {
    expect(personalIPProductionTaskHref("work/server", "script 1")).toBe(
      "/workspace/chats/new?production_content_work_id=work%2Fserver&production_script_version_id=script+1",
    );
    expect(
      personalIPProductionEntryPrompt("content-work-1", "script-1"),
    ).toContain("内容作品 content-work-1");
    expect(
      personalIPProductionEntryPrompt("content-work-1", "script-1"),
    ).toContain("正式剧本版本 script-1");
    expect(personalIPProductionEntryPrompt("", "script-1")).toBeUndefined();
    expect(
      personalIPProductionEntryPrompt("content-work-1", null),
    ).toBeUndefined();
    expect(
      personalIPProductionEntryPrompt("w".repeat(65), "script-1"),
    ).toBeUndefined();
  });
});

describe("Personal-IP editorial program projection", () => {
  const editorialProgram = {
    id: "editorial-version-private-1",
    program_id: "editorial-program-private-1",
    subject_id: null,
    version_number: 2,
    parent_program_version_id: null,
    title: "果园三日急售",
    decision: {
      contract_version: "personal-ip-editorial-program-v1",
      mission: {
        goal_priority: ["conversion"],
        time_horizon: "urgent",
        deadline_or_window: "3 天内",
        desired_action: "让同城采购方完成询价",
        success_signal: "收到可核验的询价",
        cost_of_delay: "果子错过可销售窗口",
        non_goals: [" 不做长期人物弧 "],
        rationale: "三天窗口优先于长期认知。",
      },
      audience: {
        situation: "需要快速确认货盘与履约的同城采购方",
        state: "hypothesized",
        uncertainties: ["具体采购规模未知"],
      },
      attribution: {
        primary_carrier: {
          kind: "product",
          identity: "当期果子",
        },
        supporting_carriers: [],
        desired_association: "货盘真实、履约清楚",
        attribution_guard: "不把当期货盘成交归因为果农人设。",
        rationale: "当前任务要让采购方记住可买的货。",
      },
      differentiation: {
        statement: "用当期货盘证据代替乡村叙事",
        contrast: "不做泛化果农成长故事",
        basis: [
          {
            claim: "用户明确给出三天销售窗口",
            state: "user_asserted",
          },
        ],
        reason_to_choose: "当前有明确的三日成交窗口",
        reason_to_believe: "可现场展示果园与货盘",
        sacrifice: "暂不展开长期个人故事",
        test_signal: "询价时直接询问数量与履约",
        uncertainties: ["采购方是否认可履约范围"],
        state: "hypothesized",
      },
      editorial_spine: null,
    },
    created_at: "2026-08-05T01:15:00Z",
  } satisfies EditorialProgramVersion;

  const direction = {
    contract_version: "personal-ip-direction-v2",
    route_kind: "offer",
    semantic_route: null,
    editorial_program_digest: "internal-digest-must-not-project",
    premise: "急售先解决信息与履约不确定。",
    audience_situation: "同城采购方需要快速判断货盘。",
    core_tension: "时间紧，但不能虚构销售信息。",
    content_promise: "只展示已确认的货盘和履约条件。",
    creative_route: "用真实货盘、交付范围和询价动作完成急售提案",
    rationale: "直接服务三日成交窗口。",
    truth_mode: "factual",
    claim_basis: [],
  } satisfies DirectionSnapshot;

  it("turns the typed decision into customer-facing labels without internals", () => {
    const projection = projectPersonalIPEditorialProgram(
      editorialProgram,
      direction,
    );

    expect(projection).toMatchObject({
      mission: {
        currentTask: "让同城采购方完成询价",
        priorityResult: "成交",
        timeWindow: "3 天内",
        nonGoals: ["不做长期人物弧"],
      },
      audience: {
        situation: "需要快速确认货盘与履约的同城采购方",
        state: "待验证",
        uncertainties: ["具体采购规模未知"],
      },
      attribution: {
        carrierKind: "产品",
        identity: "当期果子",
      },
      differentiation: {
        state: "待验证",
        statement: "用当期货盘证据代替乡村叙事",
      },
      contentRoute: {
        kind: "直接提案",
        description: "用真实货盘、交付范围和询价动作完成急售提案",
      },
    });
    expect(projection?.editorialSpine).toBeUndefined();
    expect(JSON.stringify(projection)).not.toContain("internal-digest");
    expect(JSON.stringify(projection)).not.toContain(
      "editorial-version-private",
    );
  });

  it("projects a long-term human question only when the decision includes one", () => {
    const projection = projectPersonalIPEditorialProgram(
      {
        ...editorialProgram,
        decision: {
          ...editorialProgram.decision,
          mission: {
            ...editorialProgram.decision.mission,
            goal_priority: ["recognition", "trust"],
            time_horizon: "long_term",
            deadline_or_window: "未来一年",
          },
          attribution: {
            primary_carrier: {
              kind: "person",
              identity: "返回舞台的鼓手本人",
            },
            supporting_carriers: [],
            desired_association: "持续行动的音乐人",
            attribution_guard: "不归因给阶段角色。",
            rationale: "目标是让人记住鼓手本人。",
          },
          editorial_spine: {
            source_concepts: ["重返舞台", "阶段角色"],
            human_theme: "人如何在阶段角色之外持续行动",
            recurring_question: "这周离重返舞台又近了哪一步？",
            boundary: "不展示孩子或伴侣。",
          },
        },
      },
      {
        ...direction,
        route_kind: "semantic_story",
        semantic_route: {
          association_path: ["重返舞台", "阶段角色", "持续行动"],
          human_theme: "阶段角色",
          causal_pattern: "可见的练习让长期目标逐步可信",
          episode_tension: "时间不足时如何仍完成一次练习",
          mission_bridge: "通过每周行动累积对鼓手本人的认知",
          attribution_guard: "不将认知归因给孩子或伴侣",
        },
      },
    );

    expect(projection?.mission.priorityResult).toBe("认知 → 信任");
    expect(projection?.mission.timeWindow).toBe("未来一年");
    expect(projection?.attribution.carrierKind).toBe("个人");
    expect(projection?.editorialSpine).toEqual({
      humanTheme: "人如何在阶段角色之外持续行动",
      recurringQuestion: "这周离重返舞台又近了哪一步？",
    });
  });

  it("leaves historical v1 lineage on the original direction projection", () => {
    expect(
      projectPersonalIPEditorialProgram(undefined, direction),
    ).toBeUndefined();
  });
});
