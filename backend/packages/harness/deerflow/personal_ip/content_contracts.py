"""Typed contracts for the Personal-IP content lineage.

These contracts deliberately keep four worlds separate:

* an Owner's objective and assertions;
* externally observed evidence;
* labelled interpretation and creative fiction;
* production translation.

They are production-owned contracts.  Nothing in this module imports the
quarantined director research tree.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

EntryRoute = Literal["zero_start", "benchmark"]
StoryMode = Literal["factual", "fictional", "hybrid"]
OutcomeGoal = Literal["conversion", "recognition", "trust"]
TimeHorizon = Literal["urgent", "near_term", "long_term"]
CarrierKind = Literal["person", "product", "brand", "organization"]
ContentRouteKind = Literal[
    "offer",
    "proof",
    "demonstration",
    "explanation",
    "semantic_story",
    "hybrid",
]
SCRIPT_BOUNDARY_VERIFIER_VERSION = "personal-ip-script-boundary-verifier-v2"
EpistemicState = Literal[
    "user_asserted",
    "source_observed",
    "derived",
    "hypothesized",
    "creative",
    "unknown",
    "contradicted",
]
ClaimUsage = Literal[
    "attributed_fact",
    "source_fact",
    "labelled_hypothesis",
    "creative_inspiration",
    "excluded",
]

NonEmptyText = Annotated[str, Field(min_length=1, max_length=20_000)]
ShortText = Annotated[str, Field(min_length=1, max_length=1_000)]

_SENSITIVE_JSON_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "encryptedaccesstoken",
    "encryptedrefreshtoken",
    "password",
    "providerauth",
    "providerpayload",
    "rawproviderpayload",
    "refreshtoken",
    "secret",
    "secrets",
    "statehash",
}


def _reject_sensitive_json_keys(value: JsonValue, *, path: str) -> JsonValue:
    """Keep credentials and opaque provider payloads out of normal content data."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            if normalized in _SENSITIVE_JSON_KEYS:
                raise ValueError(f"credential or raw-provider field is not allowed: {path}.{key}")
            _reject_sensitive_json_keys(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_sensitive_json_keys(item, path=f"{path}[{index}]")
    return value


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContentObjective(_Contract):
    """The change the Owner wants this one content work to attempt."""

    desired_change: ShortText
    audience_situation: str = Field(default="unknown", max_length=2_000)
    business_context: str = Field(default="", max_length=4_000)
    constraints: list[ShortText] = Field(default_factory=list, max_length=50)


class MissionDecision(_Contract):
    """The ordered outcome decision for one reusable editorial program."""

    goal_priority: list[OutcomeGoal] = Field(min_length=1, max_length=3)
    time_horizon: TimeHorizon
    deadline_or_window: ShortText
    desired_action: ShortText
    success_signal: ShortText
    cost_of_delay: str = Field(default="", max_length=2_000)
    non_goals: list[ShortText] = Field(default_factory=list, max_length=20)
    rationale: NonEmptyText

    @model_validator(mode="after")
    def validate_ordered_goal(self) -> Self:
        if len(set(self.goal_priority)) != len(self.goal_priority):
            raise ValueError("mission goal_priority must not contain duplicates")
        unknown_deadlines = {"unknown", "未知", "不清楚", "待确认"}
        if self.time_horizon == "urgent":
            if self.deadline_or_window.casefold() in unknown_deadlines:
                raise ValueError("urgent missions require a known deadline or operating window")
            if not self.cost_of_delay.strip():
                raise ValueError("urgent missions require the concrete cost of delay")
        return self


class AudienceHypothesis(_Contract):
    """The smallest audience judgment needed for the current program."""

    situation: ShortText
    state: Literal["user_asserted", "hypothesized", "unknown"]
    uncertainties: list[ShortText] = Field(default_factory=list, max_length=20)


class AttributionCarrier(_Contract):
    kind: CarrierKind
    identity: ShortText


class AttributionPlan(_Contract):
    """Who should accumulate the association, independent of the mission."""

    primary_carrier: AttributionCarrier
    supporting_carriers: list[AttributionCarrier] = Field(default_factory=list, max_length=10)
    desired_association: ShortText
    attribution_guard: ShortText
    rationale: NonEmptyText

    @model_validator(mode="after")
    def validate_carriers(self) -> Self:
        identities = {(self.primary_carrier.kind, self.primary_carrier.identity.casefold())}
        for carrier in self.supporting_carriers:
            identity = (carrier.kind, carrier.identity.casefold())
            if identity in identities:
                raise ValueError("attribution carriers must not contain duplicates")
            identities.add(identity)
        return self


class DifferenceBasis(_Contract):
    """One labelled basis for a still-unvalidated differentiation hypothesis."""

    claim: ShortText
    state: Literal["user_asserted", "derived", "hypothesized"]


class DifferentiationHypothesis(_Contract):
    """A route-specific hypothesis, never a validated positioning verdict."""

    state: Literal["hypothesized"] = "hypothesized"
    statement: ShortText
    contrast: ShortText
    basis: list[DifferenceBasis] = Field(min_length=1, max_length=30)
    reason_to_choose: ShortText
    reason_to_believe: ShortText
    sacrifice: ShortText
    test_signal: ShortText
    uncertainties: list[ShortText] = Field(default_factory=list, max_length=20)


class EditorialSpine(_Contract):
    """Optional cross-work semantic territory for a continuing program."""

    source_concepts: list[ShortText] = Field(min_length=1, max_length=20)
    human_theme: ShortText
    recurring_question: ShortText
    boundary: ShortText


class EditorialProgramDraft(_Contract):
    """One immutable total-editor decision that may govern many content works."""

    contract_version: Literal["personal-ip-editorial-program-v1"] = "personal-ip-editorial-program-v1"
    title: ShortText
    mission: MissionDecision
    audience: AudienceHypothesis
    attribution: AttributionPlan
    differentiation: DifferentiationHypothesis
    editorial_spine: EditorialSpine | None = None
    parent_program_version_id: str | None = Field(default=None, max_length=64)


def editorial_program_decision_payload(
    program: EditorialProgramDraft,
) -> dict[str, JsonValue]:
    """Return the immutable cross-work decision, excluding row identity fields."""
    return program.model_dump(
        mode="json",
        exclude={"title", "parent_program_version_id"},
    )


def _contract_digest(value: JsonValue) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def editorial_program_decision_digest(program: EditorialProgramDraft) -> str:
    return _contract_digest(editorial_program_decision_payload(program))


class ClaimBasis(_Contract):
    """One claim plus the only way it may be used by a script."""

    claim: NonEmptyText
    state: EpistemicState
    usage: ClaimUsage
    evidence_refs: list[ShortText] = Field(
        default_factory=list,
        max_length=100,
        description=("Canonical Evidence MCP refs for source_observed claims. Copy the bound request id and item index; for example evidence://video-.../items/0/provider/asr."),
    )

    @model_validator(mode="after")
    def validate_epistemic_usage(self) -> Self:
        allowed: dict[str, set[str]] = {
            "user_asserted": {"attributed_fact", "creative_inspiration", "excluded"},
            "source_observed": {"source_fact", "creative_inspiration", "excluded"},
            "derived": {"labelled_hypothesis", "creative_inspiration", "excluded"},
            "hypothesized": {"labelled_hypothesis", "creative_inspiration", "excluded"},
            "creative": {"creative_inspiration", "excluded"},
            "unknown": {"excluded"},
            "contradicted": {"excluded"},
        }
        if self.usage not in allowed[self.state]:
            raise ValueError(f"claim state {self.state!r} cannot be used as {self.usage!r}")
        if self.state == "source_observed" and not self.evidence_refs:
            raise ValueError("source_observed claims require at least one evidence_ref")
        return self


class BreakdownObservation(_Contract):
    observation: NonEmptyText
    evidence_refs: list[ShortText] = Field(
        min_length=1,
        max_length=100,
        description=(
            "Canonical refs into the exact typed Evidence MCP item, such as "
            "evidence://{request_id}/items/{item_index}/source, media-metadata, "
            "analysis-receipt, coverage/asr, or provider/asr. Do not use JSON field "
            "paths or request_id#field refs."
        ),
    )


class BreakdownInterpretation(_Contract):
    interpretation: NonEmptyText
    state: Literal["derived", "hypothesized"]
    based_on_observations: list[int] = Field(min_length=1, max_length=100)


class BreakdownDraft(_Contract):
    """A replayable breakdown, with observations kept apart from inference."""

    source_kind: Literal["platform_content", "uploaded_file", "owner_material"]
    source_identity: dict[str, JsonValue] = Field(min_length=1)
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_request_id: str | None = Field(
        default=None,
        min_length=12,
        max_length=80,
        description="Copy metadata.request_id from the exact Evidence MCP result.",
    )
    evidence_item_index: int | None = Field(
        default=None,
        ge=0,
        le=2,
        description="Zero-based item index in that Evidence MCP result; use 0 for its first item.",
    )
    evidence_contract_version: str | None = Field(default=None, max_length=80)
    evidence_payload_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observations: list[BreakdownObservation] = Field(min_length=1, max_length=500)
    interpretations: list[BreakdownInterpretation] = Field(default_factory=list, max_length=200)
    limitations: list[ShortText] = Field(default_factory=list, max_length=100)

    @field_validator("source_identity")
    @classmethod
    def reject_sensitive_source_identity(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        _reject_sensitive_json_keys(value, path="source_identity")
        return value

    @model_validator(mode="after")
    def validate_interpretation_refs(self) -> Self:
        observation_count = len(self.observations)
        for item in self.interpretations:
            if any(index < 0 or index >= observation_count for index in item.based_on_observations):
                raise ValueError("interpretation observation index is out of range")
        external = self.source_kind in {"platform_content", "uploaded_file"}
        evidence_fields = (
            self.evidence_contract_version,
            self.evidence_payload_digest,
        )
        if external:
            if self.evidence_request_id is None or self.evidence_item_index is None:
                raise ValueError("external breakdowns require an Evidence MCP request id and item index")
            prefix = f"evidence://{self.evidence_request_id}/items/{self.evidence_item_index}/"
            if any(not ref.startswith(prefix) for observation in self.observations for ref in observation.evidence_refs):
                raise ValueError(f"external breakdown evidence_refs must start with {prefix}; use canonical tokens such as source, media-metadata, analysis-receipt, coverage/asr, or provider/asr")
        elif any(
            value is not None
            for value in (
                self.evidence_request_id,
                self.evidence_item_index,
                *evidence_fields,
            )
        ):
            raise ValueError("owner_material cannot claim an Evidence MCP binding")
        return self


class SemanticCausalRoute(_Contract):
    """A selected meaning-to-human-causality bridge, not a business decision."""

    association_path: list[ShortText] = Field(min_length=2, max_length=12)
    human_theme: ShortText
    causal_pattern: ShortText
    episode_tension: ShortText
    mission_bridge: ShortText
    attribution_guard: ShortText

    @model_validator(mode="after")
    def validate_association_path(self) -> Self:
        normalized = [item.casefold() for item in self.association_path]
        if len(set(normalized)) != len(normalized):
            raise ValueError("semantic association_path must not contain duplicates")
        if self.human_theme.casefold() not in normalized:
            raise ValueError("semantic human_theme must be one node in association_path")
        if normalized[-1] != self.human_theme.casefold():
            raise ValueError("semantic association_path must end at human_theme")
        return self


def semantic_causal_route_digest(route: SemanticCausalRoute) -> str:
    return _contract_digest(route.model_dump(mode="json"))


class DirectionDraft(_Contract):
    """The total editor's work-level decision, not the story or shooting plan."""

    contract_version: Literal[
        "personal-ip-direction-v1",
        "personal-ip-direction-v2",
    ] = "personal-ip-direction-v1"
    premise: ShortText
    audience_situation: ShortText
    core_tension: ShortText
    content_promise: ShortText
    creative_route: ShortText
    rationale: NonEmptyText
    truth_mode: StoryMode
    business_relevance: str = Field(default="", max_length=4_000)
    route_kind: ContentRouteKind | None = None
    semantic_route: SemanticCausalRoute | None = None
    editorial_program_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="Server-bound digest of the exact EditorialProgramVersion decision.",
    )
    claim_basis: list[ClaimBasis] = Field(default_factory=list, max_length=200)
    breakdown_version_ids: list[str] = Field(default_factory=list, max_length=100)
    parent_direction_version_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_route_contract(self) -> Self:
        if self.contract_version == "personal-ip-direction-v1":
            if self.route_kind is not None or self.semantic_route is not None or self.editorial_program_digest is not None:
                raise ValueError("v1 directions cannot contain v2 editorial routing fields")
            return self
        if self.route_kind is None:
            raise ValueError("v2 directions require route_kind")
        expected_truth_mode: dict[ContentRouteKind, StoryMode] = {
            "offer": "factual",
            "proof": "factual",
            "demonstration": "factual",
            "explanation": "factual",
            "semantic_story": "fictional",
            "hybrid": "hybrid",
        }
        if self.truth_mode != expected_truth_mode[self.route_kind]:
            raise ValueError(f"route {self.route_kind!r} requires truth_mode {expected_truth_mode[self.route_kind]!r}")
        semantic_required = self.route_kind in {"semantic_story", "hybrid"}
        if semantic_required and self.semantic_route is None:
            raise ValueError("the selected route and truth mode require a semantic causal route")
        if not semantic_required and self.semantic_route is not None:
            raise ValueError("direct offer, proof, demonstration and explanation routes must skip the semantic route")
        return self


def direction_decision_payload(direction: DirectionDraft) -> dict[str, JsonValue]:
    """Return the verified editor decision, excluding server-bound evidence ids."""
    return direction.model_dump(
        mode="json",
        exclude={"breakdown_version_ids"},
    )


def direction_decision_digest(direction: DirectionDraft) -> str:
    return _contract_digest(direction_decision_payload(direction))


def validate_direction_program_binding(
    program: EditorialProgramDraft,
    direction: DirectionDraft,
) -> None:
    """Verify the exact Program -> Direction decision and semantic route."""
    if direction.contract_version != "personal-ip-direction-v2":
        return
    if direction.editorial_program_digest != editorial_program_decision_digest(program):
        raise ValueError("v2 direction does not bind the exact EditorialProgramVersion decision digest")

    semantic_route = direction.semantic_route
    if semantic_route is None:
        return
    spine = program.editorial_spine
    if spine is None:
        raise ValueError("semantic routes require an editorial spine in the selected program")
    if semantic_route.human_theme.casefold() != spine.human_theme.casefold():
        raise ValueError("semantic route human_theme must match the selected editorial program")
    source_concepts = {concept.casefold() for concept in spine.source_concepts}
    if semantic_route.association_path[0].casefold() not in source_concepts:
        raise ValueError("semantic route must start from a selected source concept")


def script_boundary_verifier_input_payload(
    direction: DirectionDraft,
    *,
    locked_story: str | None,
    script_text: str,
) -> dict[str, JsonValue]:
    """Return the exact canonical payload reviewed by the script verifier."""
    claims: list[dict[str, JsonValue]] = [
        {
            "id": f"C{index + 1}",
            **claim.model_dump(mode="json"),
        }
        for index, claim in enumerate(direction.claim_basis)
        if claim.usage != "excluded"
    ]
    semantic_route = direction.semantic_route
    return {
        "schema_version": SCRIPT_BOUNDARY_VERIFIER_VERSION,
        "story_mode": direction.truth_mode,
        "locked_story": locked_story,
        "semantic_route": (semantic_route.model_dump(mode="json") if semantic_route is not None else None),
        "semantic_route_digest": (semantic_causal_route_digest(semantic_route) if semantic_route is not None else None),
        "claim_basis": claims,
        "script_text": script_text,
    }


def script_boundary_verifier_input_digest(
    direction: DirectionDraft,
    *,
    locked_story: str | None,
    script_text: str,
) -> str:
    """Hash the exact final script and context presented to the verifier."""
    return _contract_digest(
        script_boundary_verifier_input_payload(
            direction,
            locked_story=locked_story,
            script_text=script_text,
        )
    )


class StoryEngineSeed(_Contract):
    """The complete Chinese, industry-neutral input to a fiction-only story engine."""

    recurring_conflict: ShortText
    desire_a: ShortText
    desire_b: ShortText
    relationship_at_stake: ShortText
    causal_pattern: ShortText
    tone: str = Field(default="", max_length=500)
    semantic_route_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("recurring_conflict", "desire_a", "desire_b", "relationship_at_stake", "causal_pattern", "tone")
    @classmethod
    def reject_business_and_production_leaks(cls, value: str) -> str:
        blocked = (
            "账号",
            "平台",
            "流量",
            "粉丝",
            "转化",
            "带货",
            "产品",
            "品牌",
            "业务",
            "视频",
            "镜头",
            "拍摄",
            "出镜",
            "发布",
            "文案",
            "生意",
            "经营",
            "门店",
            "店铺",
            "商家",
            "商户",
            "店主",
            "老板",
            "客户",
            "顾客",
            "公司",
            "行业",
            "职业",
            "营销",
            "商品",
            "创业",
            "企业",
            "电商",
            "运营",
            "广告",
            "内容创作",
            "创作者",
            "网红",
            "主播",
            "博主",
            "达人",
            "销售",
            "投放",
            "推广",
            "获客",
            "商业",
            "收益",
            "收入",
            "利润",
            "成本",
            "订单",
            "交易",
            "成交",
            "供应商",
            "管理者",
            "经理",
            "总监",
            "员工",
            "职员",
            "同事",
            "职场",
            "工作",
            "上班",
            "加班",
            "办公室",
            "工厂",
            "餐厅",
            "餐饮",
            "机构",
            "团队",
            "项目",
            "用户",
            "消费者",
            "服务",
            "方案",
        )
        if any(term in value for term in blocked):
            raise ValueError("story_engine_seed must contain only an industry-neutral abstract human conflict")
        if re.search(r"[A-Za-z]", value):
            raise ValueError("story_engine_seed must be Chinese-only and contain only an industry-neutral abstract human conflict")
        normalized = value.casefold()
        blocked_english = (
            "account",
            "platform",
            "traffic",
            "followers?",
            "conversion",
            "sales?",
            "selling",
            "products?",
            "brands?",
            "business",
            "videos?",
            "camera",
            "filming",
            "shooting",
            "on-camera",
            "publish(?:ing)?",
            "copywriting",
            "shops?",
            "stores?",
            "merchants?",
            "customers?",
            "clients?",
            "companies?",
            "company",
            "industr(?:y|ies)",
            "professions?",
            "marketing",
            "goods",
        )
        if any(re.search(rf"\b(?:{term})\b", normalized) for term in blocked_english):
            raise ValueError("story_engine_seed must contain only an industry-neutral abstract human conflict")
        return value


class CreativeElement(_Contract):
    element: NonEmptyText
    kind: Literal["fictional", "composite", "dramatic_device"]
    disclosure: ShortText


class ScriptDraft(_Contract):
    """One immutable script version with an explicit truth boundary."""

    title: ShortText
    story_mode: StoryMode
    script_text: NonEmptyText
    claim_basis: list[ClaimBasis] = Field(default_factory=list, max_length=200)
    creative_elements: list[CreativeElement] = Field(default_factory=list, max_length=200)
    story_engine_seed: StoryEngineSeed | None = None
    locked_story: str | None = Field(default=None, max_length=2_000)
    production_notes: dict[str, JsonValue] = Field(default_factory=dict)
    direction_version_id: str | None = Field(default=None, max_length=64)
    parent_script_version_id: str | None = Field(default=None, max_length=64)

    @field_validator("production_notes")
    @classmethod
    def reject_sensitive_production_notes(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        _reject_sensitive_json_keys(value, path="production_notes")
        return value

    @model_validator(mode="after")
    def validate_truth_boundary(self) -> Self:
        live_claims = [claim for claim in self.claim_basis if claim.usage != "excluded"]
        if self.story_mode == "factual":
            if self.creative_elements or self.story_engine_seed is not None or self.locked_story:
                raise ValueError("factual scripts cannot contain fictional story-engine material")
            if not live_claims:
                raise ValueError("factual scripts require at least one usable attributed or sourced claim")
        elif self.story_mode == "fictional":
            if self.story_engine_seed is None or not self.locked_story or not self.creative_elements:
                raise ValueError("fictional scripts require a seed, locked story and creative disclosure")
            if live_claims:
                raise ValueError("fictional scripts cannot present user or source claims inside the story")
        else:
            if self.story_engine_seed is None or not self.locked_story or not self.creative_elements:
                raise ValueError("hybrid scripts require a seed, locked story and creative disclosure")
            if not live_claims:
                raise ValueError("hybrid scripts require explicit attributed or sourced claim material")
        return self


class ScriptBoundaryReceipt(_Contract):
    """The persisted, replayable result of the fail-closed script verifier."""

    supported: Literal[True]
    unsupported_spans: list[ShortText] = Field(max_length=0)
    reason_codes: list[str] = Field(default_factory=list, max_length=20)
    semantic_route_supported: Literal[True]
    semantic_route_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verifier_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, value: list[str]) -> list[str]:
        if any(not reason or len(reason) > 80 for reason in value):
            raise ValueError("script boundary reason codes must contain 1-80 characters")
        return value


def script_decision_payload(script: ScriptDraft) -> dict[str, JsonValue]:
    """Return the verified script body, excluding its server-bound Direction id."""
    return script.model_dump(
        mode="json",
        exclude={"direction_version_id"},
    )


def script_decision_digest(script: ScriptDraft) -> str:
    return _contract_digest(script_decision_payload(script))


def validate_script_direction_binding(
    direction: DirectionDraft,
    script: ScriptDraft,
) -> None:
    """Verify all deterministic Program -> Direction -> Script receipts."""
    if script.story_mode != direction.truth_mode:
        raise ValueError("script story_mode must match its direction truth_mode")
    if direction.contract_version == "personal-ip-direction-v1":
        return

    notes = script.production_notes
    if notes.get("boundary_verifier_version") != SCRIPT_BOUNDARY_VERIFIER_VERSION:
        raise ValueError("v2 script boundary verifier version is invalid")
    if notes.get("editorial_program_sha256") != direction.editorial_program_digest:
        raise ValueError("v2 script does not bind its exact EditorialProgramVersion decision")
    if notes.get("direction_decision_sha256") != direction_decision_digest(direction):
        raise ValueError("v2 script does not bind its exact Direction decision")

    receipt_value = notes.get("boundary_receipt")
    if not isinstance(receipt_value, dict):
        raise ValueError("v2 script boundary receipt is unavailable")
    try:
        receipt = ScriptBoundaryReceipt.model_validate(receipt_value)
    except ValueError as exc:
        raise ValueError("v2 script boundary receipt is invalid") from exc
    canonical_receipt = receipt.model_dump(mode="json")
    if receipt_value != canonical_receipt:
        raise ValueError("v2 script boundary receipt is not canonical")
    if notes.get("boundary_receipt_sha256") != _contract_digest(canonical_receipt):
        raise ValueError("v2 script boundary receipt digest does not match")
    expected_verifier_input_digest = script_boundary_verifier_input_digest(
        direction,
        locked_story=script.locked_story,
        script_text=script.script_text,
    )
    if receipt.verifier_input_sha256 != expected_verifier_input_digest:
        raise ValueError("v2 script boundary receipt does not bind the exact verifier input")

    semantic_route = direction.semantic_route
    expected_route_digest = semantic_causal_route_digest(semantic_route) if semantic_route is not None else None
    if receipt.semantic_route_digest != expected_route_digest:
        raise ValueError("v2 script boundary receipt does not bind the exact semantic route")
    if semantic_route is None:
        if script.story_engine_seed is not None:
            raise ValueError("direct v2 scripts cannot contain a semantic story seed")
        if notes.get("semantic_route_sha256") is not None:
            raise ValueError("direct v2 scripts cannot contain a semantic route receipt")
        return

    seed = script.story_engine_seed
    if seed is None:
        raise ValueError("semantic v2 scripts require a story seed")
    if seed.causal_pattern != semantic_route.causal_pattern:
        raise ValueError("v2 story seed causal pattern does not match its semantic route")
    if seed.semantic_route_digest != expected_route_digest:
        raise ValueError("v2 story seed does not bind its exact semantic route")
    if notes.get("semantic_route_sha256") != expected_route_digest:
        raise ValueError("v2 script semantic route receipt does not match")


class ProductionTranslation(_Contract):
    """Shooting/form constraints applied only after the story is locked."""

    form: Literal["spoken", "scene", "mixed"] = "mixed"
    narrator: str = Field(default="", max_length=500)
    setting: str = Field(default="", max_length=1_000)
    constraints: list[ShortText] = Field(default_factory=list, max_length=50)
    delivery_notes: list[ShortText] = Field(default_factory=list, max_length=50)


class WriterBrainRequest(_Contract):
    """One total-editor handoff to the isolated causal and script writers."""

    content_work_id: str | None = Field(
        default=None,
        max_length=64,
        description=("Existing work to version. If its BreakdownVersion was already saved, reuse this work and list that breakdown id in direction.breakdown_version_ids; do not resend the same breakdown."),
    )
    subject_id: str | None = Field(default=None, max_length=64)
    work_title: ShortText
    entry_route: EntryRoute | None = None
    objective: ContentObjective | None = None
    editorial_program_version_id: str | None = Field(default=None, max_length=64)
    editorial_program: EditorialProgramDraft | None = None
    breakdown: BreakdownDraft | None = Field(
        default=None,
        description=("Only a new or intentionally revised breakdown. Omit it when content_work_id already has the exact saved BreakdownVersion; resending creates a new immutable version."),
    )
    direction: DirectionDraft
    story_engine_seed: StoryEngineSeed | None = None
    production_translation: ProductionTranslation = Field(default_factory=ProductionTranslation)
    parent_script_version_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_writer_handoff(self) -> Self:
        creating = self.content_work_id is None
        if creating and (self.entry_route is None or self.objective is None):
            raise ValueError("new content work requires entry_route and objective")
        if creating and self.entry_route == "benchmark" and self.breakdown is None:
            raise ValueError("benchmark entry requires a breakdown")
        if self.direction.contract_version != "personal-ip-direction-v2":
            raise ValueError("writer brain requires a v2 total-editor direction")
        if self.direction.editorial_program_digest is not None:
            raise ValueError("editorial_program_digest is bound by the writer service, not the caller")
        if self.editorial_program is not None and self.editorial_program_version_id is not None:
            raise ValueError("provide a new editorial_program or an existing version id, not both")
        if creating and self.editorial_program is None and self.editorial_program_version_id is None:
            raise ValueError("new writing work requires an editorial program decision or exact version")
        if self.direction.truth_mode == "factual":
            if self.story_engine_seed is not None:
                raise ValueError("factual writing does not use a fiction story-engine seed")
        elif self.story_engine_seed is None:
            raise ValueError("fictional and hybrid writing require a story_engine_seed")
        if self.story_engine_seed is not None and self.story_engine_seed.semantic_route_digest is not None:
            raise ValueError("semantic_route_digest is bound by the writer service, not the caller")
        return self


class BreakdownSaveRequest(_Contract):
    """Persist a standalone evidence breakdown before a writing decision."""

    content_work_id: str | None = Field(default=None, max_length=64)
    subject_id: str | None = Field(default=None, max_length=64)
    work_title: ShortText
    objective: ContentObjective | None = None
    breakdown: BreakdownDraft

    @model_validator(mode="after")
    def validate_new_breakdown_work(self) -> Self:
        if self.content_work_id is None and self.objective is None:
            raise ValueError("new breakdown work requires an objective")
        return self


class ContentWorkCreate(_Contract):
    idempotency_key: str = Field(min_length=1, max_length=256)
    subject_id: str | None = Field(default=None, max_length=64)
    title: ShortText
    entry_route: EntryRoute
    objective: ContentObjective
    editorial_program_version_id: str | None = Field(default=None, max_length=64)
    editorial_program: EditorialProgramDraft | None = None
    breakdown: BreakdownDraft | None = None
    direction: DirectionDraft | None = None
    script: ScriptDraft | None = None

    @model_validator(mode="after")
    def validate_entry_route_and_dependencies(self) -> Self:
        if self.entry_route == "benchmark" and self.breakdown is None:
            raise ValueError("benchmark entry requires a breakdown")
        if self.editorial_program is not None and self.editorial_program_version_id is not None:
            raise ValueError("provide a new editorial_program or an existing version id, not both")
        if (self.editorial_program is not None or self.editorial_program_version_id is not None) and self.direction is None:
            raise ValueError("an editorial program decision must be committed with a direction")
        if self.direction is not None and self.direction.contract_version == "personal-ip-direction-v2":
            if self.editorial_program is None and self.editorial_program_version_id is None:
                raise ValueError("a v2 direction requires an editorial program decision or exact version")
        if self.script is not None and self.direction is None and not self.script.direction_version_id:
            raise ValueError("a script requires a new or existing direction version")
        return self


class ContentWorkAppend(_Contract):
    idempotency_key: str = Field(min_length=1, max_length=256)
    editorial_program_version_id: str | None = Field(default=None, max_length=64)
    editorial_program: EditorialProgramDraft | None = None
    breakdown: BreakdownDraft | None = None
    direction: DirectionDraft | None = None
    script: ScriptDraft | None = None

    @model_validator(mode="after")
    def validate_nonempty_commit(self) -> Self:
        if self.breakdown is None and self.direction is None and self.script is None:
            raise ValueError("a content commit must contain at least one version")
        if self.editorial_program is not None and self.editorial_program_version_id is not None:
            raise ValueError("provide a new editorial_program or an existing version id, not both")
        if (self.editorial_program is not None or self.editorial_program_version_id is not None) and self.direction is None:
            raise ValueError("an editorial program binding must be committed with a direction")
        if self.script is not None and self.direction is None and not self.script.direction_version_id:
            raise ValueError("a script requires a new or existing direction version")
        return self


__all__ = [
    "AttributionCarrier",
    "AttributionPlan",
    "AudienceHypothesis",
    "BreakdownDraft",
    "BreakdownSaveRequest",
    "CarrierKind",
    "ClaimBasis",
    "ContentRouteKind",
    "ContentObjective",
    "ContentWorkAppend",
    "ContentWorkCreate",
    "CreativeElement",
    "DifferenceBasis",
    "DifferentiationHypothesis",
    "DirectionDraft",
    "direction_decision_digest",
    "direction_decision_payload",
    "EditorialProgramDraft",
    "EditorialSpine",
    "editorial_program_decision_digest",
    "editorial_program_decision_payload",
    "EntryRoute",
    "MissionDecision",
    "OutcomeGoal",
    "ProductionTranslation",
    "ScriptDraft",
    "ScriptBoundaryReceipt",
    "SCRIPT_BOUNDARY_VERIFIER_VERSION",
    "script_boundary_verifier_input_digest",
    "script_boundary_verifier_input_payload",
    "script_decision_digest",
    "script_decision_payload",
    "SemanticCausalRoute",
    "semantic_causal_route_digest",
    "StoryEngineSeed",
    "StoryMode",
    "TimeHorizon",
    "validate_direction_program_binding",
    "validate_script_direction_binding",
    "WriterBrainRequest",
]
