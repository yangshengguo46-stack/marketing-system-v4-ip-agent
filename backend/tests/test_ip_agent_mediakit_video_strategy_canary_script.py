from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sqlite3
import stat
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "ip_agent_mediakit_video_strategy_canary.py"
    spec = importlib.util.spec_from_file_location("ip_agent_mediakit_video_strategy_canary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


canary = _load_module()

API_KEY = "private-mediakit-api-key"
FILE_ID = "mediakit://private-upload-file-id"
UPLOAD_URL = "https://upload.tos-cn-beijing.volces.com/object?X-Signature=private"
UPLOAD_TOKEN = "private-upload-token"
TASK_ID = "private-task-id"
UPLOAD_REQUEST_ID = "private-upload-request-id"
PUT_REQUEST_ID = "private-put-request-id"
SUBMIT_REQUEST_ID = "private-submit-request-id"
POLL_REQUEST_ID = "private-poll-request-id"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


@pytest.fixture
def fixture_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"mock-mp4-source-bytes")
    output_parent = tmp_path / "ignored"
    output_parent.mkdir()
    monkeypatch.setattr(canary, "ROOT", tmp_path)
    monkeypatch.setattr(canary, "_is_git_ignored", lambda _path: True)
    monkeypatch.setenv(canary.DEFAULT_API_KEY_ENV, API_KEY)
    monkeypatch.setattr(canary, "_POLL_INTERVAL_SECONDS", 0.0)
    return canary.CanaryOptions(
        video_path=source,
        authorize_paid_call=True,
        maximum_cny=Decimal("0.10"),
        output_dir=output_parent / "run",
        api_key_env=canary.DEFAULT_API_KEY_ENV,
        mediakit_key_file=None,
    )


def _upload_target(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "request_id": UPLOAD_REQUEST_ID,
            "result": {
                "file_id": FILE_ID,
                "method": "PUT",
                "upload_url": UPLOAD_URL,
                "upload_headers": [{"key": "x-tos-token", "value": UPLOAD_TOKEN}],
            },
        },
        request=request,
    )


def _submit(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"success": True, "task_id": TASK_ID, "request_id": SUBMIT_REQUEST_ID},
        request=request,
    )


def _poll(
    request: httpx.Request,
    *,
    status: str,
    contents: list[str] | None = None,
) -> httpx.Response:
    payload: dict[str, Any] = {
        "success": True,
        "task_id": TASK_ID,
        "request_id": POLL_REQUEST_ID,
        "status": status,
    }
    if status == "completed":
        payload["result"] = {
            "duration": 61.25,
            "contents": contents or ["00:00 画面开始。"],
            "token_usage": {
                "input_tokens": 1200,
                "output_tokens": 300,
                "total_tokens": 1500,
            },
        }
    return httpx.Response(200, json=payload, request=request)


