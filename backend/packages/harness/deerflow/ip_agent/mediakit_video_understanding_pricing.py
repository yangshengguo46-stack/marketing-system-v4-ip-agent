"""Auditable public-tariff math for the fixed MediaKit Chat model.

MediaKit does not add a separate media-processing charge for Video
Understanding Chat.  The underlying Ark model is billed from the provider's
reported prompt and completion token totals.  This module deliberately
computes only a public-list-price estimate; it is neither a provider quote nor
an invoice receipt.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VIDEO_UNDERSTANDING_PRICE_CONTRACT_VERSION = "ark-public-token-tariff-estimate-v1"
VIDEO_UNDERSTANDING_PRICE_DOCUMENT_ID = "volcengine-doc-82379-1544106"
VIDEO_UNDERSTANDING_PRICE_DOCUMENT_UPDATED_AT = "2026-08-01T00:24:32+08:00"
VIDEO_UNDERSTANDING_PRICE_VERSION = "doubao-seed-2.0-pro-online-standard-2026-08-01"
VIDEO_UNDERSTANDING_PRICE_SNAPSHOT_SHA256 = "cc8fd13b848cf6b71e1e873b0f88beea521ba83035dc2e68fd137abf249a1f7e"
VIDEO_UNDERSTANDING_MODEL_ID = "doubao-seed-2-0-pro-260215"
VIDEO_UNDERSTANDING_MODEL_FAMILY = "doubao-seed-2.0-pro"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArkPublicTokenTariffEstimate(_StrictModel):
    """Secret-free list-price estimate derived from provider token usage."""

    contract_version: Literal["ark-public-token-tariff-estimate-v1"]
    document_id: Literal["volcengine-doc-82379-1544106"]
    document_updated_at: Literal["2026-08-01T00:24:32+08:00"]
    price_version: Literal["doubao-seed-2.0-pro-online-standard-2026-08-01"]
    price_snapshot_sha256: Literal["cc8fd13b848cf6b71e1e873b0f88beea521ba83035dc2e68fd137abf249a1f7e"]
    model_id: Literal["doubao-seed-2-0-pro-260215"]
    model_family: Literal["doubao-seed-2.0-pro"]
    billing_mode: Literal["online_standard"]
    service_tier: Literal["default"]
    price_status: Literal["public_tariff_estimate"]
    currency: Literal["CNY"]
    prompt_tokens: int = Field(strict=True, ge=0, le=262_144)
    completion_tokens: int = Field(strict=True, ge=0)
    input_tier_lower_exclusive_tokens: int | None
    input_tier_upper_inclusive_tokens: Literal[32768, 131072, 262144]
    input_rate_cny_per_million_tokens: Literal["3.2", "4.8", "9.6"]
    output_rate_cny_per_million_tokens: Literal["16.0", "24.0", "48.0"]
    amount_micros: int = Field(strict=True, ge=0)
    cache_assumption: Literal["all_prompt_tokens_charged_as_uncached_input"]
    reasoning_accounting: Literal["included_once_in_provider_completion_tokens"]

    @model_validator(mode="after")
    def validate_tier(self) -> ArkPublicTokenTariffEstimate:
        expected = _price_tier(self.prompt_tokens)
        observed = (
            self.input_tier_lower_exclusive_tokens,
            self.input_tier_upper_inclusive_tokens,
            self.input_rate_cny_per_million_tokens,
            self.output_rate_cny_per_million_tokens,
        )
        if observed != expected:
            raise ValueError("Ark public tariff tier does not match prompt token count")
        return self


def _price_tier(
    prompt_tokens: int,
) -> tuple[int | None, Literal[32768, 131072, 262144], Literal["3.2", "4.8", "9.6"], Literal["16.0", "24.0", "48.0"]]:
    if prompt_tokens <= 32_768:
        return None, 32_768, "3.2", "16.0"
    if prompt_tokens <= 131_072:
        return 32_768, 131_072, "4.8", "24.0"
    if prompt_tokens <= 262_144:
        return 131_072, 262_144, "9.6", "48.0"
    raise ValueError("prompt token count exceeds the published model tier")


def estimate_video_understanding_public_tariff(
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> ArkPublicTokenTariffEstimate:
    """Calculate a conservative list-price estimate in micro-CNY.

    The current fixed request does not opt into context caching, so every
    prompt token is charged at the uncached-input rate.  Provider
    ``completion_tokens`` already contains reasoning tokens; callers must not
    add the nested reasoning count again.
    """

    if isinstance(prompt_tokens, bool) or not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        raise ValueError("prompt_tokens must be a non-negative integer")
    if isinstance(completion_tokens, bool) or not isinstance(completion_tokens, int) or completion_tokens < 0:
        raise ValueError("completion_tokens must be a non-negative integer")
    lower, upper, input_rate, output_rate = _price_tier(prompt_tokens)
    amount_micros = int((Decimal(prompt_tokens) * Decimal(input_rate) + Decimal(completion_tokens) * Decimal(output_rate)).to_integral_value(rounding=ROUND_CEILING))
    return ArkPublicTokenTariffEstimate(
        contract_version=VIDEO_UNDERSTANDING_PRICE_CONTRACT_VERSION,
        document_id=VIDEO_UNDERSTANDING_PRICE_DOCUMENT_ID,
        document_updated_at=VIDEO_UNDERSTANDING_PRICE_DOCUMENT_UPDATED_AT,
        price_version=VIDEO_UNDERSTANDING_PRICE_VERSION,
        price_snapshot_sha256=VIDEO_UNDERSTANDING_PRICE_SNAPSHOT_SHA256,
        model_id=VIDEO_UNDERSTANDING_MODEL_ID,
        model_family=VIDEO_UNDERSTANDING_MODEL_FAMILY,
        billing_mode="online_standard",
        service_tier="default",
        price_status="public_tariff_estimate",
        currency="CNY",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        input_tier_lower_exclusive_tokens=lower,
        input_tier_upper_inclusive_tokens=upper,
        input_rate_cny_per_million_tokens=input_rate,
        output_rate_cny_per_million_tokens=output_rate,
        amount_micros=amount_micros,
        cache_assumption="all_prompt_tokens_charged_as_uncached_input",
        reasoning_accounting="included_once_in_provider_completion_tokens",
    )


__all__ = [
    "VIDEO_UNDERSTANDING_MODEL_FAMILY",
    "VIDEO_UNDERSTANDING_MODEL_ID",
    "VIDEO_UNDERSTANDING_PRICE_CONTRACT_VERSION",
    "VIDEO_UNDERSTANDING_PRICE_DOCUMENT_ID",
    "VIDEO_UNDERSTANDING_PRICE_DOCUMENT_UPDATED_AT",
    "VIDEO_UNDERSTANDING_PRICE_SNAPSHOT_SHA256",
    "VIDEO_UNDERSTANDING_PRICE_VERSION",
    "ArkPublicTokenTariffEstimate",
    "estimate_video_understanding_public_tariff",
]
