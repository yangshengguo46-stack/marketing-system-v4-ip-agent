"""Replaceable provider contract for Personal-IP audience preflight.

The same contract is used by today's lightweight implementation and a future
full HLLM-Creator service. Provider requests contain model features only; local
owner, subject and platform-account identifiers remain in DeerFlow.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deerflow.personal_ip.hllm_creator import HLLM_CREATOR_FIELDS

AUDIENCE_PREFLIGHT_CONTRACT_VERSION = "personal-ip-audience-preflight-v2"
AUDIENCE_BASES = {"cold_start_hypothesis", "aggregate_account_cohort"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_LOCAL_IDENTITY_KEYS = {
    "account_id",
    "account_ids",
    "owner_user_id",
    "subject_id",
    "subject_ids",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _reject_local_identity(value: Any, *, field: str) -> None:
    if isinstance(value, dict):
        normalized = {str(key).strip().lower().replace("-", "_") for key in value}
        leaked = sorted(normalized & _LOCAL_IDENTITY_KEYS)
        if leaked:
            raise ValueError(f"{field} contains local portfolio identity: {', '.join(leaked)}")
        for key, item in value.items():
            _reject_local_identity(item, field=f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_local_identity(item, field=f"{field}[{index}]")


class AudiencePreflightRequest:
    """Immutable model request derived from an HLLM-Creator example."""

    def __init__(self, *, example: dict[str, Any], variant_count: int = 3) -> None:
        if not isinstance(example, dict) or set(example) != set(HLLM_CREATOR_FIELDS):
            raise ValueError("example must use the exact HLLM-Creator field contract")
        if not 1 <= variant_count <= 8:
            raise ValueError("variant_count must be between 1 and 8")
        copied = {field: json.loads(_canonical_json(example[field])) for field in HLLM_CREATOR_FIELDS}
        _reject_local_identity(copied, field="example")
        try:
            profile = json.loads(copied["user_profile"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("example.user_profile must contain JSON") from exc
        _reject_local_identity(profile, field="example.user_profile")
        audience_basis = str(profile.get("audience_basis") or "").strip()
        if audience_basis not in AUDIENCE_BASES:
            raise ValueError("audience preflight requires cold_start_hypothesis or aggregate_account_cohort data")
        if str(copied.get("response") or "").strip():
            raise ValueError("audience preflight examples cannot contain a training response")
        self._example = copied
        self.audience_basis = audience_basis
        self.variant_count = variant_count

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract_version": AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
            "audience_basis": self.audience_basis,
            "variant_count": self.variant_count,
            "example": json.loads(_canonical_json(self._example)),
        }

    @property
    def request_digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_payload()).encode("utf-8")).hexdigest()


class AudienceMechanismHypothesis(BaseModel):
    """One observable, falsifiable content mechanism—not a neural claim."""

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
    claim: str = Field(min_length=1, max_length=2000)
    predicted_signal: str = Field(min_length=1, max_length=1000)
    failure_condition: str = Field(min_length=1, max_length=1000)

    @field_validator("claim")
    @classmethod
    def validate_claim(cls, value: str) -> str:
        text = " ".join(value.split())
        unsupported = [term for term in ("多巴胺", "镜像神经元", "蔡格尼克") if term in text]
        if unsupported:
            raise ValueError("mechanism claims must describe observable audience behavior instead of unsupported causal shorthand")
        if any(phrase in text for phrase in ("必爆", "一定会火", "一定能火", "保证完播", "保证涨粉")):
            raise ValueError("mechanism claims cannot guarantee a viral outcome")
        return text


class AudienceCreativeVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=12_000)
    match_score: float | None = Field(default=None, ge=0, le=1)
    evidence_level: Literal[
        "unmeasured_hypothesis",
        "market_referenced_hypothesis",
        "account_history_conditioned",
        "promoted_rule",
    ]
    mechanism_hypotheses: list[AudienceMechanismHypothesis] = Field(min_length=1, max_length=8)
    distribution_assumptions: list[str] = Field(min_length=1, max_length=8)
    uncertainty: str = Field(min_length=1, max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=32)


class AudiencePreflightResult(BaseModel):
    """Versioned model receipt suitable for a later immutable preflight row."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(
        default=AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
        pattern=r"^personal-ip-audience-preflight-v2$",
    )
    provider: str = Field(min_length=1, max_length=80)
    model_version: str = Field(min_length=1, max_length=160)
    algorithm_version: str = Field(min_length=1, max_length=160)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    audience_basis: Literal["cold_start_hypothesis", "aggregate_account_cohort"]
    audience_embedding_ref: str | None = Field(default=None, max_length=512)
    variants: list[AudienceCreativeVariant] = Field(min_length=1, max_length=8)
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_evidence_basis(self) -> AudiencePreflightResult:
        if self.audience_basis == "cold_start_hypothesis":
            inflated = [variant.variant_id for variant in self.variants if variant.evidence_level in {"account_history_conditioned", "promoted_rule"}]
            if inflated:
                raise ValueError("cold-start variants cannot claim account-history or promoted-rule evidence")
        return self


class HLLMCreatorHTTPProvider:
    """HTTP bridge shared by HLLM-Lite and future full HLLM deployments."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        normalized = str(base_url or "").strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("HLLM provider base_url must be an absolute HTTP URL")
        if parsed.scheme != "https" and parsed.hostname not in _LOCAL_HOSTS:
            raise ValueError("remote HLLM providers require HTTPS")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = normalized
        self.token = str(token or "").strip() or None
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def preflight(self, request: AudiencePreflightRequest) -> AudiencePreflightResult:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Idempotency-Key": request.request_digest,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=self.transport,
        ) as client:
            response = await client.post("/v1/preflight", json=request.to_payload())
            response.raise_for_status()
        result = AudiencePreflightResult.model_validate(response.json())
        if result.request_digest != request.request_digest:
            raise RuntimeError("HLLM provider receipt does not match the request")
        if result.audience_basis != request.audience_basis:
            raise RuntimeError("HLLM provider receipt uses a different audience basis")
        return result
