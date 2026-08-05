from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.ip_agent import mediakit_remux_ingress as ingress_subject
from deerflow.ip_agent import mediakit_remux_paid_operator as paid_subject
from deerflow.ip_agent.mediakit_remux_ingress import (
    MEDIAKIT_ENDPOINT,
    MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
    MediaKitRemuxHTTPSCandidate,
    MediaKitRemuxIngressError,
    MediaKitRemuxIngressReceipt,
    MediaKitRemuxSubmissionRecord,
    MediaKitRemuxSubmittedTaskRecord,
)
from deerflow.ip_agent.mediakit_remux_paid_operator import (
    MEDIAKIT_REMUX_OPERATOR_CAPPED_POLICY_VERSION,
    MEDIAKIT_REMUX_PAID_CAPABILITY,
    MEDIAKIT_REMUX_PAID_PROVIDER,
    MEDIAKIT_REMUX_PAID_SERVER,
    MEDIAKIT_REMUX_PAID_SKU,
    MEDIAKIT_REMUX_PAID_TOOL,
    MediaKitRemuxPaidOperatorError,
    build_mediakit_remux_paid_provider_request_sha256,
    run_paid_mediakit_remux,
)
from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_paid_calls import (
    EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
    PersonalIPPaidCallRepository,
)

CLIENT_TOKEN = "remux-paid-deterministic-token-v1"
TASK_ID = "provider-private-remux-task"
FILE_ID = "mediakit://provider-private-file"
UPLOAD_URL = "https://upload.tos-cn-beijing.volces.com/object?signature=private"
RUNTIME_URL = "https://output.vod.volcvideo.com/remux.mp4?signature=private"
MEDIAKIT_KEY = "private-mediakit-api-key"
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64


class _SimulatedProcessCrash(BaseException):
    pass


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _receipt(
    *,
    source_sha256: str,
    source_size: int,
    file_id: str = FILE_ID,
    client_token: str = CLIENT_TOKEN,
    task_id: str = TASK_ID,
    runtime_url: str = RUNTIME_URL,
) -> MediaKitRemuxIngressReceipt:
    completed_at = datetime.now(UTC)
    return MediaKitRemuxIngressReceipt.model_validate(
        {
            "contract_version": "ip-mediakit-remux-https-candidate-v1",
            "adapter_version": MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
            "provider": MEDIAKIT_REMUX_PAID_PROVIDER,
            "endpoint_sha256": _sha256_text(MEDIAKIT_ENDPOINT),
            "derived_from_source_sha256": source_sha256,
            "source_size_bytes": source_size,
            "source_hash_checks": 2,
            "source_hash_unchanged": True,
            "container_format": "MP4",
            "candidate_kind": "provider_remux_derivative",
            "candidate_byte_identity": "not_attested_equal_to_source",
            "provider_content_attestation": "unavailable",
            "upload_file_id_sha256": _sha256_text(file_id),
            "client_token_sha256": _sha256_text(client_token),
            "task_id_sha256": _sha256_text(task_id),
            "provider_request_id_sha256s": [],
            "runtime_url_sha256": _sha256_text(runtime_url),
            "request_sha256": ingress_subject._remux_request_sha256(
                source_sha256=source_sha256,
                source_size_bytes=source_size,
                file_id=file_id,
                client_token=client_token,
            ),
            "provider_response_sha256s": [SHA_B, SHA_C, SHA_D, SHA_E],
            "provider_response_sizes_bytes": [1, 1, 1, 1],
            "status": "completed",
            "completed_at": completed_at,
            "expires_at": completed_at + timedelta(hours=24),
            "observed_ttl_seconds": 24 * 60 * 60,
            "expiry_basis": "provider_reported",
            "poll_attempts": 1,
            "max_poll_attempts": 80,
            "poll_interval_seconds": 3.0,
            "response_size_limit_bytes": 1_048_576,
            "request_timeout_seconds": 120,
            "total_timeout_seconds": 600,
            "retries": 0,
            "billing_status": "provider_amount_unavailable",
        }
    )


def _submission_record(
    *,
    source_sha256: str,
    source_size: int,
    file_id: str = FILE_ID,
    client_token: str = CLIENT_TOKEN,
) -> MediaKitRemuxSubmissionRecord:
    return ingress_subject._build_submission_record(
        source_sha256=source_sha256,
        source_size_bytes=source_size,
        file_id=file_id,
        upload_url=UPLOAD_URL,
        client_token=client_token,
        response_hashes=[SHA_B, SHA_C],
        response_sizes=[1, 1],
        provider_request_id_sha256s=[],
    )


