# Differentiation thesis contract

Use `ip-differentiation-thesis-v2` as the private versioned handoff. Do not show
these keys or status names to customers.

## Documents

```yaml
thesis_key:
status: candidate | pilot | provisionally_adopted | validated | retired
primary_entity:
  entity_type: person | brand | product | organization | portfolio
  name:
  role:
supporting_entities:
  - entity_type:
    name:
    role:
decision_context:
  category:
  target_publics: []
  jobs_to_be_done: []
  alternatives: []
  points_of_parity: []
  desired_influence: []
  desired_outcomes: []
  time_horizon:
contrast_field:
  competitor_territories: []
  category_cliches: []
  anti_benchmarks: []
  distant_analogues: []
  cultural_tension:
proprietary_truth:
  evidence_refs: []
  rare_capabilities: []
  mechanisms: []
  history: []
  relationships_access: []
  rights_assets: []
strategic_difference:
  value_created:
  meaning_created:
  reason_to_choose:
  reason_to_believe: []
  sacrifice: []
  relevance_hypothesis:
  copy_requirements: []
dramatic_engine:
  protagonist:
  public_desire:
  counterforce:
  recurring_choice:
  cost_and_state_change:
  relationship_engine:
  world:
  event_generators: []
  genre_emotional_promise:
  point_of_view:
distinctive_encoding:
  verbal_signals: []
  visual_signals: []
  sonic_signals: []
  character_signals: []
  spatial_ritual_signals: []
  behavioral_product_signals: []
  invariants: []
  controlled_variables: []
  forbidden_combinations: []
  attribution_targets: []
operating_fit:
  capacity_constraints: []
  evidence_supply: []
  channel_constraints: []
  cost_risk: []
  extension_rules: []
validation:
  evidence_level:
  observations: []
  inferences: []
  hypotheses: []
  tests:
    - test_id:
      prediction:
      observation_window:
      success_signal:
      failure_condition:
  failure_conditions: []
  retirement_reason:
evidence_refs:
  - kind:
    id:
```

## Status labels

- `candidate`, `pilot`, `provisionally_adopted`, `validated` and `retired` are
  descriptive compatibility labels, not a maturity ladder. Any useful note may
  move directly to the label that best describes the current judgment.
- No field-completeness, observation-count or effect-class rule controls a
  status change. Missing sections stay empty and uncertainty stays visible.
- Retirement remains append-only and does not erase prior versions or
  observations; a reason is useful but not a storage admission certificate.

Use one stable `thesis_key` while revising the same strategic direction.
A materially new direction should normally use a new key so its lineage stays
clear; it does not have to restart a server stage sequence.
