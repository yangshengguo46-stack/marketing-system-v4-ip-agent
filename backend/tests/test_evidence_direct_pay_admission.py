from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.gateway.evidence_direct_pay import EvidenceASRDirectPayPolicy
from app.gateway.evidence_paid_call_admission import (
    EvidenceASRDirectPayGrantResolver,
)
from deerflow.config.database_config import DatabaseConfig
from deerflow.mcp.paid_admission import (
    PaidCallAdmissionRejected,
    PaidCallInvocation,
    PaidCallScope,
    SignedPreAdmittedGrantVerifier,
    canonical_tool_args_sha256,
    require_provider_request_binding,
)
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_paid_calls import (
    EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
    PersonalIPPaidCallRepository,
)

NOW = datetime(2026, 8, 3, 2, 0, tzinfo=UTC)
SECRET = "direct-pay-test-secret-value-00000000000000000000"
ARGS = {
    "video_refs": ["/mnt/user-data/uploads/reference.mp4"],
    "analysis_depth": "speech_text",
}
SOURCE_SHA = "a" * 64
STAGE_SHA = "b" * 64
PROVIDER_REQUEST_SHA = "c" * 64
APPROVAL_SHA = "d" * 64
OUTCOME_SHA = "e" * 64


async def _repository(tmp_path) -> PersonalIPPaidCallRepository:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    return PersonalIPPaidCallRepository(session_factory)


async def _approved_operator_capped_request(
    repository: PersonalIPPaidCallRepository,
) -> dict:
    requested = await repository.request_call(
        owner_user_id="owner-1",
        request_key="direct-asr-1",
        scope_kind="run",
        thread_id="thread-1",
        origin_run_id="origin-run-1",
        server_name="ip_evidence",
        tool_name="inspect_reference_videos",
        tool_args_sha256=canonical_tool_args_sha256(ARGS),
        provider="volcengine-mediakit",
        capability="asr",
        model="official-mediakit-asr-subtitles",
        sku="asr-subtitles",
        provider_label="火山引擎 AI MediaKit",
        capability_label="语音转写",
        object_ref_label="参考视频 aaaaaaaa…aaaaaaaa",
        source_duration_millis=8_000,
        source_sha256=SOURCE_SHA,
        stage_digest=STAGE_SHA,
        provider_request_sha256=PROVIDER_REQUEST_SHA,
        maximum_amount_micros=500_000,
        currency="CNY",
        billing_basis=("供应商价格未知；Owner 接受本地准入风险上限，该上限不是供应商计费封顶"),
        policy_version=EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
        price_version="provider-price-unknown-local-admission-cap-v1",
        provider_input_attested=False,
        evidence_coverage="partial",
        warning_code="provider_content_hash_unattested",
        expires_at=NOW + timedelta(minutes=15),
        price_status="operator_capped",
        now=NOW,
    )
    approved = await repository.approve(
        requested["id"],
        owner_user_id="owner-1",
        event_key="owner-approve-direct-asr",
        expected_request_digest=requested["request_digest"],
        approval_digest=APPROVAL_SHA,
        expected_event_count=1,
        now=NOW + timedelta(seconds=1),
    )
    assert approved is not None
    return approved


def _policy() -> EvidenceASRDirectPayPolicy:
    return EvidenceASRDirectPayPolicy(
        enabled=True,
        local_admission_limit_micros=500_000,
        max_source_duration_millis=30_000,
    )


def test_direct_pay_policy_is_explicit_bounded_and_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("IP_AGENT_EVIDENCE_ASR_DIRECT_PAY_ENABLED", raising=False)
    assert EvidenceASRDirectPayPolicy.from_environment() == EvidenceASRDirectPayPolicy()

    monkeypatch.setenv("IP_AGENT_EVIDENCE_ASR_DIRECT_PAY_ENABLED", "true")
    monkeypatch.setenv(
        "IP_AGENT_EVIDENCE_ASR_DIRECT_PAY_MAXIMUM_MICROS",
        "500000",
    )
    monkeypatch.setenv(
        "IP_AGENT_EVIDENCE_ASR_DIRECT_PAY_MAX_DURATION_SECONDS",
        "30",
    )
    policy = EvidenceASRDirectPayPolicy.from_environment()
    assert policy.enabled is True
    assert policy.admits_source(duration_millis=30_000) is True
    assert policy.admits_source(duration_millis=30_001) is False
    assert policy.policy_version == EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION


@pytest.mark.asyncio
async def test_operator_cap_cannot_be_relabelled_quote_or_expanded_to_ocr(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        common = {
            "owner_user_id": "owner-1",
            "request_key": "invalid-direct-pay",
            "scope_kind": "run",
            "thread_id": "thread-1",
            "origin_run_id": "origin-run-1",
            "server_name": "ip_evidence",
            "tool_name": "inspect_reference_videos",
            "tool_args_sha256": canonical_tool_args_sha256(ARGS),
            "provider": "volcengine-mediakit",
            "capability": "ocr",
            "model": "model",
            "sku": "ocr",
            "provider_label": "MediaKit",
            "capability_label": "OCR",
            "object_ref_label": "参考视频 aaaa…aaaa",
            "source_duration_millis": 8_000,
            "source_sha256": SOURCE_SHA,
            "stage_digest": STAGE_SHA,
            "provider_request_sha256": PROVIDER_REQUEST_SHA,
            "maximum_amount_micros": 500_000,
            "currency": "CNY",
            "billing_basis": "本地风险上限，不是供应商报价",
            "policy_version": EVIDENCE_ASR_DIRECT_PAY_POLICY_VERSION,
            "price_version": "unknown",
            "provider_input_attested": False,
            "evidence_coverage": "partial",
            "warning_code": "input_unattested",
            "expires_at": NOW + timedelta(minutes=1),
            "price_status": "operator_capped",
            "now": NOW,
        }
        with pytest.raises(ValueError, match="restricted.*MediaKit ASR"):
            await repository.request_call(**common)

        common["capability"] = "asr"
        common["price_status"] = "unknown"
        with pytest.raises(ValueError, match="cannot be represented as a quote"):
            await repository.request_call(**common)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_owner_approved_single_video_asr_is_atomically_admitted_and_reconciled(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = await _approved_operator_capped_request(repository)
        assert approved["price_status"] == "operator_capped"
        assert approved["status"] == "approved"

        resolver = EvidenceASRDirectPayGrantResolver(
            repository=repository,
            policy=_policy(),
            signing_secret=SECRET,
            clock=lambda: NOW + timedelta(seconds=2),
            provider_configured=lambda: True,
        )
        scope = PaidCallScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="execution-run-1",
            server_name="ip_evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            provider="volcengine-mediakit",
            capability="asr",
        )
        grant = await resolver.reserve_approved_call(scope)
        assert grant is not None
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "admitted"
        assert current["execution_run_id"] == "execution-run-1"
        assert current["reserved_amount_micros"] == 500_000
        assert [event["event_type"] for event in current["events"]] == [
            "requested",
            "approved",
            "reserved",
            "admitted",
        ]
        serialized = json.dumps(current, ensure_ascii=False)
        assert grant not in serialized
        assert "direct-pay-test-secret" not in serialized

        invocation = PaidCallInvocation(
            server_name="ip_evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            provider="volcengine-mediakit",
            capability="asr",
        )
        verifier = SignedPreAdmittedGrantVerifier(signing_secret=SECRET)
        claim = await verifier.verify_and_admit_once(grant, invocation)
        assert claim.owner_user_id == "owner-1"
        assert claim.thread_id == "thread-1"
        assert claim.run_id == "execution-run-1"
        assert claim.source_sha256 == SOURCE_SHA
        assert claim.stage_spec_sha256 == STAGE_SHA
        assert claim.provider_request_sha256 == PROVIDER_REQUEST_SHA
        assert claim.maximum_amount_micros == 500_000
        require_provider_request_binding(
            claim,
            provider_request_sha256=PROVIDER_REQUEST_SHA,
            source_sha256=SOURCE_SHA,
            stage_spec_sha256=STAGE_SHA,
            estimated_amount_micros=500_000,
            currency="CNY",
        )
        with pytest.raises(
            PaidCallAdmissionRejected,
            match="PAID_CALL_GRANT_REPLAYED",
        ):
            await verifier.verify_and_admit_once(grant, invocation)
        assert await resolver.reserve_approved_call(scope) is None

        reconciled = await repository.mark_operator_capped_asr_reconciliation_exact(
            owner_user_id="owner-1",
            thread_id="thread-1",
            execution_run_id="execution-run-1",
            server_name="ip_evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            source_duration_millis=8_000,
            source_sha256=SOURCE_SHA,
            stage_digest=STAGE_SHA,
            provider_request_sha256=PROVIDER_REQUEST_SHA,
            event_key="reconcile-unknown-provider-charge",
            execution_outcome_digest=OUTCOME_SHA,
            now=NOW + timedelta(seconds=3),
        )
        assert reconciled is not None
        assert reconciled["status"] == "reconciliation_required"
        assert reconciled["reserved_amount_micros"] == 500_000
        assert reconciled["settled_amount_micros"] is None

        settled = await repository.settle(
            approved["id"],
            owner_user_id="owner-1",
            event_key="provider-cost-received",
            expected_request_digest=approved["request_digest"],
            execution_run_id="execution-run-1",
            actual_amount_micros=120_000,
            provider_receipt_digest="f" * 64,
            expected_event_count=5,
            now=NOW + timedelta(seconds=4),
        )
        assert settled is not None
        assert settled["status"] == "settled"
        assert settled["settled_amount_micros"] == 120_000
        assert settled["reserved_amount_micros"] == 0
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_atomic_admission_rejects_overlong_source_and_non_asr_scope(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        await _approved_operator_capped_request(repository)
        too_short_policy = EvidenceASRDirectPayPolicy(
            enabled=True,
            local_admission_limit_micros=500_000,
            max_source_duration_millis=7_999,
        )
        resolver = EvidenceASRDirectPayGrantResolver(
            repository=repository,
            policy=too_short_policy,
            signing_secret=SECRET,
            clock=lambda: NOW + timedelta(seconds=2),
            provider_configured=lambda: True,
        )
        scope = PaidCallScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="execution-run-1",
            server_name="ip_evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            provider="volcengine-mediakit",
            capability="asr",
        )
        assert await resolver.reserve_approved_call(scope) is None
        assert await resolver.reserve_approved_call(scope.model_copy(update={"capability": "ocr"})) is None
        rows = await repository.list_thread(
            owner_user_id="owner-1",
            thread_id="thread-1",
        )
        assert rows[0]["status"] == "approved"
        assert rows[0]["execution_run_id"] is None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_missing_provider_configuration_cannot_consume_owner_approval(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = await _approved_operator_capped_request(repository)
        resolver = EvidenceASRDirectPayGrantResolver(
            repository=repository,
            policy=_policy(),
            signing_secret=SECRET,
            clock=lambda: NOW + timedelta(seconds=2),
            provider_configured=lambda: False,
        )
        scope = PaidCallScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="execution-run-without-provider",
            server_name="ip_evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            provider="volcengine-mediakit",
            capability="asr",
        )

        assert await resolver.reserve_approved_call(scope) is None
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] == "approved"
        assert current["execution_run_id"] is None
        assert current["event_count"] == 2
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_unresolved_invocation_never_leaves_consumed_grant_admitted(
    tmp_path,
) -> None:
    repository = await _repository(tmp_path)
    try:
        approved = await _approved_operator_capped_request(repository)
        resolver = EvidenceASRDirectPayGrantResolver(
            repository=repository,
            policy=_policy(),
            signing_secret=SECRET,
            clock=lambda: NOW + timedelta(seconds=2),
            provider_configured=lambda: True,
        )
        scope = PaidCallScope(
            owner_user_id="owner-1",
            thread_id="thread-1",
            run_id="execution-run-failed",
            server_name="ip_evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            provider="volcengine-mediakit",
            capability="asr",
        )
        assert await resolver.reserve_approved_call(scope) is not None

        unresolved = await repository.mark_operator_capped_asr_invocation_unresolved(
            owner_user_id="owner-1",
            thread_id="thread-1",
            execution_run_id="execution-run-failed",
            server_name="ip_evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256=canonical_tool_args_sha256(ARGS),
            event_key="provider-result-unresolved",
            execution_outcome_digest=OUTCOME_SHA,
            now=NOW + timedelta(seconds=3),
        )

        assert unresolved is not None
        assert unresolved["status"] == "reconciliation_required"
        assert unresolved["reserved_amount_micros"] == 500_000
        assert unresolved["settled_amount_micros"] is None
        assert unresolved["events"][-1]["reason_code"] == ("provider_execution_outcome_unresolved")
        current = await repository.get(approved["id"], owner_user_id="owner-1")
        assert current is not None
        assert current["status"] != "admitted"
    finally:
        await close_engine()