def _submitted_task_record(
    *,
    task_id: str = TASK_ID,
) -> MediaKitRemuxSubmittedTaskRecord:
    return MediaKitRemuxSubmittedTaskRecord.model_validate(
        {
            "contract_version": "ip-mediakit-remux-submitted-task-recovery-v1",
            "provider": MEDIAKIT_REMUX_PAID_PROVIDER,
            "capability": MEDIAKIT_REMUX_PAID_CAPABILITY,
            "task_id": task_id,
            "task_id_sha256": _sha256_text(task_id),
            "provider_response_sha256": SHA_D,
            "provider_response_size_bytes": 1,
            "provider_request_id_sha256s": [],
        }
    )


def _terminal_projection(
    receipt: MediaKitRemuxIngressReceipt,
    *,
    file_id: str = FILE_ID,
    client_token: str = CLIENT_TOKEN,
    task_id: str = TASK_ID,
    runtime_url: str = RUNTIME_URL,
) -> dict[str, Any]:
    return {
        "contract_version": "ip-mediakit-remux-provider-terminal-recovery-v2",
        "provider": MEDIAKIT_REMUX_PAID_PROVIDER,
        "capability": MEDIAKIT_REMUX_PAID_CAPABILITY,
        "upload_file_id_sha256": _sha256_text(file_id),
        "upload_url_sha256": _sha256_text(UPLOAD_URL),
        "client_token_sha256": _sha256_text(client_token),
        "task_id_sha256": _sha256_text(task_id),
        "runtime_url_sha256": _sha256_text(runtime_url),
        "provider_terminal_payload_sha256": SHA_C,
        "remux_receipt_sha256": _canonical_sha256(receipt.model_dump(mode="json")),
        "expires_at": receipt.expires_at.astimezone(UTC).isoformat(),
    }


async def _admitted_scope(
    tmp_path: Path,
    *,
    capability: str = MEDIAKIT_REMUX_PAID_CAPABILITY,
) -> tuple[PersonalIPPaidCallRepository, dict[str, Any], Path, str]:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path / "db")))
    session_factory = get_session_factory()
    assert session_factory is not None
    repository = PersonalIPPaidCallRepository(
        session_factory,
        provider_task_cipher=ChannelCredentialCipher.from_key("remux-paid-recovery-test-key-0000000000000000000000"),
    )
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-paid-remux-source")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    now = datetime.now(UTC)
    requested = await repository.request_call(
        owner_user_id="owner-remux",
        request_key=f"remux-request-{capability}",
        scope_kind="run",
        thread_id="operator-thread",
        origin_run_id="operator-origin-run",
        server_name=MEDIAKIT_REMUX_PAID_SERVER,
        tool_name=MEDIAKIT_REMUX_PAID_TOOL,
        tool_args_sha256=SHA_E,
        provider=MEDIAKIT_REMUX_PAID_PROVIDER,
        capability=capability,
        model=MEDIAKIT_REMUX_INGRESS_ADAPTER_VERSION,
        sku=MEDIAKIT_REMUX_PAID_SKU,
        provider_label="MediaKit",
        capability_label="Managed HTTPS remux",
        object_ref_label="sealed source 1234...abcd",
        source_duration_millis=70_867,
        source_sha256=source_sha256,
        stage_digest=SHA_B,
        provider_request_sha256=build_mediakit_remux_paid_provider_request_sha256(
            source_sha256=source_sha256,
            client_token=CLIENT_TOKEN,
        ),
        maximum_amount_micros=500_000,
        currency="CNY",
        billing_basis="local operator risk limit; provider amount is not quoted",
        policy_version=(MEDIAKIT_REMUX_OPERATOR_CAPPED_POLICY_VERSION if capability == MEDIAKIT_REMUX_PAID_CAPABILITY else EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION),
        price_version="mediakit-remux-2026-08-03",
        provider_input_attested=False,
        evidence_coverage="partial",
        warning_code="provider_content_hash_unattested",
        expires_at=now + timedelta(minutes=15),
        price_status="operator_capped",
        now=now,
    )
    approved = await repository.approve(
        requested["id"],
        owner_user_id="owner-remux",
        event_key="owner-approved-remux",
        expected_request_digest=requested["request_digest"],
        approval_digest=SHA_C,
        expected_event_count=1,
        now=now + timedelta(seconds=1),
    )
    assert approved is not None
    reserved = await repository.reserve(
        requested["id"],
        owner_user_id="owner-remux",
        event_key="reserved-remux",
        expected_request_digest=requested["request_digest"],
        execution_run_id="operator-execution-run",
        amount_micros=400_000,
        expected_event_count=2,
        now=now + timedelta(seconds=2),
    )
    assert reserved is not None
    admitted = await repository.admit(
        requested["id"],
        owner_user_id="owner-remux",
        event_key="admitted-remux",
        expected_request_digest=requested["request_digest"],
        execution_run_id="operator-execution-run",
        admission_jti="remux-paid-admission-jti-0001",
        admission_proof_digest=SHA_D,
        expected_event_count=3,
        now=now + timedelta(seconds=3),
    )
    assert admitted is not None
    return repository, admitted, source, source_sha256


