from __future__ import annotations

import json

import httpx
import pytest

from deerflow.personal_ip.audience_provider import (
    AudiencePreflightRequest,
    HLLMCreatorHTTPProvider,
)
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter


def _example() -> dict:
    return HLLMCreatorAdapter().build_example(
        history=[
            {
                "content_id": "content-1",
                "published_at": "2026-07-20T08:00:00Z",
                "platform": "douyin",
                "title": "本地智能体",
                "content_type": "short_video",
                "metrics": {"views": 1200, "likes": 80},
            }
        ],
        audience_profile={"cohort_label": "个人 IP 创作者"},
        creator_profile={"name": "创作者本人", "voice": ["直接"]},
        target={"content_id": "draft-1", "title": "新内容", "description": "介绍 HLLM-Lite"},
    )


def test_preflight_request_contains_no_owner_or_account_identity() -> None:
    request = AudiencePreflightRequest(example=_example(), variant_count=3)

    payload = request.to_payload()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["contract_version"] == "personal-ip-audience-preflight-v1"
    assert payload["variant_count"] == 3
    assert payload["audience_basis"] == "aggregate_account_cohort"
    assert "owner_user_id" not in serialized
    assert "account_id" not in serialized
    assert len(request.request_digest) == 64


@pytest.mark.asyncio
async def test_http_provider_returns_verified_structured_receipt() -> None:
    request = AudiencePreflightRequest(example=_example(), variant_count=2)

    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.headers["Idempotency-Key"] == request.request_digest
        assert http_request.headers["Authorization"] == "Bearer secret-token"
        payload = json.loads(http_request.content)
        assert payload == request.to_payload()
        return httpx.Response(
            200,
            json={
                "contract_version": "personal-ip-audience-preflight-v1",
                "provider": "hllm-lite",
                "model_version": "lite-2026-07-21",
                "algorithm_version": "hllm-inspired-v1",
                "request_digest": request.request_digest,
                "audience_basis": "aggregate_account_cohort",
                "audience_embedding_ref": "audience-emb-42",
                "variants": [
                    {"variant_id": "v1", "text": "版本一", "match_score": 0.81},
                    {"variant_id": "v2", "text": "版本二", "match_score": 0.74},
                ],
                "warnings": ["aggregate proxy"],
            },
        )

    provider = HLLMCreatorHTTPProvider(
        base_url="http://127.0.0.1:9128",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.preflight(request)

    assert result.provider == "hllm-lite"
    assert result.request_digest == request.request_digest
    assert [variant.text for variant in result.variants] == ["版本一", "版本二"]
    assert result.variants[0].match_score == 0.81


@pytest.mark.asyncio
async def test_http_provider_rejects_a_mismatched_receipt_digest() -> None:
    request = AudiencePreflightRequest(example=_example())

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "contract_version": "personal-ip-audience-preflight-v1",
                "provider": "hllm-creator-cloud",
                "model_version": "full-1",
                "algorithm_version": "upstream-864f172",
                "request_digest": "0" * 64,
                "audience_basis": "aggregate_account_cohort",
                "variants": [{"variant_id": "v1", "text": "结果", "match_score": 0.5}],
            },
        )

    provider = HLLMCreatorHTTPProvider(
        base_url="http://localhost:9128",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeError, match="receipt does not match"):
        await provider.preflight(request)


def test_http_provider_requires_tls_for_non_local_services() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        HLLMCreatorHTTPProvider(base_url="http://model.example.com")
