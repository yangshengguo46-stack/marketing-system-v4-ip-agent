from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import Any

import httpx
import pytest

from deerflow.ip_agent import mediakit_remux_ingress as subject

NOW = datetime(2026, 8, 3, 8, 30, tzinfo=UTC)
MEDIAKIT_KEY = "mediakit-api-key-secret"
CLIENT_TOKEN = "remux-canary-deterministic-token-v1"
FILE_ID = "mediakit://file-secret-id"
TASK_ID = "task-secret-id"
UPLOAD_URL = "https://upload.tos-cn-beijing.volces.com/object?upload=secret"
RUNTIME_URL = "https://output.vod.volcvideo.com/remux.mp4?signature=runtime-secret"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "hostname",
    [
        "tob-upload-y-d.volcvod.com",
        "output.volcvideo.com",
        "upload.tos-cn-beijing.volces.com",
    ],
)
def test_known_official_media_hosts_are_accepted(hostname: str) -> None:
    assert subject._is_provider_host(hostname) is True


@pytest.mark.parametrize(
    "hostname",
    [
        "volcvod.com.evil.example",
        "fakevolcvod.com",
        "example.com",
    ],
)
def test_lookalike_media_hosts_are_rejected(hostname: str) -> None:
    assert subject._is_provider_host(hostname) is False


@pytest.fixture(autouse=True)
def _fixed_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subject, "resolve_host_addresses", lambda _hostname: [ip_address("93.184.216.34")])
    monkeypatch.setattr(subject, "_utcnow", lambda: NOW)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(subject.asyncio, "sleep", no_sleep)


def _upload_target(request: httpx.Request, *, file_id: str = FILE_ID) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "request_id": "upload-target-request-secret",
            "result": {
                "file_id": file_id,
                "method": "PUT",
                "upload_url": UPLOAD_URL,
                "upload_headers": [{"key": "x-tos-token", "value": "upload-token-secret"}],
            },
        },
        request=request,
    )


def _submit(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "task_id": TASK_ID,
            "request_id": "submit-request-secret",
        },
        request=request,
    )


def _completed(request: httpx.Request, *, expires_at: Any = None) -> httpx.Response:
    result: dict[str, Any] = {"video_url": RUNTIME_URL}
    payload = {
        "success": True,
        "task_id": TASK_ID,
        "request_id": "poll-completed-request-secret",
        "status": "completed",
        "result": result,
    }
    if expires_at is not None:
        payload["expires_at"] = expires_at
    return httpx.Response(200, json=payload, request=request)


@pytest.mark.asyncio
async def test_remux_ingress_uploads_once_polls_bounded_and_returns_secret_free_receipt(tmp_path: Path) -> None:
    source = tmp_path / "sealed-source.mp4"
    source.write_bytes(b"sealed-video-source-bytes")
    requests: list[httpx.Request] = []
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        requests.append(request)
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            assert request.method == "POST"
            assert request.headers["authorization"] == f"Bearer {MEDIAKIT_KEY}"
            assert json.loads(request.content) == {"tool_name": "remux-video"}
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            assert request.method == "PUT"
            assert "authorization" not in request.headers
            assert request.headers["x-tos-token"] == "upload-token-secret"
            assert request.headers["content-length"] == str(source.stat().st_size)
            assert request.content == source.read_bytes()
            return httpx.Response(200, content=b"", request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            assert request.method == "POST"
            assert request.headers["authorization"] == f"Bearer {MEDIAKIT_KEY}"
            assert json.loads(request.content) == {
                "video_url": FILE_ID,
                "container_format": "MP4",
                "client_token": CLIENT_TOKEN,
            }
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "task_id": TASK_ID,
                        "request_id": "poll-running-request-secret",
                        "status": "running",
                    },
                    request=request,
                )
            return _completed(request, expires_at=int((NOW + timedelta(hours=24)).timestamp()))
        raise AssertionError(f"unexpected request path: {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        candidate = await subject.create_mediakit_remux_https_candidate(
            source_path=source,
            expected_source_sha256=_sha256(source),
            mediakit_api_key=MEDIAKIT_KEY,
            client_token=CLIENT_TOKEN,
            client=client,
        )

    assert candidate.runtime_url == RUNTIME_URL
    receipt = candidate.receipt
    assert receipt.derived_from_source_sha256 == _sha256(source)
    assert receipt.source_hash_checks == 2
    assert receipt.source_hash_unchanged is True
    assert receipt.candidate_kind == "provider_remux_derivative"
    assert receipt.candidate_byte_identity == "not_attested_equal_to_source"
    assert receipt.provider_content_attestation == "unavailable"
    assert receipt.container_format == "MP4"
    assert receipt.status == "completed"
    assert receipt.poll_attempts == 2
    assert receipt.max_poll_attempts == 80
    assert receipt.retries == 0
    assert receipt.expires_at == NOW + timedelta(hours=24)
    assert receipt.observed_ttl_seconds == 24 * 60 * 60
    assert receipt.expiry_basis == "provider_reported"
    assert receipt.upload_file_id_sha256 == hashlib.sha256(FILE_ID.encode()).hexdigest()
    assert receipt.client_token_sha256 == hashlib.sha256(CLIENT_TOKEN.encode()).hexdigest()
    assert receipt.task_id_sha256 == hashlib.sha256(TASK_ID.encode()).hexdigest()
    assert receipt.runtime_url_sha256 == hashlib.sha256(RUNTIME_URL.encode()).hexdigest()
    assert len(receipt.provider_response_sha256s) == 5
    assert len(receipt.provider_response_sizes_bytes) == 5
    assert len(requests) == 5

    safe_text = receipt.model_dump_json() + repr(candidate)
    for secret in (
        MEDIAKIT_KEY,
        FILE_ID,
        TASK_ID,
        CLIENT_TOKEN,
        UPLOAD_URL,
        RUNTIME_URL,
        "upload-token-secret",
        "upload-target-request-secret",
        "submit-request-secret",
        "poll-running-request-secret",
        "poll-completed-request-secret",
    ):
        assert secret not in safe_text