def test_success_uses_exact_official_contract_and_writes_only_redacted_receipt(
    fixture_options: Any,
) -> None:
    observed_paths: list[str] = []
    submit_bodies: list[dict[str, Any]] = []
    poll_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        observed_paths.append(request.url.path)
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            assert request.method == "POST"
            assert json.loads(await request.aread()) == {"tool_name": "video-understand-router"}
            assert request.headers["authorization"] == f"Bearer {API_KEY}"
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            assert request.method == "PUT"
            assert request.headers["content-type"] == "video/mp4"
            assert "authorization" not in request.headers
            assert request.headers["x-tos-token"] == UPLOAD_TOKEN
            assert await request.aread() == fixture_options.video_path.read_bytes()
            return httpx.Response(200, headers={"x-tos-request-id": PUT_REQUEST_ID}, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            assert request.method == "POST"
            body = json.loads(await request.aread())
            submit_bodies.append(body)
            assert body == {
                "video_urls": [FILE_ID],
                "prompt": canary.FIXED_PROMPT,
                "level": "Quality",
                "scene": "editing",
                "manual_option": {"need_audio": True},
                "client_token": canary._client_token(
                    source_sha256=hashlib.sha256(fixture_options.video_path.read_bytes()).hexdigest(),
                    source_size_bytes=fixture_options.video_path.stat().st_size,
                ),
            }
            assert not ({"callback_url", "callback_args", "queue_id", "prefer_models", "prefer_endpoints"} & body.keys())
            return _submit(request)
        if request.url.path == f"{canary.TASK_PATH_PREFIX}{TASK_ID}":
            assert request.method == "GET"
            poll_count += 1
            if poll_count == 1:
                return _poll(request, status="running")
            contents = [f"visible event; {UPLOAD_URL}; {FILE_ID}; https://unreported.example/private; safe conclusion"]
            return _poll(request, status="completed", contents=contents)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def run() -> tuple[dict[str, Any], Path]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            return await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    receipt, receipt_path = asyncio.run(run())
    assert observed_paths == [
        canary.UPLOAD_TARGET_PATH,
        "/object",
        canary.SUBMIT_PATH,
        f"{canary.TASK_PATH_PREFIX}{TASK_ID}",
        f"{canary.TASK_PATH_PREFIX}{TASK_ID}",
    ]
    assert len(submit_bodies) == 1
    assert receipt["status"] == "completed"
    assert receipt["billing_outcome"] == "usage_returned"
    assert receipt["execution"]["submit_attempts"] == 1
    assert receipt["request_projection"]["submit_retries"] == 0
    assert receipt["provider_identifier_sha256"]["file_id"] == hashlib.sha256(FILE_ID.encode()).hexdigest()
    assert receipt["provider_identifier_sha256"]["upload_url"] == hashlib.sha256(UPLOAD_URL.encode()).hexdigest()
    assert receipt["provider_identifier_sha256"]["task_id"] == hashlib.sha256(TASK_ID.encode()).hexdigest()
    assert receipt["provider_reported_duration_seconds"] == "61.250000"
    assert receipt["token_usage"] == {"input_tokens": 1200, "output_tokens": 300, "total_tokens": 1500}
    assert "[redacted-url]" in receipt["contents"][0]["text"]
    assert "[redacted-provider-identifier]" in receipt["contents"][0]["text"]

    persisted = receipt_path.read_text(encoding="utf-8")
    for forbidden in (
        API_KEY,
        FILE_ID,
        UPLOAD_URL,
        UPLOAD_TOKEN,
        TASK_ID,
        UPLOAD_REQUEST_ID,
        PUT_REQUEST_ID,
        SUBMIT_REQUEST_ID,
        POLL_REQUEST_ID,
        submit_bodies[0]["client_token"],
    ):
        assert forbidden not in persisted
    assert "https://" not in persisted
    assert "mediakit://" not in persisted
    assert _mode(fixture_options.output_dir) == 0o700
    assert _mode(receipt_path) == 0o600
    assert {path.name for path in fixture_options.output_dir.iterdir()} == {
        "paid-recovery.key",
        "receipt.json",
        "recovery-db",
    }
    assert _mode(fixture_options.output_dir / "paid-recovery.key") == 0o600
    assert _mode(fixture_options.output_dir / "recovery-db") == 0o700
    assert all(_mode(path) == 0o600 for path in (fixture_options.output_dir / "recovery-db").iterdir())


def test_public_pricing_keeps_mediakit_ark_cap_and_invoice_boundaries_separate(
    fixture_options: Any,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            return _submit(request)
        return _poll(request, status="completed")

    async def run() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            receipt, _ = await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("90"),
            )
            return receipt

    receipt = asyncio.run(run())
    pricing = receipt["pricing"]
    assert pricing["status"] == "public_tariff_estimate_not_provider_quote_or_invoice"
    assert pricing["mediakit"]["unit_price_cny_per_input_minute"] == "0.01"
    assert pricing["mediakit"]["preflight_public_estimate_cny"] == "0.015000"
    assert pricing["mediakit"]["actual_cny_returned_by_api"] is False
    assert pricing["ark_tokens"]["preflight_usage"] == "unknown_until_provider_usage"
    assert pricing["ark_tokens"]["returned_aggregate_usage"]["total_tokens"] == 1500
    assert pricing["ark_tokens"]["cny_estimate_status"] == "unavailable"
    assert "audio_vs_non_audio_input_token_split_not_returned" in pricing["ark_tokens"]["cny_estimate_unavailable_reasons"]
    assert pricing["combined_total_cny"] == "unknown"
    authorization = receipt["authorization"]
    assert authorization["maximum_cny_cap"] == "0.100000"
    assert authorization["provider_enforced"] is False
    assert authorization["cap_is_provider_quote"] is False
    assert authorization["cap_is_invoice"] is False
    assert authorization["ark_token_charge_is_not_bounded_by_this_cap"] is True


def test_submit_crash_window_resumes_with_one_exact_body_token_replay(
    fixture_options: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_submit_body: dict[str, Any] | None = None
    first_paths: list[str] = []
    original_persist = canary._persist_submitted_task

    async def crash_before_task_id_persisted(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated crash after provider accepted submit")

    async def first_handler(request: httpx.Request) -> httpx.Response:
        nonlocal first_submit_body
        first_paths.append(request.url.path)
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            first_submit_body = json.loads(await request.aread())
            return _submit(request)
        raise AssertionError("first process must crash before polling")

    async def first_run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(first_handler), trust_env=False) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    monkeypatch.setattr(canary, "_persist_submitted_task", crash_before_task_id_persisted)
    with pytest.raises(canary.CanaryError, match="INTERNAL_ERROR"):
        asyncio.run(first_run())
    assert first_submit_body is not None
    assert first_paths == [
        canary.UPLOAD_TARGET_PATH,
        "/object",
        canary.SUBMIT_PATH,
    ]
    crashed_receipt = json.loads((fixture_options.output_dir / "receipt.json").read_text(encoding="utf-8"))
    assert crashed_receipt["recovery"]["encrypted_exact_submission_persisted"] is True
    assert crashed_receipt["recovery"]["raw_task_authority_persisted"] is False
    assert TASK_ID not in json.dumps(crashed_receipt)
    recovery_database = (fixture_options.output_dir / "recovery-db" / "deerflow.db").read_bytes()
    assert FILE_ID.encode() not in recovery_database
    assert first_submit_body["client_token"].encode() not in recovery_database

    monkeypatch.setattr(canary, "_persist_submitted_task", original_persist)
    resume_options = canary.CanaryOptions(**{**fixture_options.__dict__, "resume": True})
    resumed_paths: list[str] = []
    replay_bodies: list[dict[str, Any]] = []

    async def resume_handler(request: httpx.Request) -> httpx.Response:
        resumed_paths.append(request.url.path)
        if request.url.path == canary.SUBMIT_PATH:
            replay_bodies.append(json.loads(await request.aread()))
            return _submit(request)
        if request.url.path == f"{canary.TASK_PATH_PREFIX}{TASK_ID}":
            return _poll(request, status="completed")
        raise AssertionError("resume may not upload or create a fresh submission")

    async def resume_run() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(resume_handler), trust_env=False) as client:
            receipt, _ = await canary.execute_canary(
                resume_options,
                client=client,
                duration_probe=lambda _path: (_ for _ in ()).throw(AssertionError("resume must not probe or reopen the source")),
            )
            return receipt

    receipt = asyncio.run(resume_run())
    assert resumed_paths == [
        canary.SUBMIT_PATH,
        f"{canary.TASK_PATH_PREFIX}{TASK_ID}",
    ]
    assert replay_bodies == [first_submit_body]
    assert receipt["status"] == "completed"
    assert receipt["safe_error_code"] is None
    assert receipt["execution"]["upload_target_attempts"] == 1
    assert receipt["execution"]["media_upload_attempts"] == 1
    assert receipt["execution"]["submit_attempts"] == 2
    assert receipt["request_projection"]["submit_retries"] == 1
    assert receipt["recovery"]["exact_submit_replay_claimed"] is True
    assert receipt["recovery"]["raw_task_authority_persisted"] is True
    assert TASK_ID.encode() not in (fixture_options.output_dir / "recovery-db" / "deerflow.db").read_bytes()


def test_submitted_task_resume_is_get_only_without_upload_or_post(
    fixture_options: Any,
) -> None:
    first_paths: list[str] = []

    async def first_handler(request: httpx.Request) -> httpx.Response:
        first_paths.append(request.url.path)
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            return _submit(request)
        if request.url.path == f"{canary.TASK_PATH_PREFIX}{TASK_ID}":
            raise asyncio.CancelledError
        raise AssertionError("unexpected first-run request")

    async def first_run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(first_handler), trust_env=False) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(first_run())
    assert first_paths == [
        canary.UPLOAD_TARGET_PATH,
        "/object",
        canary.SUBMIT_PATH,
        f"{canary.TASK_PATH_PREFIX}{TASK_ID}",
    ]

    resume_options = canary.CanaryOptions(**{**fixture_options.__dict__, "resume": True})
    resumed_paths: list[str] = []

    async def resume_handler(request: httpx.Request) -> httpx.Response:
        resumed_paths.append(request.url.path)
        assert request.method == "GET"
        assert request.url.path == f"{canary.TASK_PATH_PREFIX}{TASK_ID}"
        return _poll(request, status="completed")

    async def resume_run() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(resume_handler), trust_env=False) as client:
            receipt, _ = await canary.execute_canary(
                resume_options,
                client=client,
                duration_probe=lambda _path: (_ for _ in ()).throw(AssertionError("query-only resume must not inspect source")),
            )
            return receipt

    receipt = asyncio.run(resume_run())
    assert resumed_paths == [f"{canary.TASK_PATH_PREFIX}{TASK_ID}"]
    assert receipt["status"] == "completed"
    assert receipt["execution"]["submit_attempts"] == 1
    assert receipt["request_projection"]["submit_retries"] == 0
    assert receipt["recovery"]["resumed_with_query_only"] is True
    assert receipt["recovery"]["raw_task_authority_persisted"] is True


