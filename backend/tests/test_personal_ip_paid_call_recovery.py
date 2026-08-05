from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_paid_calls import PersonalIPPaidCallRepository
from deerflow.persistence.personal_ip_paid_calls.model import PersonalIPPaidCallScopeRow

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
CLIENT_TOKEN = "mediakit-client-token-recovery-0001"
RAW_TASK_ID = "mediakit-task-private-0001"
UPLOAD_FILE_ID = "mediakit://private-upload-file-0001"
UPLOAD_URL = "https://tob-upload-y-d.volcvod.com/private-upload?signature=secret"
MEDIAKIT_ENDPOINT = "https://mediakit.cn-beijing.volces.com"
REMUX_CAPABILITY = "managed_https_ingress_remux"
STRATEGY_CAPABILITY = "video_understanding_smart_strategy"
STRATEGY_CLIENT_TOKEN = "strategy-owner-call-fixed-token-001"
STRATEGY_TASK_ID = "amk-tool-video-understand-router-private-001"
STRATEGY_VIDEO_REF = "mediakit://private-video-strategy-source-001"
STRATEGY_PROMPT = "Only return bounded chronological audiovisual observations."
STRATEGY_ENDPOINT = "https://mediakit.cn-beijing.volces.com/api/v1/tools/video-understand-router"


def _canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _submission_envelope(
    *,
    client_token: str = CLIENT_TOKEN,
    upload_file_id: str = UPLOAD_FILE_ID,
) -> dict:
    upload_file_id_sha256 = hashlib.sha256(upload_file_id.encode()).hexdigest()
    client_token_sha256 = hashlib.sha256(client_token.encode()).hexdigest()
    request_projection = {
        "contract_version": "ip-mediakit-remux-https-candidate-v1",
        "adapter_version": "volcengine-mediakit-remux-https-ingress-v1",
        "endpoint": MEDIAKIT_ENDPOINT,
        "derived_from_source_sha256": SHA_A,
        "source_size_bytes": 1_024,
        "upload_file_id_sha256": upload_file_id_sha256,
        "container_format": "MP4",
        "client_token_sha256": client_token_sha256,
        "retries": 0,
    }
    return {
        "contract_version": "ip-mediakit-remux-submission-recovery-v1",
        "provider": "volcengine-mediakit",
        "capability": REMUX_CAPABILITY,
        "adapter_version": "volcengine-mediakit-remux-https-ingress-v1",
        "endpoint_sha256": hashlib.sha256(MEDIAKIT_ENDPOINT.encode()).hexdigest(),
        "source_sha256": SHA_A,
        "source_size_bytes": 1_024,
        "upload_file_id": upload_file_id,
        "upload_file_id_sha256": upload_file_id_sha256,
        "upload_url_sha256": hashlib.sha256(UPLOAD_URL.encode()).hexdigest(),
        "client_token_sha256": client_token_sha256,
        "container_format": "MP4",
        "request_sha256": _canonical_sha256(request_projection),
        "submit_body_sha256": _canonical_sha256(
            {
                "video_url": upload_file_id,
                "container_format": "MP4",
                "client_token": client_token,
            }
        ),
        "provider_response_sha256s": [SHA_C, SHA_D],
        "provider_response_sizes_bytes": [128, 0],
        "provider_request_id_sha256s": [SHA_E],
        "retries": 0,
    }


def _submitted_task_record(*, task_id: str = RAW_TASK_ID) -> dict:
    return {
        "contract_version": "ip-mediakit-remux-submitted-task-recovery-v1",
        "provider": "volcengine-mediakit",
        "capability": REMUX_CAPABILITY,
        "task_id": task_id,
        "task_id_sha256": hashlib.sha256(task_id.encode()).hexdigest(),
        "provider_response_sha256": SHA_B,
        "provider_response_size_bytes": 256,
        "provider_request_id_sha256s": [SHA_C],
    }