async def _primed_observer(
    repository: PersonalIPPaidCallRepository,
    admitted: dict[str, Any],
    source_size: int,
    source_sha256: str,
) -> Any:
    observer = paid_subject._PaidRecoveryObserver(
        repository=repository,
        scope_id=admitted["id"],
        owner_user_id="owner-remux",
        request_digest=admitted["request_digest"],
        execution_run_id="operator-execution-run",
        source_sha256=source_sha256,
        client_token=CLIENT_TOKEN,
    )
    await observer.provider_submission_prepared(
        submission_record=_submission_record(
            source_sha256=source_sha256,
            source_size=source_size,
        ),
        client_token=CLIENT_TOKEN,
    )
    await observer.provider_task_submission_confirmed(submitted_task_record=_submitted_task_record())
    return observer


async def _complete_fake_ingress(
    *,
    source_path: str | Path,
    expected_source_sha256: str,
    mediakit_api_key: str,
    client_token: str,
    task_observer: Any,
    file_id: str = FILE_ID,
) -> MediaKitRemuxHTTPSCandidate:
    assert Path(source_path).is_file()
    assert mediakit_api_key == MEDIAKIT_KEY
    submission = _submission_record(
        source_sha256=expected_source_sha256,
        source_size=Path(source_path).stat().st_size,
        file_id=file_id,
        client_token=client_token,
    )
    await task_observer.provider_submission_prepared(
        submission_record=submission,
        client_token=client_token,
    )
    await task_observer.provider_task_submission_confirmed(submitted_task_record=_submitted_task_record())
    await task_observer.provider_task_running(
        raw_task_id=TASK_ID,
        observed_status="running",
    )
    receipt = _receipt(
        source_sha256=expected_source_sha256,
        source_size=Path(source_path).stat().st_size,
        file_id=file_id,
    )
    await task_observer.provider_task_terminal(
        raw_task_id=TASK_ID,
        terminal_status="completed",
        terminal_envelope=_terminal_projection(
            receipt,
            file_id=file_id,
            client_token=client_token,
        ),
    )
    return MediaKitRemuxHTTPSCandidate(runtime_url=RUNTIME_URL, receipt=receipt)


async def _complete_fake_recovery(
    *,
    source_path: str | Path,
    expected_source_sha256: str,
    mediakit_api_key: str,
    recovery_request: Any,
    task_observer: Any,
) -> MediaKitRemuxHTTPSCandidate:
    assert Path(source_path).is_file()
    assert mediakit_api_key == MEDIAKIT_KEY
    assert recovery_request.submission.source_sha256 == expected_source_sha256
    if recovery_request.action == "replay_submission_once":
        await task_observer.provider_task_submission_confirmed(submitted_task_record=_submitted_task_record())
    else:
        assert recovery_request.action == "query_existing_task"
        assert recovery_request.submitted_task.task_id == TASK_ID
    receipt = _receipt(
        source_sha256=expected_source_sha256,
        source_size=Path(source_path).stat().st_size,
    )
    await task_observer.provider_task_terminal(
        raw_task_id=TASK_ID,
        terminal_status="completed",
        terminal_envelope=_terminal_projection(receipt),
    )
    return MediaKitRemuxHTTPSCandidate(runtime_url=RUNTIME_URL, receipt=receipt)


