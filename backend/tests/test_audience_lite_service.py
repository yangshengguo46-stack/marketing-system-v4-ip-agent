from __future__ import annotations

import json

import httpx
import pytest

from app.audience_lite.app import create_audience_lite_app
from app.audience_lite.doubao import DoubaoAudienceGenerator
from deerflow.personal_ip.audience_provider import (
    AudienceCreativeVariant,
    AudiencePreflightRequest,
    HLLMCreatorHTTPProvider,
)
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter


class _FakeGenerator:
    provider = "hllm-lite"
    model_version = "fake-doubao"
    algorithm_version = "profile-conditioned-v0"

    async def generate(self, request: AudiencePreflightRequest) -> list[AudienceCreativeVariant]:
        return [
            AudienceCreativeVariant(
                variant_id=f"v{index + 1}",
                text=f"创意 {index + 1}",
                tags=["fake"],
            )
            for index in range(request.variant_count)
        ]


def _request() -> AudiencePreflightRequest:
    example = HLLMCreatorAdapter().build_example(
        history=[
            {
                "content_id": "published-1",
                "published_at": "2026-07-20T08:00:00Z",
                "platform": "douyin",
                "title": "旧内容",
                "content_type": "short_video",
                "metrics": {"views": 900, "likes": 60},
            }
        ],
        audience_profile={"cohort_label": "本地智能体关注者"},
        creator_profile={"voice": ["直接"]},
        target={"content_id": "draft-1", "title": "新内容", "description": "说明"},
    )
    return AudiencePreflightRequest(example=example, variant_count=2)


@pytest.mark.asyncio
async def test_lite_service_implements_the_shared_provider_contract() -> None:
    app = create_audience_lite_app(generator=_FakeGenerator(), token="service-token")
    provider = HLLMCreatorHTTPProvider(
        base_url="http://localhost:9128",
        token="service-token",
        transport=httpx.ASGITransport(app=app),
    )

    result = await provider.preflight(_request())

    assert result.provider == "hllm-lite"
    assert result.model_version == "fake-doubao"
    assert len(result.variants) == 2
    assert result.variants[0].match_score is None
    assert "does not emit a learned match score" in result.warnings[0]


@pytest.mark.asyncio
async def test_lite_service_rejects_an_invalid_token() -> None:
    app = create_audience_lite_app(generator=_FakeGenerator(), token="service-token")
    transport = httpx.ASGITransport(app=app)
    request = _request()

    async with httpx.AsyncClient(base_url="http://localhost:9128", transport=transport) as client:
        response = await client.post(
            "/v1/preflight",
            headers={"Idempotency-Key": request.request_digest, "Authorization": "Bearer wrong"},
            json=request.to_payload(),
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_lite_service_rejects_an_incorrect_idempotency_digest() -> None:
    app = create_audience_lite_app(generator=_FakeGenerator())
    transport = httpx.ASGITransport(app=app)
    request = _request()

    async with httpx.AsyncClient(base_url="http://localhost:9128", transport=transport) as client:
        response = await client.post(
            "/v1/preflight",
            headers={"Idempotency-Key": "0" * 64},
            json=request.to_payload(),
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_doubao_generator_uses_ark_json_generation_without_fake_scores() -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.url.path == "/api/v3/chat/completions"
        assert http_request.headers["Authorization"] == "Bearer ark-key"
        payload = json.loads(http_request.content)
        assert payload["model"] == "doubao-test"
        assert payload["response_format"] == {"type": "json_object"}
        assert "匿名受众画像" in payload["messages"][0]["content"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '```json\n{"variants":[{"text":"候选甲","tags":["反差"]},{"text":"候选乙"}]}\n```'}}]},
        )

    generator = DoubaoAudienceGenerator(
        api_key="ark-key",
        model="doubao-test",
        base_url="http://localhost:9999/api/v3",
        transport=httpx.MockTransport(handler),
    )

    variants = await generator.generate(_request())

    assert [variant.text for variant in variants] == ["候选甲", "候选乙"]
    assert variants[0].tags == ["反差"]
    assert all(variant.match_score is None for variant in variants)
