# Video method contract

## Contents

1. Source boundary
2. Overview
3. Evidence units
4. Atomic methods
5. Trigger tests
6. Glossary
7. Scope and installation
8. Cangjie adaptation

## Source boundary

The semantic compiler consumes a sealed `personal-ip-video-pattern-v1`
contract. Build that contract from timestamp-capable parser receipts before
method extraction.

Allowed source evidence includes:

- ASR and speaker-aware transcript artifacts;
- OCR and caption artifacts;
- chapters and temporal grounding;
- scene and storyline analysis.

Raw transcript and OCR stay in artifacts. The semantic contract stores only
abstract summaries, source-span SHA-256 values, timestamps and evidence refs.

## Overview

`overview` contains:

~~~yaml
content_kind: long_video | course | interview | podcast
thesis: one concise source thesis
structure:
  - natural chapter or time-ordered section
limitations:
  - speaker, evidence, period or coverage limitation
~~~

## Evidence units

Each `evidence_units[]` item contains:

~~~yaml
id: lowercase-hyphen-id
kind: framework | principle | case | counterexample | term
context_group: independent-context-id
start_seconds: 12.5
end_seconds: 38.0
summary: short abstract evidence statement
evidence_refs:
  - analysis receipt id, URI, ref, segment id or video-segment URI
content_sha256: exact source-span SHA-256
~~~

Two excerpts from one example must share one `context_group`. Cross-context
support requires at least two different groups.

## Atomic methods

Each `methods[]` item contains:

~~~yaml
id: stable-method-id
skill_name: future-skill-name
title: human-readable method title
type: framework | principle | checklist | decision_rule
interpretation: abstract method in original wording
evidence_unit_ids: [at-least-two-independent-contexts]
applications:
  - evidence_unit_id: linked-evidence
    situation: observed problem
    action: observed use
    outcome: observed result
trigger_signals:
  - recognizable user situation or language
non_triggers:
  - nearby situation where this method should not run
execution_steps:
  - order: 1
    action: concrete action
    done_when: observable completion condition
    stop_if: optional stop condition
boundaries:
  - source or applicability limitation
predictive_test:
  novel_scenario: source did not directly answer this scenario
  derived_use: method-derived response
distinctiveness_rationale: why this is not generic advice
related_methods:
  - method_id: another-method
    relation: depends_on | contrasts_with | composes_with
test_cases: []
~~~

The server computes `qualification`. The model must not supply or claim a
passing qualification.

## Trigger tests

Each method carries 6–20 test cases:

~~~yaml
- id: trigger-one
  type: should_trigger | should_not_trigger | edge_case
  prompt: realistic user request
  expected_behavior: observable routing and action
  expected_method_id: method-id-or-empty
~~~

Minimum coverage:

- three `should_trigger`;
- two `should_not_trigger`;
- one `edge_case`;
- one sibling-method decoy when the distillation contains multiple methods.

These cases are an evaluation plan, not a test receipt. The compiled candidate
marks held-out execution as required.

## Glossary

Optional glossary items carry a term, its definition, its key distinction and
the supporting evidence-unit identifiers. Include only source-specific meanings
that affect downstream execution.

## Scope and installation

The method candidate compiler emits:

- one Skill definition;
- one sealed distillation reference;
- one held-out trigger evaluation plan;
- ordered Skill-manager installation steps.

It never installs automatically.

Experimental is the default for one source. Account scope requires target
account ids. Portable scope requires an approved content-pattern or
platform-pattern promotion with at least three distinct measured publications.

## Cangjie adaptation

This workflow adapts the MIT-licensed Cangjie Skill RIA-TV++ ideas:

- whole-source structural and critical understanding;
- framework, principle, case, counterexample and glossary views;
- cross-context, predictive and distinctiveness checks;
- trigger, execution and boundary construction;
- sibling-confusion pressure tests.

DeerFlow replaces direct Skill-directory writes with typed contracts,
instruction/data separation, rights receipts, `skill_manage` scanning,
owner-isolated version history and measured promotion.
