from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBJECT_PATH = REPO_ROOT / "product/research/ip-agent/python/mediakit_video_strategy.py"
SPEC = importlib.util.spec_from_file_location("research_mediakit_video_strategy", SUBJECT_PATH)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = subject
SPEC.loader.exec_module(subject)

VIDEO_REF = "https://media.example.test/exact.mp4?sig=ABC%2F123&expires=1770000000"
CLIENT_TOKEN = "owner-call-fixed-token:001"
API_KEY = "private-mediakit-api-key"
TASK_ID = "amk-tool-video-understand-router-private-001"
SUBMIT_REQUEST_ID = "submit-request-private-001"
QUERY_REQUEST_ID = "query-request-private-001"


def _model_content(*, summary: str = "视频按时间展示街道、室内和天台画面。") -> str:
    return json.dumps(
        {
            "summary": summary,
            "segments": [
                {
                    "start_seconds": 0.0,
                    "end_seconds": 30.0,
                    "visual_observation": "固定远景中可见街道、车辆和行人。",
                    "audio_observation": "可清楚听到城市环境声，节奏平稳，无可辨歌词或对白。",
                    "editing_observation": "开场为固定远景，未观察到转场。",
                    "certainty": "observed",
                },
                {
                    "start_seconds": 30.0,
                    "end_seconds": 120.0,
                    "visual_observation": "画面依次切换到室内跟拍和天台远景。",
                    "audio_observation": None,
                    "editing_observation": "约 30 秒发生硬切，后段镜头由跟拍转为固定远景。",
                    "certainty": "uncertain",
                },
            ],
            "uncertainties": ["后半段音频不够清楚，未记录歌词或对白。"],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _submission_response() -> dict[str, Any]:
    return {
        "success": True,
        "task_id": TASK_ID,
        "request_id": SUBMIT_REQUEST_ID,
    }


def _completed_response(*, content: str | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "task_id": TASK_ID,
        "task_type": "video-understand-router",
        "status": "completed",
        "result": {
            "duration": 120.0,
            "contents": [content if content is not None else _model_content()],
            "token_usage": {
                "input_tokens": 900,
                "output_tokens": 100,
                "total_tokens": 1000,
            },
        },
        "request_id": QUERY_REQUEST_ID,
        "created_at": 1777291767,
        "finished_at": 1777291851,
        "expires_at": 1777464650,
    }


def _serialized(value: Any) -> str:
    return json.dumps(value.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def test_request_projection_is_exact_fixed_and_shared_by_hash_builder() -> None:
    projection = subject.build_video_strategy_request_projection(
        video_ref=VIDEO_REF,
        client_token=CLIENT_TOKEN,
    )

    assert projection["method"] == "POST"
    assert projection["provider_tool_name"] == "video-understand-router"
    assert projection["automatic_retries"] == 0
    assert projection["callback_url_mode"] == "omitted"
    assert set(projection["body"]) == {
        "video_urls",
        "prompt",
        "level",
        "scene",
        "manual_option",
        "client_token",
    }
    assert projection["body"]["video_urls"] == [VIDEO_REF]
    assert projection["body"]["client_token"] == CLIENT_TOKEN
    assert projection["body"]["level"] == "Quality"
    assert projection["body"]["scene"] == "editing"
    assert projection["body"]["manual_option"] == {"need_audio": True}
    assert "callback_url" not in projection["body"]
    assert "prefer_models" not in projection["body"]
    assert "prefer_endpoints" not in projection["body"]
    assert "按时间顺序" in projection["body"]["prompt"]
    assert "URL、任务 ID 或请求 ID" in projection["body"]["prompt"]

    proposed = subject.build_video_strategy_request_sha256(
        video_ref=VIDEO_REF,
        client_token=CLIENT_TOKEN,
    )
    executed = subject.build_video_strategy_request_sha256(
        video_ref=VIDEO_REF,
        client_token=CLIENT_TOKEN,
    )
    assert proposed == executed
    assert proposed != subject.build_video_strategy_request_sha256(
        video_ref=VIDEO_REF,
        client_token=CLIENT_TOKEN,
        level="Balanced",
    )


@pytest.mark.asyncio
async def test_submit_once_uses_authorization_only_and_returns_hash_only_public_observation() -> None:
    requests: list[httpx.Request] = []
    expected_sha = subject.build_video_strategy_request_sha256(
        video_ref=VIDEO_REF,
        client_token=CLIENT_TOKEN,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == subject.MEDIAKIT_VIDEO_STRATEGY_ENDPOINT
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert API_KEY not in request.content.decode("utf-8")
        assert (
            json.loads(request.content)
            == subject.build_video_strategy_request_projection(
                video_ref=VIDEO_REF,
                client_token=CLIENT_TOKEN,
            )["body"]
        )
        assert request.content not in {b"", b"{}", b"null"}
        return httpx.Response(200, json=_submission_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        handle = await subject.submit_video_strategy_once(
            video_ref=VIDEO_REF,
            client_token=CLIENT_TOKEN,
            api_key=API_KEY,
            expected_request_sha256=expected_sha,
            client=client,
        )

    assert len(requests) == 1
    assert handle.task_id == TASK_ID
    assert handle.submission.request_sha256 == expected_sha
    public = _serialized(handle.submission)
    for raw_value in (VIDEO_REF, CLIENT_TOKEN, API_KEY, TASK_ID, SUBMIT_REQUEST_ID):
        assert raw_value not in public
        assert raw_value not in repr(handle)
    assert handle.submission.provider_input_ref_sha256 == subject._sha256_text(VIDEO_REF)
    assert handle.submission.provider_task_id_sha256 == subject._sha256_text(TASK_ID)
    assert handle.submission.provider_request_id_sha256 == subject._sha256_text(SUBMIT_REQUEST_ID)


@pytest.mark.asyncio
async def test_completed_query_is_one_get_and_separates_three_cost_boundaries() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        if request.method == "POST":
            return httpx.Response(200, json=_submission_response())
        assert request.method == "GET"
        assert request.content == b""
        assert str(request.url) == f"{subject.MEDIAKIT_TASK_ENDPOINT_PREFIX}/{TASK_ID}"
        return httpx.Response(200, json=_completed_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        handle = await subject.submit_video_strategy_once(
            video_ref=VIDEO_REF,
            client_token=CLIENT_TOKEN,
            api_key=API_KEY,
            client=client,
        )
        observation = await subject.query_video_strategy_task_once(
            handle=handle,
            api_key=API_KEY,
            client=client,
        )

    assert methods == ["POST", "GET"]
    assert observation.status == "completed"
    assert observation.authority_status == "research_observation_not_inference_authority"
    assert observation.inference_authority is False
    assert observation.content.summary.startswith("视频按时间")
    assert observation.token_usage.total_tokens == 1000
    assert observation.coverage.collection_status == "partial"

    mediakit = observation.cost.mediakit_preprocessing_public_tariff
    assert mediakit.rate_cny_per_input_minute == "0.01"
    assert mediakit.input_duration_seconds == 120.0
    assert mediakit.estimated_amount_micros == 20_000
    assert mediakit.price_status == "public_tariff_estimate_not_actual_bill"

    ark = observation.cost.ark_token_tariff
    assert ark.input_tokens == 900
    assert ark.output_tokens == 100
    assert ark.estimated_amount_micros is None
    assert ark.price_status == "unavailable_aggregate_input_tokens_lack_audio_split"
    assert ark.selected_model_attestation == "not_returned_by_task_result"

    actual = observation.cost.actual_bill
    assert actual.bill_status == "not_returned_by_task_api"
    assert actual.mediakit_amount_micros is None
    assert actual.ark_amount_micros is None
    assert actual.total_amount_micros is None

    public = _serialized(observation)
    for raw_value in (
        VIDEO_REF,
        CLIENT_TOKEN,
        API_KEY,
        TASK_ID,
        SUBMIT_REQUEST_ID,
        QUERY_REQUEST_ID,
        subject.MEDIAKIT_VIDEO_STRATEGY_ENDPOINT,
        subject.MEDIAKIT_TASK_ENDPOINT_PREFIX,
    ):
        assert raw_value not in public


@pytest.mark.asyncio
async def test_running_query_does_not_poll_or_invent_result() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.method == "POST":
            return httpx.Response(200, json=_submission_response())
        return httpx.Response(
            200,
            json={
                "success": True,
                "task_id": TASK_ID,
                "status": "running",
                "created_at": 1777291767,
                "request_id": QUERY_REQUEST_ID,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        handle = await subject.submit_video_strategy_once(
            video_ref=VIDEO_REF,
            client_token=CLIENT_TOKEN,
            api_key=API_KEY,
            client=client,
        )
        observation = await subject.query_video_strategy_task_once(
            handle=handle,
            api_key=API_KEY,
            client=client,
        )

    assert calls == 2
    assert observation.status == "running"
    assert observation.content is None
    assert observation.token_usage is None
    assert observation.duration_seconds is None
    assert observation.cost is None


@pytest.mark.asyncio
async def test_failed_task_returns_only_hashed_error_observation() -> None:
    raw_error = {
        "code": "DownloadFailed",
        "type": "TaskError",
        "message": f"failed to download {VIDEO_REF}",
        "param": "video_urls[0]",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=_submission_response())
        return httpx.Response(
            200,
            json={
                "success": True,
                "task_id": TASK_ID,
                "status": "failed",
                "error": raw_error,
                "created_at": 1777291767,
                "finished_at": 1777291851,
                "request_id": QUERY_REQUEST_ID,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        handle = await subject.submit_video_strategy_once(
            video_ref=VIDEO_REF,
            client_token=CLIENT_TOKEN,
            api_key=API_KEY,
            client=client,
        )
        observation = await subject.query_video_strategy_task_once(
            handle=handle,
            api_key=API_KEY,
            client=client,
        )

    assert observation.status == "failed"
    assert observation.provider_error_sha256 == subject._canonical_sha256(raw_error)
    assert observation.content is None
    assert VIDEO_REF not in _serialized(observation)


@pytest.mark.asyncio
async def test_provider_content_with_raw_url_or_identifier_is_rejected() -> None:
    leaking_content = _model_content(summary=f"provider echoed {VIDEO_REF} and {TASK_ID}")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json=_submission_response())
        return httpx.Response(200, json=_completed_response(content=leaking_content))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        handle = await subject.submit_video_strategy_once(
            video_ref=VIDEO_REF,
            client_token=CLIENT_TOKEN,
            api_key=API_KEY,
            client=client,
        )
        with pytest.raises(subject.MediaKitVideoStrategyError) as captured:
            await subject.query_video_strategy_task_once(
                handle=handle,
                api_key=API_KEY,
                client=client,
            )

    assert captured.value.code == "INVALID_PROVIDER_CONTENT_SCHEMA"
    assert VIDEO_REF not in str(captured.value)
    assert TASK_ID not in str(captured.value)


@pytest.mark.asyncio
async def test_transport_failure_is_bounded_and_never_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            503,
            json={
                "success": False,
                "request_id": SUBMIT_REQUEST_ID,
                "error": {
                    "code": "ServiceUnavailable",
                    "message": f"do not expose {VIDEO_REF} or {API_KEY}",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitVideoStrategyError) as captured:
            await subject.submit_video_strategy_once(
                video_ref=VIDEO_REF,
                client_token=CLIENT_TOKEN,
                api_key=API_KEY,
                client=client,
            )

    assert calls == 1
    assert captured.value.code == "PROVIDER_SERVICEUNAVAILABLE"
    assert VIDEO_REF not in str(captured.value)
    assert API_KEY not in str(captured.value)
    assert SUBMIT_REQUEST_ID not in str(captured.value)


@pytest.mark.asyncio
async def test_declared_oversized_response_is_rejected_without_retry() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            content=b"{}",
            headers={"Content-Length": str(512 * 1024 + 1)},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitVideoStrategyError) as captured:
            await subject.submit_video_strategy_once(
                video_ref=VIDEO_REF,
                client_token=CLIENT_TOKEN,
                api_key=API_KEY,
                client=client,
            )

    assert calls == 1
    assert captured.value.code == "RESPONSE_TOO_LARGE"


def test_public_tariff_estimate_is_not_ark_price_or_actual_bill() -> None:
    estimate = subject.estimate_mediakit_preprocessing_public_tariff(duration_seconds=3600)
    assert estimate.estimated_amount_micros == 600_000
    assert estimate.rate_cny_per_input_minute == "0.01"
    assert "actual_bill" in estimate.price_status