@pytest.mark.asyncio
async def test_source_hash_mismatch_fails_before_any_http(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"actual")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256="0" * 64,
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "SOURCE_HASH_MISMATCH"
    assert error.value.billing_outcome == "not_submitted"
    assert calls == 0


@pytest.mark.asyncio
async def test_upload_stream_drift_fails_before_paid_remux_submission(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    sealed_bytes = b"sealed-source"
    changed_bytes = b"changed-bytes"
    assert len(changed_bytes) == len(sealed_bytes)
    source.write_bytes(sealed_bytes)
    source_sha256 = _sha256(source)
    put_calls = 0
    remux_submit_calls = 0
    submission_prepared_calls = 0
    uploaded_bytes: bytes | None = None

    class Observer:
        async def provider_submission_prepared(self, **_kwargs: Any) -> None:
            nonlocal submission_prepared_calls
            submission_prepared_calls += 1

    class MutatingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal put_calls, remux_submit_calls, uploaded_bytes
            if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
                return _upload_target(request)
            if str(request.url) == UPLOAD_URL:
                put_calls += 1
                source.write_bytes(changed_bytes)
                uploaded_bytes = await request.aread()
                source.write_bytes(sealed_bytes)
                return httpx.Response(200, request=request)
            if request.url.path == "/api/v1/tools/remux-video":
                remux_submit_calls += 1
                return _submit(request)
            raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=MutatingTransport()) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=source_sha256,
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
                task_observer=Observer(),
            )

    assert uploaded_bytes == changed_bytes
    assert _sha256(source) == source_sha256
    assert error.value.code == "UPLOADED_SOURCE_INTEGRITY_MISMATCH"
    assert error.value.billing_outcome == "not_submitted"
    assert put_calls == 1
    assert remux_submit_calls == 0
    assert submission_prepared_calls == 0


