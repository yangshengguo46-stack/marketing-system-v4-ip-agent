"""Replaceable provider contract for Personal-IP audience preflight.

The same contract is used by today's lightweight implementation and a future
full HLLM-Creator service. Provider requests contain model features only; local
owner, subject and platform-account identifiers remain in DeerFlow.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from deerflow.personal_ip.hllm_creator import HLLM_CREATOR_FIELDS

AUDIENCE_PREFLIGHT_CONTRACT_VERSION = "personal-ip-audience-preflight-v1"
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
        if profile.get("audience_basis") != "aggregate_account_cohort":
            raise ValueError("audience preflight requires aggregate_account_cohort data")
        if str(copied.get("response") or "").strip():
            raise ValueError("audience preflight examples cannot contain a training response")
        self._example = copied
        self.variant_count = variant_count

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract_version": AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
            "audience_basis": "aggregate_account_cohort",
            "variant_count": self.variant_count,
            "example": json.loads(_canonical_json(self._example)),
        }

    @property
    def request_digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_payload()).encode("utf-8")).hexdigest()


class AudienceCreativeVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=12_000)
    match_score: float | None = Field(default=None, ge=0, le=1)
    tags: list[str] = Field(default_factory=list, max_length=32)


class AudiencePreflightResult(BaseModel):
    """Versioned model receipt suitable for a later immutable preflight row."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(
        default=AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
        pattern=r"^personal-ip-audience-preflight-v1$",
    )
    provider: str = Field(min_length=1, max_length=80)
    model_version: str = Field(min_length=1, max_length=160)
    algorithm_version: str = Field(min_length=1, max_length=160)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    audience_basis: str = Field(pattern=r"^aggregate_account_cohort$")
    audience_embedding_ref: str | None = Field(default=None, max_length=512)
    variants: list[AudienceCreativeVariant] = Field(min_length=1, max_length=8)
    warnings: list[str] = Field(default_factory=list, max_length=32)


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
        return result
