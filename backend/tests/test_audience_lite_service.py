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
                evidence_level="account_history_conditioned",
                mechanism_hypotheses=[
                    {
                        "layer": "attention_prediction",
                        "claim": "目标人群识别到相关问题后更可能继续观看",
                        "predicted_signal": "首段继续观看比例提高",
                        "failure_condition": "目标人群无法复述内容承诺",
                    }
                ],
                distribution_assumptions=["平台分发给相关兴趣人群"],
                uncertainty="历史数据不能保证本次结果",
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
    assert "not viral guarantees" in result.warnings[0]


@pytest.mark.asyncio
async def test_lite_service_marks_first_pilot_as_an_unmeasured_cold_start_hypothesis() -> None:
    example = HLLMCreatorAdapter().build_example(
        history=[],
        audience_profile={"hypothesis": "可能关心真实开店过程的人"},
        creator_profile={"voice": ["具体"]},
        target={"content_id": "pilot-1", "title": "选址第一天", "description": "记录选址判断"},
    )
    request = AudiencePreflightRequest(example=example, variant_count=1)
    app = create_audience_lite_app(generator=_FakeGenerator())
    provider = HLLMCreatorHTTPProvider(
        base_url="http://localhost:9128",
        transport=httpx.ASGITransport(app=app),
    )

    result = await provider.preflight(request)

    assert result.audience_basis == "cold_start_hypothesis"
    assert result.variants[0].evidence_level == "unmeasured_hypothesis"
    assert "unmeasured cold-start hypotheses" in result.warnings[0]


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
        assert "不得用多巴胺" in payload["messages"][0]["content"]
        content = {
            "variants": [
                {
                    "text": "候选甲",
                    "mechanism_hypotheses": [
                        {
                            "layer": "attention_prediction",
                            "claim": "反差与目标问题相关时更可能获得继续观看",
                            "predicted_signal": "首段继续观看比例提高",
                            "failure_condition": "观众无法复述承诺",
                        }
                    ],
                    "distribution_assumptions": ["分发到相关兴趣人群"],
                    "uncertainty": "没有本次发布结果",
                    "tags": ["反差"],
                },
                {
                    "text": "候选乙",
                    "mechanism_hypotheses": [
                        {
                            "layer": "social_transmission",
                            "claim": "内容对明确接收者有用时更可能被分享",
                            "predicted_signal": "分享行为增加",
                            "failure_condition": "分享没有出现且评论认为不适用",
                        }
                    ],
                    "distribution_assumptions": ["获得足够有效曝光"],
                    "uncertainty": "分享动机仍需发布验证",
                },
            ]
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]},
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
    assert all(variant.evidence_level == "account_history_conditioned" for variant in variants)
