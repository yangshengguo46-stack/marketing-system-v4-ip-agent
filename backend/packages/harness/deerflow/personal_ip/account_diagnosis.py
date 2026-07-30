"""Evidence-bound account diagnosis for the eight Personal-IP platforms.

Content is the primary object of diagnosis. Platform mechanics are treated as
observable eligibility constraints and distribution amplifiers, never as a
substitute for content quality or as a source of invented ranking weights.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION = "personal-ip-account-diagnostic-context-v2"
ACCOUNT_DIAGNOSIS_CONTRACT_VERSION = "personal-ip-account-diagnosis-v2"
PERSISTENT_RESTRICTION_MIN_DURATION = timedelta(days=7)
STRUCTURAL_EVIDENCE_MAX_AGE = timedelta(hours=24)
CONTENT_EVIDENCE_MAX_AGE = timedelta(days=30)

CONTENT_MECHANISM_LAYERS = (
    "processing_access",
    "attention_prediction",
    "emotion_identity",
    "narrative_consumption",
    "social_transmission",
    "behavior_conversion",
    "platform_distribution",
)
FUNNEL_STAGES = ("reach", "trust", "intent", "conversion")
IP_ASSET_OUTCOME_DOMAINS = ("influence", "behavioral", "economic")
STRUCTURAL_ISSUE_CODES = {
    "persistent_recommendation_ineligibility",
    "legacy_audience_positioning_lock",
    "identity_business_conflict",
    "unrecoverable_compliance_history",
}
_INTENT_METRIC_MARKERS = (
    "lead",
    "inquiry",
    "dm",
    "message",
    "contact",
    "profile_click",
    "link_click",
)
_CONVERSION_METRIC_MARKERS = (
    "conversion",
    "order",
    "revenue",
    "purchase",
    "sale",
    "booking",
    "checkout",
    "payment",
    "paid",
    "gmv",
)
_UNSUPPORTED_CAUSAL_TERMS = ("多巴胺", "镜像神经元", "蔡格尼克")
_ABSOLUTE_OUTCOME_PHRASES = ("必爆", "一定会火", "一定能火", "保证完播", "保证涨粉")
_NON_IDENTITY_QUERY_KEYS = {
    "feature",
    "from",
    "from_page",
    "from_source",
    "is_from_webapp",
    "ref",
    "refer",
    "referrer",
    "sec_uid",
    "sender_device",
    "sender_web_id",
    "share",
    "share_id",
    "share_medium",
    "share_source",
    "share_token",
    "si",
    "source",
    "spm",
    "timestamp",
    "ts",
    "xsec_source",
    "xsec_token",
}
_PLATFORM_CERTAINTY_PATTERNS = (
    re.compile(
        r"\beligibility\s+(?:guarantees|ensures)\s+"
        r"(?:distribution|reach|recommendation)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beligible\s+(?:means|guarantees|ensures)\s+"
        r"(?:distribution|reach|recommendation)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beligibility\s+is\s+(?:a\s+)?guarantee\s+of\s+"
        r"(?:distribution|reach|recommendation)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\beligible\s+accounts?\s+are\s+guaranteed\s+"
        r"(?:distribution|reach|recommendation)\b",
        re.IGNORECASE,
    ),
    re.compile(r"推荐资格(?:就)?(?:保证|确保|等于|意味着一定)"),
    re.compile(r"有推荐资格(?:就)?一定"),
    re.compile(r"有推荐资格(?:就)?会获得稳定分发"),
)
_HOSTILE_DIAGNOSIS_PATTERNS = (
    re.compile(r"你(?:就是|只是在|纯属)?自嗨"),
    re.compile(r"你只顾自我感动"),
    re.compile(r"作品.{0,12}只是自我感觉"),
    re.compile(r"孤芳自赏"),
    re.compile(r"自我陶醉"),
    re.compile(r"自以为是"),
    re.compile(r"\byour content is (?:crap|garbage|shit)\b", re.IGNORECASE),
    re.compile(r"\byou are delusional\b", re.IGNORECASE),
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _compact_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _compact_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _default_objective_system() -> dict[str, Any]:
    """Return a conservative cold-start objective system, never a binary mode."""

    return {
        "asset_mechanism": "influence",
        "influence_goals": [],
        "behavioral_goals": [],
        "economic_goals": [],
        "time_horizon": {},
        "priority_order": list(IP_ASSET_OUTCOME_DOMAINS),
        "guardrails": [],
        "not_optimizing_now": [],
        "source": "cold_start_unmeasured",
    }


def _canonical_content_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            return value
        query = urlencode(
            sorted(
                (key, item)
                for key, item in parse_qsl(
                    parts.query,
                    keep_blank_values=True,
                )
                if key.lower() not in _NON_IDENTITY_QUERY_KEYS and not key.lower().startswith("utm_")
            ),
            doseq=True,
        )
        path = parts.path.rstrip("/") or "/"
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                path,
                query,
                "",
            )
        )
    except ValueError:
        return value


def _record_identity(record: Mapping[str, Any]) -> str | None:
    for field in (
        "post_id",
        "content_id",
        "item_id",
        "video_id",
        "note_id",
        "tweet_id",
        "external_post_id",
        "id",
        "url",
    ):
        value = str(record.get(field) or "").strip()
        if value:
            return _canonical_content_url(value) if field == "url" else value
    return None


def _unique_record_count(value: Any) -> int:
    return len({identity for record in _compact_records(value) if (identity := _record_identity(record)) is not None})


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _validate_text_claim(value: str) -> str:
    text = _clean_text(value)
    if any(pattern.search(text) for pattern in _PLATFORM_CERTAINTY_PATTERNS):
        raise ValueError("recommendation eligibility is a constraint, not a guarantee of distribution")
    if any(pattern.search(text) for pattern in _HOSTILE_DIAGNOSIS_PATTERNS):
        raise ValueError("state the operating gap without insulting or psychologically judging the user")
    return text


class DiagnosisEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "metric_observation",
        "platform_observation",
        "publish_receipt",
        "retrospective",
        "strategy_version",
        "differentiation_version",
    ]
    id: str = Field(min_length=1, max_length=128)


class MechanismAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: Literal[
        "processing_access",
        "attention_prediction",
        "emotion_identity",
        "narrative_consumption",
        "social_transmission",
        "behavior_conversion",
        "platform_distribution",
    ]
    state: Literal["pass", "fail", "unmeasured"]
    claim: str = Field(min_length=1, max_length=1200)
    evidence_refs: list[DiagnosisEvidenceRef] = Field(default_factory=list, max_length=30)

    @field_validator("claim")
    @classmethod
    def validate_claim(cls, value: str) -> str:
        text = _validate_text_claim(value)
        if any(term in text for term in _UNSUPPORTED_CAUSAL_TERMS):
            raise ValueError("use observable audience behavior instead of unsupported causal shorthand")
        if any(phrase in text for phrase in _ABSOLUTE_OUTCOME_PHRASES):
            raise ValueError("a content mechanism cannot guarantee a viral outcome")
        return text

    @model_validator(mode="after")
    def require_evidence_for_measured_state(self) -> MechanismAssessment:
        if self.state == "unmeasured" and self.evidence_refs:
            raise ValueError("unmeasured mechanisms cannot cite evidence as a measured conclusion")
        if self.state != "unmeasured" and not self.evidence_refs:
            raise ValueError("measured mechanisms require immutable evidence")
        return self


class FunnelAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["reach", "trust", "intent", "conversion"]
    state: Literal["pass", "fail", "unmeasured"]
    claim: str = Field(min_length=1, max_length=1200)
    evidence_refs: list[DiagnosisEvidenceRef] = Field(default_factory=list, max_length=30)

    @field_validator("claim")
    @classmethod
    def normalize_claim(cls, value: str) -> str:
        return _validate_text_claim(value)

    @model_validator(mode="after")
    def require_evidence_for_measured_state(self) -> FunnelAssessment:
        if self.state == "unmeasured" and self.evidence_refs:
            raise ValueError("unmeasured funnel stages cannot cite evidence as a measured conclusion")
        if self.state != "unmeasured" and not self.evidence_refs:
            raise ValueError("measured funnel stages require immutable evidence")
        return self


class AccountStructureAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_eligibility: Literal["eligible", "restricted", "unknown"]
    audience_positioning_fit: Literal["aligned", "misaligned", "unknown"]
    identity_business_fit: Literal["aligned", "conflicted", "unknown"]
    structural_issue_codes: list[
        Literal[
            "persistent_recommendation_ineligibility",
            "legacy_audience_positioning_lock",
            "identity_business_conflict",
            "unrecoverable_compliance_history",
        ]
    ] = Field(default_factory=list, max_length=4)
    evidence_refs: list[DiagnosisEvidenceRef] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_structure_evidence(self) -> AccountStructureAssessment:
        if self.structural_issue_codes and not self.evidence_refs:
            raise ValueError("account structural issues require immutable evidence")
        if self.recommendation_eligibility == "restricted" and not self.evidence_refs:
            raise ValueError("recommendation restriction requires immutable evidence")
        if "persistent_recommendation_ineligibility" in self.structural_issue_codes and self.recommendation_eligibility != "restricted":
            raise ValueError("persistent recommendation ineligibility requires a restricted eligibility finding")
        if "legacy_audience_positioning_lock" in self.structural_issue_codes and self.audience_positioning_fit != "misaligned":
            raise ValueError("legacy audience-positioning lock requires a misaligned audience finding")
        if "identity_business_conflict" in self.structural_issue_codes and self.identity_business_fit != "conflicted":
            raise ValueError("identity/business conflict requires a conflicted identity finding")
        return self


class AccountDiagnosisExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis: str = Field(min_length=1, max_length=1200)
    content_changes: list[str] = Field(min_length=1, max_length=8)
    predicted_signals: list[str] = Field(min_length=1, max_length=8)
    failure_condition: str = Field(min_length=1, max_length=1200)
    minimum_post_count: int = Field(ge=3, le=12)
    observation_window: str = Field(min_length=1, max_length=500)
    keep_platform_constant: Literal[True] = True

    @field_validator(
        "hypothesis",
        "failure_condition",
        "observation_window",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        text = _validate_text_claim(value)
        if any(phrase in text for phrase in _ABSOLUTE_OUTCOME_PHRASES):
            raise ValueError("the next experiment cannot guarantee a viral outcome")
        return text

    @field_validator("content_changes", "predicted_signals")
    @classmethod
    def normalize_items(cls, value: list[str]) -> list[str]:
        normalized = [_validate_text_claim(item) for item in value]
        if any(not item for item in normalized):
            raise ValueError("experiment items cannot be empty")
        return normalized


class AccountDiagnosisAssessment(BaseModel):
    """Model judgment that is compiled only against server-loaded evidence."""

    model_config = ConfigDict(extra="forbid")

    platform_role: Literal["constraint_and_amplifier"]
    mechanisms: list[MechanismAssessment] = Field(min_length=7, max_length=7)
    funnel: list[FunnelAssessment] = Field(min_length=4, max_length=4)
    account_structure: AccountStructureAssessment
    primary_failure_domain: Literal[
        "content",
        "platform_constraint",
        "account_structure",
        "insufficient_evidence",
    ]
    decision: Literal[
        "insufficient_evidence",
        "continue_current_account",
        "adjust_and_retest",
        "start_new_account",
    ]
    classification: Literal["operating_content", "self_entertainment", "unproven"]
    confidence: float = Field(ge=0, le=1)
    rationale: list[str] = Field(min_length=1, max_length=8)
    next_experiment: AccountDiagnosisExperiment

    @field_validator("rationale")
    @classmethod
    def normalize_rationale(cls, value: list[str]) -> list[str]:
        normalized = [_validate_text_claim(item) for item in value]
        if any(not item for item in normalized):
            raise ValueError("rationale items cannot be empty")
        return normalized

    @model_validator(mode="after")
    def validate_complete_dimensions(self) -> AccountDiagnosisAssessment:
        mechanism_layers = [item.layer for item in self.mechanisms]
        if set(mechanism_layers) != set(CONTENT_MECHANISM_LAYERS) or len(set(mechanism_layers)) != 7:
            raise ValueError("mechanisms must cover each content mechanism layer exactly once")
        funnel_stages = [item.stage for item in self.funnel]
        if set(funnel_stages) != set(FUNNEL_STAGES) or len(set(funnel_stages)) != 4:
            raise ValueError("funnel must cover reach, trust, intent and conversion exactly once")
        return self


class PersonalIPAccountDiagnosticContextService:
    """Build a compact diagnosis context from authenticated owner repositories."""

    def __init__(
        self,
        *,
        accounts: Any,
        metrics: Any,
        platform_observations: Any,
        publish_receipts: Any,
        retrospectives: Any,
        brand: Any | None = None,
        differentiation: Any | None = None,
    ) -> None:
        self._accounts = accounts
        self._metrics = metrics
        self._platform_observations = platform_observations
        self._publish_receipts = publish_receipts
        self._retrospectives = retrospectives
        self._brand = brand
        self._differentiation = differentiation

    async def build(self, *, owner_user_id: str, account_id: str) -> dict[str, Any]:
        diagnostic_time = datetime.now(UTC)
        account = await self._accounts.get(account_id, owner_user_id=owner_user_id)
        if account is None:
            raise ValueError("Personal-IP account not found")

        receipts = await self._publish_receipts.list(
            owner_user_id,
            account_id=account_id,
            limit=100,
        )
        metrics = await self._metrics.list(
            owner_user_id,
            account_id=account_id,
            limit=200,
        )
        observations = await self._platform_observations.list(
            owner_user_id,
            account_id=account_id,
            limit=200,
        )
        retrospectives = await self._retrospectives.list(
            owner_user_id,
            account_id=account_id,
            limit=100,
        )

        subject_id = account.get("subject_id")
        strategy = None
        differentiation = None
        asset_observations: list[dict[str, Any]] = []
        if self._brand is not None and subject_id:
            strategy = await self._brand.get_latest_strategy(
                str(subject_id),
                owner_user_id=owner_user_id,
            )
        if self._differentiation is not None and subject_id:
            differentiation_version_id = str(strategy.get("differentiation_version_id") or "").strip() if isinstance(strategy, Mapping) else ""
            if differentiation_version_id:
                differentiation = await self._differentiation.get_version(
                    differentiation_version_id,
                    owner_user_id=owner_user_id,
                )
            else:
                differentiation = await self._differentiation.get_latest(
                    str(subject_id),
                    owner_user_id=owner_user_id,
                )
            if hasattr(self._differentiation, "list_observations"):
                asset_observations = await self._differentiation.list_observations(
                    owner_user_id,
                    subject_id=str(subject_id),
                    limit=200,
                )

        published = [item for item in receipts if item.get("status") == "published"]
        published_receipt_ids = {str(item["id"]) for item in published if item.get("id")}
        usable_metrics = [
            item
            for item in metrics
            if item.get("status") in {"observed", "partial"}
            and (item.get("scope") != "post" or str(item.get("receipt_id") or "") in published_receipt_ids)
            and _evidence_is_within_age(
                item,
                as_of=diagnostic_time,
                max_age=CONTENT_EVIDENCE_MAX_AGE,
            )
        ]
        latest_by_dataset: dict[str, dict[str, Any]] = {}
        for item in observations:
            dataset = str(item.get("dataset") or "")
            if dataset and dataset not in latest_by_dataset:
                latest_by_dataset[dataset] = item

        metric_receipt_ids = {str(item["receipt_id"]) for item in usable_metrics if item.get("scope") == "post" and item.get("receipt_id")}
        inventory_observation = _fresh_dataset_observation(
            latest_by_dataset.get("content_inventory"),
            as_of=diagnostic_time,
            max_age=CONTENT_EVIDENCE_MAX_AGE,
        )
        performance_observation = _fresh_dataset_observation(
            latest_by_dataset.get("content_metrics"),
            as_of=diagnostic_time,
            max_age=CONTENT_EVIDENCE_MAX_AGE,
        )
        inventory_count = _unique_record_count(inventory_observation.get("records"))
        performance_count = _unique_record_count(performance_observation.get("records"))
        known_post_count = max(
            len(published),
            inventory_count,
        )
        evaluated_post_count = max(
            len(metric_receipt_ids),
            performance_count,
        )
        minimum_post_count = 3
        metric_names = sorted({str(name) for item in usable_metrics for name in _compact_mapping(item.get("metrics"))})
        content_performance_available = bool(usable_metrics) or _dataset_available(performance_observation)
        metric_rows_with_intent = [item for item in usable_metrics if _has_intent_metric(_compact_mapping(item.get("metrics")))]
        metric_rows_with_conversion = [item for item in usable_metrics if _has_conversion_metric(_compact_mapping(item.get("metrics")))]
        complete_post_intent_rows = [
            item
            for item in metric_rows_with_intent
            if _complete_post_commercial_metric(
                item,
                published_receipt_ids=published_receipt_ids,
            )
        ]
        complete_post_conversion_rows = [
            item
            for item in metric_rows_with_conversion
            if _complete_post_commercial_metric(
                item,
                published_receipt_ids=published_receipt_ids,
            )
        ]
        intent_metric_receipt_ids = {str(item["receipt_id"]) for item in complete_post_intent_rows}
        conversion_metric_receipt_ids = {str(item["receipt_id"]) for item in complete_post_conversion_rows}
        complete_account_commercial_rows = [
            item for item in usable_metrics if _complete_account_window_metric(item) and _has_intent_metric(_compact_mapping(item.get("metrics"))) and _has_conversion_metric(_compact_mapping(item.get("metrics")))
        ]
        conversions_observation = _fresh_dataset_observation(
            latest_by_dataset.get("conversions"),
            as_of=diagnostic_time,
            max_age=CONTENT_EVIDENCE_MAX_AGE,
        )
        conversion_summary = _compact_mapping(conversions_observation.get("summary"))
        observation_intent_state = _normalize_signal_state(conversion_summary.get("intent_state"))
        observation_conversion_state = _normalize_signal_state(conversion_summary.get("conversion_state"))
        per_post_commercial_coverage = evaluated_post_count >= minimum_post_count and len(intent_metric_receipt_ids) >= evaluated_post_count and len(conversion_metric_receipt_ids) >= evaluated_post_count
        account_window_commercial_coverage = bool(complete_account_commercial_rows)
        observation_commercial_coverage = (
            conversions_observation.get("status") == "observed"
            and _coverage_declares_complete(_compact_mapping(conversions_observation.get("coverage")))
            and observation_intent_state != "unmeasured"
            and observation_conversion_state != "unmeasured"
        )
        commercial_outcomes_available = per_post_commercial_coverage or account_window_commercial_coverage or observation_commercial_coverage
        observed_intent_state = (
            _metric_signal_state(
                [
                    *complete_post_intent_rows,
                    *complete_account_commercial_rows,
                ],
                _INTENT_METRIC_MARKERS,
            )
            if per_post_commercial_coverage or account_window_commercial_coverage
            else observation_intent_state
        )
        observed_conversion_state = (
            _metric_signal_state(
                [
                    *complete_post_conversion_rows,
                    *complete_account_commercial_rows,
                ],
                _CONVERSION_METRIC_MARKERS,
            )
            if per_post_commercial_coverage or account_window_commercial_coverage
            else observation_conversion_state
        )
        compact_metrics = [
            {
                "id": str(item.get("id") or ""),
                "receipt_id": item.get("receipt_id"),
                "scope": item.get("scope"),
                "metric_mode": item.get("metric_mode"),
                "status": item.get("status"),
                "observed_at": item.get("observed_at"),
                "metrics": _compact_mapping(item.get("metrics")),
                "coverage": _compact_mapping(item.get("coverage")),
            }
            for item in usable_metrics[:80]
            if item.get("id")
        ]
        compact_observations = [
            {
                "id": str(item.get("id") or ""),
                "dataset": str(item.get("dataset") or ""),
                "status": item.get("status"),
                "source": item.get("source"),
                "observed_at": item.get("observed_at"),
                "record_count": len(_compact_records(item.get("records"))),
                "summary": _compact_mapping(item.get("summary")),
                "coverage": _compact_mapping(item.get("coverage")),
                "is_latest_for_dataset": latest_by_dataset.get(
                    str(item.get("dataset") or ""),
                    {},
                ).get("id")
                == item.get("id"),
            }
            for item in observations[:80]
            if item.get("id")
        ]
        compact_retrospectives = [
            {
                "id": str(item.get("id") or ""),
                "publish_receipt_id": item.get("publish_receipt_id"),
                "status": item.get("status"),
                "comparison_state": item.get("comparison_state"),
                "training_status": _compact_mapping(item.get("training_eligibility")).get("status"),
                "created_at": item.get("created_at"),
            }
            for item in retrospectives[:50]
            if item.get("id")
        ]
        compact_receipts = [
            {
                "id": str(item.get("id") or ""),
                "status": item.get("status"),
                "published_at": item.get("published_at"),
                "external_post_id_present": bool(item.get("external_post_id")),
            }
            for item in receipts[:100]
            if item.get("id")
        ]

        evidence_index = [
            *[{"kind": "metric_observation", "id": item["id"]} for item in compact_metrics],
            *[{"kind": "platform_observation", "id": item["id"]} for item in compact_observations],
            *[{"kind": "publish_receipt", "id": item["id"]} for item in compact_receipts],
            *[{"kind": "retrospective", "id": item["id"]} for item in compact_retrospectives],
        ]
        compact_asset_observations = [
            {
                "id": str(item.get("id") or ""),
                "differentiation_version_id": item.get("differentiation_version_id"),
                "observation_type": str(item.get("observation_type") or ""),
                "source": item.get("source"),
                "observed_at": item.get("observed_at"),
                "coverage_status": item.get("coverage_status"),
                "result": _compact_mapping(item.get("measures")).get("result"),
            }
            for item in asset_observations
            if item.get("id")
            and _evidence_is_within_age(
                item,
                as_of=diagnostic_time,
                max_age=CONTENT_EVIDENCE_MAX_AGE,
            )
        ]
        evidence_index.extend(
            {
                "kind": "ip_asset_observation",
                "id": item["id"],
            }
            for item in compact_asset_observations
        )
        if isinstance(strategy, Mapping) and strategy.get("id"):
            evidence_index.append({"kind": "strategy_version", "id": str(strategy["id"])})
        if isinstance(differentiation, Mapping) and differentiation.get("id"):
            evidence_index.append(
                {
                    "kind": "differentiation_version",
                    "id": str(differentiation["id"]),
                }
            )
        business_model = _compact_mapping(strategy.get("business_model")) if isinstance(strategy, Mapping) else {}
        objective_system = _compact_mapping(business_model.get("objective_system")) or _default_objective_system()
        asset_signal_states = _asset_signal_states(compact_asset_observations)
        context = {
            "contract_version": ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION,
            "generated_at": diagnostic_time.isoformat(),
            "account": {
                "id": str(account.get("id") or account_id),
                "subject_id": subject_id,
                "platform": str(account.get("platform") or ""),
                "display_name": str(account.get("display_name") or ""),
                "handle": account.get("handle"),
                "status": str(account.get("status") or ""),
            },
            "strategy": {
                "id": strategy.get("id") if isinstance(strategy, Mapping) else None,
                "stage": strategy.get("stage") if isinstance(strategy, Mapping) else None,
                "objective_system": objective_system,
                "source": "latest_strategy" if strategy else "product_default",
                "diagnosis_basis": {
                    "primary_goal": business_model.get("primary_goal"),
                    "buyer_segments": business_model.get("buyer_segments", []),
                    "primary_monetization_path": business_model.get(
                        "primary_monetization_path",
                        {},
                    ),
                    "positioning_candidates": (strategy.get("positioning_candidates", []) if isinstance(strategy, Mapping) else []),
                    "launch_package": (strategy.get("launch_package", {}) if isinstance(strategy, Mapping) else {}),
                },
            },
            "differentiation": {
                "id": (differentiation.get("id") if isinstance(differentiation, Mapping) else None),
                "status": (differentiation.get("status") if isinstance(differentiation, Mapping) else None),
                "decision_basis": {
                    "desired_influence": (_compact_mapping(differentiation.get("decision_context")).get("desired_influence", []) if isinstance(differentiation, Mapping) else []),
                    "desired_outcomes": (_compact_mapping(differentiation.get("decision_context")).get("desired_outcomes", []) if isinstance(differentiation, Mapping) else []),
                    "reason_to_choose": (_compact_mapping(differentiation.get("strategic_difference")).get("reason_to_choose") if isinstance(differentiation, Mapping) else None),
                    "sacrifice": (_compact_mapping(differentiation.get("strategic_difference")).get("sacrifice", []) if isinstance(differentiation, Mapping) else []),
                },
            },
            "sample": {
                "minimum_post_count": minimum_post_count,
                "published_post_count": len(published),
                "known_post_count": known_post_count,
                "metric_linked_post_count": len(metric_receipt_ids),
                "content_inventory_record_count": inventory_count,
                "content_performance_record_count": performance_count,
                "evaluated_post_count": evaluated_post_count,
                "decision_ready": (evaluated_post_count >= minimum_post_count and content_performance_available),
            },
            "coverage": {
                "account_health": _any_dataset_available(
                    latest_by_dataset,
                    "account_profile",
                    "dashboard",
                    "platform_receipts",
                ),
                "content_inventory": _dataset_available(inventory_observation),
                "content_performance": content_performance_available,
                "traffic_sources": _dataset_available(latest_by_dataset.get("traffic_sources")),
                "audience": _dataset_available(latest_by_dataset.get("audience_analytics")),
                "comments": _dataset_available(latest_by_dataset.get("comments")),
                "commercial_outcomes": commercial_outcomes_available,
            },
            "observed_signal_states": {
                "intent": observed_intent_state,
                "conversion": observed_conversion_state,
            },
            "asset_signal_states": asset_signal_states,
            "metric_names": metric_names,
            "metric_observations": compact_metrics,
            "platform_observations": compact_observations,
            "publish_receipts": compact_receipts,
            "retrospectives": compact_retrospectives,
            "asset_observations": compact_asset_observations,
            "evidence_index": evidence_index,
            "guardrails": {
                "content_is_primary": True,
                "platform_role": "constraint_and_amplifier",
                "low_reach_alone_can_trigger_new_account": False,
                "new_account_requires_structural_evidence": sorted(STRUCTURAL_ISSUE_CODES),
                "unpublished_platform_weights_are_unknown": True,
                "content_evidence_max_age_days": 30,
                "structural_evidence_max_age_hours": 24,
                "persistent_restriction_min_days": 7,
            },
        }
        context["context_digest"] = _digest(context)
        return context


def _evidence_is_within_age(
    observation: Mapping[str, Any],
    *,
    as_of: datetime,
    max_age: timedelta,
) -> bool:
    try:
        observed_at = _parse_observed_at(observation.get("observed_at"))
    except ValueError:
        return False
    age = as_of - observed_at
    return timedelta(minutes=-5) <= age <= max_age


def _fresh_dataset_observation(
    observation: Mapping[str, Any] | None,
    *,
    as_of: datetime,
    max_age: timedelta,
) -> dict[str, Any]:
    if not observation or not _evidence_is_within_age(
        observation,
        as_of=as_of,
        max_age=max_age,
    ):
        return {}
    return dict(observation)


def _dataset_available(item: Mapping[str, Any] | None) -> bool:
    return bool(item and item.get("status") in {"observed", "partial"})


def _coverage_declares_complete(coverage: Mapping[str, Any]) -> bool:
    return coverage.get("complete") is True or str(coverage.get("coverage_status") or "").lower() == "complete" or str(coverage.get("scope") or "").lower() == "complete"


def _complete_account_window_metric(item: Mapping[str, Any]) -> bool:
    return item.get("status") == "observed" and item.get("scope") == "account" and item.get("metric_mode") in {"window_total", "delta"} and _coverage_declares_complete(_compact_mapping(item.get("coverage")))


def _complete_post_commercial_metric(
    item: Mapping[str, Any],
    *,
    published_receipt_ids: set[str],
) -> bool:
    return item.get("status") == "observed" and item.get("scope") == "post" and str(item.get("receipt_id") or "") in published_receipt_ids and _coverage_declares_complete(_compact_mapping(item.get("coverage")))


def _has_metric_marker(
    metrics: Mapping[str, Any],
    markers: Sequence[str],
) -> bool:
    return any(marker in str(metric_name).lower() for metric_name in metrics for marker in markers)


def _has_intent_metric(metrics: Mapping[str, Any]) -> bool:
    return _has_metric_marker(metrics, _INTENT_METRIC_MARKERS)


def _has_conversion_metric(metrics: Mapping[str, Any]) -> bool:
    return _has_metric_marker(metrics, _CONVERSION_METRIC_MARKERS)


def _normalize_signal_state(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "absent": "fail",
        "failed": "fail",
        "none": "fail",
        "zero": "fail",
        "present": "pass",
        "observed": "pass",
        "positive": "pass",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in {"pass", "fail"} else "unmeasured"


def _asset_signal_states(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    domain_types = {
        "influence": {"recognition", "trust", "extension"},
        "behavioral": {"intent", "adoption"},
        "economic": {"conversion", "economic"},
    }
    result: dict[str, str] = {}
    for domain, observation_types in domain_types.items():
        outcomes = [str(item.get("result") or "").strip() for item in observations if item.get("coverage_status") == "complete" and item.get("observation_type") in observation_types]
        if "supports" in outcomes:
            result[domain] = "pass"
        elif outcomes and all(outcome == "contradicts" for outcome in outcomes):
            result[domain] = "fail"
        else:
            result[domain] = "unmeasured"
    return result


def _combine_signal_states(*states: Any) -> str:
    normalized = [_normalize_signal_state(state) for state in states]
    if "pass" in normalized:
        return "pass"
    measured = [state for state in normalized if state != "unmeasured"]
    return "fail" if measured and all(state == "fail" for state in measured) else "unmeasured"


def _metric_signal_state(
    rows: Sequence[Mapping[str, Any]],
    markers: Sequence[str],
) -> str:
    values: list[float] = []
    for row in rows:
        for metric_name, raw_value in _compact_mapping(row.get("metrics")).items():
            if not any(marker in str(metric_name).lower() for marker in markers):
                continue
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                continue
            values.append(float(raw_value))
    if not values:
        return "unmeasured"
    return "pass" if any(value > 0 for value in values) else "fail"


def _any_dataset_available(
    datasets: Mapping[str, Mapping[str, Any]],
    *names: str,
) -> bool:
    return any(_dataset_available(datasets.get(name)) for name in names)


def _normalized_summary_state(
    observation: Mapping[str, Any],
    field: str,
) -> str:
    summary = _compact_mapping(observation.get("summary"))
    return str(summary.get(field) or "").strip().lower()


def _platform_observation_map(
    context: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in _compact_records(context.get("platform_observations")) if item.get("id")}


def _parse_observed_at(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("structural platform evidence requires ISO-8601 observed_at") from exc
    if parsed.tzinfo is None:
        raise ValueError("structural platform evidence observed_at requires a timezone")
    return parsed.astimezone(UTC)


def _observation_is_fresh(
    context: Mapping[str, Any],
    observation: Mapping[str, Any],
) -> bool:
    diagnostic_time = _parse_observed_at(context.get("generated_at"))
    observed_at = _parse_observed_at(observation.get("observed_at"))
    age = diagnostic_time - observed_at
    return timedelta(minutes=-5) <= age <= STRUCTURAL_EVIDENCE_MAX_AGE


def _validate_structural_proof(
    *,
    context: Mapping[str, Any],
    assessment: AccountDiagnosisAssessment,
    structural_codes: set[str],
) -> None:
    refs = assessment.account_structure.evidence_refs
    platform_ref_ids = {ref.id for ref in refs if ref.kind == "platform_observation"}
    observations_by_id = _platform_observation_map(context)
    cited_observations = [observations_by_id[ref_id] for ref_id in platform_ref_ids if ref_id in observations_by_id]
    if len(cited_observations) != len(platform_ref_ids):
        raise ValueError("new-account evidence must include the cited platform observation payloads")
    strategy_ref_ids = {ref.id for ref in refs if ref.kind == "strategy_version"}
    current_strategy_id = str(_compact_mapping(context.get("strategy")).get("id") or "")

    if "persistent_recommendation_ineligibility" in structural_codes:
        account_status_datasets = {
            "account_profile",
            "dashboard",
            "platform_receipts",
        }
        all_account_status_observations = [item for item in observations_by_id.values() if item.get("dataset") in account_status_datasets and item.get("status") in {"observed", "partial"}]
        if not all_account_status_observations:
            raise ValueError("persistent recommendation ineligibility requires current account-status evidence")
        restricted = [
            item
            for item in cited_observations
            if item.get("dataset") in account_status_datasets
            and item.get("status") in {"observed", "partial"}
            and _normalized_summary_state(
                item,
                "recommendation_eligibility",
            )
            in {"restricted", "ineligible", "not_eligible"}
        ]
        observed_times = {_parse_observed_at(item.get("observed_at")) for item in restricted}
        if len(observed_times) < 2:
            raise ValueError("persistent recommendation ineligibility requires restricted observations from at least two collection times")
        if max(observed_times) - min(observed_times) < PERSISTENT_RESTRICTION_MIN_DURATION:
            raise ValueError("persistent recommendation ineligibility requires at least seven days of observed restriction")
        restriction_reason_ids = {_normalized_summary_state(item, "restriction_reason_id") for item in restricted}
        if "" in restriction_reason_ids or len(restriction_reason_ids) != 1:
            raise ValueError("persistent recommendation ineligibility requires one stable restriction reason")
        latest_account_status = max(
            all_account_status_observations,
            key=lambda item: _parse_observed_at(item.get("observed_at")),
        )
        diagnostic_time = _parse_observed_at(context.get("generated_at"))
        latest_observed_at = _parse_observed_at(latest_account_status.get("observed_at"))
        evidence_age = diagnostic_time - latest_observed_at
        if evidence_age < timedelta(minutes=-5):
            raise ValueError("structural platform evidence cannot be dated in the future")
        if evidence_age > STRUCTURAL_EVIDENCE_MAX_AGE:
            raise ValueError("new-account decisions require account-status evidence observed within the last 24 hours")
        if str(latest_account_status.get("id") or "") not in platform_ref_ids or _normalized_summary_state(
            latest_account_status,
            "recommendation_eligibility",
        ) not in {"restricted", "ineligible", "not_eligible"}:
            raise ValueError("the latest account status must still show recommendation ineligibility")
        if (
            _normalized_summary_state(
                latest_account_status,
                "restriction_reason_id",
            )
            not in restriction_reason_ids
        ):
            raise ValueError("the latest restriction must match the persistent restriction reason")
        if (
            _normalized_summary_state(
                latest_account_status,
                "remediation_status",
            )
            in {
                "appeal_denied",
                "exhausted",
                "failed",
                "not_recoverable",
            }
        ) is False:
            raise ValueError("persistent recommendation ineligibility requires evidence that repair or appeal was exhausted")

    if "legacy_audience_positioning_lock" in structural_codes:
        if not current_strategy_id or current_strategy_id not in strategy_ref_ids:
            raise ValueError("audience-positioning lock requires the current strategy version")
        if not any(item.get("dataset") == "audience_analytics" and _normalized_summary_state(item, "audience_positioning_fit") == "misaligned" and _observation_is_fresh(context, item) for item in cited_observations):
            raise ValueError("audience-positioning lock requires platform-observed audience mismatch")

    if "identity_business_conflict" in structural_codes:
        if not current_strategy_id or current_strategy_id not in strategy_ref_ids:
            raise ValueError("identity/business conflict requires the current strategy version")
        if not any(item.get("dataset") in {"account_profile", "content_inventory"} and _normalized_summary_state(item, "identity_business_fit") == "conflicted" and _observation_is_fresh(context, item) for item in cited_observations):
            raise ValueError("identity/business conflict requires platform-observed account evidence")

    if "unrecoverable_compliance_history" in structural_codes and not any(
        item.get("dataset") in {"account_profile", "dashboard", "platform_receipts"} and _normalized_summary_state(item, "compliance_recoverability") == "unrecoverable" and _observation_is_fresh(context, item) for item in cited_observations
    ):
        raise ValueError("unrecoverable compliance history requires an explicit platform status")


def compile_account_diagnosis(
    *,
    context: Mapping[str, Any],
    assessment: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a direct account decision while enforcing evidence gates."""

    if context.get("contract_version") != ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION:
        raise ValueError("unsupported account diagnostic context")
    parsed = AccountDiagnosisAssessment.model_validate(assessment)

    allowed_refs = {(str(item.get("kind")), str(item.get("id"))) for item in _compact_records(context.get("evidence_index"))}
    cited_refs = _assessment_evidence_refs(parsed)
    unknown_refs = sorted(cited_refs - allowed_refs)
    if unknown_refs:
        raise ValueError("diagnosis cites evidence outside the authenticated account context")

    sample = _compact_mapping(context.get("sample"))
    observed_signal_states = _compact_mapping(context.get("observed_signal_states"))
    decision_ready = bool(sample.get("decision_ready"))
    funnel = {item.stage: item.state for item in parsed.funnel}
    mechanism_states = {item.state for item in parsed.mechanisms}
    structural_codes = set(parsed.account_structure.structural_issue_codes)

    for stage in ("intent", "conversion"):
        observed_state = observed_signal_states.get(stage)
        if observed_state in {"pass", "fail"} and funnel[stage] != observed_state:
            raise ValueError(f"{stage} assessment must match the server-observed signal state")

    if decision_ready:
        if parsed.decision == "insufficient_evidence":
            raise ValueError("decision-ready account evidence requires a direct operating decision")
    else:
        if parsed.decision != "insufficient_evidence":
            raise ValueError("insufficient account evidence cannot support an operating account decision")
        if parsed.classification != "unproven":
            raise ValueError("insufficient account evidence must remain unproven")
        if parsed.primary_failure_domain != "insufficient_evidence":
            raise ValueError("insufficient account evidence must remain the primary failure domain")

    if parsed.decision == "continue_current_account":
        if not any(funnel[stage] == "pass" for stage in ("trust", "intent", "conversion")):
            raise ValueError("continuing unchanged requires a positive downstream signal")
        if "fail" in mechanism_states or any(state == "fail" for state in funnel.values()):
            raise ValueError("a measured content or funnel failure requires adjustment and retest")
        if parsed.account_structure.recommendation_eligibility == "restricted":
            raise ValueError("a recommendation-restricted account cannot continue unchanged")

    if parsed.decision == "adjust_and_retest":
        content_or_funnel_failed = "fail" in mechanism_states or any(state == "fail" for state in funnel.values())
        repairable_platform_constraint = parsed.account_structure.recommendation_eligibility == "restricted" and not structural_codes
        if not content_or_funnel_failed and not repairable_platform_constraint:
            raise ValueError("adjustment requires a measured content/funnel failure or repairable platform constraint")

    if parsed.decision == "start_new_account":
        if not structural_codes:
            raise ValueError("low reach or weak content alone cannot justify a new account")
        platform_structure_refs = {ref.id for ref in parsed.account_structure.evidence_refs if ref.kind == "platform_observation"}
        if not platform_structure_refs:
            raise ValueError("a new-account decision requires platform-observed structural evidence")
        _validate_structural_proof(
            context=context,
            assessment=parsed,
            structural_codes=structural_codes,
        )
        if parsed.primary_failure_domain != "account_structure":
            raise ValueError("a new-account decision must identify account structure as primary")

    if parsed.primary_failure_domain == "account_structure" and not structural_codes:
        raise ValueError("account structure cannot be primary without a structural issue")
    if parsed.primary_failure_domain == "platform_constraint" and parsed.account_structure.recommendation_eligibility != "restricted":
        raise ValueError("platform constraint can be primary only when recommendation eligibility is restricted")
    if parsed.primary_failure_domain == "content" and structural_codes:
        raise ValueError("content cannot be primary while unresolved structural issues are asserted")

    asset_states = _compact_mapping(context.get("asset_signal_states"))
    outcome_states = {
        "influence": _normalize_signal_state(asset_states.get("influence")),
        "behavioral": _combine_signal_states(
            asset_states.get("behavioral"),
            observed_signal_states.get("intent"),
        ),
        "economic": _combine_signal_states(
            asset_states.get("economic"),
            observed_signal_states.get("conversion"),
        ),
    }
    self_entertainment_proven = decision_ready and all(state == "fail" for state in outcome_states.values())
    if self_entertainment_proven and parsed.classification != "self_entertainment":
        raise ValueError("measured influence, behavioral and economic failure must not be softened to unproven")
    if parsed.classification == "self_entertainment":
        if not decision_ready or not all(state in {"pass", "fail"} for state in outcome_states.values()):
            raise ValueError("self-entertainment classification requires measured influence, behavioral and economic outcomes")
        if any(state != "fail" for state in outcome_states.values()):
            raise ValueError("self-entertainment requires influence, behavioral and economic outcomes all to have failed")
        if parsed.decision == "start_new_account" and not structural_codes:
            raise ValueError("self-entertainment alone never justifies starting a new account")

    if parsed.classification == "operating_content" and "pass" not in outcome_states.values():
        raise ValueError("operating content requires an observed influence, behavioral or economic signal")
    if parsed.classification == "unproven" and "pass" in outcome_states.values():
        raise ValueError("an observed influence, behavioral or economic signal cannot be relabeled unproven")

    contract = {
        "contract_version": ACCOUNT_DIAGNOSIS_CONTRACT_VERSION,
        "account_id": _compact_mapping(context.get("account")).get("id"),
        "platform": _compact_mapping(context.get("account")).get("platform"),
        "evidence_context_digest": context.get("context_digest"),
        "objective_system": _compact_mapping(_compact_mapping(context.get("strategy")).get("objective_system")),
        "outcome_states": outcome_states,
        "assessment": parsed.model_dump(mode="json"),
    }
    contract["diagnosis_digest"] = _digest(contract)
    return contract


def _assessment_evidence_refs(
    assessment: AccountDiagnosisAssessment,
) -> set[tuple[str, str]]:
    refs = {(ref.kind, ref.id) for item in assessment.mechanisms for ref in item.evidence_refs}
    refs.update((ref.kind, ref.id) for item in assessment.funnel for ref in item.evidence_refs)
    refs.update((ref.kind, ref.id) for ref in assessment.account_structure.evidence_refs)
    return refs