@pytest.mark.asyncio
async def test_source_is_rehashed_after_completion_and_drift_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    source_sha256 = _sha256(source)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(200, request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            source.write_bytes(b"changed-during-provider-call")
            return _completed(request, expires_at=int((NOW + timedelta(hours=24)).timestamp()))
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=source_sha256,
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "SOURCE_HASH_CHANGED_AFTER_UPLOAD"
    assert error.value.billing_outcome == "unknown"


@pytest.mark.asyncio
async def test_provider_response_size_limit_fails_without_retry(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"x" * (subject._MAX_RESPONSE_BYTES + 1), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "RESPONSE_TOO_LARGE"
    assert error.value.billing_outcome == "not_submitted"
    assert calls == 1


@pytest.mark.asyncio
async def test_total_deadline_fails_before_http_when_budget_is_exhausted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    times = iter([0.0, float(subject._TOTAL_TIMEOUT_SECONDS) + 1.0])
    monkeypatch.setattr(subject, "_monotonic", lambda: next(times))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "TOTAL_TIMEOUT"
    assert error.value.billing_outcome == "not_submitted"
    assert calls == 0


@pytest.mark.asyncio
async def test_submit_timeout_is_unknown_and_never_retried(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(200, request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            raise httpx.ReadTimeout(f"provider echoed {MEDIAKIT_KEY}", request=request)
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "REMUX_SUBMIT_TIMEOUT"
    assert error.value.billing_outcome == "unknown"
    assert MEDIAKIT_KEY not in str(error.value)
    assert error.value.__cause__ is None
    assert paths.count("/api/v1/tools/remux-video") == 1
    assert len(paths) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expires_at", "expected_code"),
    [
        (None, "MISSING_PROVIDER_EXPIRY"),
        ((NOW + timedelta(hours=22)).isoformat(), "PROVIDER_EXPIRY_OUT_OF_RANGE"),
        ((NOW + timedelta(hours=26)).isoformat(), "PROVIDER_EXPIRY_OUT_OF_RANGE"),
        ("not-a-time", "INVALID_PROVIDER_EXPIRY"),
    ],
)
async def test_provider_expiry_is_required_and_must_be_about_24_hours(
    tmp_path: Path,
    expires_at: str | None,
    expected_code: str,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(200, request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            return _completed(request, expires_at=expires_at)
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == expected_code
    assert error.value.billing_outcome == "unknown"


@pytest.mark.asyncio
async def test_polling_stops_at_configured_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    monkeypatch.setattr(subject, "_MAX_POLL_ATTEMPTS", 2)
    polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(200, request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            polls += 1
            return httpx.Response(
                200,
                json={"success": True, "task_id": TASK_ID, "status": "queued"},
                request=request,
            )
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "REMUX_POLL_LIMIT_REACHED"
    assert error.value.billing_outcome == "unknown"
    assert polls == 2


@pytest.mark.asyncio
async def test_unknown_task_status_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(200, request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            return httpx.Response(
                200,
                json={"success": True, "task_id": TASK_ID, "status": "mystery"},
                request=request,
            )
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "UNKNOWN_REMUX_TASK_STATUS"
    assert error.value.billing_outcome == "unknown"


@pytest.mark.asyncio
async def test_poll_result_must_match_submitted_task(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(200, request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "task_id": "different-task-secret-id",
                    "status": "completed",
                    "expires_at": int((NOW + timedelta(hours=24)).timestamp()),
                    "result": {"video_url": RUNTIME_URL},
                },
                request=request,
            )
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "REMUX_TASK_ID_MISMATCH"
    assert error.value.billing_outcome == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("client_token", ["", "x" * 65, "contains space", "非ASCII"])
async def test_client_token_is_required_bounded_and_ascii(tmp_path: Path, client_token: str) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=client_token,
                client=client,
            )
    assert error.value.code == "INVALID_CLIENT_TOKEN"
    assert error.value.billing_outcome == "not_submitted"
    assert calls == 0


@pytest.mark.asyncio
async def test_upload_target_requires_explicit_mediakit_uri(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _upload_target(request, file_id="bare-file-id")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.create_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                client_token=CLIENT_TOKEN,
                client=client,
            )
    assert error.value.code == "INVALID_MEDIAKIT_FILE_URI"
    assert error.value.billing_outcome == "not_submitted"
    assert calls == 1


def _submission_record(source: Path) -> subject.MediaKitRemuxSubmissionRecord:
    return subject._build_submission_record(
        source_sha256=_sha256(source),
        source_size_bytes=source.stat().st_size,
        file_id=FILE_ID,
        upload_url=UPLOAD_URL,
        client_token=CLIENT_TOKEN,
        response_hashes=[hashlib.sha256(b"upload-target").hexdigest(), hashlib.sha256(b"").hexdigest()],
        response_sizes=[len(b"upload-target"), 0],
        provider_request_id_sha256s=[hashlib.sha256(b"upload-request-id").hexdigest()],
    )


def _submitted_task_record() -> subject.MediaKitRemuxSubmittedTaskRecord:
    encoded = json.dumps(
        {
            "success": True,
            "task_id": TASK_ID,
            "request_id": "submit-request-secret",
        },
        separators=(",", ":"),
    ).encode()
    return subject._build_submitted_task_record(
        task_id=TASK_ID,
        submit_encoded=encoded,
        submit_payload=json.loads(encoded),
    )


@pytest.mark.asyncio
async def test_fresh_path_emits_exact_replay_safe_records_before_and_after_submit(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    events: list[str] = []
    captured: dict[str, Any] = {}

    class Observer:
        async def provider_submission_prepared(
            self,
            *,
            submission_record: subject.MediaKitRemuxSubmissionRecord,
            client_token: str,
        ) -> None:
            events.append("prepared")
            captured["submission"] = submission_record
            captured["client_token"] = client_token

        async def provider_task_submission_confirmed(
            self,
            *,
            submitted_task_record: subject.MediaKitRemuxSubmittedTaskRecord,
        ) -> None:
            events.append("confirmed")
            captured["submitted_task"] = submitted_task_record

        async def before_provider_submit(self, **_kwargs: Any) -> None:
            raise AssertionError("legacy pre-submit callback must not run")

        async def provider_task_submitted(self, **_kwargs: Any) -> None:
            raise AssertionError("legacy submitted callback must not run")

        async def provider_task_running(self, **_kwargs: Any) -> None:
            events.append("running")

        async def provider_task_terminal(self, **_kwargs: Any) -> None:
            events.append("terminal")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tools-sync/request-media-upload-url":
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            return httpx.Response(200, request=request)
        if request.url.path == "/api/v1/tools/remux-video":
            assert events == ["prepared"]
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            assert events == ["prepared", "confirmed"]
            return _completed(request, expires_at=int((NOW + timedelta(hours=24)).timestamp()))
        raise AssertionError(request.url.path)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await subject.create_mediakit_remux_https_candidate(
            source_path=source,
            expected_source_sha256=_sha256(source),
            mediakit_api_key=MEDIAKIT_KEY,
            client_token=CLIENT_TOKEN,
            client=client,
            task_observer=Observer(),
        )

    submission = captured["submission"]
    assert submission.upload_file_id == FILE_ID
    assert submission.source_sha256 == _sha256(source)
    assert submission.source_size_bytes == source.stat().st_size
    assert submission.submit_body_sha256 == subject._canonical_sha256({"video_url": FILE_ID, "container_format": "MP4", "client_token": CLIENT_TOKEN})
    assert len(submission.provider_response_sha256s) == 2
    assert len(submission.provider_response_sizes_bytes) == 2
    assert captured["client_token"] == CLIENT_TOKEN
    submitted_task = captured["submitted_task"]
    assert submitted_task.task_id == TASK_ID
    assert submitted_task.provider_response_size_bytes > 0
    assert events == ["prepared", "confirmed", "terminal"]
    assert FILE_ID not in repr(submission)
    assert CLIENT_TOKEN not in repr(submission)
    assert TASK_ID not in repr(submitted_task)


@pytest.mark.asyncio
async def test_query_recovery_only_gets_existing_task_and_rebuilds_full_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    submission = _submission_record(source)
    submitted_task = _submitted_task_record()
    paths: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append((request.method, request.url.path))
        assert request.method == "GET"
        assert request.url.path == f"/api/v1/tasks/{TASK_ID}"
        return _completed(request, expires_at=int((NOW + timedelta(hours=24)).timestamp()))

    recovery_request = subject.MediaKitRemuxRecoveryRequest(
        contract_version=subject.MEDIAKIT_REMUX_RECOVERY_REQUEST_CONTRACT_VERSION,
        action="query_existing_task",
        submission=submission,
        client_token=CLIENT_TOKEN,
        submitted_task=submitted_task,
    )
    assert CLIENT_TOKEN not in repr(recovery_request)
    assert FILE_ID not in repr(recovery_request)
    assert TASK_ID not in repr(recovery_request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidate = await subject.recover_mediakit_remux_https_candidate(
            source_path=source,
            expected_source_sha256=_sha256(source),
            mediakit_api_key=MEDIAKIT_KEY,
            recovery_request=recovery_request,
            client=client,
        )

    assert paths == [("GET", f"/api/v1/tasks/{TASK_ID}")]
    assert candidate.receipt.task_id_sha256 == hashlib.sha256(TASK_ID.encode()).hexdigest()
    assert candidate.receipt.provider_response_sha256s[:2] == submission.provider_response_sha256s
    assert candidate.receipt.provider_response_sha256s[2] == submitted_task.provider_response_sha256
    assert len(candidate.receipt.provider_response_sha256s) == 4
    assert candidate.receipt.source_hash_checks == 2


@pytest.mark.asyncio
async def test_submission_recovery_replays_exact_post_once_and_never_uploads(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    submission = _submission_record(source)
    paths: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append((request.method, request.url.path))
        if request.url.path == "/api/v1/tools/remux-video":
            assert request.method == "POST"
            assert json.loads(request.content) == {
                "video_url": FILE_ID,
                "container_format": "MP4",
                "client_token": CLIENT_TOKEN,
            }
            return _submit(request)
        if request.url.path == f"/api/v1/tasks/{TASK_ID}":
            assert request.method == "GET"
            return _completed(request, expires_at=int((NOW + timedelta(hours=24)).timestamp()))
        raise AssertionError(f"recovery attempted a forbidden request: {request.url.path}")

    recovery_request = subject.MediaKitRemuxRecoveryRequest(
        contract_version=subject.MEDIAKIT_REMUX_RECOVERY_REQUEST_CONTRACT_VERSION,
        action="replay_submission_once",
        submission=submission,
        client_token=CLIENT_TOKEN,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        candidate = await subject.recover_mediakit_remux_https_candidate(
            source_path=source,
            expected_source_sha256=_sha256(source),
            mediakit_api_key=MEDIAKIT_KEY,
            recovery_request=recovery_request,
            client=client,
        )

    assert paths == [
        ("POST", "/api/v1/tools/remux-video"),
        ("GET", f"/api/v1/tasks/{TASK_ID}"),
    ]
    assert candidate.receipt.provider_response_sha256s[:2] == submission.provider_response_sha256s
    assert len(candidate.receipt.provider_response_sha256s) == 4


@pytest.mark.asyncio
async def test_recovery_binding_failure_happens_before_any_http(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    submission = _submission_record(source)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    bad_request = {
        "contract_version": subject.MEDIAKIT_REMUX_RECOVERY_REQUEST_CONTRACT_VERSION,
        "action": "query_existing_task",
        "submission": submission.model_dump(),
        "client_token": "different-token",
        "submitted_task": _submitted_task_record().model_dump(),
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.recover_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                recovery_request=bad_request,
                client=client,
            )
    assert error.value.code == "INVALID_REMUX_RECOVERY_REQUEST"
    assert error.value.billing_outcome == "unknown"
    assert calls == 0
    assert CLIENT_TOKEN not in str(error.value)
    assert error.value.__cause__ is None


@pytest.mark.asyncio
async def test_query_recovery_rehashes_source_after_provider_completion(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    source_digest = _sha256(source)
    submission = _submission_record(source)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        source.write_bytes(b"changed-after-first-hash")
        return _completed(request, expires_at=int((NOW + timedelta(hours=24)).timestamp()))

    recovery_request = subject.MediaKitRemuxRecoveryRequest(
        contract_version=subject.MEDIAKIT_REMUX_RECOVERY_REQUEST_CONTRACT_VERSION,
        action="query_existing_task",
        submission=submission,
        client_token=CLIENT_TOKEN,
        submitted_task=_submitted_task_record(),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.recover_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=source_digest,
                mediakit_api_key=MEDIAKIT_KEY,
                recovery_request=recovery_request,
                client=client,
            )
    assert error.value.code == "SOURCE_HASH_CHANGED_AFTER_UPLOAD"
    assert error.value.billing_outcome == "unknown"


@pytest.mark.asyncio
async def test_submission_recovery_timeout_never_replays_post_twice(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"sealed")
    submission = _submission_record(source)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        assert request.url.path == "/api/v1/tools/remux-video"
        raise httpx.ReadTimeout("submit timed out", request=request)

    recovery_request = subject.MediaKitRemuxRecoveryRequest(
        contract_version=subject.MEDIAKIT_REMUX_RECOVERY_REQUEST_CONTRACT_VERSION,
        action="replay_submission_once",
        submission=submission,
        client_token=CLIENT_TOKEN,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(subject.MediaKitRemuxIngressError) as error:
            await subject.recover_mediakit_remux_https_candidate(
                source_path=source,
                expected_source_sha256=_sha256(source),
                mediakit_api_key=MEDIAKIT_KEY,
                recovery_request=recovery_request,
                client=client,
            )
    assert error.value.code == "REMUX_SUBMIT_TIMEOUT"
    assert error.value.billing_outcome == "unknown"
    assert calls == 1
