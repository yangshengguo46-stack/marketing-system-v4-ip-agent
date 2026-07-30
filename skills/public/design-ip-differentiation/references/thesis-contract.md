# Differentiation thesis contract

Use `ip-differentiation-thesis-v1` as the private versioned handoff. Do not show
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

## Status gates

- `candidate`: primary entity, decision context, proprietary truth, strategic
  difference, validation hypotheses and real evidence references are complete.
- `pilot`: the candidate plus contrast field, dramatic engine, distinctive
  encoding and operating fit are complete.
- `provisionally_adopted`: at least one sealed complete observation exists for
  the thesis lineage.
- `validated`: at least three sealed complete observations cover two or more
  effect classes and include intent, adoption, conversion or economic effect.
- `retired`: a retirement reason is mandatory. Retirement is append-only and
  does not erase prior versions or observations.

Use one stable `thesis_key` while revising the same strategic direction.
A materially new direction must use a new key and restart at `candidate`.
