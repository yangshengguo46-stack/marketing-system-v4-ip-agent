"""FastAPI sidecar implementing the shared Personal-IP audience contract."""

from __future__ import annotations

import hmac
import os
from typing import Any, Protocol

from fastapi import FastAPI, Header, HTTPException

from app.audience_lite.doubao import AudienceLiteGenerationError, DoubaoAudienceGenerator
from deerflow.personal_ip.audience_provider import (
    AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
    AudienceCreativeVariant,
    AudiencePreflightRequest,
    AudiencePreflightResult,
)


class AudienceCreativeGenerator(Protocol):
    provider: str
    model_version: str
    algorithm_version: str

    async def generate(self, request: AudiencePreflightRequest) -> list[AudienceCreativeVariant]: ...


def create_audience_lite_app(
    *,
    generator: AudienceCreativeGenerator | None = None,
    token: str | None = None,
) -> FastAPI:
    active_generator = generator or DoubaoAudienceGenerator.from_env()
    expected_token = str(token if token is not None else os.getenv("PERSONAL_IP_AUDIENCE_TOKEN", "")).strip()
    service = FastAPI(title="HLLM-Lite Audience Provider", version="0.1.0")

    @service.get("/health")
    async def health() -> dict[str, Any]:
        configured = getattr(active_generator, "configured", True)
        return {
            "status": "healthy" if configured else "unconfigured",
            "provider": active_generator.provider,
            "model_version": active_generator.model_version,
            "contract_version": AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
        }

    @service.post("/v1/preflight", response_model=AudiencePreflightResult)
    async def preflight(
        body: dict[str, Any],
        idempotency_key: str = Header(alias="Idempotency-Key"),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> AudiencePreflightResult:
        if expected_token:
            supplied = str(authorization or "")
            expected = f"Bearer {expected_token}"
            if not hmac.compare_digest(supplied, expected):
                raise HTTPException(status_code=401, detail="Invalid audience provider token")
        if body.get("contract_version") != AUDIENCE_PREFLIGHT_CONTRACT_VERSION:
            raise HTTPException(status_code=422, detail="Unsupported audience preflight contract")
        try:
            request = AudiencePreflightRequest(
                example=body.get("example"),
                variant_count=body.get("variant_count", 3),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not hmac.compare_digest(idempotency_key, request.request_digest):
            raise HTTPException(status_code=409, detail="Idempotency digest does not match request")
        try:
            variants = await active_generator.generate(request)
        except AudienceLiteGenerationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if request.audience_basis == "cold_start_hypothesis":
            variants = [variant.model_copy(update={"evidence_level": "unmeasured_hypothesis"}) for variant in variants]
        return AudiencePreflightResult(
            provider=active_generator.provider,
            model_version=active_generator.model_version,
            algorithm_version=active_generator.algorithm_version,
            request_digest=request.request_digest,
            audience_basis=request.audience_basis,
            variants=variants,
            warnings=[
                ("HLLM-Lite emits account-history-conditioned hypotheses" if request.audience_basis == "aggregate_account_cohort" else "HLLM-Lite emits unmeasured cold-start hypotheses") + ", not viral guarantees or a learned match score."
            ],
        )

    return service


app = create_audience_lite_app()
