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

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

EntryRoute = Literal["zero_start", "benchmark"]
StoryMode = Literal["factual", "fictional", "hybrid"]
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


class DirectionDraft(_Contract):
    """The decision brain's chosen route, not the story or shooting plan."""

    premise: ShortText
    audience_situation: ShortText
    core_tension: ShortText
    content_promise: ShortText
    creative_route: ShortText
    rationale: NonEmptyText
    truth_mode: StoryMode
    business_relevance: str = Field(default="", max_length=4_000)
    claim_basis: list[ClaimBasis] = Field(default_factory=list, max_length=200)
    breakdown_version_ids: list[str] = Field(default_factory=list, max_length=100)
    parent_direction_version_id: str | None = Field(default=None, max_length=64)


class StoryEngineSeed(_Contract):
    """The complete Chinese, industry-neutral input to a fiction-only story engine."""

    recurring_conflict: ShortText
    desire_a: ShortText
    desire_b: ShortText
    relationship_at_stake: ShortText
    causal_pattern: ShortText
    tone: str = Field(default="", max_length=500)

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


class ProductionTranslation(_Contract):
    """Shooting/form constraints applied only after the story is locked."""

    form: Literal["spoken", "scene", "mixed"] = "mixed"
    narrator: str = Field(default="", max_length=500)
    setting: str = Field(default="", max_length=1_000)
    constraints: list[ShortText] = Field(default_factory=list, max_length=50)
    delivery_notes: list[ShortText] = Field(default_factory=list, max_length=50)


class WriterBrainRequest(_Contract):
    """One decision-brain handoff to the isolated script writer."""

    content_work_id: str | None = Field(
        default=None,
        max_length=64,
        description=("Existing work to version. If its BreakdownVersion was already saved, reuse this work and list that breakdown id in direction.breakdown_version_ids; do not resend the same breakdown."),
    )
    subject_id: str | None = Field(default=None, max_length=64)
    work_title: ShortText
    entry_route: EntryRoute | None = None
    objective: ContentObjective | None = None
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
        if self.direction.truth_mode == "factual":
            if self.story_engine_seed is not None:
                raise ValueError("factual writing does not use a fiction story-engine seed")
        elif self.story_engine_seed is None:
            raise ValueError("fictional and hybrid writing require a story_engine_seed")
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
    breakdown: BreakdownDraft | None = None
    direction: DirectionDraft | None = None
    script: ScriptDraft | None = None

    @model_validator(mode="after")
    def validate_entry_route_and_dependencies(self) -> Self:
        if self.entry_route == "benchmark" and self.breakdown is None:
            raise ValueError("benchmark entry requires a breakdown")
        if self.script is not None and self.direction is None and not self.script.direction_version_id:
            raise ValueError("a script requires a new or existing direction version")
        return self


class ContentWorkAppend(_Contract):
    idempotency_key: str = Field(min_length=1, max_length=256)
    breakdown: BreakdownDraft | None = None
    direction: DirectionDraft | None = None
    script: ScriptDraft | None = None

    @model_validator(mode="after")
    def validate_nonempty_commit(self) -> Self:
        if self.breakdown is None and self.direction is None and self.script is None:
            raise ValueError("a content commit must contain at least one version")
        if self.script is not None and self.direction is None and not self.script.direction_version_id:
            raise ValueError("a script requires a new or existing direction version")
        return self


__all__ = [
    "BreakdownDraft",
    "BreakdownSaveRequest",
    "ClaimBasis",
    "ContentObjective",
    "ContentWorkAppend",
    "ContentWorkCreate",
    "CreativeElement",
    "DirectionDraft",
    "EntryRoute",
    "ProductionTranslation",
    "ScriptDraft",
    "StoryEngineSeed",
    "StoryMode",
    "WriterBrainRequest",
]
