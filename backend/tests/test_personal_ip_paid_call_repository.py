from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_paid_calls import (
    EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
    EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
    EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
    OperatorCappedEvidenceStagePolicy,
    PersonalIPPaidCallRepository,
)
from deerflow.personal_ip.data_lifecycle import (
    DELETE_CONFIRMATION_PHRASE,
    EXPORT_DATASET_NAMES,
    PERSONAL_IP_DELETION_ONLY_TABLES,
    PersonalIPDataLifecycleService,
)

NOW = datetime(2026, 8, 2, 10, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
REMUX_CAPABILITY = "managed_https_ingress_remux"
VIDEO_CHAT_CAPABILITY = "video_understanding_chat"
OPERATOR_LIMIT_MICROS = 500_000
OPERATOR_DURATION_MILLIS = 60_000


class _FakeMineContext:
    def clear(self, owner_user_id: str, *, scope: str) -> dict:
        return {"owner_user_id": owner_user_id, "scope": scope, "local_data_deleted": True}


async def _repository(tmp_path) -> PersonalIPPaidCallRepository:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    return PersonalIPPaidCallRepository(session_factory)


async def _request(
    repository: PersonalIPPaidCallRepository,
    *,
    request_key: str = "asr-request-1",
    owner_user_id: str = "owner-1",
    thread_id: str = "thread-1",
    origin_run_id: str = "origin-run-1",
    maximum_amount_micros: int | None = 500_000,
    source_sha256: str = SHA_A,
    stage_digest: str = SHA_B,
    tool_args_sha256: str = SHA_E,
    provider: str = "volcengine-mediakit",
    capability: str = "asr",
    policy_version: str = "paid-call-policy-v1",
    price_status: str | None = None,
    source_duration_millis: int = 8_000,
) -> dict:
    return await repository.request_call(
        owner_user_id=owner_user_id,
        request_key=request_key,
        scope_kind="run",
        thread_id=thread_id,
        origin_run_id=origin_run_id,
        server_name="ip-agent-evidence",
        tool_name="inspect_reference_videos",
        tool_args_sha256=tool_args_sha256,
        provider=provider,
        capability=capability,
        model="media-asr-v1",
        sku="asr.standard",
        provider_label="火山引擎 AI MediaKit",
        capability_label="语音识别",
        object_ref_label="参考视频 90a3…4644",
        source_duration_millis=source_duration_millis,
        source_sha256=source_sha256,
        stage_digest=stage_digest,
        provider_request_sha256=SHA_D,
        maximum_amount_micros=maximum_amount_micros,
        currency="CNY",
        billing_basis="官方按量计费报价",
        policy_version=policy_version,
        price_version="mediakit-price-2026-08-02",
        provider_input_attested=False,
        evidence_coverage="partial",
        warning_code="provider_content_hash_unattested",
        expires_at=NOW + timedelta(minutes=15),
        price_status=price_status,
        now=NOW,
    )


def _stage_policy(
    capability: str,
    *,
    local_limit_micros: int = OPERATOR_LIMIT_MICROS,
    max_duration_millis: int = OPERATOR_DURATION_MILLIS,
    policy_version: str | None = None,
) -> OperatorCappedEvidenceStagePolicy:
    policies = {
        "asr": EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
        REMUX_CAPABILITY: EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
        VIDEO_CHAT_CAPABILITY: EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
    }
    return OperatorCappedEvidenceStagePolicy(
        capability=capability,
        policy_version=policy_version or policies[capability],
        local_admission_limit_micros=local_limit_micros,
        max_source_duration_millis=max_duration_millis,
    )


async def _operator_request(
    repository: PersonalIPPaidCallRepository,
    *,
    request_key: str,
    capability: str,
    owner_user_id: str = "owner-1",
    thread_id: str = "thread-1",
    tool_args_sha256: str = SHA_E,
    local_limit_micros: int = OPERATOR_LIMIT_MICROS,
    source_duration_millis: int = 8_000,
    policy_version: str | None = None,
) -> dict:
    stage = _stage_policy(
        capability,
        local_limit_micros=local_limit_micros,
        policy_version=policy_version,
    )
    return await _request(
        repository,
        request_key=request_key,
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        maximum_amount_micros=local_limit_micros,
        tool_args_sha256=tool_args_sha256,
        capability=capability,
        policy_version=stage.policy_version,
        price_status="operator_capped",
        source_duration_millis=source_duration_millis,
    )


async def _approve_only(
    repository: PersonalIPPaidCallRepository,
    scope: dict,
    *,
    prefix: str,
) -> dict:
    approved = await repository.approve(
        scope["id"],
        owner_user_id=scope["owner_user_id"],
        event_key=f"approve-{prefix}",
        expected_request_digest=scope["request_digest"],
        approval_digest=SHA_C,
        expected_event_count=1,
        now=NOW + timedelta(seconds=1),
    )
    assert approved is not None
    return approved


async def _admit_next_operator_stage(
    repository: PersonalIPPaidCallRepository,
    *,
    policies: tuple[OperatorCappedEvidenceStagePolicy, ...],
    owner_user_id: str = "owner-1",
    tool_args_sha256: str = SHA_E,
    execution_run_id: str = "execution-run-operator",
    key_prefix: str = "operator",
    admission_jti: str = "operator-admission-jti-0001",
) -> dict | None:
    return await repository.admit_next_operator_capped_evidence_stage_exact(
        owner_user_id=owner_user_id,
        thread_id="thread-1",
        execution_run_id=execution_run_id,
        server_name="ip-agent-evidence",
        tool_name="inspect_reference_videos",
        tool_args_sha256=tool_args_sha256,
        provider="volcengine-mediakit",
        trusted_stage_policies=policies,
        currency="CNY",
        reservation_event_key=f"reserve-{key_prefix}",
        admission_event_key=f"admit-{key_prefix}",
        admission_jti=admission_jti,
        admission_proof_digest=SHA_D,
        now=NOW + timedelta(seconds=2),
    )


async def _approve_and_reserve(
    repository: PersonalIPPaidCallRepository,
    scope: dict,
    *,
    prefix: str = "one",
    amount_micros: int = 400_000,
    execution_run_id: str = "execution-run-1",
) -> dict:
    approved = await repository.approve(
        scope["id"],
        owner_user_id=scope["owner_user_id"],
        event_key=f"approve-{prefix}",
        expected_request_digest=scope["request_digest"],
        approval_digest=SHA_C,
        expected_event_count=1,
        now=NOW + timedelta(seconds=1),
    )
    assert approved is not None
    reserved = await repository.reserve(
        scope["id"],
        owner_user_id=scope["owner_user_id"],
        event_key=f"reserve-{prefix}",
        expected_request_digest=scope["request_digest"],
        execution_run_id=execution_run_id,
        amount_micros=amount_micros,
        expected_event_count=2,
        now=NOW + timedelta(seconds=2),
    )
    assert reserved is not None
    return reserved


async def _admit(
    repository: PersonalIPPaidCallRepository,
    scope: dict,
    *,
    event_key: str = "admit-one",
    jti: str = "one-time-admission-jti-0001",
    execution_run_id: str = "execution-run-1",
) -> dict:
    admitted = await repository.admit(
        scope["id"],
        owner_user_id=scope["owner_user_id"],
        event_key=event_key,
        expected_request_digest=scope["request_digest"],
        execution_run_id=execution_run_id,
        admission_jti=jti,
        admission_proof_digest=SHA_D,
        expected_event_count=3,
        now=NOW + timedelta(seconds=3),
    )
    assert admitted is not None
    return admitted


@pytest.mark.asyncio
async def test_unknown_price_is_visible_but_cannot_be_approved_or_faked_as_free(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _request(repository, maximum_amount_micros=None)
        assert requested["status"] == "requested"
        assert requested["price_status"] == "unknown"
        assert requested["maximum_amount_micros"] is None
        assert requested["operation_event"]["amount_micros"] is None
        assert requested["operation_event"]["payload"]["billing"]["price_status"] == "unknown"
        assert requested["operation_event"]["payload"]["provider_input_attested"] is False
        with pytest.raises(ValueError, match="positive quoted maximum"):
            await repository.approve(
                requested["id"],
                owner_user_id="owner-1",
                event_key="approve-unknown",
                expected_request_digest=requested["request_digest"],
                approval_digest=SHA_C,
                expected_event_count=1,
                now=NOW + timedelta(seconds=1),
            )
        current = await repository.get(requested["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "requested"
        assert current["event_count"] == 1

        replay = await _request(repository, maximum_amount_micros=None)
        assert replay["id"] == requested["id"]
        assert replay["idempotent_replay"] is True
        with pytest.raises(ValueError, match="different paid-call request"):
            await _request(repository, maximum_amount_micros=1)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_request_rejects_unsafe_display_ref_and_requires_partial_warning(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        common = {
            "owner_user_id": "owner-1",
            "request_key": "unsafe",
            "scope_kind": "run",
            "thread_id": "thread-1",
            "origin_run_id": "origin-run-1",
            "server_name": "ip-agent-evidence",
            "tool_name": "inspect_reference_videos",
            "tool_args_sha256": SHA_E,
            "provider": "volcengine-mediakit",
            "capability": "asr",
            "model": "media-asr-v1",
            "sku": "asr.standard",
            "provider_label": "MediaKit",
            "capability_label": "ASR",
            "object_ref_label": "/Users/person/private.mp4",
            "source_duration_millis": 8_000,
            "source_sha256": SHA_A,
            "stage_digest": SHA_B,
            "provider_request_sha256": SHA_D,
            "maximum_amount_micros": 1,
            "currency": "CNY",
            "billing_basis": "quoted",
            "policy_version": "v1",
            "price_version": "v1",
            "provider_input_attested": False,
            "evidence_coverage": "partial",
            "warning_code": "input_unattested",
            "expires_at": NOW + timedelta(minutes=1),
            "now": NOW,
        }
        with pytest.raises(ValueError, match="path, URL"):
            await repository.request_call(**common)
        common["object_ref_label"] = "参考视频 aaaa…aaaa"
        common["warning_code"] = None
        with pytest.raises(ValueError, match="warning_code"):
            await repository.request_call(**common)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_origin_run_approval_is_reachable_once_from_a_later_execution_run(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _request(repository)
        assert requested["origin_run_id"] == "origin-run-1"
        assert requested["execution_run_id"] is None
        approved = await repository.approve(
            requested["id"],
            owner_user_id="owner-1",
            event_key="approve-one",
            expected_request_digest=requested["request_digest"],
            approval_digest=SHA_C,
            expected_event_count=1,
            now=NOW + timedelta(seconds=1),
        )
        assert approved is not None and approved["status"] == "approved"
        matched = await repository.find_approved_for_invocation(
            owner_user_id="owner-1",
            thread_id="thread-1",
            server_name="ip-agent-evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=SHA_E,
            provider="volcengine-mediakit",
            capability="asr",
            now=NOW + timedelta(seconds=1),
        )
        assert matched is not None and matched["id"] == requested["id"]
        assert (
            await repository.find_approved_for_invocation(
                owner_user_id="owner-1",
                thread_id="thread-1",
                server_name="ip-agent-evidence",
                tool_name="inspect_reference_videos",
                tool_args_sha256=SHA_E,
                provider="volcengine-mediakit",
                capability="ocr",
                now=NOW + timedelta(seconds=1),
            )
            is None
        )
        approval_replay = await repository.approve(
            requested["id"],
            owner_user_id="owner-1",
            event_key="approve-one",
            expected_request_digest=requested["request_digest"],
            approval_digest=SHA_C,
            expected_event_count=1,
            now=NOW + timedelta(seconds=9),
        )
        assert approval_replay is not None and approval_replay["idempotent_replay"] is True

        reserved = await repository.reserve(
            requested["id"],
            owner_user_id="owner-1",
            event_key="reserve-one",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            amount_micros=400_000,
            expected_event_count=2,
            now=NOW + timedelta(seconds=2),
        )
        assert reserved is not None and reserved["reserved_amount_micros"] == 400_000
        assert reserved["execution_run_id"] == "execution-run-1"
        assert (
            await repository.find_approved_for_invocation(
                owner_user_id="owner-1",
                thread_id="thread-1",
                server_name="ip-agent-evidence",
                tool_name="inspect_reference_videos",
                tool_args_sha256=SHA_E,
                provider="volcengine-mediakit",
                capability="asr",
                now=NOW + timedelta(seconds=2),
            )
            is None
        )
        reserve_replay = await repository.reserve(
            requested["id"],
            owner_user_id="owner-1",
            event_key="reserve-one",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            amount_micros=400_000,
            expected_event_count=2,
            now=NOW + timedelta(seconds=8),
        )
        assert reserve_replay is not None and reserve_replay["idempotent_replay"] is True
        with pytest.raises(ValueError, match="reserved execution run"):
            await repository.reserve(
                requested["id"],
                owner_user_id="owner-1",
                event_key="reserve-one",
                expected_request_digest=requested["request_digest"],
                execution_run_id="competing-execution-run",
                amount_micros=400_000,
                now=NOW + timedelta(seconds=8),
            )
        with pytest.raises(ValueError, match="reserved execution run"):
            await repository.admit(
                requested["id"],
                owner_user_id="owner-1",
                event_key="wrong-run-admit",
                expected_request_digest=requested["request_digest"],
                execution_run_id="competing-execution-run",
                admission_jti="wrong-run-admission-jti-0001",
                admission_proof_digest=SHA_D,
                now=NOW + timedelta(seconds=3),
            )
        admitted = await _admit(repository, reserved)
        assert admitted["status"] == "admitted"
        serialized = json.dumps(admitted)
        assert "one-time-admission-jti-0001" not in serialized
        admission_replay = await repository.admit(
            requested["id"],
            owner_user_id="owner-1",
            event_key="admit-one",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            admission_jti="one-time-admission-jti-0001",
            admission_proof_digest=SHA_D,
            expected_event_count=3,
            now=NOW + timedelta(seconds=10),
        )
        assert admission_replay is not None and admission_replay["idempotent_replay"] is True
        with pytest.raises(ValueError, match="requires reserved status"):
            await repository.admit(
                requested["id"],
                owner_user_id="owner-1",
                event_key="admit-again",
                expected_request_digest=requested["request_digest"],
                execution_run_id="execution-run-1",
                admission_jti="one-time-admission-jti-0002",
                admission_proof_digest=SHA_D,
                now=NOW + timedelta(seconds=4),
            )
        with pytest.raises(ValueError, match="only before provider admission"):
            await repository.release(
                requested["id"],
                owner_user_id="owner-1",
                event_key="release-too-late",
                expected_request_digest=requested["request_digest"],
                execution_run_id="execution-run-1",
                no_provider_call_digest=SHA_E,
                reason_code="cancelled",
                now=NOW + timedelta(seconds=4),
            )

        settled = await repository.settle(
            requested["id"],
            owner_user_id="owner-1",
            event_key="settle-one",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            actual_amount_micros=320_000,
            provider_receipt_digest=SHA_E,
            expected_event_count=4,
            now=NOW + timedelta(seconds=5),
        )
        assert settled is not None
        assert settled["status"] == "settled"
        assert settled["reserved_amount_micros"] == 0
        assert settled["settled_amount_micros"] == 320_000
        assert [event["event_type"] for event in settled["events"]] == [
            "requested",
            "approved",
            "reserved",
            "admitted",
            "settled",
        ]
        settlement_replay = await repository.settle(
            requested["id"],
            owner_user_id="owner-1",
            event_key="settle-one",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            actual_amount_micros=320_000,
            provider_receipt_digest=SHA_E,
            expected_event_count=4,
            now=NOW + timedelta(seconds=11),
        )
        assert settlement_replay is not None and settlement_replay["idempotent_replay"] is True
        assert await repository.get(requested["id"], owner_user_id="another-owner") is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_unknown_actual_cost_keeps_reservation_until_later_receipt(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _request(repository)
        reserved = await _approve_and_reserve(repository, requested)
        await _admit(repository, reserved)
        held = await repository.settle(
            requested["id"],
            owner_user_id="owner-1",
            event_key="settle-unknown",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            actual_amount_micros=None,
            provider_receipt_digest=SHA_E,
            expected_event_count=4,
            now=NOW + timedelta(seconds=4),
        )
        assert held is not None
        assert held["status"] == "reconciliation_required"
        assert held["reserved_amount_micros"] == 400_000
        assert held["settled_amount_micros"] is None

        settled = await repository.settle(
            requested["id"],
            owner_user_id="owner-1",
            event_key="settle-known",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            actual_amount_micros=350_000,
            provider_receipt_digest=SHA_A,
            expected_event_count=5,
            now=NOW + timedelta(seconds=5),
        )
        assert settled is not None
        assert settled["status"] == "settled"
        assert settled["reserved_amount_micros"] == 0
        assert settled["settled_amount_micros"] == 350_000
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_overrun_requires_explicit_reconciliation_and_cannot_release(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _request(repository)
        reserved = await _approve_and_reserve(repository, requested)
        await _admit(repository, reserved)
        held = await repository.settle(
            requested["id"],
            owner_user_id="owner-1",
            event_key="settle-overrun",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            actual_amount_micros=700_000,
            provider_receipt_digest=SHA_E,
            now=NOW + timedelta(seconds=4),
        )
        assert held is not None and held["status"] == "reconciliation_required"
        assert held["reserved_amount_micros"] == 400_000
        reconciled = await repository.reconcile(
            requested["id"],
            owner_user_id="owner-1",
            event_key="manual-reconciliation",
            expected_request_digest=requested["request_digest"],
            execution_run_id="execution-run-1",
            actual_amount_micros=700_000,
            reconciliation_digest=SHA_A,
            expected_event_count=5,
            now=NOW + timedelta(seconds=5),
        )
        assert reconciled is not None
        assert reconciled["status"] == "settled"
        assert reconciled["settled_amount_micros"] == 700_000
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_two_execution_runs_competing_for_one_approval_are_serialized(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _request(repository)
        approved = await repository.approve(
            requested["id"],
            owner_user_id="owner-1",
            event_key="approve-concurrent",
            expected_request_digest=requested["request_digest"],
            approval_digest=SHA_C,
            expected_event_count=1,
            now=NOW + timedelta(seconds=1),
        )
        assert approved is not None

        async def reserve(event_key: str):
            return await repository.reserve(
                requested["id"],
                owner_user_id="owner-1",
                event_key=event_key,
                expected_request_digest=requested["request_digest"],
                execution_run_id=event_key.replace("reserve", "execution"),
                amount_micros=400_000,
                expected_event_count=2,
                now=NOW + timedelta(seconds=2),
            )

        results = await asyncio.gather(reserve("reserve-a"), reserve("reserve-b"), return_exceptions=True)
        assert sum(isinstance(result, dict) for result in results) == 1
        assert sum(isinstance(result, ValueError) for result in results) == 1
        current = await repository.get(requested["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "reserved"
        assert current["event_count"] == 3
        assert current["reserved_amount_micros"] == 400_000
        assert current["execution_run_id"] in {"execution-a", "execution-b"}
        assert current["events"][-1]["execution_run_id"] == current["execution_run_id"]
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_multiple_approved_proposals_for_same_invocation_fail_closed_as_ambiguous(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        first = await _request(repository, request_key="duplicate-first", stage_digest=SHA_C)
        second = await _request(repository, request_key="duplicate-second", stage_digest=SHA_C)
        for index, scope in enumerate((first, second), start=1):
            approved = await repository.approve(
                scope["id"],
                owner_user_id="owner-1",
                event_key=f"approve-duplicate-{index}",
                expected_request_digest=scope["request_digest"],
                approval_digest=SHA_D,
                expected_event_count=1,
                now=NOW + timedelta(seconds=index),
            )
            assert approved is not None

        with pytest.raises(ValueError, match="multiple approved"):
            await repository.find_approved_for_invocation(
                owner_user_id="owner-1",
                thread_id="thread-1",
                server_name="ip-agent-evidence",
                tool_name="inspect_reference_videos",
                tool_args_sha256=SHA_E,
                provider="volcengine-mediakit",
                capability="asr",
                now=NOW + timedelta(seconds=3),
            )
    finally:
        await close_engine()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capability", "policy_version"),
    [
        ("asr", EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION),
        (REMUX_CAPABILITY, EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION),
        (
            VIDEO_CHAT_CAPABILITY,
            EVIDENCE_VIDEO_UNDERSTANDING_CHAT_OPERATOR_CAP_POLICY_VERSION,
        ),
    ],
)
async def test_operator_capped_request_allowlist_accepts_only_named_mediakit_policies(
    tmp_path,
    capability: str,
    policy_version: str,
) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _operator_request(
            repository,
            request_key=f"allowlisted-{capability}",
            capability=capability,
            policy_version=policy_version,
        )
        assert requested["provider"] == "volcengine-mediakit"
        assert requested["capability"] == capability
        assert requested["policy_version"] == policy_version
        assert requested["price_status"] == "operator_capped"
    finally:
        await close_engine()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "capability", "policy_version"),
    [
        (
            "volcengine-mediakit",
            REMUX_CAPABILITY,
            EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
        ),
        (
            "volcengine-mediakit",
            "ocr",
            EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
        ),
        (
            "another-provider",
            REMUX_CAPABILITY,
            EVIDENCE_MANAGED_REMUX_OPERATOR_CAP_POLICY_VERSION,
        ),
    ],
)
async def test_operator_capped_request_rejects_wrong_provider_capability_or_policy(
    tmp_path,
    provider: str,
    capability: str,
    policy_version: str,
) -> None:
    repository = await _repository(tmp_path)
    try:
        with pytest.raises(ValueError, match="restricted.*MediaKit ASR"):
            await _request(
                repository,
                request_key="unsupported-operator-cap",
                maximum_amount_micros=OPERATOR_LIMIT_MICROS,
                provider=provider,
                capability=capability,
                policy_version=policy_version,
                price_status="operator_capped",
            )
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_generic_operator_capped_admission_returns_none_for_zero_matches(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        result = await _admit_next_operator_stage(
            repository,
            policies=(
                _stage_policy("asr"),
                _stage_policy(REMUX_CAPABILITY),
                _stage_policy(VIDEO_CHAT_CAPABILITY),
            ),
        )
        assert result is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_generic_operator_capped_admission_atomically_returns_actual_stage(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    jti = "actual-stage-admission-jti-secret-0001"
    try:
        requested = await _operator_request(
            repository,
            request_key="unique-video-chat",
            capability=VIDEO_CHAT_CAPABILITY,
        )
        await _approve_only(repository, requested, prefix="unique-video-chat")

        admitted = await _admit_next_operator_stage(
            repository,
            policies=(
                _stage_policy("asr"),
                _stage_policy(REMUX_CAPABILITY),
                _stage_policy(VIDEO_CHAT_CAPABILITY),
            ),
            key_prefix="unique-video-chat",
            admission_jti=jti,
        )

        assert admitted is not None
        assert admitted["id"] == requested["id"]
        assert admitted["capability"] == VIDEO_CHAT_CAPABILITY
        assert admitted["status"] == "admitted"
        assert admitted["execution_run_id"] == "execution-run-operator"
        assert admitted["reserved_amount_micros"] == OPERATOR_LIMIT_MICROS
        assert [event["event_type"] for event in admitted["events"]] == [
            "requested",
            "approved",
            "reserved",
            "admitted",
        ]
        assert jti not in json.dumps(admitted)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_generic_operator_capped_admission_fails_ambiguous_without_state_change(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = [
            await _operator_request(
                repository,
                request_key=f"ambiguous-{capability}",
                capability=capability,
            )
            for capability in (REMUX_CAPABILITY, VIDEO_CHAT_CAPABILITY)
        ]
        for capability, scope in zip(
            (REMUX_CAPABILITY, VIDEO_CHAT_CAPABILITY),
            requested,
            strict=True,
        ):
            await _approve_only(repository, scope, prefix=f"ambiguous-{capability}")

        with pytest.raises(ValueError, match="multiple approved operator-capped"):
            await _admit_next_operator_stage(
                repository,
                policies=(
                    _stage_policy(REMUX_CAPABILITY),
                    _stage_policy(VIDEO_CHAT_CAPABILITY),
                ),
                key_prefix="ambiguous",
            )

        for scope in requested:
            current = await repository.get(scope["id"], owner_user_id="owner-1")
            assert current is not None
            assert current["status"] == "approved"
            assert current["execution_run_id"] is None
            assert current["reserved_amount_micros"] == 0
            assert current["admission_jti_hash"] is None
            assert current["event_count"] == 2
            assert [event["event_type"] for event in current["events"]] == [
                "requested",
                "approved",
            ]
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_generic_operator_capped_admission_is_exactly_owner_and_args_scoped(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _operator_request(
            repository,
            request_key="owner-args-scope",
            capability=REMUX_CAPABILITY,
        )
        await _approve_only(repository, requested, prefix="owner-args-scope")
        policy = (_stage_policy(REMUX_CAPABILITY),)

        assert (
            await _admit_next_operator_stage(
                repository,
                policies=policy,
                owner_user_id="owner-2",
                key_prefix="wrong-owner",
            )
            is None
        )
        assert (
            await _admit_next_operator_stage(
                repository,
                policies=policy,
                tool_args_sha256=SHA_D,
                key_prefix="wrong-args",
            )
            is None
        )
        current = await repository.get(requested["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "approved"
        assert current["event_count"] == 2
    finally:
        await close_engine()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    [
        OperatorCappedEvidenceStagePolicy(
            capability="ocr",
            policy_version=EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
            local_admission_limit_micros=OPERATOR_LIMIT_MICROS,
            max_source_duration_millis=OPERATOR_DURATION_MILLIS,
        ),
        _stage_policy(
            REMUX_CAPABILITY,
            policy_version=EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
        ),
        _stage_policy(REMUX_CAPABILITY, local_limit_micros=0),
        _stage_policy(REMUX_CAPABILITY, max_duration_millis=0),
    ],
)
async def test_generic_operator_capped_admission_rejects_untrusted_stage_policy(
    tmp_path,
    policy: OperatorCappedEvidenceStagePolicy,
) -> None:
    repository = await _repository(tmp_path)
    try:
        with pytest.raises(ValueError) as caught:
            await _admit_next_operator_stage(
                repository,
                policies=(policy,),
                admission_jti="must-not-leak-this-admission-jti",
            )
        assert "must-not-leak-this-admission-jti" not in str(caught.value)
    finally:
        await close_engine()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    [
        _stage_policy(REMUX_CAPABILITY, local_limit_micros=400_000),
        _stage_policy(REMUX_CAPABILITY, max_duration_millis=1_000),
    ],
)
async def test_generic_operator_capped_admission_does_not_relax_limit_or_duration(
    tmp_path,
    policy: OperatorCappedEvidenceStagePolicy,
) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _operator_request(
            repository,
            request_key="exact-limit-duration",
            capability=REMUX_CAPABILITY,
        )
        await _approve_only(repository, requested, prefix="exact-limit-duration")
        assert (
            await _admit_next_operator_stage(
                repository,
                policies=(policy,),
                key_prefix="mismatched-limit-duration",
            )
            is None
        )
        current = await repository.get(requested["id"], owner_user_id="owner-1")
        assert current is not None and current["status"] == "approved"
        assert current["event_count"] == 2
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_generic_operator_capped_admission_jti_is_global_and_rollback_safe(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    reused_jti = "operator-global-jti-secret-0001"
    try:
        first = await _operator_request(
            repository,
            request_key="generic-jti-first",
            capability=REMUX_CAPABILITY,
            tool_args_sha256=SHA_E,
        )
        second = await _operator_request(
            repository,
            request_key="generic-jti-second",
            capability=VIDEO_CHAT_CAPABILITY,
            tool_args_sha256=SHA_D,
        )
        await _approve_only(repository, first, prefix="generic-jti-first")
        await _approve_only(repository, second, prefix="generic-jti-second")
        admitted = await _admit_next_operator_stage(
            repository,
            policies=(_stage_policy(REMUX_CAPABILITY),),
            tool_args_sha256=SHA_E,
            key_prefix="generic-jti-first",
            admission_jti=reused_jti,
        )
        assert admitted is not None
        assert reused_jti not in json.dumps(admitted)

        with pytest.raises(ValueError, match="already been consumed") as caught:
            await _admit_next_operator_stage(
                repository,
                policies=(_stage_policy(VIDEO_CHAT_CAPABILITY),),
                tool_args_sha256=SHA_D,
                key_prefix="generic-jti-second",
                admission_jti=reused_jti,
            )
        assert reused_jti not in str(caught.value)
        current = await repository.get(second["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "approved"
        assert current["event_count"] == 2
        assert current["execution_run_id"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_legacy_operator_capped_asr_wrapper_uses_generic_admission(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        requested = await _operator_request(
            repository,
            request_key="legacy-asr-wrapper",
            capability="asr",
        )
        await _approve_only(repository, requested, prefix="legacy-asr-wrapper")
        admitted = await repository.admit_operator_capped_asr_exact(
            owner_user_id="owner-1",
            thread_id="thread-1",
            execution_run_id="legacy-asr-execution",
            server_name="ip-agent-evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=SHA_E,
            max_source_duration_millis=OPERATOR_DURATION_MILLIS,
            local_admission_limit_micros=OPERATOR_LIMIT_MICROS,
            currency="CNY",
            reservation_event_key="legacy-asr-reserve",
            admission_event_key="legacy-asr-admit",
            admission_jti="legacy-asr-admission-jti-0001",
            admission_proof_digest=SHA_D,
            now=NOW + timedelta(seconds=2),
        )
        assert admitted is not None
        assert admitted["id"] == requested["id"]
        assert admitted["capability"] == "asr"
        assert admitted["status"] == "admitted"
        assert admitted["execution_run_id"] == "legacy-asr-execution"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_over_budget_is_terminal_and_global_admission_jti_cannot_be_reused(tmp_path) -> None:
    repository = await _repository(tmp_path)
    try:
        rejected = await _request(repository, request_key="over-budget")
        approved = await repository.approve(
            rejected["id"],
            owner_user_id="owner-1",
            event_key="approve-over",
            expected_request_digest=rejected["request_digest"],
            approval_digest=SHA_C,
            now=NOW + timedelta(seconds=1),
        )
        assert approved is not None
        denied = await repository.reserve(
            rejected["id"],
            owner_user_id="owner-1",
            event_key="reserve-over",
            expected_request_digest=rejected["request_digest"],
            execution_run_id="execution-run-over",
            amount_micros=500_001,
            now=NOW + timedelta(seconds=2),
        )
        assert denied is not None and denied["status"] == "budget_rejected"
        with pytest.raises(ValueError, match="requires reserved status"):
            await repository.admit(
                rejected["id"],
                owner_user_id="owner-1",
                event_key="admit-denied",
                expected_request_digest=rejected["request_digest"],
                execution_run_id="execution-run-over",
                admission_jti="never-execute-this-jti",
                admission_proof_digest=SHA_D,
                now=NOW + timedelta(seconds=3),
            )

        first = await _request(repository, request_key="jti-first", stage_digest=SHA_C)
        second = await _request(repository, request_key="jti-second", stage_digest=SHA_D)
        await _approve_and_reserve(repository, first, prefix="jti-first")
        await _approve_and_reserve(repository, second, prefix="jti-second")
        reused_jti = "globally-unique-jti-0001"
        await _admit(repository, first, event_key="admit-first", jti=reused_jti)
        with pytest.raises(ValueError, match="already been consumed"):
            await _admit(repository, second, event_key="admit-second", jti=reused_jti)
        current = await repository.get(second["id"], owner_user_id="owner-1")
        assert current is not None and current["status"] == "reserved"
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_call_ledger_is_deletion_only_and_never_restored_from_owner_backup(tmp_path) -> None:
    repository = await _repository(tmp_path)
    session_factory = get_session_factory()
    assert session_factory is not None
    lifecycle = PersonalIPDataLifecycleService(session_factory, minecontext=_FakeMineContext())
    try:
        requested = await _request(repository)
        backup = await lifecycle.export_backup("owner-1", now=NOW)
        serialized = json.dumps(backup, ensure_ascii=False)
        assert "paid_call_scopes" not in EXPORT_DATASET_NAMES
        assert "paid_call_events" not in EXPORT_DATASET_NAMES
        assert "asr-request-1" not in serialized
        assert "参考视频 90a3…4644" not in serialized
        assert backup["credential_policy"]["paid_call_admissions_included"] is False
        assert PERSONAL_IP_DELETION_ONLY_TABLES == {
            "personal_ip_paid_call_scopes",
            "personal_ip_paid_call_events",
        }

        preview = await lifecycle.preview_delete("owner-1", now=NOW)
        assert preview["record_counts"]["paid_call_scopes"] == 1
        assert preview["record_counts"]["paid_call_events"] == 1
        with pytest.raises(ValueError, match="empty owner scope"):
            await lifecycle.restore_backup("owner-1", backup)

        receipt = await lifecycle.delete_all(
            "owner-1",
            {
                "schema_version": "personal-ip-destructive-delete-confirmation-v1",
                "owner_user_id": "owner-1",
                "state_digest": preview["state_digest"],
                "confirmation_phrase": DELETE_CONFIRMATION_PHRASE,
                "backup_acknowledged": True,
                "delete_local_context": True,
            },
            now=NOW,
        )
        assert receipt["paid_call_admissions_deleted"] is True
        assert await repository.get(requested["id"], owner_user_id="owner-1") is None
        restored = await lifecycle.restore_backup("owner-1", backup)
        assert restored["paid_call_admissions_restored"] is False
        assert restored["paid_call_reapproval_required"] is True
    finally:
        await close_engine()