def _strategy_request_projection(
    *,
    client_token: str = STRATEGY_CLIENT_TOKEN,
    video_ref: str = STRATEGY_VIDEO_REF,
) -> dict:
    return {
        "contract_version": "ip-mediakit-video-strategy-request-v1",
        "adapter_version": "volcengine-mediakit-video-strategy-research-v1",
        "profile_version": "ip-editing-audiovisual-research-observation-v1",
        "provider_tool_name": "video-understand-router",
        "method": "POST",
        "endpoint_sha256": hashlib.sha256(STRATEGY_ENDPOINT.encode()).hexdigest(),
        "body": {
            "video_urls": [video_ref],
            "prompt": STRATEGY_PROMPT,
            "level": "Quality",
            "scene": "editing",
            "manual_option": {"need_audio": True},
            "client_token": client_token,
        },
        "automatic_retries": 0,
        "callback_url_mode": "omitted",
    }


def _strategy_submission_envelope(
    *,
    client_token: str = STRATEGY_CLIENT_TOKEN,
    video_ref: str = STRATEGY_VIDEO_REF,
) -> dict:
    request_projection = _strategy_request_projection(
        client_token=client_token,
        video_ref=video_ref,
    )
    submit_body = request_projection["body"]
    return {
        "contract_version": "ip-mediakit-video-strategy-submission-recovery-v1",
        "provider": "volcengine-mediakit",
        "capability": STRATEGY_CAPABILITY,
        "adapter_version": "volcengine-mediakit-video-strategy-research-v1",
        "profile_version": "ip-editing-audiovisual-research-observation-v1",
        "endpoint_sha256": request_projection["endpoint_sha256"],
        "source_sha256": SHA_A,
        "provider_input_ref_sha256": hashlib.sha256(video_ref.encode()).hexdigest(),
        "request_sha256": _canonical_sha256(request_projection),
        "submit_body_sha256": _canonical_sha256(submit_body),
        "submit_body": submit_body,
        "automatic_retries": 0,
        "callback_url_mode": "omitted",
    }


def _strategy_submitted_task_record(
    *,
    task_id: str = STRATEGY_TASK_ID,
    client_token: str = STRATEGY_CLIENT_TOKEN,
    video_ref: str = STRATEGY_VIDEO_REF,
) -> dict:
    request_sha256 = _canonical_sha256(
        _strategy_request_projection(
            client_token=client_token,
            video_ref=video_ref,
        )
    )
    return {
        "contract_version": "ip-mediakit-video-strategy-submitted-task-recovery-v1",
        "provider": "volcengine-mediakit",
        "capability": STRATEGY_CAPABILITY,
        "task_id": task_id,
        "task_id_sha256": hashlib.sha256(task_id.encode()).hexdigest(),
        "request_sha256": request_sha256,
        "client_token_sha256": hashlib.sha256(client_token.encode()).hexdigest(),
        "provider_response_sha256": SHA_B,
        "provider_response_size_bytes": 256,
        "provider_request_id_sha256s": [SHA_C],
    }