def test_upload_url_has_its_own_bound_for_real_long_signed_tos_urls() -> None:
    long_signed_url = "https://tob-upload-x-d.volcvod.com/object?signature=" + ("a" * 6000)
    assert canary._validate_upload_url(long_signed_url) == long_signed_url

    with pytest.raises(canary.CanaryError, match="INVALID_UPLOAD_URL"):
        canary._validate_upload_url(long_signed_url + "\n")

    with pytest.raises(canary.CanaryError, match="INVALID_UPLOAD_URL"):
        canary._validate_upload_url("https://example.com/object?signature=" + ("a" * 6000))


def test_missing_authorization_reads_no_source_secret_or_provider(
    fixture_options: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = canary.CanaryOptions(
        video_path=fixture_options.video_path,
        authorize_paid_call=False,
        maximum_cny=Decimal("0.10"),
        output_dir=fixture_options.output_dir,
        api_key_env=fixture_options.api_key_env,
        mediakit_key_file=None,
    )

    def forbidden_probe(_path: Path) -> Decimal:
        raise AssertionError("unauthorized run must not inspect media or secrets")

    monkeypatch.setattr(canary, "_load_api_key", lambda _options: (_ for _ in ()).throw(AssertionError()))
    with pytest.raises(canary.CanaryError, match="PAID_CALL_NOT_AUTHORIZED"):
        asyncio.run(canary.execute_canary(options, duration_probe=forbidden_probe))
    assert not options.output_dir.exists()


def test_resume_is_explicit_and_requires_the_existing_output_dir(
    fixture_options: Any,
) -> None:
    with pytest.raises(canary.CanaryError, match="RESUME_REQUIRES_OUTPUT_DIR"):
        canary._parse_args(
            [
                str(fixture_options.video_path),
                "--authorize-paid-call",
                "--maximum-cny",
                "0.100000",
                "--resume",
            ]
        )
    parsed = canary._parse_args(
        [
            str(fixture_options.video_path),
            "--authorize-paid-call",
            "--maximum-cny",
            "0.100000",
            "--output-dir",
            str(fixture_options.output_dir),
            "--resume",
        ]
    )
    assert parsed.authorize_paid_call is True
    assert parsed.resume is True
    assert parsed.output_dir == fixture_options.output_dir


def test_known_mediakit_estimate_over_cap_fails_before_secret_and_output(
    fixture_options: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = canary.CanaryOptions(
        video_path=fixture_options.video_path,
        authorize_paid_call=True,
        maximum_cny=Decimal("0.009"),
        output_dir=fixture_options.output_dir,
        api_key_env=fixture_options.api_key_env,
        mediakit_key_file=None,
    )
    monkeypatch.setattr(canary, "_load_api_key", lambda _options: (_ for _ in ()).throw(AssertionError()))
    with pytest.raises(canary.CanaryError, match="MEDIAKIT_ESTIMATE_EXCEEDS_MAXIMUM_CNY"):
        asyncio.run(
            canary.execute_canary(
                options,
                duration_probe=lambda _path: Decimal("60"),
            )
        )
    assert not options.output_dir.exists()


def test_secret_file_must_be_existing_git_ignored_owner_0600(
    fixture_options: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv(canary.DEFAULT_API_KEY_ENV, raising=False)
    key_file = tmp_path / "mediakit-key"
    key_file.write_text(API_KEY, encoding="utf-8")
    key_file.chmod(0o644)
    with pytest.raises(canary.CanaryError, match="MEDIAKIT_KEY_FILE_INVALID"):
        canary._read_key_file(key_file)

    key_file.chmod(0o600)
    assert canary._read_key_file(key_file) == API_KEY

    link = tmp_path / "mediakit-key-link"
    link.symlink_to(key_file)
    with pytest.raises(canary.CanaryError, match="MEDIAKIT_KEY_FILE_INVALID"):
        canary._read_key_file(link)

    monkeypatch.setattr(canary, "_is_git_ignored", lambda _path: False)
    with pytest.raises(canary.CanaryError, match="MEDIAKIT_KEY_FILE_NOT_GIT_IGNORED"):
        canary._read_key_file(key_file)


def test_secret_file_rejects_a_symlinked_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    key = outside / "key"
    key.write_text(API_KEY, encoding="utf-8")
    key.chmod(0o600)
    (repository / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(canary, "ROOT", repository)
    monkeypatch.setattr(canary, "_is_git_ignored", lambda _path: True)
    with pytest.raises(canary.CanaryError, match="MEDIAKIT_KEY_FILE_INVALID"):
        canary._read_key_file(repository / "linked" / "key")


def test_pinned_repository_ffprobe_precedes_system_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pinned = tmp_path / ".deer-flow" / "toolchains" / "ffmpeg" / "bin" / "ffprobe"
    pinned.parent.mkdir(parents=True)
    pinned.write_bytes(b"pinned-ffprobe")
    pinned.chmod(0o755)
    observed: list[list[str]] = []

    def run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        observed.append(args)
        return subprocess.CompletedProcess(
            args,
            0,
            stdout=b'{"format":{"duration":"1.500000","format_name":"mov,mp4"}}',
            stderr=b"",
        )

    monkeypatch.setattr(canary, "ROOT", tmp_path)
    monkeypatch.setattr(canary.shutil, "which", lambda _name: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(canary.subprocess, "run", run)
    assert canary._probe_duration_seconds(tmp_path / "source.mp4") == Decimal("1.500000")
    assert observed[0][0] == str(pinned)


def test_upload_headers_reject_conflicts_hop_by_hop_and_unknown_names() -> None:
    for headers in (
        [
            {"key": "x-tos-token", "value": "one-private-token"},
            {"key": "X-TOS-TOKEN", "value": "two-private-token"},
        ],
        [{"key": "Content-Length", "value": "999"}],
        [{"key": "Transfer-Encoding", "value": "chunked"}],
        [{"key": "x-unexpected", "value": "private"}],
    ):
        with pytest.raises(canary.CanaryError, match="INVALID_UPLOAD_HEADERS"):
            canary._parse_upload_headers(headers, api_key=API_KEY)


def test_submit_timeout_is_never_retried_and_persists_unknown_outcome(
    fixture_options: Any,
) -> None:
    submit_attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submit_attempts
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            submit_attempts += 1
            raise httpx.ReadTimeout("submit outcome unknown", request=request)
        raise AssertionError("poll must not run after unknown submit outcome")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(canary.CanaryError, match="SUBMIT_TIMEOUT"):
        asyncio.run(run())
    assert submit_attempts == 1
    receipt = json.loads((fixture_options.output_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "submit_outcome_unknown"
    assert receipt["billing_outcome"] == "unknown"
    assert receipt["safe_error_code"] == "SUBMIT_TIMEOUT"
    assert receipt["execution"]["submit_attempts"] == 1
    assert receipt["request_projection"]["submit_retries"] == 0


@pytest.mark.parametrize(
    ("provider_status", "error_code", "receipt_status"),
    [
        ("cancelled", "PROVIDER_TASK_CANCELLED", "cancelled"),
        ("mystery", "UNKNOWN_TASK_STATUS", "unknown"),
    ],
)
def test_cancelled_and_unknown_task_statuses_fail_safe(
    fixture_options: Any,
    provider_status: str,
    error_code: str,
    receipt_status: str,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            return _submit(request)
        return _poll(request, status=provider_status)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(canary.CanaryError, match=error_code):
        asyncio.run(run())
    receipt = json.loads((fixture_options.output_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == receipt_status
    assert receipt["billing_outcome"] == "unknown"
    assert receipt["safe_error_code"] == error_code
    assert TASK_ID not in json.dumps(receipt)


def test_poll_count_is_bounded(
    fixture_options: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canary, "_MAX_POLL_ATTEMPTS", 2)
    polls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal polls
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            return _submit(request)
        polls += 1
        return _poll(request, status="running")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(canary.CanaryError, match="POLL_LIMIT_REACHED"):
        asyncio.run(run())
    assert polls == 2
    receipt = json.loads((fixture_options.output_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["execution"]["poll_attempts"] == 2
    assert receipt["execution"]["maximum_poll_attempts"] == 2
    assert receipt["status"] == "poll_timeout"


def test_provider_response_and_persisted_contents_are_bounded(
    fixture_options: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_content = "剪辑观察" * 20_000

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            return _submit(request)
        return _poll(request, status="completed", contents=[long_content])

    async def run() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            receipt, _ = await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )
            return receipt

    receipt = asyncio.run(run())
    normalized = receipt["contents"][0]
    assert normalized["truncated"] is True
    assert normalized["stored_utf8_bytes"] <= canary._MAX_CONTENT_TEXT_BYTES
    assert (fixture_options.output_dir / "receipt.json").stat().st_size <= canary._MAX_RECEIPT_BYTES

    second_options = canary.CanaryOptions(**{**fixture_options.__dict__, "output_dir": fixture_options.output_dir.parent / "oversize"})
    monkeypatch.setattr(canary, "_MAX_RESPONSE_BYTES", 16)

    async def oversized_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 17, request=request)

    async def oversized_run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(oversized_handler)) as client:
            await canary.execute_canary(
                second_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(canary.CanaryError, match="RESPONSE_TOO_LARGE"):
        asyncio.run(oversized_run())


def test_client_token_is_deterministic_ascii_and_bound_to_fixed_projection() -> None:
    first = canary._client_token(source_sha256="a" * 64, source_size_bytes=123)
    second = canary._client_token(source_sha256="a" * 64, source_size_bytes=123)
    changed = canary._client_token(source_sha256="b" * 64, source_size_bytes=123)
    assert first == second
    assert first != changed
    assert len(first) == 64
    assert first.isascii() and first.isprintable()


def test_public_mediakit_estimate_ceil_is_frozen_at_one_micro_cny() -> None:
    assert canary._published_mediakit_estimate(Decimal("60")) == Decimal("0.010000")
    assert canary._published_mediakit_estimate(Decimal("70.867")) == Decimal("0.011812")
    with pytest.raises(canary.CanaryError, match="INVALID_MAXIMUM_CNY"):
        canary._parse_positive_decimal("0.0000009", code="INVALID_MAXIMUM_CNY")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"success": False},
        {"success": 0},
        {"success": "true"},
        {"success": True, "error": {"message": API_KEY}},
    ],
)
def test_provider_success_must_be_literal_true_without_error(payload: dict[str, Any]) -> None:
    with pytest.raises(canary.CanaryError, match="REJECTED"):
        canary._require_success(
            payload,
            code="REJECTED",
            billing_outcome="unknown",
            stage="submit",
            forbidden=(API_KEY,),
        )


def test_provider_task_rejection_preserves_private_debug_message_and_terminal_state(
    fixture_options: Any,
) -> None:
    raw_message = f"download failed: {UPLOAD_URL}; key={API_KEY}; task={TASK_ID}"

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            return _submit(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "task_id": TASK_ID,
                "request_id": POLL_REQUEST_ID,
                "status": "failed",
                "error": {
                    "code": "DownloadFailed",
                    "type": "TaskError",
                    "param": "video_urls[0]",
                    "message": raw_message,
                    "private_url": UPLOAD_URL,
                },
            },
            request=request,
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(canary.CanaryError, match="PROVIDER_TASK_FAILED"):
        asyncio.run(run())
    receipt_text = (fixture_options.output_dir / "receipt.json").read_text(encoding="utf-8")
    receipt = json.loads(receipt_text)
    assert receipt["status"] == "provider_task_rejected"
    assert receipt["billing_outcome"] == "unknown"
    assert receipt["failure"] == {
        "classification": "terminal_provider_task_rejection",
        "stage": "poll",
        "provider_error": {
            "fields": {
                "code": {"storage": "allowlisted_value", "value": "DownloadFailed"},
                "type": {"storage": "allowlisted_value", "value": "TaskError"},
                "param": {"storage": "allowlisted_value", "value": "video_urls[0]"},
            },
            "message": "download failed: [redacted]; key=[redacted]; task=[redacted]",
            "message_truncated": False,
        },
    }
    assert receipt["execution"]["poll_attempts"] == 1
    database_path = fixture_options.output_dir / canary.RECOVERY_DATABASE_DIR_NAME / "deerflow.db"
    with sqlite3.connect(database_path) as connection:
        provider_state = connection.execute("SELECT provider_task_status, provider_terminal_status, encrypted_provider_terminal_json FROM personal_ip_paid_call_scopes").fetchone()
    assert provider_state is not None
    assert provider_state[0:2] == ("terminal", "failed")
    assert isinstance(provider_state[2], str) and provider_state[2]
    for forbidden in (raw_message, API_KEY, UPLOAD_URL, TASK_ID, POLL_REQUEST_ID):
        assert forbidden not in receipt_text


def test_cli_failure_payload_shows_safe_provider_message() -> None:
    error = canary._provider_rejection_error(
        "PROVIDER_TASK_FAILED",
        payload={
            "error": {
                "code": "AbilityProcessingError",
                "type": "InternalServerError",
                "message": f"speech config empty; key={API_KEY}; source={UPLOAD_URL}",
            }
        },
        stage="poll",
        billing_outcome="unknown",
        forbidden=(API_KEY,),
    )

    assert canary._cli_failure_payload(error) == {
        "status": "failed_safe",
        "safe_error_code": "PROVIDER_TASK_FAILED",
        "billing_outcome": "unknown",
        "automatic_submit_retries": 0,
        "provider_error_message": "speech config empty; key=[redacted]; source=[redacted-url]",
    }


def test_unsafe_provider_error_fields_are_hashed_and_transport_is_distinct(
    fixture_options: Any,
) -> None:
    async def rejection_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        return httpx.Response(
            503,
            json={
                "success": False,
                "request_id": SUBMIT_REQUEST_ID,
                "error": {"code": API_KEY, "type": UPLOAD_URL, "param": SUBMIT_REQUEST_ID, "message": "discard me"},
            },
            request=request,
        )

    async def rejected() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(rejection_handler)) as client:
            await canary.execute_canary(fixture_options, client=client, duration_probe=lambda _path: Decimal("60"))

    with pytest.raises(canary.CanaryError, match="SUBMIT_HTTP_ERROR"):
        asyncio.run(rejected())
    receipt = json.loads((fixture_options.output_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["failure"]["classification"] == "terminal_provider_submission_rejection"
    assert receipt["billing_outcome"] == "provider_rejected"
    fields = receipt["failure"]["provider_error"]["fields"]
    assert {field: value["storage"] for field, value in fields.items()} == {
        "code": "sha256_only",
        "type": "sha256_only",
        "param": "sha256_only",
    }

    transport_options = canary.CanaryOptions(**{**fixture_options.__dict__, "output_dir": fixture_options.output_dir.parent / "transport"})

    async def transport_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        raise httpx.ReadError("connection lost", request=request)

    async def unknown() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport_handler)) as client:
            await canary.execute_canary(transport_options, client=client, duration_probe=lambda _path: Decimal("60"))

    with pytest.raises(canary.CanaryError, match="SUBMIT_TRANSPORT_UNKNOWN"):
        asyncio.run(unknown())
    transport_receipt = json.loads((transport_options.output_dir / "receipt.json").read_text(encoding="utf-8"))
    assert transport_receipt["status"] == "submit_outcome_unknown"
    assert transport_receipt["failure"] == {
        "classification": "transport_unknown",
        "stage": "submit",
        "provider_error": None,
    }


def test_malformed_request_ids_are_ignored_without_escaping_as_type_errors() -> None:
    request = httpx.Request("GET", "https://mediakit.cn-beijing.volces.com/api/v1/tasks/x")
    response = httpx.Response(200, request=request)
    assert canary._request_ids({"request_id": ["untrusted"]}, response) == []
    assert canary._request_ids({"request_id": {"value": "untrusted"}}, response) == []


def test_local_cancellation_after_submit_is_persisted_without_resubmission(
    fixture_options: Any,
) -> None:
    submits = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submits
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            submits += 1
            return _submit(request)
        raise asyncio.CancelledError

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
    assert submits == 1
    receipt = json.loads((fixture_options.output_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "local_cancelled"
    assert receipt["billing_outcome"] == "unknown"
    assert receipt["safe_error_code"] == "LOCAL_CANCELLED"
    assert receipt["recovery"] == {
        "encrypted_exact_submission_persisted": True,
        "raw_task_authority_persisted": True,
        "maximum_exact_submit_replays": 1,
        "upload_replayed_on_resume": False,
        "query_only_after_task_id": True,
        "can_count_as_recoverable_execution": True,
    }


def test_source_path_replacement_is_rejected_before_any_provider_byte(
    fixture_options: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = fixture_options.video_path.read_bytes()
    replacement = b"x" * len(original)
    provider_calls = 0

    def replace_during_key_load(_options: Any) -> tuple[str, str]:
        fixture_options.video_path.unlink()
        fixture_options.video_path.write_bytes(replacement)
        return API_KEY, "environment"

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("source binding must fail before provider I/O")

    monkeypatch.setattr(canary, "_load_api_key", replace_during_key_load)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await canary.execute_canary(
                fixture_options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )

    with pytest.raises(canary.CanaryError, match="SOURCE_CHANGED_BEFORE_UPLOAD"):
        asyncio.run(run())
    assert provider_calls == 0


def test_provider_duration_over_local_mediakit_cap_requires_reconciliation(
    fixture_options: Any,
) -> None:
    options = canary.CanaryOptions(**{**fixture_options.__dict__, "maximum_cny": Decimal("0.010000")})

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == canary.UPLOAD_TARGET_PATH:
            return _upload_target(request)
        if str(request.url) == UPLOAD_URL:
            await request.aread()
            return httpx.Response(200, request=request)
        if request.url.path == canary.SUBMIT_PATH:
            return _submit(request)
        return _poll(request, status="completed")

    async def run() -> dict[str, Any]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            receipt, _ = await canary.execute_canary(
                options,
                client=client,
                duration_probe=lambda _path: Decimal("60"),
            )
            return receipt

    receipt = asyncio.run(run())
    assert receipt["pricing"]["mediakit"]["postflight_public_estimate_cny"] == "0.010209"
    assert receipt["authorization"]["postflight_mediakit_estimate_exceeds_cap"] is True
    assert receipt["status"] == "completed_reconciliation_required"


def test_redaction_rejects_any_raw_url_or_forbidden_value() -> None:
    with pytest.raises(canary.CanaryError, match="RECEIPT_REDACTION_FAILED"):
        canary._assert_redacted({"value": "https://signed.example/private"}, forbidden=())
    with pytest.raises(canary.CanaryError, match="RECEIPT_REDACTION_FAILED"):
        canary._assert_redacted({"value": "private-secret"}, forbidden=("private-secret",))
