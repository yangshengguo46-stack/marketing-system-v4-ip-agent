# Third-party Skill sources

This distribution vendors selected Skill packages while keeping product
strategy, customer data and evaluation sets separate.

## Generative Media Skills

- Source: <https://github.com/calesthio/generative-media-skills>
- Revision: `8c85352d5d75d4dcbe58480bd138e37b9742bab1`
- License: MIT
- Scope: selected production Skills under `skills/public`, including their
  upstream hidden evaluation contracts and deterministic validators.

License text: [licenses/generative-media-skills-MIT.txt](licenses/generative-media-skills-MIT.txt)

## Tencent SkillHone

- Source: <https://github.com/Tencent/SkillHone>
- Revision: `69f6003949459d7e47629c6bb8b472eccb592678`
- License: MIT
- Scope: isolated evaluation and optimization packages under
  `product/skill-lab/vendor`; they are not exposed to the customer Agent.

License text: [licenses/tencent-skillhone-MIT.txt](licenses/tencent-skillhone-MIT.txt)

## Cangjie Skill

- Source: <https://github.com/kangarooking/cangjie-skill>
- Revision: `355dd47a97eeb87d249bf7d32aab561405b6de76`
- License: MIT
- Scope: the RIA-TV++ whole-source understanding, five-view extraction,
  cross-context/predictive/distinctiveness checks and sibling-confusion test
  ideas are adapted by `video-method-distillation`; the upstream repository is
  not bundled. DeerFlow adds typed evidence contracts, instruction/data
  separation, rights receipts, owner isolation, security scanning, rollback
  and measured promotion.

License text: [licenses/cangjie-skill-MIT.txt](licenses/cangjie-skill-MIT.txt)