async def _admitted_repository(
    tmp_path,
    *,
    capability: str = REMUX_CAPABILITY,
    provider_request_sha256: str = SHA_D,
    request_key: str = "recovery-remux-1",
) -> tuple[PersonalIPPaidCallRepository, dict]:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path / "db")))
    session_factory = get_session_factory()
    assert session_factory is not None
    repository = PersonalIPPaidCallRepository(
        session_factory,
        provider_task_cipher=ChannelCredentialCipher.from_key("provider-task-recovery-test-key-000000000000000000"),
    )
    requested = await repository.request_call(
        owner_user_id="owner-1",
        request_key=request_key,
        scope_kind="run",
        thread_id="thread-1",
        origin_run_id="origin-run-1",
        server_name="ip_evidence",
        tool_name="inspect_reference_videos",
        tool_args_sha256=SHA_E,
        provider="volcengine-mediakit",
        capability=capability,
        model=("volcengine-mediakit-remux-https-ingress-v1" if capability == REMUX_CAPABILITY else "volcengine-mediakit-video-strategy-research-v1"),
        sku=("remux-video" if capability == REMUX_CAPABILITY else "video-understand-router"),
        provider_label="MediaKit",
        capability_label=("Remux" if capability == REMUX_CAPABILITY else "Video Strategy"),
        object_ref_label="reference aaaa...aaaa",
        source_duration_millis=8_000,
        source_sha256=SHA_A,
        stage_digest=SHA_B,
        provider_request_sha256=provider_request_sha256,
        maximum_amount_micros=500_000,
        currency="CNY",
        billing_basis="official quoted maximum",
        policy_version="paid-call-policy-v1",
        price_version="mediakit-price-v1",
        provider_input_attested=False,
        evidence_coverage="partial",
        warning_code="provider_content_hash_unattested",
        expires_at=NOW + timedelta(minutes=15),
        now=NOW,
    )
    approved = await repository.approve(
        requested["id"],
        owner_user_id="owner-1",
        event_key="approve-recovery",
        expected_request_digest=requested["request_digest"],
        approval_digest=SHA_C,
        expected_event_count=1,
        now=NOW + timedelta(seconds=1),
    )
    assert approved is not None
    reserved = await repository.reserve(
        requested["id"],
        owner_user_id="owner-1",
        event_key="reserve-recovery",
        expected_request_digest=requested["request_digest"],
        execution_run_id="execution-run-1",
        amount_micros=400_000,
        expected_event_count=2,
        now=NOW + timedelta(seconds=2),
    )
    assert reserved is not None
    admitted = await repository.admit(
        requested["id"],
        owner_user_id="owner-1",
        event_key="admit-recovery",
        expected_request_digest=requested["request_digest"],
        execution_run_id="execution-run-1",
        admission_jti="provider-task-recovery-admission-0001",
        admission_proof_digest=SHA_D,
        expected_event_count=3,
        now=NOW + timedelta(seconds=3),
    )
    assert admitted is not None
    return repository, admitted


