"""Offline validator for the quarantined IP director concept contract.

This module is research-only.  It deliberately has no imports from the product
runtime and performs no model, network, persistence, or publishing work.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_VERSION = "ip-director-concept-v1"
RUNTIME_STATUS = "research_quarantined"

ENTITY_KINDS = {
    "person",
    "product",
    "organization",
    "audience",
    "fictional_character",
    "content_series",
}
OPERATED_SUBJECT_KINDS = {"person", "product", "organization"}
HUMAN_DESIRE_KINDS = {"person", "audience", "fictional_character"}
EPISTEMIC_STATES = {
    "user_asserted",
    "source_observed",
    "derived",
    "hypothesized",
    "creative",
    "unknown",
    "contradicted",
}
CLAIM_KINDS = {
    "fact",
    "desire",
    "objective",
    "constraint",
    "observation",
    "mechanism",
}
RELATION_CHANGES = {
    "recognition",
    "memory",
    "trust",
    "expectation",
    "preference",
    "action",
}
ROLE_KINDS = {"life_role", "business_role", "story_role", "content_role"}
SEMANTIC_DISTANCES = {"near", "mid", "far"}
COMMUNICATION_MODES = {"story", "proof", "teaching", "experience", "ritual", "hybrid"}
ANCHOR_NAMES = {"attention", "trust", "meaning", "transaction"}
COMMERCIAL_OBJECT_MODES = {"absent", "causal"}


def canonical_sha256(value: Any) -> str:
    """Return a stable digest for a JSON-compatible contract."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _is_list(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: Any, *, minimum: int = 0) -> bool:
    return _is_list(value) and len(value) >= minimum and all(_nonempty_text(item) for item in value)


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def validate_contract(contract: Any) -> list[dict[str, str]]:
    """Validate structural invariants that prompts alone must not own."""

    issues: list[dict[str, str]] = []
    if not _is_mapping(contract):
        return [_issue("contract.type", "$", "contract must be an object")]

    if contract.get("schema_version") != SCHEMA_VERSION:
        issues.append(
            _issue(
                "contract.schema_version",
                "schema_version",
                f"schema_version must equal {SCHEMA_VERSION}",
            )
        )
    if contract.get("runtime_status") != RUNTIME_STATUS:
        issues.append(
            _issue(
                "contract.runtime_status",
                "runtime_status",
                "prototype must remain research_quarantined",
            )
        )
    if not _nonempty_text(contract.get("contract_id")):
        issues.append(_issue("contract.id", "contract_id", "contract_id is required"))

    system = contract.get("system")
    if not _is_mapping(system):
        issues.append(_issue("system.type", "system", "system must be an object"))
        system = {}
    if not _nonempty_text(system.get("target_public")):
        issues.append(_issue("system.target_public", "system.target_public", "target_public is required"))
    relation_changes = system.get("desired_relation_changes")
    if not _string_list(relation_changes, minimum=1) or not set(relation_changes).issubset(RELATION_CHANGES):
        issues.append(
            _issue(
                "system.relation_changes",
                "system.desired_relation_changes",
                "relation changes must use the shared IP relationship vocabulary",
            )
        )
    for field in ("desired_action", "boundary", "time_horizon"):
        if not _nonempty_text(system.get(field)):
            issues.append(
                _issue(
                    f"system.{field}",
                    f"system.{field}",
                    f"{field} is required",
                )
            )

    ontology = contract.get("ontology")
    if not _is_mapping(ontology):
        issues.append(_issue("ontology.type", "ontology", "ontology must be an object"))
        ontology = {}
    entities = ontology.get("entities")
    entity_by_id: dict[str, Mapping[str, Any]] = {}
    if not _is_list(entities) or not entities:
        issues.append(_issue("ontology.entities", "ontology.entities", "at least one entity is required"))
    else:
        for index, entity in enumerate(entities):
            path = f"ontology.entities[{index}]"
            if not _is_mapping(entity):
                issues.append(_issue("ontology.entity_type", path, "entity must be an object"))
                continue
            entity_id = entity.get("id")
            kind = entity.get("kind")
            if not _nonempty_text(entity_id):
                issues.append(_issue("ontology.entity_id", f"{path}.id", "entity id is required"))
            elif entity_id in entity_by_id:
                issues.append(_issue("ontology.entity_id", f"{path}.id", "entity ids must be unique"))
            else:
                entity_by_id[entity_id] = entity
            if kind not in ENTITY_KINDS:
                issues.append(
                    _issue(
                        "ontology.entity_kind",
                        f"{path}.kind",
                        "a role or generic brand claim cannot masquerade as an entity kind",
                    )
                )
            if entity.get("epistemic_state") not in EPISTEMIC_STATES:
                issues.append(
                    _issue(
                        "ontology.entity_state",
                        f"{path}.epistemic_state",
                        "entity epistemic state is invalid",
                    )
                )

    operated_ref = ontology.get("operated_subject_ref")
    operated_kind = ontology.get("operated_subject_kind")
    operated_entity = entity_by_id.get(operated_ref)
    if operated_entity is None:
        issues.append(
            _issue(
                "ontology.operated_subject_ref",
                "ontology.operated_subject_ref",
                "operated subject must reference a declared entity",
            )
        )
    if operated_kind not in OPERATED_SUBJECT_KINDS or (operated_entity is not None and operated_entity.get("kind") != operated_kind):
        issues.append(
            _issue(
                "ontology.operated_subject_kind",
                "ontology.operated_subject_kind",
                "operated subject kind must be a matching person, product, or organization",
            )
        )
    primary_carrier_ref = ontology.get("primary_carrier_ref")
    if primary_carrier_ref not in entity_by_id:
        issues.append(
            _issue(
                "ontology.primary_carrier_ref",
                "ontology.primary_carrier_ref",
                "primary carrier must reference a declared entity",
            )
        )

    roles = ontology.get("role_assignments")
    if not _is_list(roles):
        issues.append(
            _issue(
                "ontology.roles",
                "ontology.role_assignments",
                "role assignments must be a list",
            )
        )
    else:
        for index, role in enumerate(roles):
            path = f"ontology.role_assignments[{index}]"
            if not _is_mapping(role):
                issues.append(_issue("ontology.role", path, "role assignment must be an object"))
                continue
            ref = role.get("entity_ref")
            role_kind = role.get("role_kind")
            if ref not in entity_by_id:
                issues.append(_issue("ontology.role_ref", f"{path}.entity_ref", "role entity is unknown"))
            if role_kind not in ROLE_KINDS:
                issues.append(_issue("ontology.role_kind", f"{path}.role_kind", "role kind is invalid"))
            if role_kind == "life_role" and entity_by_id.get(ref, {}).get("kind") != "person":
                issues.append(
                    _issue(
                        "ontology.life_role_subject",
                        f"{path}.entity_ref",
                        "life roles belong to people; they are not standalone subjects",
                    )
                )
            if not _nonempty_text(role.get("role")) or not _nonempty_text(role.get("valid_time")):
                issues.append(
                    _issue(
                        "ontology.role_fields",
                        path,
                        "role and valid_time are required",
                    )
                )

    brand_cognition = ontology.get("brand_cognition")
    if not _is_mapping(brand_cognition):
        issues.append(
            _issue(
                "ontology.brand_cognition",
                "ontology.brand_cognition",
                "operator identity and audience cognition must be separated",
            )
        )
    else:
        target_refs = brand_cognition.get("attribution_target_refs")
        if not _string_list(target_refs, minimum=1) or any(ref not in entity_by_id for ref in target_refs):
            issues.append(
                _issue(
                    "ontology.brand_attribution_refs",
                    "ontology.brand_cognition.attribution_target_refs",
                    "brand cognition targets must reference declared entities",
                )
            )
        if not _string_list(brand_cognition.get("desired_associations"), minimum=1):
            issues.append(
                _issue(
                    "ontology.brand_associations",
                    "ontology.brand_cognition.desired_associations",
                    "at least one desired public association is required",
                )
            )

    information = contract.get("information")
    if not _is_mapping(information):
        issues.append(_issue("information.type", "information", "information must be an object"))
        information = {}
    claims = information.get("claims")
    claim_by_id: dict[str, Mapping[str, Any]] = {}
    if not _is_list(claims):
        issues.append(_issue("information.claims", "information.claims", "claims must be a list"))
    else:
        for index, claim in enumerate(claims):
            path = f"information.claims[{index}]"
            if not _is_mapping(claim):
                issues.append(_issue("information.claim", path, "claim must be an object"))
                continue
            claim_id = claim.get("id")
            state = claim.get("state")
            kind = claim.get("kind")
            if not _nonempty_text(claim_id) or claim_id in claim_by_id:
                issues.append(_issue("information.claim_id", f"{path}.id", "claim id is missing or duplicated"))
            else:
                claim_by_id[claim_id] = claim
            if state not in EPISTEMIC_STATES:
                issues.append(_issue("information.claim_state", f"{path}.state", "claim state is invalid"))
            if kind not in CLAIM_KINDS:
                issues.append(_issue("information.claim_kind", f"{path}.kind", "claim kind is invalid"))
            subject_refs = claim.get("subject_refs")
            if not _string_list(subject_refs, minimum=1) or any(ref not in entity_by_id for ref in subject_refs):
                issues.append(
                    _issue(
                        "information.claim_subject",
                        f"{path}.subject_refs",
                        "claim subjects must reference declared entities",
                    )
                )
            if state in {"user_asserted", "source_observed", "derived"} and not _string_list(claim.get("source_refs"), minimum=1):
                issues.append(
                    _issue(
                        "information.provenance",
                        f"{path}.source_refs",
                        "asserted, observed, and derived claims require provenance",
                    )
                )
            basis_refs = claim.get("basis_refs")
            if not _is_list(basis_refs):
                issues.append(
                    _issue(
                        "information.basis_refs",
                        f"{path}.basis_refs",
                        "basis_refs must be an explicit list",
                    )
                )
            if not _nonempty_text(claim.get("statement")) or not _nonempty_text(claim.get("coverage")):
                issues.append(
                    _issue(
                        "information.claim_fields",
                        path,
                        "statement and coverage are required",
                    )
                )

    for claim_id, claim in claim_by_id.items():
        basis_refs = claim.get("basis_refs")
        if _is_list(basis_refs) and any(ref not in claim_by_id for ref in basis_refs):
            issues.append(
                _issue(
                    "information.basis_ref",
                    f"information.claims[{claim_id}].basis_refs",
                    "claim basis references must resolve",
                )
            )
        if claim.get("state") == "derived" and not _string_list(basis_refs, minimum=1):
            issues.append(
                _issue(
                    "information.derived_basis",
                    f"information.claims[{claim_id}].basis_refs",
                    "derived claims require at least one basis claim",
                )
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit_claim(claim_id: str) -> None:
        if claim_id in visiting:
            issues.append(
                _issue(
                    "information.basis_cycle",
                    f"information.claims[{claim_id}]",
                    "claim basis graph must be acyclic",
                )
            )
            return
        if claim_id in visited:
            return
        visiting.add(claim_id)
        claim = claim_by_id.get(claim_id, {})
        for basis_ref in claim.get("basis_refs") or []:
            if basis_ref in claim_by_id:
                _visit_claim(basis_ref)
        visiting.remove(claim_id)
        visited.add(claim_id)

    for claim_id in claim_by_id:
        _visit_claim(claim_id)

    semantic = contract.get("semantic")
    if not _is_mapping(semantic):
        issues.append(_issue("semantic.type", "semantic", "semantic must be an object"))
        semantic = {}
    frame = semantic.get("frame")
    if not _is_mapping(frame) or not _nonempty_text(frame.get("head_concept")):
        issues.append(
            _issue(
                "semantic.frame",
                "semantic.frame",
                "semantic frame and head concept are required",
            )
        )
    else:
        if not _string_list(frame.get("surface_terms"), minimum=1):
            issues.append(
                _issue(
                    "semantic.surface_terms",
                    "semantic.frame.surface_terms",
                    "surface terms are required",
                )
            )
        if not _string_list(frame.get("event_roles"), minimum=2):
            issues.append(
                _issue(
                    "semantic.event_roles",
                    "semantic.frame.event_roles",
                    "event semantics require at least two participant roles",
                )
            )
    de_labelling = semantic.get("de_labelling")
    if not _is_mapping(de_labelling) or de_labelling.get("result") != "pass" or not _nonempty_text(de_labelling.get("subject_without_labels")) or not _nonempty_text(de_labelling.get("role_reintroduced_effect")):
        issues.append(
            _issue(
                "semantic.de_labelling",
                "semantic.de_labelling",
                "label removal and role reintroduction must both be explicit",
            )
        )

    direction = contract.get("direction")
    if not _is_mapping(direction):
        issues.append(_issue("direction.type", "direction", "direction must be an object"))
        direction = {}
    candidates = direction.get("candidate_worlds")
    candidate_by_id: dict[str, Mapping[str, Any]] = {}
    domains: list[str] = []
    distances: list[str] = []
    if not _is_list(candidates) or len(candidates) < 3:
        issues.append(
            _issue(
                "direction.candidate_count",
                "direction.candidate_worlds",
                "at least three candidate worlds are required",
            )
        )
    else:
        for index, candidate in enumerate(candidates):
            path = f"direction.candidate_worlds[{index}]"
            if not _is_mapping(candidate):
                issues.append(_issue("direction.candidate", path, "candidate must be an object"))
                continue
            candidate_id = candidate.get("id")
            domain = candidate.get("social_domain")
            distance = candidate.get("semantic_distance")
            if not _nonempty_text(candidate_id) or candidate_id in candidate_by_id:
                issues.append(
                    _issue(
                        "direction.candidate_id",
                        f"{path}.id",
                        "candidate id is missing or duplicated",
                    )
                )
            else:
                candidate_by_id[candidate_id] = candidate
            if _nonempty_text(domain):
                domains.append(domain.strip())
            if distance in SEMANTIC_DISTANCES:
                distances.append(distance)
            else:
                issues.append(
                    _issue(
                        "direction.semantic_distance",
                        f"{path}.semantic_distance",
                        "semantic distance is invalid",
                    )
                )
            relation_structure = candidate.get("relation_structure")
            if not _string_list(relation_structure, minimum=3):
                issues.append(
                    _issue(
                        "direction.relation_structure",
                        f"{path}.relation_structure",
                        "candidate needs a relation structure, not a decorative analogy",
                    )
                )
            desire_ref = candidate.get("desire_subject_ref")
            if entity_by_id.get(desire_ref, {}).get("kind") not in HUMAN_DESIRE_KINDS:
                issues.append(
                    _issue(
                        "direction.desire_subject",
                        f"{path}.desire_subject_ref",
                        "desire may belong only to people, audiences, or disclosed fictional characters",
                    )
                )
            fact_refs = candidate.get("fact_refs")
            if not _is_list(fact_refs) or any(ref not in claim_by_id for ref in fact_refs):
                issues.append(
                    _issue(
                        "direction.fact_refs",
                        f"{path}.fact_refs",
                        "candidate fact references must resolve to claims",
                    )
                )
            if not _string_list(candidate.get("assumptions")):
                issues.append(
                    _issue(
                        "direction.assumptions",
                        f"{path}.assumptions",
                        "candidate assumptions must be an explicit list",
                    )
                )
            if not _nonempty_text(candidate.get("premise")):
                issues.append(_issue("direction.premise", f"{path}.premise", "candidate premise is required"))
        if len(domains) != len(candidates) or len(set(domains)) != len(domains):
            issues.append(
                _issue(
                    "direction.candidate_domains",
                    "direction.candidate_worlds",
                    "candidate worlds must occupy distinct social domains",
                )
            )
        if distances.count("far") < 2:
            issues.append(
                _issue(
                    "direction.far_candidate",
                    "direction.candidate_worlds",
                    "at least two structurally matched far-domain candidates are required",
                )
            )

    desire_model = direction.get("desire_model")
    if not _is_mapping(desire_model):
        issues.append(
            _issue(
                "direction.desire_model",
                "direction.desire_model",
                "creator desire, audience desire, and commercial objective must be separated",
            )
        )
    else:
        creator_refs = desire_model.get("creator_desire_claim_refs")
        audience_refs = desire_model.get("audience_desire_claim_refs")
        commercial_refs = desire_model.get("commercial_objective_claim_refs")
        groups = (creator_refs, audience_refs, commercial_refs)
        if any(not _is_list(group) for group in groups):
            issues.append(
                _issue(
                    "direction.desire_refs",
                    "direction.desire_model",
                    "all desire/objective reference groups must be explicit lists",
                )
            )
        else:
            flat_refs = [ref for group in groups for ref in group]
            if any(ref not in claim_by_id for ref in flat_refs):
                issues.append(
                    _issue(
                        "direction.desire_ref",
                        "direction.desire_model",
                        "desire/objective references must resolve to claims",
                    )
                )
            if set(creator_refs) & set(audience_refs) or set(creator_refs) & set(commercial_refs) or set(audience_refs) & set(commercial_refs):
                issues.append(
                    _issue(
                        "direction.desire_conflation",
                        "direction.desire_model",
                        "creator desire, audience desire, and commercial objective cannot reuse one claim",
                    )
                )

    selected_ref = direction.get("selected_candidate_ref")
    if selected_ref not in candidate_by_id:
        issues.append(
            _issue(
                "direction.selection",
                "direction.selected_candidate_ref",
                "selected candidate must reference a candidate world",
            )
        )
    if not _nonempty_text(direction.get("selection_reason")) or not _nonempty_text(direction.get("tradeoff")):
        issues.append(
            _issue(
                "direction.selection_basis",
                "direction",
                "selection reason and trade-off are required",
            )
        )

    anchors = direction.get("four_anchors")
    if not _is_mapping(anchors) or set(anchors) != ANCHOR_NAMES:
        issues.append(
            _issue(
                "direction.four_anchors",
                "direction.four_anchors",
                "attention, trust, meaning, and transaction anchors are all required",
            )
        )
    else:
        for name in sorted(ANCHOR_NAMES):
            anchor = anchors.get(name)
            path = f"direction.four_anchors.{name}"
            if not _is_mapping(anchor) or anchor.get("entity_ref") not in entity_by_id:
                issues.append(
                    _issue(
                        "direction.anchor_ref",
                        f"{path}.entity_ref",
                        "anchor must reference a declared entity",
                    )
                )
            if not _is_mapping(anchor) or not _nonempty_text(anchor.get("mechanism")):
                issues.append(
                    _issue(
                        "direction.anchor_mechanism",
                        f"{path}.mechanism",
                        "anchor mechanism is required",
                    )
                )

    communication = direction.get("communication")
    if not _is_mapping(communication) or communication.get("mode") not in COMMUNICATION_MODES:
        issues.append(
            _issue(
                "direction.communication_mode",
                "direction.communication.mode",
                "communication mode is invalid",
            )
        )
    elif communication.get("mode") in {"story", "hybrid"}:
        desire = communication.get("desire_behavior")
        if not _is_mapping(desire) or entity_by_id.get(desire.get("subject_ref"), {}).get("kind") not in HUMAN_DESIRE_KINDS:
            issues.append(
                _issue(
                    "direction.story_desire_subject",
                    "direction.communication.desire_behavior.subject_ref",
                    "story desire must belong to a human or disclosed fictional character",
                )
            )
        else:
            story_fields = (
                "semantic_action",
                "relationship_at_stake",
                "trigger",
                "want",
                "goal",
                "initial_tactic",
                "counterforce",
                "feedback",
                "strategy_change",
                "costly_choice",
                "cost",
                "state_change",
                "viewer_desire",
                "logline",
            )
            if not all(_nonempty_text(desire.get(field)) for field in story_fields):
                issues.append(
                    _issue(
                        "direction.story_causality",
                        "direction.communication.desire_behavior",
                        "story mode requires the full semantic-action-to-state-change causal bridge and a logline",
                    )
                )
            if desire.get("epistemic_state") not in {"source_observed", "creative"}:
                issues.append(
                    _issue(
                        "direction.story_epistemic_state",
                        "direction.communication.desire_behavior.epistemic_state",
                        "story events must be source_observed or explicitly creative",
                    )
                )
            if desire.get("commercial_object_mode") not in COMMERCIAL_OBJECT_MODES:
                issues.append(
                    _issue(
                        "direction.story_object_mode",
                        "direction.communication.desire_behavior.commercial_object_mode",
                        "commercial objects must be causally necessary or absent from the story world",
                    )
                )
            if not _nonempty_text(desire.get("substitution_test")):
                issues.append(
                    _issue(
                        "direction.story_substitution_test",
                        "direction.communication.desire_behavior.substitution_test",
                        "story mode must explain what changes when the commercial object is removed or replaced",
                    )
                )
            if desire.get("source_candidate_ref") != selected_ref:
                issues.append(
                    _issue(
                        "direction.story_source",
                        "direction.communication.desire_behavior.source_candidate_ref",
                        "the causal bridge must translate the selected association candidate",
                    )
                )
            story_fact_refs = desire.get("fact_refs")
            if not _string_list(story_fact_refs, minimum=1) or any(ref not in claim_by_id for ref in story_fact_refs):
                issues.append(
                    _issue(
                        "direction.story_fact_refs",
                        "direction.communication.desire_behavior.fact_refs",
                        "story fact references must resolve to declared claims",
                    )
                )
            assumptions = desire.get("assumptions")
            if not _is_list(assumptions) or (desire.get("epistemic_state") == "creative" and not _string_list(assumptions, minimum=1)):
                issues.append(
                    _issue(
                        "direction.story_assumptions",
                        "direction.communication.desire_behavior.assumptions",
                        "creative story events require explicit assumptions",
                    )
                )

    marketing = direction.get("marketing")
    if not _is_mapping(marketing) or not all(
        _nonempty_text(marketing.get(field))
        for field in (
            "viewer_desire",
            "reason_to_choose",
            "reason_to_believe",
            "desired_behavior",
            "business_connection",
        )
    ):
        issues.append(
            _issue(
                "direction.marketing",
                "direction.marketing",
                "marketing convergence must connect viewer desire, belief, choice, behavior, and business",
            )
        )

    production = direction.get("production")
    if not _is_mapping(production) or not _string_list(production.get("expression_carriers"), minimum=1):
        issues.append(
            _issue(
                "direction.production",
                "direction.production",
                "at least one feasible expression carrier is required",
            )
        )
    elif not _is_list(production.get("constraints")) or not _nonempty_text(production.get("feasibility_reason")):
        issues.append(
            _issue(
                "direction.production_fit",
                "direction.production",
                "production constraints and feasibility reason are required",
            )
        )

    stress = direction.get("stress_test")
    if not _is_mapping(stress):
        issues.append(_issue("direction.stress_test", "direction.stress_test", "stress test is required"))
    else:
        generators = stress.get("episode_generators")
        if not _string_list(generators, minimum=12) or len(set(generators)) != len(generators):
            issues.append(
                _issue(
                    "direction.episode_supply",
                    "direction.stress_test.episode_generators",
                    "twelve distinct event generators are required",
                )
            )
        for field in (
            "label_removal_result",
            "role_reintroduction_result",
            "no_hotspot_result",
            "resource_reduction_result",
        ):
            if stress.get(field) != "pass":
                issues.append(
                    _issue(
                        "direction.stress_result",
                        f"direction.stress_test.{field}",
                        f"{field} must pass",
                    )
                )

    control = contract.get("control")
    if not _is_mapping(control) or not all(
        _nonempty_text(control.get(field))
        for field in (
            "pilot_hypothesis",
            "single_variable",
            "observation_window",
            "success_signal",
            "failure_signal",
            "revision_rule",
        )
    ):
        issues.append(
            _issue(
                "control.pilot",
                "control",
                "a falsifiable single-variable pilot and revision rule are required",
            )
        )

    return issues


def assert_valid_contract(contract: Any) -> None:
    """Raise a compact error when a research contract violates invariants."""

    issues = validate_contract(contract)
    if issues:
        summary = "; ".join(f"{item['code']}@{item['path']}" for item in issues)
        raise ValueError(summary)