@pytest.mark.asyncio
async def test_real_ingress_awaits_recovery_before_first_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "observer-source.mp4"
    source.write_bytes(b"observer-source")
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    events: list[str] = []

    class _Observer:
        async def before_provider_submit(self, **kwargs: Any) -> None:
            assert kwargs == {"upload_file_id": FILE_ID, "client_token": CLIENT_TOKEN}
            events.append("before_submit")

        async def provider_task_submitted(self, **kwargs: Any) -> None:
            assert kwargs == {"raw_task_id": TASK_ID}
            events.append("submitted")

        async def provider_task_running(self, **_kwargs: Any) -> None:
            events.append("running")

        async def provider_task_terminal(self, **kwargs: Any) -> None:
            assert kwargs["raw_task_id"] == TASK_ID
            assert kwargs["terminal_status"] == "completed"
            envelope = kwargs["terminal_envelope"]
            assert envelope["contract_version"] == "ip-mediakit-remux-provider-terminal-recovery-v2"
            assert envelope["upload_file_id_sha256"] == _sha256_text(FILE_ID)
            assert envelope["client_token_sha256"] == _sha256_text(CLIENT_TOKEN)
            assert envelope["task_id_sha256"] == _sha256_text(TASK_ID)
            assert envelope["runtime_url_sha256"] == _sha256_text(RUNTIME_URL)
            assert FILE_ID not in str(envelope)
            assert CLIENT_TOKEN not in str(envelope)
            assert TASK_ID not in str(envelope)
            assert RUNTIME_URL not in str(envelope)
            events.append("terminal")

    async def fake_request_bytes(
        _client: httpx.AsyncClient,
        **kwargs: Any,
    ) -> tuple[httpx.Response, bytes]:
        stage = kwargs["stage"]
        if stage == "UPLOAD_TARGET":
            payload = {
                "success": True,
                "result": {
                    "file_id": FILE_ID,
                    "method": "PUT",
                    "upload_url": UPLOAD_URL,
                    "upload_headers": {},
                },
            }
        elif stage == "MEDIA_UPLOAD":
            async for _chunk in kwargs["content"]:
                pass
            payload = {}
        elif stage == "REMUX_SUBMIT":
            assert events == ["before_submit"]
            payload = {"success": True, "task_id": TASK_ID}
        elif stage == "REMUX_POLL":
            assert events == ["before_submit", "submitted"]
            payload = {
                "success": True,
                "status": "completed",
                "task_id": TASK_ID,
                "expires_at": int((datetime.now(UTC) + timedelta(hours=24)).timestamp()),
                "result": {"video_url": RUNTIME_URL},
            }
        else:
            raise AssertionError(f"unexpected stage {stage}")
        encoded = json.dumps(payload).encode("utf-8")
        return httpx.Response(200), encoded

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(ingress_subject, "_request_bytes", fake_request_bytes)
    monkeypatch.setattr(
        ingress_subject,
        "_validate_runtime_https_url",
        lambda value, **_kwargs: str(value),
    )
    monkeypatch.setattr(ingress_subject.asyncio, "sleep", no_sleep)

    candidate = await ingress_subject.create_mediakit_remux_https_candidate(
        source_path=source,
        expected_source_sha256=source_sha256,
        mediakit_api_key=MEDIAKIT_KEY,
        client_token=CLIENT_TOKEN,
        task_observer=_Observer(),
    )

    assert candidate.runtime_url == RUNTIME_URL
    assert events == ["before_submit", "submitted", "terminal"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "terminal_status",
    ["Completed", " completed", "completed ", "unknown", ""],
)
async def test_paid_observer_rejects_noncanonical_terminal_status(
    tmp_path: Path,
    terminal_status: str,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    receipt = _receipt(source_sha256=source_sha256, source_size=source.stat().st_size)
    try:
        observer = await _primed_observer(
            repository,
            admitted,
            source.stat().st_size,
            source_sha256,
        )
        with pytest.raises(ValueError, match="terminal status must be normalized"):
            await observer.provider_task_terminal(
                raw_task_id=TASK_ID,
                terminal_status=terminal_status,
                terminal_envelope=_terminal_projection(receipt),
            )
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None
        assert current["provider_task_status"] == "submitted"
        assert current["provider_terminal_status"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_observer_requires_completed_terminal_summaries(tmp_path: Path) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    receipt = _receipt(source_sha256=source_sha256, source_size=source.stat().st_size)
    incomplete = _terminal_projection(receipt)
    incomplete.pop("runtime_url_sha256")
    try:
        observer = await _primed_observer(
            repository,
            admitted,
            source.stat().st_size,
            source_sha256,
        )
        with pytest.raises(ValueError, match="terminal recovery fields are invalid"):
            await observer.provider_task_terminal(
                raw_task_id=TASK_ID,
                terminal_status="completed",
                terminal_envelope=incomplete,
            )
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None
        assert current["provider_task_status"] == "submitted"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_success_returns_runtime_url_but_persists_hashes_only(
    tmp_path: Path,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    try:
        result = await run_paid_mediakit_remux(
            repository=repository,
            owner_user_id="owner-remux",
            scope_id=admitted["id"],
            expected_request_digest=admitted["request_digest"],
            execution_run_id="operator-execution-run",
            source_path=source,
            expected_source_sha256=source_sha256,
            client_token=CLIENT_TOKEN,
            mediakit_api_key=MEDIAKIT_KEY,
            ingress_runner=_complete_fake_ingress,
        )

        assert result.runtime_url == RUNTIME_URL
        assert result.paid_execution_receipt.paid_call_status == "reconciliation_required"
        assert result.paid_execution_receipt.chat_authorization == "required_separate_paid_call"
        assert result.paid_execution_receipt.chat_capability == "video_understanding_chat"
        recovery = await repository.list_recoverable_provider_tasks(owner_user_id="owner-remux")
        assert len(recovery) == 1
        assert recovery[0]["client_token"] == CLIENT_TOKEN
        assert recovery[0]["raw_task_id"] == TASK_ID
        terminal_envelope = recovery[0]["terminal_envelope"]
        assert terminal_envelope["runtime_url_sha256"] == _sha256_text(RUNTIME_URL)
        assert terminal_envelope["upload_file_id_sha256"] == _sha256_text(FILE_ID)
        assert terminal_envelope["task_id_sha256"] == _sha256_text(TASK_ID)
        for secret in (FILE_ID, UPLOAD_URL, CLIENT_TOKEN, TASK_ID, RUNTIME_URL):
            assert secret not in str(terminal_envelope)

        public_text = result.remux_receipt.model_dump_json() + result.paid_execution_receipt.model_dump_json() + repr(result) + str(await repository.get(admitted["id"], owner_user_id="owner-remux"))
        for secret in (CLIENT_TOKEN, FILE_ID, TASK_ID, UPLOAD_URL, RUNTIME_URL, MEDIAKIT_KEY):
            assert secret not in public_text
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_rejects_candidate_b_after_recording_terminal_a(
    tmp_path: Path,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    file_b = "mediakit://different-provider-file"
    task_b = "different-provider-task"
    runtime_b = "https://output.vod.volcvideo.com/different.mp4?signature=private-b"

    async def records_a_returns_b(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        observer = kwargs["task_observer"]
        await observer.provider_submission_prepared(
            submission_record=_submission_record(
                source_sha256=kwargs["expected_source_sha256"],
                source_size=Path(kwargs["source_path"]).stat().st_size,
            ),
            client_token=kwargs["client_token"],
        )
        await observer.provider_task_submission_confirmed(submitted_task_record=_submitted_task_record())
        receipt_a = _receipt(
            source_sha256=kwargs["expected_source_sha256"],
            source_size=Path(kwargs["source_path"]).stat().st_size,
        )
        await observer.provider_task_terminal(
            raw_task_id=TASK_ID,
            terminal_status="completed",
            terminal_envelope=_terminal_projection(receipt_a),
        )
        receipt_b = _receipt(
            source_sha256=kwargs["expected_source_sha256"],
            source_size=Path(kwargs["source_path"]).stat().st_size,
            file_id=file_b,
            task_id=task_b,
            runtime_url=runtime_b,
        )
        return MediaKitRemuxHTTPSCandidate(runtime_url=runtime_b, receipt=receipt_b)

    try:
        with pytest.raises(MediaKitRemuxPaidOperatorError) as captured:
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=CLIENT_TOKEN,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=records_a_returns_b,
            )
        assert captured.value.code == "REMUX_RECEIPT_BINDING_MISMATCH"
        assert captured.value.reconciliation_required is True
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None
        assert current["status"] == "reconciliation_required"
        assert current["provider_task_id_sha256"] == _sha256_text(TASK_ID)
        assert current["provider_task_id_sha256"] != _sha256_text(task_b)
        for secret in (file_b, task_b, runtime_b):
            assert secret not in str(current)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_settlement_failure_is_bounded_without_detail_leak(
    tmp_path: Path,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    leaked_detail = "https://provider.example/private?token=must-not-leak"

    class _FailingSettlementRepository:
        def __getattr__(self, name: str) -> Any:
            return getattr(repository, name)

        async def settle(self, scope_id: str, **kwargs: Any) -> dict[str, Any]:
            del scope_id, kwargs
            raise RuntimeError(leaked_detail)

    try:
        with pytest.raises(MediaKitRemuxPaidOperatorError) as captured:
            await run_paid_mediakit_remux(
                repository=_FailingSettlementRepository(),
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=CLIENT_TOKEN,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=_complete_fake_ingress,
            )
        assert captured.value.code == "PAID_CALL_RECONCILIATION_NOT_RECORDED"
        assert captured.value.reconciliation_required is True
        assert leaked_detail not in str(captured.value)
        assert captured.value.__cause__ is None
        assert captured.value.__suppress_context__ is True
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None
        assert current["status"] == "admitted"
        assert current["provider_task_status"] == "terminal"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_callback_failure_is_reconciled_and_secrets_stay_encrypted(
    tmp_path: Path,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)

    class _FailingRepository:
        def __getattr__(self, name: str) -> Any:
            return getattr(repository, name)

        async def record_provider_task_submission_confirmed(
            self,
            scope_id: str,
            **kwargs: Any,
        ) -> dict[str, Any]:
            del scope_id, kwargs
            raise RuntimeError("database callback detail must be hidden")

    async def failing_ingress(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        observer = kwargs["task_observer"]
        await observer.provider_submission_prepared(
            submission_record=_submission_record(
                source_sha256=kwargs["expected_source_sha256"],
                source_size=Path(kwargs["source_path"]).stat().st_size,
            ),
            client_token=kwargs["client_token"],
        )
        try:
            await observer.provider_task_submission_confirmed(submitted_task_record=_submitted_task_record())
        except Exception:
            raise MediaKitRemuxIngressError(
                "PROVIDER_TASK_RECOVERY_FAILED",
                billing_outcome="unknown",
            ) from None
        raise AssertionError("callback unexpectedly succeeded")

    try:
        with pytest.raises(MediaKitRemuxPaidOperatorError) as captured:
            await run_paid_mediakit_remux(
                repository=_FailingRepository(),
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=CLIENT_TOKEN,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=failing_ingress,
            )
        assert captured.value.code == "PROVIDER_TASK_RECOVERY_FAILED"
        assert captured.value.reconciliation_required is False

        public = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert public is not None
        assert public["status"] == "admitted"
        assert public["provider_task_status"] == "submitting"
        safe_text = str(public) + str(captured.value)
        for secret in (CLIENT_TOKEN, FILE_ID, TASK_ID, UPLOAD_URL, RUNTIME_URL):
            assert secret not in safe_text
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_submit_crash_stops_without_reupload_or_resubmit(
    tmp_path: Path,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    submitted_tokens: list[str] = []

    async def crash_after_submit(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        observer = kwargs["task_observer"]
        await observer.provider_submission_prepared(
            submission_record=_submission_record(
                source_sha256=kwargs["expected_source_sha256"],
                source_size=Path(kwargs["source_path"]).stat().st_size,
            ),
            client_token=kwargs["client_token"],
        )
        submitted_tokens.append(kwargs["client_token"])
        raise _SimulatedProcessCrash

    async def should_not_reupload(**_kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        raise AssertionError("unfinished provider task must use query recovery, not re-upload")

    recovery_actions: list[str] = []

    async def recover_once(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        recovery_actions.append(kwargs["recovery_request"].action)
        return await _complete_fake_recovery(**kwargs)

    try:
        with pytest.raises(_SimulatedProcessCrash):
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=CLIENT_TOKEN,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=crash_after_submit,
            )

        interrupted = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert interrupted is not None
        assert interrupted["status"] == "admitted"
        assert interrupted["provider_task_status"] == "submitting"

        result = await run_paid_mediakit_remux(
            repository=repository,
            owner_user_id="owner-remux",
            scope_id=admitted["id"],
            expected_request_digest=admitted["request_digest"],
            execution_run_id="operator-execution-run",
            source_path=source,
            expected_source_sha256=source_sha256,
            client_token=None,
            mediakit_api_key=MEDIAKIT_KEY,
            ingress_runner=should_not_reupload,
            recovery_runner=recover_once,
        )

        assert submitted_tokens == [CLIENT_TOKEN]
        assert recovery_actions == ["replay_submission_once"]
        assert result.paid_execution_receipt.recovered_from_encrypted_state is True
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None and current["status"] == "reconciliation_required"
        public_text = str(current) + repr(result)
        for secret in (CLIENT_TOKEN, FILE_ID, TASK_ID, UPLOAD_URL, RUNTIME_URL, MEDIAKIT_KEY):
            assert secret not in public_text
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_completed_terminal_is_hash_only_and_requires_query_recovery(
    tmp_path: Path,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    provider_calls = 0
    refreshed_runtime_url = "https://output.vod.volcvideo.com/remux-refreshed.mp4?signature=private-2"

    async def crash_after_terminal(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        nonlocal provider_calls
        provider_calls += 1
        await _complete_fake_ingress(**kwargs)
        raise _SimulatedProcessCrash

    async def should_not_recall_provider(**_kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        nonlocal provider_calls
        provider_calls += 1
        assert _kwargs["recovery_request"].action == "query_existing_task"
        receipt = _receipt(
            source_sha256=_kwargs["expected_source_sha256"],
            source_size=Path(_kwargs["source_path"]).stat().st_size,
            runtime_url=refreshed_runtime_url,
        )
        await _kwargs["task_observer"].provider_task_terminal(
            raw_task_id=TASK_ID,
            terminal_status="completed",
            terminal_envelope=_terminal_projection(
                receipt,
                runtime_url=refreshed_runtime_url,
            ),
        )
        return MediaKitRemuxHTTPSCandidate(
            runtime_url=refreshed_runtime_url,
            receipt=receipt,
        )

    try:
        with pytest.raises(_SimulatedProcessCrash):
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=CLIENT_TOKEN,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=crash_after_terminal,
            )
        terminal = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert terminal is not None
        assert terminal["status"] == "admitted"
        assert terminal["provider_task_status"] == "terminal"
        assert terminal["provider_terminal_status"] == "completed"
        recovery = await repository.list_recoverable_provider_tasks(owner_user_id="owner-remux")
        assert len(recovery) == 1
        terminal_envelope = recovery[0]["terminal_envelope"]
        assert terminal_envelope["runtime_url_sha256"] == _sha256_text(RUNTIME_URL)
        for secret in (FILE_ID, UPLOAD_URL, CLIENT_TOKEN, TASK_ID, RUNTIME_URL):
            assert secret not in str(terminal_envelope)

        result = await run_paid_mediakit_remux(
            repository=repository,
            owner_user_id="owner-remux",
            scope_id=admitted["id"],
            expected_request_digest=admitted["request_digest"],
            execution_run_id="operator-execution-run",
            source_path=source,
            expected_source_sha256=source_sha256,
            client_token=None,
            mediakit_api_key=MEDIAKIT_KEY,
            ingress_runner=lambda **_kwargs: pytest.fail("fresh ingress must not run"),
            recovery_runner=should_not_recall_provider,
        )

        assert provider_calls == 2
        assert result.runtime_url == refreshed_runtime_url
        assert result.paid_execution_receipt.recovered_from_encrypted_state is True
        assert result.paid_execution_receipt.provider_terminal_sha256 == terminal["provider_terminal_sha256"]
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None and current["status"] == "reconciliation_required"

        replayed_after_lost_return = await run_paid_mediakit_remux(
            repository=repository,
            owner_user_id="owner-remux",
            scope_id=admitted["id"],
            expected_request_digest=admitted["request_digest"],
            execution_run_id="operator-execution-run",
            source_path=source,
            expected_source_sha256=source_sha256,
            client_token=None,
            mediakit_api_key=MEDIAKIT_KEY,
            recovery_runner=should_not_recall_provider,
        )
        assert provider_calls == 3
        assert replayed_after_lost_return.runtime_url == refreshed_runtime_url
        assert replayed_after_lost_return.paid_execution_receipt.provider_terminal_sha256 == terminal["provider_terminal_sha256"]
    finally:
        await close_engine()


@pytest.mark.asyncio
@pytest.mark.parametrize("persisted_status", ["submitted", "running"])
async def test_paid_remux_query_interruption_keeps_exact_task_recoverable(
    tmp_path: Path,
    persisted_status: str,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    actions: list[str] = []
    try:
        observer = await _primed_observer(
            repository,
            admitted,
            source.stat().st_size,
            source_sha256,
        )
        if persisted_status == "running":
            await observer.provider_task_running(
                raw_task_id=TASK_ID,
                observed_status="running",
            )

        async def interrupted_query(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
            actions.append(kwargs["recovery_request"].action)
            raise MediaKitRemuxIngressError(
                "REMUX_POLL_TIMEOUT",
                billing_outcome="unknown",
            )

        with pytest.raises(MediaKitRemuxPaidOperatorError) as captured:
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=None,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=lambda **_kwargs: pytest.fail("fresh ingress must not run"),
                recovery_runner=interrupted_query,
            )

        assert actions == ["query_existing_task"]
        assert captured.value.code == "REMUX_POLL_TIMEOUT"
        assert captured.value.reconciliation_required is False
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None
        assert current["status"] == "admitted"
        assert current["provider_task_status"] == persisted_status
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_submit_replay_claim_never_permits_second_post(
    tmp_path: Path,
) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(tmp_path)
    replay_calls = 0

    async def crash_after_prepared(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        await kwargs["task_observer"].provider_submission_prepared(
            submission_record=_submission_record(
                source_sha256=kwargs["expected_source_sha256"],
                source_size=Path(kwargs["source_path"]).stat().st_size,
            ),
            client_token=kwargs["client_token"],
        )
        raise _SimulatedProcessCrash

    async def interrupted_replay(**kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        nonlocal replay_calls
        replay_calls += 1
        assert kwargs["recovery_request"].action == "replay_submission_once"
        raise MediaKitRemuxIngressError(
            "REMUX_SUBMIT_TIMEOUT",
            billing_outcome="unknown",
        )

    try:
        with pytest.raises(_SimulatedProcessCrash):
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=CLIENT_TOKEN,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=crash_after_prepared,
            )
        with pytest.raises(MediaKitRemuxPaidOperatorError) as first:
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=None,
                mediakit_api_key=MEDIAKIT_KEY,
                recovery_runner=interrupted_replay,
            )
        assert first.value.code == "REMUX_SUBMIT_TIMEOUT"
        assert first.value.reconciliation_required is False

        with pytest.raises(MediaKitRemuxPaidOperatorError) as second:
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=None,
                mediakit_api_key=MEDIAKIT_KEY,
                recovery_runner=interrupted_replay,
            )
        assert replay_calls == 1
        assert second.value.code == "PROVIDER_SUBMISSION_REPLAY_ALREADY_CLAIMED"
        current = await repository.get(admitted["id"], owner_user_id="owner-remux")
        assert current is not None
        assert current["status"] == "admitted"
        assert current["provider_task_status"] == "submitting"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_remux_rejects_chat_scope_without_calling_provider(tmp_path: Path) -> None:
    repository, admitted, source, source_sha256 = await _admitted_scope(
        tmp_path,
        capability="video_understanding_chat",
    )
    provider_called = False

    async def should_not_run(**_kwargs: Any) -> MediaKitRemuxHTTPSCandidate:
        nonlocal provider_called
        provider_called = True
        raise AssertionError("remux provider must not run for a Chat authorization")

    try:
        with pytest.raises(MediaKitRemuxPaidOperatorError) as captured:
            await run_paid_mediakit_remux(
                repository=repository,
                owner_user_id="owner-remux",
                scope_id=admitted["id"],
                expected_request_digest=admitted["request_digest"],
                execution_run_id="operator-execution-run",
                source_path=source,
                expected_source_sha256=source_sha256,
                client_token=CLIENT_TOKEN,
                mediakit_api_key=MEDIAKIT_KEY,
                ingress_runner=should_not_run,
            )
        assert captured.value.code == "PAID_CALL_BINDING_MISMATCH"
        assert provider_called is False
    finally:
        await close_engine()