@pytest.mark.asyncio
async def test_provider_task_recovery_is_encrypted_owner_scoped_and_replayable(
    tmp_path,
) -> None:
    repository, admitted = await _admitted_repository(tmp_path)
    try:
        submitting = await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitting",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=REMUX_CAPABILITY,
            source_sha256=SHA_A,
            client_token=CLIENT_TOKEN,
            submission_envelope=_submission_envelope(),
            now=NOW + timedelta(seconds=4),
        )
        assert submitting is not None
        assert submitting["status"] == "admitted"
        assert submitting["provider_task_status"] == "submitting"
        assert "encrypted_provider_client_token" not in submitting
        assert CLIENT_TOKEN not in str(submitting)

        replay = await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitting",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=REMUX_CAPABILITY,
            source_sha256=SHA_A,
            client_token=CLIENT_TOKEN,
            submission_envelope=_submission_envelope(),
            now=NOW + timedelta(seconds=5),
        )
        assert replay is not None and replay["idempotent_replay"] is True
        with pytest.raises(ValueError, match="different paid-call transition"):
            await repository.begin_provider_task_submission(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="provider-submitting",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                capability=REMUX_CAPABILITY,
                source_sha256=SHA_A,
                client_token="different-client-token-0002",
                submission_envelope=_submission_envelope(client_token="different-client-token-0002"),
                now=NOW + timedelta(seconds=5),
            )

        assert (
            await repository.record_provider_task_submission_confirmed(
                admitted["id"],
                owner_user_id="owner-2",
                event_key="provider-submitted",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                submitted_task_record=_submitted_task_record(),
                now=NOW + timedelta(seconds=6),
            )
            is None
        )
        assert await repository.list_recoverable_provider_tasks(owner_user_id="owner-2") == []

        submitted = await repository.record_provider_task_submission_confirmed(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitted",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            submitted_task_record=_submitted_task_record(),
            now=NOW + timedelta(seconds=6),
        )
        assert submitted is not None
        assert submitted["provider_task_status"] == "submitted"
        assert RAW_TASK_ID not in str(submitted)

        recoverable = await repository.list_recoverable_provider_tasks(owner_user_id="owner-1")
        assert len(recoverable) == 1
        assert recoverable[0]["client_token"] == CLIENT_TOKEN
        assert recoverable[0]["submission_envelope"] == _submission_envelope()
        assert recoverable[0]["submitted_task_record"] == _submitted_task_record()
        assert recoverable[0]["raw_task_id"] == RAW_TASK_ID
        assert recoverable[0]["terminal_envelope"] is None

        session_factory = get_session_factory()
        assert session_factory is not None
        async with session_factory() as session:
            row = (await session.execute(select(PersonalIPPaidCallScopeRow).where(PersonalIPPaidCallScopeRow.id == admitted["id"]))).scalar_one()
            assert CLIENT_TOKEN not in row.encrypted_provider_client_token
            assert UPLOAD_FILE_ID not in row.encrypted_provider_submission_json
            assert RAW_TASK_ID not in row.encrypted_provider_task_id
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_provider_submit_replay_claim_is_append_only_and_granted_once(
    tmp_path,
) -> None:
    repository, admitted = await _admitted_repository(tmp_path)
    try:
        submitting = await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitting",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=REMUX_CAPABILITY,
            source_sha256=SHA_A,
            client_token=CLIENT_TOKEN,
            submission_envelope=_submission_envelope(),
            now=NOW + timedelta(seconds=4),
        )
        assert submitting is not None
        submission_digest = submitting["provider_submission_sha256"]

        first = await repository.claim_provider_task_submission_replay(
            admitted["id"],
            owner_user_id="owner-1",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            expected_submission_sha256=submission_digest,
            now=NOW + timedelta(seconds=5),
        )
        second = await repository.claim_provider_task_submission_replay(
            admitted["id"],
            owner_user_id="owner-1",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            expected_submission_sha256=submission_digest,
            now=NOW + timedelta(seconds=6),
        )

        assert first is not None
        assert first["provider_submission_replay_claimed"] is True
        assert first["idempotent_replay"] is False
        assert second is not None
        assert second["provider_submission_replay_claimed"] is False
        assert second["idempotent_replay"] is True
        replay_events = [event for event in second["events"] if event["payload"].get("recovery_action") == "exact_submit_replay_claimed"]
        assert len(replay_events) == 1
        assert replay_events[0]["payload"] == {
            "contract_version": "personal-ip-mediakit-provider-task-v1",
            "provider_task_status": "submitting",
            "provider_submission_sha256": submission_digest,
            "recovery_action": "exact_submit_replay_claimed",
            "maximum_replay_count": 1,
        }
        assert UPLOAD_FILE_ID not in str(replay_events)
        assert CLIENT_TOKEN not in str(replay_events)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_provider_submission_rejects_changed_exact_body_before_persisting(
    tmp_path,
) -> None:
    repository, admitted = await _admitted_repository(tmp_path)
    changed = _submission_envelope()
    changed["upload_file_id"] = "mediakit://another-upload"
    try:
        with pytest.raises(ValueError, match="upload file binding changed"):
            await repository.begin_provider_task_submission(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="provider-submitting",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                capability=REMUX_CAPABILITY,
                source_sha256=SHA_A,
                client_token=CLIENT_TOKEN,
                submission_envelope=changed,
                now=NOW + timedelta(seconds=4),
            )
        current = await repository.get(admitted["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["provider_task_status"] is None
        assert current["provider_submission_sha256"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_submitted_task_record_rejects_unbound_or_invalid_evidence(
    tmp_path,
) -> None:
    repository, admitted = await _admitted_repository(tmp_path)
    try:
        await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitting",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=REMUX_CAPABILITY,
            source_sha256=SHA_A,
            client_token=CLIENT_TOKEN,
            submission_envelope=_submission_envelope(),
            now=NOW + timedelta(seconds=4),
        )

        unbound = _submitted_task_record()
        unbound["task_id_sha256"] = SHA_A
        with pytest.raises(ValueError, match="task identifier binding changed"):
            await repository.record_provider_task_submission_confirmed(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="provider-submitted-unbound",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                submitted_task_record=unbound,
                now=NOW + timedelta(seconds=5),
            )

        invalid_response = _submitted_task_record()
        invalid_response["provider_response_sha256"] = "not-a-digest"
        with pytest.raises(ValueError, match="lowercase SHA-256"):
            await repository.record_provider_task_submission_confirmed(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="provider-submitted-invalid-response",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                submitted_task_record=invalid_response,
                now=NOW + timedelta(seconds=5),
            )

        current = await repository.get(admitted["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["provider_task_status"] == "submitting"
        assert not any(event["payload"].get("provider_task_status") == "submitted" for event in current["events"])
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_provider_task_restarts_then_reaches_monotonic_terminal_result(
    tmp_path,
) -> None:
    repository, admitted = await _admitted_repository(tmp_path)
    try:
        await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitting",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=REMUX_CAPABILITY,
            source_sha256=SHA_A,
            client_token=CLIENT_TOKEN,
            submission_envelope=_submission_envelope(),
            now=NOW + timedelta(seconds=4),
        )
        await repository.record_provider_task_submission_confirmed(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitted",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            submitted_task_record=_submitted_task_record(),
            now=NOW + timedelta(seconds=5),
        )

        session_factory = get_session_factory()
        assert session_factory is not None
        restarted = PersonalIPPaidCallRepository(
            session_factory,
            provider_task_cipher=ChannelCredentialCipher.from_key("provider-task-recovery-test-key-000000000000000000"),
        )
        resumed = await restarted.list_recoverable_provider_tasks(owner_user_id="owner-1")
        assert resumed[0]["provider_task_status"] == "submitted"
        assert resumed[0]["raw_task_id"] == RAW_TASK_ID
        assert resumed[0]["submitted_task_record"] == _submitted_task_record()

        with pytest.raises(ValueError, match="conflicting task identifier"):
            await restarted.record_provider_task_running(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="provider-running-conflict",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                raw_task_id="another-task-id",
                observed_provider_status="running",
                now=NOW + timedelta(seconds=6),
            )

        running = await restarted.record_provider_task_running(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-running",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            raw_task_id=RAW_TASK_ID,
            observed_provider_status="running",
            now=NOW + timedelta(seconds=7),
        )
        assert running is not None and running["provider_task_status"] == "running"

        envelope = {
            "task_id": RAW_TASK_ID,
            "status": "completed",
            "result_url": "https://result.volces.com/private-result.json",
        }
        terminal = await restarted.record_provider_task_terminal(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-terminal",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            raw_task_id=RAW_TASK_ID,
            terminal_status="completed",
            terminal_envelope=envelope,
            now=NOW + timedelta(seconds=8),
        )
        assert terminal is not None
        assert terminal["provider_task_status"] == "terminal"
        assert terminal["provider_terminal_status"] == "completed"
        assert "result.volces.com" not in str(terminal)

        replay = await restarted.record_provider_task_terminal(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-terminal",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            raw_task_id=RAW_TASK_ID,
            terminal_status="completed",
            terminal_envelope=envelope,
            now=NOW + timedelta(seconds=9),
        )
        assert replay is not None and replay["idempotent_replay"] is True
        with pytest.raises(ValueError, match="different paid-call transition"):
            await restarted.record_provider_task_terminal(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="provider-terminal",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                raw_task_id=RAW_TASK_ID,
                terminal_status="completed",
                terminal_envelope={"status": "completed", "result_url": "changed"},
                now=NOW + timedelta(seconds=9),
            )

        recovered = await restarted.list_recoverable_provider_tasks(owner_user_id="owner-1")
        assert recovered[0]["terminal_envelope"] == envelope
        assert recovered[0]["raw_task_id"] == RAW_TASK_ID
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_provider_task_may_complete_before_first_running_poll(tmp_path) -> None:
    repository, admitted = await _admitted_repository(tmp_path)
    try:
        await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitting-fast",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=REMUX_CAPABILITY,
            source_sha256=SHA_A,
            client_token=CLIENT_TOKEN,
            submission_envelope=_submission_envelope(),
            now=NOW + timedelta(seconds=4),
        )
        await repository.record_provider_task_submission_confirmed(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitted-fast",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            submitted_task_record=_submitted_task_record(),
            now=NOW + timedelta(seconds=5),
        )

        terminal = await repository.record_provider_task_terminal(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-terminal-fast",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            raw_task_id=RAW_TASK_ID,
            terminal_status="completed",
            terminal_envelope={"status": "completed", "result_ref": "private"},
            now=NOW + timedelta(seconds=6),
        )

        assert terminal is not None
        assert terminal["provider_task_status"] == "terminal"
        assert [event["payload"].get("provider_task_status") for event in terminal["events"][-3:]] == [
            "submitting",
            "submitted",
            "terminal",
        ]
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_exact_provider_task_recovery_is_not_limited_by_list_window(
    tmp_path,
) -> None:
    repository, admitted = await _admitted_repository(tmp_path)
    try:
        await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="provider-submitting-window-target",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=REMUX_CAPABILITY,
            source_sha256=SHA_A,
            client_token=CLIENT_TOKEN,
            submission_envelope=_submission_envelope(),
            now=NOW + timedelta(seconds=4),
        )

        session_factory = get_session_factory()
        assert session_factory is not None
        cipher = ChannelCredentialCipher.from_key("provider-task-recovery-test-key-000000000000000000")
        async with session_factory() as session:
            target = (await session.execute(select(PersonalIPPaidCallScopeRow).where(PersonalIPPaidCallScopeRow.id == admitted["id"]))).scalar_one()
            base = {column.name: getattr(target, column.name) for column in PersonalIPPaidCallScopeRow.__table__.columns}
            fillers: list[PersonalIPPaidCallScopeRow] = []
            for index in range(500):
                token = f"mediakit-client-token-window-{index:04d}"
                upload_file_id = f"mediakit://private-upload-window-{index:04d}"
                envelope = _submission_envelope(
                    client_token=token,
                    upload_file_id=upload_file_id,
                )
                envelope_json = json.dumps(
                    envelope,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                values = dict(base)
                values.update(
                    id=f"older-recoverable-{index:04d}",
                    request_key=f"older-recoverable-{index:04d}",
                    request_digest=hashlib.sha256(f"request-{index}".encode()).hexdigest(),
                    admission_jti_hash=hashlib.sha256(f"admission-{index}".encode()).hexdigest(),
                    encrypted_provider_client_token=cipher.encrypt_text(token),
                    provider_client_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                    encrypted_provider_submission_json=cipher.encrypt_text(envelope_json),
                    provider_submission_sha256=_canonical_sha256(envelope),
                    created_at=NOW - timedelta(days=1),
                    updated_at=NOW - timedelta(days=1, seconds=index),
                )
                fillers.append(PersonalIPPaidCallScopeRow(**values))

            no_task_values = dict(base)
            no_task_values.update(
                id="scope-without-provider-task",
                request_key="scope-without-provider-task",
                request_digest=SHA_E,
                admission_jti_hash=hashlib.sha256(b"scope-without-provider-task-admission").hexdigest(),
                provider_task_status=None,
                encrypted_provider_client_token=None,
                provider_client_token_sha256=None,
                encrypted_provider_submission_json=None,
                provider_submission_sha256=None,
                encrypted_provider_task_id=None,
                provider_task_id_sha256=None,
                provider_terminal_status=None,
                encrypted_provider_terminal_json=None,
                provider_terminal_sha256=None,
                created_at=NOW,
                updated_at=NOW,
            )
            session.add_all(
                [
                    *fillers,
                    PersonalIPPaidCallScopeRow(**no_task_values),
                ]
            )
            await session.commit()

        listed = await repository.list_recoverable_provider_tasks(
            owner_user_id="owner-1",
            limit=500,
        )
        assert len(listed) == 500
        assert admitted["id"] not in {item["id"] for item in listed}

        exact = await repository.get_recoverable_provider_task(
            admitted["id"],
            owner_user_id="owner-1",
        )
        assert exact is not None
        assert exact["id"] == admitted["id"]
        assert exact["client_token"] == CLIENT_TOKEN
        assert exact["submission_envelope"] == _submission_envelope()
        assert (
            await repository.get_recoverable_provider_task(
                admitted["id"],
                owner_user_id="owner-2",
            )
            is None
        )
        assert (
            await repository.get_recoverable_provider_task(
                "scope-without-provider-task",
                owner_user_id="owner-1",
            )
            is None
        )
        assert (
            await repository.get_recoverable_provider_task(
                "missing-scope",
                owner_user_id="owner-1",
            )
            is None
        )
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_strategy_exact_submission_is_encrypted_owner_scoped_and_publicly_redacted(
    tmp_path,
) -> None:
    envelope = _strategy_submission_envelope()
    repository, admitted = await _admitted_repository(
        tmp_path,
        capability=STRATEGY_CAPABILITY,
        provider_request_sha256=envelope["request_sha256"],
        request_key="recovery-strategy-owner-1",
    )
    try:
        mixed_contract = dict(envelope)
        mixed_contract["contract_version"] = "ip-mediakit-remux-submission-recovery-v1"
        with pytest.raises(ValueError, match="contract dispatch is unsupported"):
            await repository.begin_provider_task_submission(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="strategy-provider-submitting-mixed-contract",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                capability=STRATEGY_CAPABILITY,
                source_sha256=SHA_A,
                client_token=STRATEGY_CLIENT_TOKEN,
                submission_envelope=mixed_contract,
                now=NOW + timedelta(seconds=4),
            )
        submitting = await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="strategy-provider-submitting",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=STRATEGY_CAPABILITY,
            source_sha256=SHA_A,
            client_token=STRATEGY_CLIENT_TOKEN,
            submission_envelope=envelope,
            now=NOW + timedelta(seconds=4),
        )

        assert submitting is not None
        assert submitting["provider_task_status"] == "submitting"
        public = json.dumps(submitting, ensure_ascii=False, sort_keys=True)
        assert STRATEGY_VIDEO_REF not in public
        assert STRATEGY_CLIENT_TOKEN not in public
        assert STRATEGY_TASK_ID not in public
        assert (
            await repository.get_recoverable_provider_task(
                admitted["id"],
                owner_user_id="owner-2",
            )
            is None
        )

        recovered = await repository.get_recoverable_provider_task(
            admitted["id"],
            owner_user_id="owner-1",
        )
        assert recovered is not None
        assert recovered["client_token"] == STRATEGY_CLIENT_TOKEN
        assert recovered["submission_envelope"] == envelope
        assert recovered["raw_task_id"] is None

        mixed_task_contract = _strategy_submitted_task_record()
        mixed_task_contract["contract_version"] = "ip-mediakit-remux-submitted-task-recovery-v1"
        with pytest.raises(ValueError, match="contract dispatch is unsupported"):
            await repository.record_provider_task_submission_confirmed(
                admitted["id"],
                owner_user_id="owner-1",
                event_key="strategy-provider-submitted-mixed-contract",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                submitted_task_record=mixed_task_contract,
                now=NOW + timedelta(seconds=5),
            )

        submitted = await repository.record_provider_task_submission_confirmed(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="strategy-provider-submitted",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            submitted_task_record=_strategy_submitted_task_record(),
            now=NOW + timedelta(seconds=5),
        )
        assert submitted is not None
        assert submitted["provider_task_status"] == "submitted"
        assert STRATEGY_TASK_ID not in json.dumps(
            submitted,
            ensure_ascii=False,
            sort_keys=True,
        )

        session_factory = get_session_factory()
        assert session_factory is not None
        async with session_factory() as session:
            row = (await session.execute(select(PersonalIPPaidCallScopeRow).where(PersonalIPPaidCallScopeRow.id == admitted["id"]))).scalar_one()
            assert STRATEGY_CLIENT_TOKEN not in row.encrypted_provider_client_token
            assert STRATEGY_VIDEO_REF not in row.encrypted_provider_submission_json
            assert STRATEGY_TASK_ID not in row.encrypted_provider_task_id
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_strategy_crash_window_grants_one_same_body_same_token_submit_replay(
    tmp_path,
) -> None:
    envelope = _strategy_submission_envelope()
    repository, admitted = await _admitted_repository(
        tmp_path,
        capability=STRATEGY_CAPABILITY,
        provider_request_sha256=envelope["request_sha256"],
        request_key="recovery-strategy-crash-window",
    )
    try:
        submitting = await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="strategy-provider-submitting-crash",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=STRATEGY_CAPABILITY,
            source_sha256=SHA_A,
            client_token=STRATEGY_CLIENT_TOKEN,
            submission_envelope=envelope,
            now=NOW + timedelta(seconds=4),
        )
        assert submitting is not None
        submission_sha256 = submitting["provider_submission_sha256"]

        first = await repository.claim_provider_task_submission_replay(
            admitted["id"],
            owner_user_id="owner-1",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            expected_submission_sha256=submission_sha256,
            now=NOW + timedelta(seconds=5),
        )
        second = await repository.claim_provider_task_submission_replay(
            admitted["id"],
            owner_user_id="owner-1",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            expected_submission_sha256=submission_sha256,
            now=NOW + timedelta(seconds=6),
        )

        assert first is not None
        assert first["provider_submission_replay_claimed"] is True
        assert second is not None
        assert second["provider_submission_replay_claimed"] is False
        recovered = await repository.get_recoverable_provider_task(
            admitted["id"],
            owner_user_id="owner-1",
        )
        assert recovered is not None
        assert recovered["submission_envelope"]["submit_body"] == envelope["submit_body"]
        assert recovered["client_token"] == STRATEGY_CLIENT_TOKEN
        replay_events = [event for event in second["events"] if event["payload"].get("recovery_action") == "exact_submit_replay_claimed"]
        assert len(replay_events) == 1
        assert STRATEGY_VIDEO_REF not in str(replay_events)
        assert STRATEGY_CLIENT_TOKEN not in str(replay_events)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_strategy_submitted_and_running_recovery_are_query_only(
    tmp_path,
) -> None:
    envelope = _strategy_submission_envelope()
    repository, admitted = await _admitted_repository(
        tmp_path,
        capability=STRATEGY_CAPABILITY,
        provider_request_sha256=envelope["request_sha256"],
        request_key="recovery-strategy-query-only",
    )
    try:
        submitting = await repository.begin_provider_task_submission(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="strategy-provider-submitting-query-only",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            capability=STRATEGY_CAPABILITY,
            source_sha256=SHA_A,
            client_token=STRATEGY_CLIENT_TOKEN,
            submission_envelope=envelope,
            now=NOW + timedelta(seconds=4),
        )
        assert submitting is not None
        await repository.record_provider_task_submission_confirmed(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="strategy-provider-submitted-query-only",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            submitted_task_record=_strategy_submitted_task_record(),
            now=NOW + timedelta(seconds=5),
        )

        submitted = await repository.get_recoverable_provider_task(
            admitted["id"],
            owner_user_id="owner-1",
        )
        assert submitted is not None
        assert submitted["provider_task_status"] == "submitted"
        assert submitted["raw_task_id"] == STRATEGY_TASK_ID
        with pytest.raises(
            ValueError,
            match="unfinished exact submission",
        ):
            await repository.claim_provider_task_submission_replay(
                admitted["id"],
                owner_user_id="owner-1",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                expected_submission_sha256=submitting["provider_submission_sha256"],
                now=NOW + timedelta(seconds=6),
            )

        await repository.record_provider_task_running(
            admitted["id"],
            owner_user_id="owner-1",
            event_key="strategy-provider-running-query-only",
            expected_request_digest=admitted["request_digest"],
            execution_run_id="execution-run-1",
            raw_task_id=STRATEGY_TASK_ID,
            observed_provider_status="running",
            now=NOW + timedelta(seconds=7),
        )
        running = await repository.get_recoverable_provider_task(
            admitted["id"],
            owner_user_id="owner-1",
        )
        assert running is not None
        assert running["provider_task_status"] == "running"
        assert running["raw_task_id"] == STRATEGY_TASK_ID
        with pytest.raises(
            ValueError,
            match="unfinished exact submission",
        ):
            await repository.claim_provider_task_submission_replay(
                admitted["id"],
                owner_user_id="owner-1",
                expected_request_digest=admitted["request_digest"],
                execution_run_id="execution-run-1",
                expected_submission_sha256=submitting["provider_submission_sha256"],
                now=NOW + timedelta(seconds=8),
            )
    finally:
        await close_engine()
