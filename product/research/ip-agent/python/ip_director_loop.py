"""Mechanical contracts for the quarantined two-stage IP director loop.

The validator owns structure and evidence boundaries only. It does not score
originality, predict performance, call a model, or import product runtime code.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

BRIEF_SCHEMA_VERSION = "ip-director-loop-brief-v1"
ROUTE_SCHEMA_VERSION = "ip-director-route-result-v1"
STORY_SCHEMA_VERSION = "ip-director-story-result-v1"
ROUTE_SCHEMA_VERSION_V2 = "ip-director-route-result-v2"
STORY_SCHEMA_VERSION_V2 = "ip-director-story-result-v2"
RUNTIME_STATUS = "research_quarantined"

SEMANTIC_DISTANCES = {"near", "mid", "far"}
INDUSTRY_ROLES = {
    "near": {"subject"},
    "mid": {"metaphor"},
    "far": {"stage", "absent"},
}
COMMERCIAL_OBJECT_MODES = {"absent", "causal"}
BUSINESS_WORLD_TERMS = {"账号", "平台", "流量", "粉丝", "咨询", "订单", "成交"}
STORY_TEXT_FIELDS = {
    "trigger",
    "want",
    "goal",
    "initial_tactic",
    "counterforce",
    "feedback",
    "strategy_change",
    "costly_choice",
    "cost",
    "relationship_before",
    "relationship_after",
    "state_change",
    "viewer_question",
}
REQUIRED_CAUSAL_EDGES = {
    ("trigger", "initial_tactic"),
    ("initial_tactic", "feedback"),
    ("feedback", "strategy_change"),
    ("strategy_change", "costly_choice"),
    ("costly_choice", "state_change"),
}
STORY_TEXT_FIELDS_V2 = {
    "trigger",
    "want",
    "goal",
    "initial_tactic",
    "counterforce",
    "feedback",
    "strategy_change",
    "relationship_before",
    "relationship_after",
    "state_change",
    "viewer_question",
}
STORY_CAUSAL_NODES_V2 = STORY_TEXT_FIELDS_V2 | {
    "costly_choice",
    "cost",
    "goal_outcome",
}
REQUIRED_CAUSAL_EDGES_V2 = {
    ("trigger", "initial_tactic"),
    ("initial_tactic", "feedback"),
    ("feedback", "strategy_change"),
    ("strategy_change", "costly_choice"),
    ("costly_choice", "cost"),
    ("cost", "goal_outcome"),
    ("goal_outcome", "state_change"),
}


def canonical_sha256(value: Any) -> str:
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


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_list(value: Any, *, minimum: int = 0) -> bool:
    return _is_list(value) and len(value) >= minimum and all(_text(item) for item in value)


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def validate_brief(brief: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not _is_mapping(brief):
        return [_issue("brief.type", "$", "brief must be an object")]
    if brief.get("schema_version") != BRIEF_SCHEMA_VERSION:
        issues.append(_issue("brief.schema", "schema_version", "brief schema version is invalid"))
    if brief.get("runtime_status") != RUNTIME_STATUS:
        issues.append(_issue("brief.status", "runtime_status", "brief must remain research_quarantined"))
    if brief.get("research_fixture") is not True:
        issues.append(_issue("brief.fixture", "research_fixture", "research fixture flag must be true"))
    if not _text(brief.get("case_id")):
        issues.append(_issue("brief.case_id", "case_id", "case_id is required"))

    subject = brief.get("subject")
    if not _is_mapping(subject):
        issues.append(_issue("brief.subject", "subject", "subject must be an object"))
    else:
        if subject.get("kind") not in {"person", "product", "brand", "organization"}:
            issues.append(_issue("brief.subject_kind", "subject.kind", "subject kind is invalid"))
        if not _text(subject.get("description")):
            issues.append(_issue("brief.subject_description", "subject.description", "subject description is required"))

    facts = brief.get("facts")
    fact_ids: set[str] = set()
    if not _is_list(facts) or not facts:
        issues.append(_issue("brief.facts", "facts", "at least one fact is required"))
    else:
        for index, fact in enumerate(facts):
            path = f"facts[{index}]"
            if not _is_mapping(fact):
                issues.append(_issue("brief.fact", path, "fact must be an object"))
                continue
            fact_id = fact.get("id")
            if not _text(fact_id) or fact_id in fact_ids:
                issues.append(_issue("brief.fact_id", f"{path}.id", "fact id is missing or duplicated"))
            else:
                fact_ids.add(fact_id)
            if not _text(fact.get("statement")):
                issues.append(_issue("brief.fact_statement", f"{path}.statement", "fact statement is required"))

    for field in ("objective", "audience_hypotheses", "production_constraints"):
        if not _text_list(brief.get(field), minimum=1):
            issues.append(_issue(f"brief.{field}", field, f"{field} must be a non-empty text list"))
    for field in ("surface_terms", "commercial_object_terms"):
        if not _is_list(brief.get(field)) or not all(_text(item) for item in brief.get(field, [])):
            issues.append(_issue(f"brief.{field}", field, f"{field} must be a text list"))

    policy = brief.get("selection_policy")
    if not _is_mapping(policy):
        issues.append(_issue("brief.selection_policy", "selection_policy", "selection policy is required"))
    else:
        allowed = policy.get("allowed_distances")
        if not _text_list(allowed, minimum=1) or not set(allowed).issubset(SEMANTIC_DISTANCES):
            issues.append(
                _issue(
                    "brief.allowed_distances",
                    "selection_policy.allowed_distances",
                    "allowed distances must use near, mid, or far",
                )
            )
        if policy.get("required_mode") != "story":
            issues.append(
                _issue(
                    "brief.required_mode",
                    "selection_policy.required_mode",
                    "this first experiment validates story mode only",
                )
            )
    return issues


def _fact_ids(brief: Mapping[str, Any]) -> set[str]:
    return {fact["id"] for fact in brief["facts"]}


def validate_route_result(result: Any, brief: Any) -> list[dict[str, str]]:
    # Route malformed v2-shaped output through the v2 validator so a schema
    # typo is reported as evidence instead of falling into the legacy parser.
    # The output itself is never normalized or accepted under an alias.
    if _is_mapping(result) and (
        result.get("schema_version") == ROUTE_SCHEMA_VERSION_V2
        or result.get("epistemic_state") == "creative_hypothesis"
    ):
        return validate_route_result_v2(result, brief)
    issues = validate_brief(brief)
    if issues:
        return issues
    if not _is_mapping(result):
        return [_issue("route.type", "$", "route result must be an object")]
    if result.get("schema_version") != ROUTE_SCHEMA_VERSION:
        issues.append(_issue("route.schema", "schema_version", "route schema version is invalid"))
    if result.get("epistemic_state") != "creative":
        issues.append(_issue("route.state", "epistemic_state", "route result must be labelled creative"))

    fact_ids = _fact_ids(brief)
    facts_used = result.get("facts_used")
    if not _is_list(facts_used) or any(ref not in fact_ids for ref in facts_used):
        issues.append(_issue("route.fact_refs", "facts_used", "facts_used must resolve to brief facts"))
    if not _is_list(result.get("creative_assumptions")) or not all(
        _text(item) for item in result.get("creative_assumptions", [])
    ):
        issues.append(
            _issue(
                "route.assumptions",
                "creative_assumptions",
                "creative assumptions must be an explicit text list",
            )
        )

    semantic = result.get("semantic_kernel")
    if not _is_mapping(semantic):
        issues.append(_issue("route.semantic", "semantic_kernel", "semantic kernel is required"))
    else:
        for field in (
            "head_concept",
            "literal_action",
            "human_action",
            "relationship_at_stake",
            "social_rule",
            "desire_conflict",
        ):
            if not _text(semantic.get(field)):
                issues.append(_issue(f"route.semantic_{field}", f"semantic_kernel.{field}", f"{field} is required"))
        for field in ("surface_terms", "modifiers"):
            if not _is_list(semantic.get(field)) or not all(_text(item) for item in semantic.get(field, [])):
                issues.append(_issue(f"route.semantic_{field}", f"semantic_kernel.{field}", f"{field} must be a text list"))

    directions = result.get("directions")
    direction_by_id: dict[str, Mapping[str, Any]] = {}
    distances: set[str] = set()
    signatures: set[tuple[str, str, str]] = set()
    if not _is_list(directions) or len(directions) != 3:
        issues.append(_issue("route.direction_count", "directions", "exactly three directions are required"))
    else:
        for index, direction in enumerate(directions):
            path = f"directions[{index}]"
            if not _is_mapping(direction):
                issues.append(_issue("route.direction", path, "direction must be an object"))
                continue
            direction_id = direction.get("id")
            distance = direction.get("semantic_distance")
            industry_role = direction.get("industry_role")
            if not _text(direction_id) or direction_id in direction_by_id:
                issues.append(_issue("route.direction_id", f"{path}.id", "direction id is missing or duplicated"))
            else:
                direction_by_id[direction_id] = direction
            if distance not in SEMANTIC_DISTANCES:
                issues.append(_issue("route.distance", f"{path}.semantic_distance", "semantic distance is invalid"))
            else:
                distances.add(distance)
                if industry_role not in INDUSTRY_ROLES[distance]:
                    issues.append(
                        _issue(
                            "route.industry_role",
                            f"{path}.industry_role",
                            f"industry role {industry_role!r} is invalid for {distance}",
                        )
                    )
            for field in (
                "content_subject",
                "audience_tension",
                "expression_mode",
                "subject_ownership",
                "business_attribution",
            ):
                if not _text(direction.get(field)):
                    issues.append(_issue(f"route.direction_{field}", f"{path}.{field}", f"{field} is required"))
            minimum_path = 3 if distance == "near" else 4
            if not _text_list(direction.get("association_path"), minimum=minimum_path):
                issues.append(
                    _issue(
                        "route.association_path",
                        f"{path}.association_path",
                        f"association path needs at least {minimum_path} explicit steps",
                    )
                )
            mappings = direction.get("structure_mapping")
            minimum_mappings = 1 if distance == "near" else 2
            if not _is_list(mappings) or len(mappings) < minimum_mappings:
                issues.append(
                    _issue(
                        "route.structure_mapping",
                        f"{path}.structure_mapping",
                        f"structure mapping needs at least {minimum_mappings} explicit edge mappings",
                    )
                )
            else:
                edge_pairs: set[tuple[str, str]] = set()
                for mapping_index, edge in enumerate(mappings):
                    edge_path = f"{path}.structure_mapping[{mapping_index}]"
                    if not _is_mapping(edge) or not _text(edge.get("source_edge")) or not _text(
                        edge.get("target_edge")
                    ):
                        issues.append(
                            _issue(
                                "route.structure_edge",
                                edge_path,
                                "each mapping needs non-empty source_edge and target_edge",
                            )
                        )
                        continue
                    pair = (edge["source_edge"].strip(), edge["target_edge"].strip())
                    if pair in edge_pairs:
                        issues.append(
                            _issue(
                                "route.structure_edge_duplicate",
                                edge_path,
                                "structure mappings must contain distinct edges",
                            )
                        )
                    edge_pairs.add(pair)
            evidence_refs = direction.get("evidence_refs")
            if not _is_list(evidence_refs) or any(ref not in fact_ids for ref in evidence_refs):
                issues.append(
                    _issue(
                        "route.direction_fact_refs",
                        f"{path}.evidence_refs",
                        "direction evidence references must resolve to brief facts",
                    )
                )
            if not _is_list(direction.get("creative_assumptions")) or not all(
                _text(item) for item in direction.get("creative_assumptions", [])
            ):
                issues.append(
                    _issue(
                        "route.direction_assumptions",
                        f"{path}.creative_assumptions",
                        "direction assumptions must be an explicit text list",
                    )
                )
            if all(_text(direction.get(field)) for field in ("content_subject", "audience_tension")) and _text(
                industry_role
            ):
                signature = (
                    direction["content_subject"].strip(),
                    direction["audience_tension"].strip(),
                    industry_role,
                )
                if signature in signatures:
                    issues.append(_issue("route.direction_duplicate", path, "directions must be structurally distinct"))
                signatures.add(signature)
    if distances != SEMANTIC_DISTANCES:
        issues.append(_issue("route.distance_coverage", "directions", "directions must cover near, mid, and far exactly once"))

    recommendation = result.get("recommendation")
    if not _is_mapping(recommendation):
        issues.append(_issue("route.recommendation", "recommendation", "recommendation is required"))
    else:
        selected_ref = recommendation.get("selected_direction_ref")
        selected = direction_by_id.get(selected_ref)
        if selected is None:
            issues.append(
                _issue(
                    "route.selected_ref",
                    "recommendation.selected_direction_ref",
                    "selected direction must reference a declared direction",
                )
            )
        elif selected.get("semantic_distance") not in set(brief["selection_policy"]["allowed_distances"]):
            issues.append(
                _issue(
                    "route.selected_distance",
                    "recommendation.selected_direction_ref",
                    "selected direction violates the frozen experiment policy",
                )
            )
        for field in ("reason", "tradeoff", "why_not_near"):
            if not _text(recommendation.get(field)):
                issues.append(_issue(f"route.recommendation_{field}", f"recommendation.{field}", f"{field} is required"))
    return issues


def selected_direction(route_result: Mapping[str, Any]) -> Mapping[str, Any] | None:
    recommendation = route_result.get("recommendation") or {}
    selected_ref = recommendation.get("selected_direction_ref")
    return next((item for item in route_result.get("directions", []) if item.get("id") == selected_ref), None)


def validate_story_result(result: Any, brief: Any, route_result: Any) -> list[dict[str, str]]:
    if _is_mapping(result) and (
        result.get("schema_version") == STORY_SCHEMA_VERSION_V2
        or result.get("epistemic_state") == "creative_hypothesis"
    ):
        return validate_story_result_v2(result, brief, route_result)
    issues = validate_route_result(route_result, brief)
    if issues:
        return issues
    if not _is_mapping(result):
        return [_issue("story.type", "$", "story result must be an object")]
    if result.get("schema_version") != STORY_SCHEMA_VERSION:
        issues.append(_issue("story.schema", "schema_version", "story schema version is invalid"))
    if result.get("epistemic_state") != "creative":
        issues.append(_issue("story.state", "epistemic_state", "story result must be labelled creative"))
    expected_route_sha = canonical_sha256(route_result)
    if result.get("source_route_sha256") != expected_route_sha:
        issues.append(_issue("story.route_sha", "source_route_sha256", "story must bind the frozen route result"))

    chosen = selected_direction(route_result)
    chosen_ref = (route_result.get("recommendation") or {}).get("selected_direction_ref")
    if result.get("selected_direction_ref") != chosen_ref:
        issues.append(_issue("story.selected_ref", "selected_direction_ref", "story must compile the frozen direction"))

    fact_ids = _fact_ids(brief)
    facts_used = result.get("facts_used")
    if not _is_list(facts_used) or any(ref not in fact_ids for ref in facts_used):
        issues.append(_issue("story.fact_refs", "facts_used", "facts_used must resolve to brief facts"))
    if not _is_list(result.get("creative_assumptions")) or not all(
        _text(item) for item in result.get("creative_assumptions", [])
    ):
        issues.append(_issue("story.assumptions", "creative_assumptions", "story assumptions must be explicit"))

    mode = result.get("commercial_object_mode")
    if mode not in COMMERCIAL_OBJECT_MODES:
        issues.append(_issue("story.commercial_mode", "commercial_object_mode", "mode must be absent or causal"))
    if not _text(result.get("substitution_test")):
        issues.append(_issue("story.substitution_test", "substitution_test", "substitution test is required"))

    story = result.get("story_world")
    if not _is_mapping(story):
        issues.append(_issue("story.world", "story_world", "story world is required"))
        story = {}
    else:
        if not _text_list(story.get("actors"), minimum=1):
            issues.append(_issue("story.actors", "story_world.actors", "at least one actor is required"))
        for field in STORY_TEXT_FIELDS:
            if not _text(story.get(field)):
                issues.append(_issue(f"story.{field}", f"story_world.{field}", f"{field} is required"))
        values = [story.get(field, "").strip() for field in STORY_TEXT_FIELDS if _text(story.get(field))]
        if len(set(values)) < 8:
            issues.append(_issue("story.repetition", "story_world", "story nodes must describe distinct states and actions"))
        edges = story.get("causal_edges")
        seen_edges: set[tuple[str, str]] = set()
        if not _is_list(edges):
            issues.append(_issue("story.causal_edges", "story_world.causal_edges", "causal edges must be a list"))
        else:
            for index, edge in enumerate(edges):
                path = f"story_world.causal_edges[{index}]"
                if not _is_mapping(edge) or edge.get("from") not in STORY_TEXT_FIELDS or edge.get("to") not in STORY_TEXT_FIELDS or not _text(edge.get("because")):
                    issues.append(
                        _issue(
                            "story.causal_edge",
                            path,
                            "causal edge must connect declared story nodes with a reason",
                        )
                    )
                    continue
                seen_edges.add((edge["from"], edge["to"]))
        if not REQUIRED_CAUSAL_EDGES.issubset(seen_edges):
            issues.append(
                _issue(
                    "story.causal_edge_coverage",
                    "story_world.causal_edges",
                    "causal chain does not connect trigger through state change",
                )
            )

    bridge = result.get("business_bridge")
    if not _is_mapping(bridge):
        issues.append(_issue("story.business_bridge", "business_bridge", "business bridge is required"))
    else:
        for field in ("meaning_attributed_to_subject", "connection_to_objective"):
            if not _text(bridge.get(field)):
                issues.append(_issue(f"story.bridge_{field}", f"business_bridge.{field}", f"{field} is required"))

    logline = result.get("logline")
    if not _text(logline) or "\n" in logline or len(logline.strip()) < 24:
        issues.append(_issue("story.logline", "logline", "logline must be one substantive line"))
    story_text = json.dumps(story, ensure_ascii=False) + (logline if isinstance(logline, str) else "")
    for term in BUSINESS_WORLD_TERMS:
        if term in story_text:
            issues.append(_issue("story.business_world_leak", "story_world", f"business term {term!r} leaked into story"))
    if mode == "absent":
        for term in brief.get("commercial_object_terms", []):
            if term and term in story_text:
                issues.append(_issue("story.absent_object_leak", "story_world", f"absent term {term!r} leaked into story"))
    if chosen is None:
        issues.append(_issue("story.route_missing", "selected_direction_ref", "frozen direction is missing"))
    return issues


def _brief_fact_statements(brief: Mapping[str, Any]) -> dict[str, str]:
    return {fact["id"]: fact["statement"] for fact in brief["facts"]}


def _validate_exact_fact_records(
    value: Any,
    brief: Mapping[str, Any],
    *,
    code_prefix: str,
    path: str,
) -> tuple[list[dict[str, str]], set[str]]:
    issues: list[dict[str, str]] = []
    fact_statements = _brief_fact_statements(brief)
    used_refs: set[str] = set()
    if not _is_list(value) or not value:
        return (
            [
                _issue(
                    f"{code_prefix}.facts",
                    path,
                    "facts_used must contain at least one exact fact record",
                )
            ],
            used_refs,
        )
    for index, record in enumerate(value):
        record_path = f"{path}[{index}]"
        if not _is_mapping(record):
            issues.append(
                _issue(
                    f"{code_prefix}.fact_record",
                    record_path,
                    "fact record must be an object",
                )
            )
            continue
        fact_id = record.get("id")
        statement = record.get("statement")
        if fact_id not in fact_statements or fact_id in used_refs:
            issues.append(
                _issue(
                    f"{code_prefix}.fact_ref",
                    f"{record_path}.id",
                    "fact id is missing, unknown, or duplicated",
                )
            )
            continue
        used_refs.add(fact_id)
        if statement != fact_statements[fact_id]:
            issues.append(
                _issue(
                    f"{code_prefix}.fact_statement",
                    f"{record_path}.statement",
                    "fact statement must be copied byte-for-byte from the brief",
                )
            )
    return issues, used_refs


def _validate_fact_ref_list(
    value: Any,
    allowed_refs: set[str],
    *,
    code: str,
    path: str,
    minimum: int = 1,
) -> list[dict[str, str]]:
    if not _is_list(value) or len(value) < minimum:
        return [
            _issue(
                code,
                path,
                "fact references must be unique and resolve to exact facts_used records",
            )
        ]
    if any(not isinstance(ref, str) or ref not in allowed_refs for ref in value):
        return [
            _issue(
                code,
                path,
                "fact references must be unique and resolve to exact facts_used records",
            )
        ]
    if len(value) != len(set(value)):
        return [
            _issue(
                code,
                path,
                "fact references must be unique and resolve to exact facts_used records",
            )
        ]
    return []


def validate_route_result_v2(result: Any, brief: Any) -> list[dict[str, str]]:
    issues = validate_brief(brief)
    if issues:
        return issues
    if not _is_mapping(result):
        return [_issue("route_v2.type", "$", "route result must be an object")]
    if result.get("schema_version") != ROUTE_SCHEMA_VERSION_V2:
        issues.append(_issue("route_v2.schema", "schema_version", "route v2 schema version is invalid"))
    if result.get("epistemic_state") != "creative_hypothesis":
        issues.append(
            _issue(
                "route_v2.state",
                "epistemic_state",
                "route v2 must be labelled creative_hypothesis",
            )
        )

    fact_issues, used_refs = _validate_exact_fact_records(
        result.get("facts_used"),
        brief,
        code_prefix="route_v2",
        path="facts_used",
    )
    issues.extend(fact_issues)

    semantic = result.get("semantic_kernel")
    if not _is_mapping(semantic):
        issues.append(_issue("route_v2.semantic", "semantic_kernel", "semantic kernel is required"))
    else:
        if semantic.get("surface_terms") != brief.get("surface_terms"):
            issues.append(
                _issue(
                    "route_v2.surface_terms",
                    "semantic_kernel.surface_terms",
                    "surface terms must be copied exactly from the brief",
                )
            )
        for field in (
            "head_concept_hypothesis",
            "human_action_hypothesis",
            "relationship_hypothesis",
            "social_rule_hypothesis",
            "desire_conflict_hypothesis",
        ):
            if not _text(semantic.get(field)):
                issues.append(
                    _issue(
                        f"route_v2.semantic_{field}",
                        f"semantic_kernel.{field}",
                        f"{field} is required",
                    )
                )
        literal_action = semantic.get("literal_action")
        if not _is_mapping(literal_action) or not _text(literal_action.get("statement")):
            issues.append(
                _issue(
                    "route_v2.literal_action",
                    "semantic_kernel.literal_action",
                    "literal action needs one statement and exact fact references",
                )
            )
        else:
            issues.extend(
                _validate_fact_ref_list(
                    literal_action.get("fact_refs"),
                    used_refs,
                    code="route_v2.literal_fact_refs",
                    path="semantic_kernel.literal_action.fact_refs",
                )
            )

    directions = result.get("directions")
    direction_by_id: dict[str, Mapping[str, Any]] = {}
    distances: set[str] = set()
    signatures: set[tuple[str, str, str]] = set()
    if not _is_list(directions) or len(directions) != 3:
        issues.append(_issue("route_v2.direction_count", "directions", "exactly three directions are required"))
    else:
        for index, direction in enumerate(directions):
            path = f"directions[{index}]"
            if not _is_mapping(direction):
                issues.append(_issue("route_v2.direction", path, "direction must be an object"))
                continue
            direction_id = direction.get("id")
            distance = direction.get("semantic_distance")
            industry_role = direction.get("industry_role")
            if not _text(direction_id) or direction_id in direction_by_id:
                issues.append(
                    _issue(
                        "route_v2.direction_id",
                        f"{path}.id",
                        "direction id is missing or duplicated",
                    )
                )
            else:
                direction_by_id[direction_id] = direction
            if distance not in SEMANTIC_DISTANCES:
                issues.append(
                    _issue(
                        "route_v2.distance",
                        f"{path}.semantic_distance",
                        "semantic distance is invalid",
                    )
                )
            else:
                distances.add(distance)
                if industry_role not in INDUSTRY_ROLES[distance]:
                    issues.append(
                        _issue(
                            "route_v2.industry_role",
                            f"{path}.industry_role",
                            f"industry role {industry_role!r} is invalid for {distance}",
                        )
                    )

            for field in (
                "content_subject_hypothesis",
                "audience_tension_hypothesis",
                "expression_mode_hypothesis",
                "business_attribution_hypothesis",
            ):
                if not _text(direction.get(field)):
                    issues.append(
                        _issue(
                            f"route_v2.direction_{field}",
                            f"{path}.{field}",
                            f"{field} is required",
                        )
                    )
            minimum_path = 3 if distance == "near" else 4
            if not _text_list(direction.get("association_path_hypothesis"), minimum=minimum_path):
                issues.append(
                    _issue(
                        "route_v2.association_path",
                        f"{path}.association_path_hypothesis",
                        f"association path needs at least {minimum_path} explicit steps",
                    )
                )
            mappings = direction.get("structure_mapping_hypothesis")
            minimum_mappings = 1 if distance == "near" else 2
            if not _is_list(mappings) or len(mappings) < minimum_mappings:
                issues.append(
                    _issue(
                        "route_v2.structure_mapping",
                        f"{path}.structure_mapping_hypothesis",
                        f"structure mapping needs at least {minimum_mappings} explicit edges",
                    )
                )
            else:
                pairs: set[tuple[str, str]] = set()
                for mapping_index, edge in enumerate(mappings):
                    edge_path = f"{path}.structure_mapping_hypothesis[{mapping_index}]"
                    if (
                        not _is_mapping(edge)
                        or not _text(edge.get("source_edge"))
                        or not _text(edge.get("target_edge"))
                    ):
                        issues.append(
                            _issue(
                                "route_v2.structure_edge",
                                edge_path,
                                "each mapping needs source_edge and target_edge",
                            )
                        )
                        continue
                    pair = (edge["source_edge"].strip(), edge["target_edge"].strip())
                    if pair in pairs:
                        issues.append(
                            _issue(
                                "route_v2.structure_edge_duplicate",
                                edge_path,
                                "structure mappings must contain distinct edges",
                            )
                        )
                    pairs.add(pair)

            ownership = direction.get("subject_ownership")
            if not _is_mapping(ownership) or not _text(ownership.get("hypothesis")):
                issues.append(
                    _issue(
                        "route_v2.ownership",
                        f"{path}.subject_ownership",
                        "ownership needs exact fact references and one hypothesis",
                    )
                )
            else:
                issues.extend(
                    _validate_fact_ref_list(
                        ownership.get("fact_refs"),
                        used_refs,
                        code="route_v2.ownership_fact_refs",
                        path=f"{path}.subject_ownership.fact_refs",
                    )
                )
            if not _text_list(direction.get("assumptions"), minimum=1):
                issues.append(
                    _issue(
                        "route_v2.assumptions",
                        f"{path}.assumptions",
                        "each direction must list its unverified assumptions",
                    )
                )

            deletion = direction.get("far_deletion_test")
            if distance == "far":
                if not _is_mapping(deletion):
                    issues.append(
                        _issue(
                            "route_v2.far_deletion_test",
                            f"{path}.far_deletion_test",
                            "far direction must survive explicit surface deletion",
                        )
                    )
                else:
                    removed = deletion.get("removed_surface_terms")
                    if not _text_list(removed) or not set(brief["surface_terms"]).issubset(set(removed)):
                        issues.append(
                            _issue(
                                "route_v2.far_removed_terms",
                                f"{path}.far_deletion_test.removed_surface_terms",
                                "far deletion must remove every brief surface term",
                            )
                        )
                    remaining = deletion.get("remaining_human_subject_hypothesis")
                    if not _text(remaining):
                        issues.append(
                            _issue(
                                "route_v2.far_remaining_subject",
                                f"{path}.far_deletion_test.remaining_human_subject_hypothesis",
                                "far direction needs a remaining human subject",
                            )
                        )
                    else:
                        forbidden_terms = {
                            *brief.get("surface_terms", []),
                            *brief.get("commercial_object_terms", []),
                        }
                        leaked = sorted(term for term in forbidden_terms if term and term in remaining)
                        if leaked:
                            issues.append(
                                _issue(
                                    "route_v2.far_surface_leak",
                                    f"{path}.far_deletion_test.remaining_human_subject_hypothesis",
                                    f"far remaining subject still contains removed terms: {leaked!r}",
                                )
                            )
                    issues.extend(
                        _validate_fact_ref_list(
                            deletion.get("ownership_fact_refs"),
                            used_refs,
                            code="route_v2.far_ownership_refs",
                            path=f"{path}.far_deletion_test.ownership_fact_refs",
                        )
                    )
            elif deletion is not None:
                issues.append(
                    _issue(
                        "route_v2.non_far_deletion_test",
                        f"{path}.far_deletion_test",
                        "near and mid directions must set far_deletion_test to null",
                    )
                )

            signature_fields = (
                direction.get("content_subject_hypothesis"),
                direction.get("audience_tension_hypothesis"),
                industry_role,
            )
            if all(_text(value) for value in signature_fields):
                signature = tuple(value.strip() for value in signature_fields)
                if signature in signatures:
                    issues.append(
                        _issue(
                            "route_v2.direction_duplicate",
                            path,
                            "directions must be structurally distinct",
                        )
                    )
                signatures.add(signature)

    if distances != SEMANTIC_DISTANCES:
        issues.append(
            _issue(
                "route_v2.distance_coverage",
                "directions",
                "directions must cover near, mid, and far exactly once",
            )
        )

    recommendation = result.get("recommendation")
    if not _is_mapping(recommendation):
        issues.append(
            _issue(
                "route_v2.recommendation",
                "recommendation",
                "recommendation is required",
            )
        )
    else:
        selected_ref = recommendation.get("selected_direction_ref")
        selected = direction_by_id.get(selected_ref)
        if selected is None:
            issues.append(
                _issue(
                    "route_v2.selected_ref",
                    "recommendation.selected_direction_ref",
                    "selected direction must reference a declared direction",
                )
            )
        elif selected.get("semantic_distance") not in set(brief["selection_policy"]["allowed_distances"]):
            issues.append(
                _issue(
                    "route_v2.selected_distance",
                    "recommendation.selected_direction_ref",
                    "selected direction violates the frozen policy",
                )
            )
        issues.extend(
            _validate_fact_ref_list(
                recommendation.get("fact_refs"),
                used_refs,
                code="route_v2.recommendation_fact_refs",
                path="recommendation.fact_refs",
            )
        )
        if not _text_list(recommendation.get("assumptions"), minimum=1):
            issues.append(
                _issue(
                    "route_v2.recommendation_assumptions",
                    "recommendation.assumptions",
                    "recommendation must expose its unverified assumptions",
                )
            )
        for field in (
            "reason_hypothesis",
            "tradeoff_hypothesis",
            "why_not_near_hypothesis",
        ):
            if not _text(recommendation.get(field)):
                issues.append(
                    _issue(
                        f"route_v2.recommendation_{field}",
                        f"recommendation.{field}",
                        f"{field} is required",
                    )
                )
    return issues


def validate_story_result_v2(
    result: Any,
    brief: Any,
    route_result: Any,
) -> list[dict[str, str]]:
    issues = validate_route_result(route_result, brief)
    if issues:
        return issues
    if not _is_mapping(route_result) or route_result.get("schema_version") != ROUTE_SCHEMA_VERSION_V2:
        return [
            _issue(
                "story_v2.route_schema",
                "source_route_sha256",
                "story v2 requires a mechanically valid route v2 result",
            )
        ]
    if not _is_mapping(result):
        return [_issue("story_v2.type", "$", "story result must be an object")]
    if result.get("schema_version") != STORY_SCHEMA_VERSION_V2:
        issues.append(_issue("story_v2.schema", "schema_version", "story v2 schema version is invalid"))
    if result.get("epistemic_state") != "creative_hypothesis":
        issues.append(
            _issue(
                "story_v2.state",
                "epistemic_state",
                "story v2 must be labelled creative_hypothesis",
            )
        )
    if result.get("source_route_sha256") != canonical_sha256(route_result):
        issues.append(
            _issue(
                "story_v2.route_sha",
                "source_route_sha256",
                "story must bind the frozen route bytes",
            )
        )
    chosen_ref = (route_result.get("recommendation") or {}).get("selected_direction_ref")
    if result.get("selected_direction_ref") != chosen_ref:
        issues.append(
            _issue(
                "story_v2.selected_ref",
                "selected_direction_ref",
                "story must compile the frozen selected direction",
            )
        )

    fact_issues, _used_refs = _validate_exact_fact_records(
        result.get("facts_used"),
        brief,
        code_prefix="story_v2",
        path="facts_used",
    )
    issues.extend(fact_issues)
    if not _is_list(result.get("creative_assumptions")) or not all(
        _text(item) for item in result.get("creative_assumptions", [])
    ):
        issues.append(
            _issue(
                "story_v2.assumptions",
                "creative_assumptions",
                "story assumptions must be an explicit text list",
            )
        )
    mode = result.get("commercial_object_mode")
    if mode not in COMMERCIAL_OBJECT_MODES:
        issues.append(
            _issue(
                "story_v2.commercial_mode",
                "commercial_object_mode",
                "mode must be absent or causal",
            )
        )
    if not _text(result.get("substitution_test_hypothesis")):
        issues.append(
            _issue(
                "story_v2.substitution_test",
                "substitution_test_hypothesis",
                "substitution test hypothesis is required",
            )
        )

    story = result.get("story_world")
    actor_by_id: dict[str, Mapping[str, Any]] = {}
    protagonist_ref: str | None = None
    if not _is_mapping(story):
        issues.append(_issue("story_v2.world", "story_world", "story world is required"))
        story = {}
    else:
        actors = story.get("actors")
        if not _is_list(actors) or not actors:
            issues.append(
                _issue(
                    "story_v2.actors",
                    "story_world.actors",
                    "at least one structured actor is required",
                )
            )
        else:
            for index, actor in enumerate(actors):
                path = f"story_world.actors[{index}]"
                if not _is_mapping(actor):
                    issues.append(_issue("story_v2.actor", path, "actor must be an object"))
                    continue
                actor_id = actor.get("id")
                if not _text(actor_id) or actor_id in actor_by_id:
                    issues.append(
                        _issue(
                            "story_v2.actor_id",
                            f"{path}.id",
                            "actor id is missing or duplicated",
                        )
                    )
                else:
                    actor_by_id[actor_id] = actor
                if actor.get("role") not in {"subject_self", "fictional_character"}:
                    issues.append(
                        _issue(
                            "story_v2.actor_role",
                            f"{path}.role",
                            "actor role is invalid",
                        )
                    )
                if actor.get("camera_presence") not in {"on_camera", "off_camera", "voice_only"}:
                    issues.append(
                        _issue(
                            "story_v2.camera_presence",
                            f"{path}.camera_presence",
                            "camera presence is invalid",
                        )
                    )
                if not _text(actor.get("description")):
                    issues.append(
                        _issue(
                            "story_v2.actor_description",
                            f"{path}.description",
                            "actor description is required",
                        )
                    )
        protagonist_ref = story.get("protagonist_ref")
        if protagonist_ref not in actor_by_id:
            issues.append(
                _issue(
                    "story_v2.protagonist_ref",
                    "story_world.protagonist_ref",
                    "protagonist must reference a declared actor",
                )
            )
        for field in STORY_TEXT_FIELDS_V2:
            if not _text(story.get(field)):
                issues.append(
                    _issue(
                        f"story_v2.{field}",
                        f"story_world.{field}",
                        f"{field} is required",
                    )
                )
        values = [story.get(field, "").strip() for field in STORY_TEXT_FIELDS_V2 if _text(story.get(field))]
        if len(set(values)) < 8:
            issues.append(
                _issue(
                    "story_v2.repetition",
                    "story_world",
                    "story nodes must describe distinct states and actions",
                )
            )

        choice = story.get("costly_choice")
        if not _is_mapping(choice) or any(
            not _text(choice.get(field))
            for field in ("option_a", "option_b", "chosen", "why_incompatible_now")
        ):
            issues.append(
                _issue(
                    "story_v2.costly_choice",
                    "story_world.costly_choice",
                    "costly choice needs two options, one exact choice, and current incompatibility",
                )
            )
        else:
            if choice["option_a"].strip() == choice["option_b"].strip():
                issues.append(
                    _issue(
                        "story_v2.choice_duplicate",
                        "story_world.costly_choice",
                        "choice options must be different",
                    )
                )
            if choice["chosen"] not in {choice["option_a"], choice["option_b"]}:
                issues.append(
                    _issue(
                        "story_v2.choice_resolution",
                        "story_world.costly_choice.chosen",
                        "chosen must exactly equal option_a or option_b",
                    )
                )

        cost = story.get("cost")
        if not _is_mapping(cost) or not _text(cost.get("paid")) or not _text(cost.get("persists_after_scene")):
            issues.append(
                _issue(
                    "story_v2.cost",
                    "story_world.cost",
                    "cost needs a protagonist bearer and a persistent consequence",
                )
            )
        elif cost.get("bearer_ref") != protagonist_ref:
            issues.append(
                _issue(
                    "story_v2.cost_bearer",
                    "story_world.cost.bearer_ref",
                    "the protagonist must bear the cost",
                )
            )

        outcome = story.get("goal_outcome")
        if (
            not _is_mapping(outcome)
            or outcome.get("status") not in {"achieved", "failed", "transformed"}
            or not _text(outcome.get("result"))
        ):
            issues.append(
                _issue(
                    "story_v2.goal_outcome",
                    "story_world.goal_outcome",
                    "goal outcome must state achieved, failed, or transformed with a result",
                )
            )

        edges = story.get("causal_edges")
        seen_edges: set[tuple[str, str]] = set()
        if not _is_list(edges):
            issues.append(
                _issue(
                    "story_v2.causal_edges",
                    "story_world.causal_edges",
                    "causal edges must be a list",
                )
            )
        else:
            for index, edge in enumerate(edges):
                path = f"story_world.causal_edges[{index}]"
                if (
                    not _is_mapping(edge)
                    or edge.get("from") not in STORY_CAUSAL_NODES_V2
                    or edge.get("to") not in STORY_CAUSAL_NODES_V2
                    or not _text(edge.get("because"))
                ):
                    issues.append(
                        _issue(
                            "story_v2.causal_edge",
                            path,
                            "causal edge must connect declared v2 nodes with a reason",
                        )
                    )
                    continue
                seen_edges.add((edge["from"], edge["to"]))
        if not REQUIRED_CAUSAL_EDGES_V2.issubset(seen_edges):
            issues.append(
                _issue(
                    "story_v2.causal_edge_coverage",
                    "story_world.causal_edges",
                    "causal chain must connect trigger, protagonist cost, goal outcome, and state change",
                )
            )

    production = result.get("production_translation")
    if not _is_mapping(production):
        issues.append(
            _issue(
                "story_v2.production",
                "production_translation",
                "production translation is required",
            )
        )
    else:
        for field in ("telling_mode", "constraint_fit_hypothesis"):
            if not _text(production.get(field)):
                issues.append(
                    _issue(
                        f"story_v2.production_{field}",
                        f"production_translation.{field}",
                        f"{field} is required",
                    )
                )
        on_camera = production.get("on_camera_actor_refs")
        off_camera = production.get("off_camera_actor_refs")
        if not _is_list(on_camera) or not on_camera or any(ref not in actor_by_id for ref in on_camera):
            issues.append(
                _issue(
                    "story_v2.on_camera_refs",
                    "production_translation.on_camera_actor_refs",
                    "at least one on-camera actor reference must resolve",
                )
            )
            on_camera = []
        if not _is_list(off_camera) or any(ref not in actor_by_id for ref in off_camera):
            issues.append(
                _issue(
                    "story_v2.off_camera_refs",
                    "production_translation.off_camera_actor_refs",
                    "off-camera actor references must resolve",
                )
            )
            off_camera = []
        if set(on_camera) & set(off_camera):
            issues.append(
                _issue(
                    "story_v2.camera_ref_overlap",
                    "production_translation",
                    "one actor cannot be both on- and off-camera",
                )
            )
        if set(on_camera) | set(off_camera) != set(actor_by_id):
            issues.append(
                _issue(
                    "story_v2.camera_ref_coverage",
                    "production_translation",
                    "production translation must classify every actor",
                )
            )
        for ref in on_camera:
            if actor_by_id[ref].get("camera_presence") != "on_camera":
                issues.append(
                    _issue(
                        "story_v2.on_camera_mismatch",
                        "production_translation.on_camera_actor_refs",
                        "on-camera reference conflicts with actor camera_presence",
                    )
                )
        for ref in off_camera:
            if actor_by_id[ref].get("camera_presence") not in {"off_camera", "voice_only"}:
                issues.append(
                    _issue(
                        "story_v2.off_camera_mismatch",
                        "production_translation.off_camera_actor_refs",
                        "off-camera reference conflicts with actor camera_presence",
                    )
                )
        if "一人一机" in brief.get("production_constraints", []) and len(on_camera) > 1:
            issues.append(
                _issue(
                    "story_v2.one_person_limit",
                    "production_translation.on_camera_actor_refs",
                    "one-person production cannot require multiple on-camera actors",
                )
            )
        if not _text_list(production.get("required_visible_actions"), minimum=1):
            issues.append(
                _issue(
                    "story_v2.visible_actions",
                    "production_translation.required_visible_actions",
                    "at least one visible, shootable action is required",
                )
            )

    bridge = result.get("business_bridge")
    if not _is_mapping(bridge):
        issues.append(
            _issue(
                "story_v2.business_bridge",
                "business_bridge",
                "business bridge is required",
            )
        )
    else:
        for field in (
            "meaning_attributed_to_subject_hypothesis",
            "connection_to_objective_hypothesis",
        ):
            if not _text(bridge.get(field)):
                issues.append(
                    _issue(
                        f"story_v2.bridge_{field}",
                        f"business_bridge.{field}",
                        f"{field} is required",
                    )
                )

    logline = result.get("logline")
    if not _text(logline) or "\n" in logline or len(logline.strip()) < 24:
        issues.append(
            _issue(
                "story_v2.logline",
                "logline",
                "logline must be one substantive line",
            )
        )
    story_text = json.dumps(story, ensure_ascii=False) + (logline if isinstance(logline, str) else "")
    for term in BUSINESS_WORLD_TERMS:
        if term in story_text:
            issues.append(
                _issue(
                    "story_v2.business_world_leak",
                    "story_world",
                    f"business term {term!r} leaked into story",
                )
            )
    if mode == "absent":
        for term in brief.get("commercial_object_terms", []):
            if term and term in story_text:
                issues.append(
                    _issue(
                        "story_v2.absent_object_leak",
                        "story_world",
                        f"absent term {term!r} leaked into story",
                    )
                )
    return issues
