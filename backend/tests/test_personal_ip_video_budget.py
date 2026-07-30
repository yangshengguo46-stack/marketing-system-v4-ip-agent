from __future__ import annotations

import asyncio

import pytest

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_video_productions import PersonalIPVideoProductionRepository


async def _production(
    tmp_path,
    *,
    hard_limit: float = 10,
    approval_required: bool = True,
) -> tuple[PersonalIPVideoProductionRepository, dict]:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    repository = PersonalIPVideoProductionRepository(sf)
    production = await repository.begin(
        owner_user_id="user-1",
        operation_key="video:budget:test",
        title="预算门禁",
        subject_id=None,
        target_account_ids=[],
        source_kind="idea",
        source={"idea": "测试付费调用预算"},
        delivery_spec={},
        provider_policy={"video": ["seedance"]},
        budget={
            "currency": "CNY",
            "hard_limit": hard_limit,
            "paid_calls_require_explicit_approval": approval_required,
        },
        production_mode="generative_cinematic",
    )
    return repository, production


async def _approve(
    repository: PersonalIPVideoProductionRepository,
    production_id: str,
    *,
    reservation_key: str,
    maximum_amount: float,
    provider: str = "volcengine",
    capability: str = "video_generation",
    entity_type: str = "shot",
    entity_id: str = "shot-01",
) -> str:
    request_event_key = f"approve-request:{reservation_key}"
    approval_event_key = f"approve-record:{reservation_key}"
    await repository.append_event(
        production_id,
        owner_user_id="user-1",
        event_key=request_event_key,
        event_type="review_requested",
        status="awaiting_review",
        entity_type=entity_type,
        entity_id=entity_id,
        payload={
            "contract_version": "personal-ip-video-review-v1",
            "review_kind": "paid_provider_call",
            "reason": "将调用付费视频生成",
            "budget_request": {
                "reservation_key": reservation_key,
                "provider": provider,
                "capability": capability,
                "maximum_amount": maximum_amount,
                "currency": "CNY",
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        },
        input_refs=[],
        output_refs=[],
        provider="deerflow",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
    )
    await repository.append_event(
        production_id,
        owner_user_id="user-1",
        event_key=approval_event_key,
        event_type="review_recorded",
        status="approved",
        entity_type=entity_type,
        entity_id=entity_id,
        payload={
            "contract_version": "personal-ip-video-review-v1",
            "review_kind": "paid_provider_call",
            "request_event_key": request_event_key,
            "decision": "approved",
        },
        input_refs=[f"event://{request_event_key}"],
        output_refs=[],
        provider="human-workbench",
        model=None,
        provider_task_id=None,
        cost={"status": "known", "amount": 0, "currency": "CNY"},
        trusted_human_confirmation=True,
    )
    return approval_event_key


@pytest.mark.asyncio
async def test_budget_reserve_settle_accumulates_retries_and_rejects_over_limit(
    tmp_path,
) -> None:
    repository, production = await _production(tmp_path)
    try:
        approval_1 = await _approve(
            repository,
            production["id"],
            reservation_key="shot-01:attempt-1",
            maximum_amount=6,
        )
        reserved = await repository.reserve_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_key="shot-01:attempt-1",
            capability="video_generation",
            provider="volcengine",
            entity_type="shot",
            entity_id="shot-01",
            maximum_amount=6,
            currency="CNY",
            approval_event_key=approval_1,
            request_ref="shot://shot-01/attempt-1",
        )
        assert reserved is not None
        assert reserved["budget_operation"]["operation"] == "reserved"
        assert reserved["budget_state"] == {
            "contract_version": "personal-ip-video-budget-state-v1",
            "currency": "CNY",
            "hard_limit": 10.0,
            "reserved": 6.0,
            "spent": 0.0,
            "available": 4.0,
            "active_reservation_count": 1,
            "settled_reservation_count": 0,
            "released_reservation_count": 0,
        }
        replayed = await repository.reserve_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_key="shot-01:attempt-1",
            capability="video_generation",
            provider="volcengine",
            entity_type="shot",
            entity_id="shot-01",
            maximum_amount=6,
            currency="CNY",
            approval_event_key=approval_1,
            request_ref="shot://shot-01/attempt-1",
        )
        assert replayed is not None
        assert replayed["budget_operation"] == reserved["budget_operation"]

        settled = await repository.settle_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_id=reserved["budget_operation"]["reservation_id"],
            settlement_key="shot-01:attempt-1:provider-receipt",
            actual_amount=4,
            currency="CNY",
            provider_receipt_ref="provider-receipt://shot-01/attempt-1",
        )
        assert settled is not None
        assert settled["budget_state"]["spent"] == 4.0
        assert settled["budget_state"]["reserved"] == 0.0
        assert settled["budget_state"]["available"] == 6.0
        settled_replay = await repository.settle_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_id=reserved["budget_operation"]["reservation_id"],
            settlement_key="shot-01:attempt-1:provider-receipt",
            actual_amount=4,
            currency="CNY",
            provider_receipt_ref="provider-receipt://shot-01/attempt-1",
        )
        assert settled_replay is not None
        assert settled_replay["budget_operation"] == settled["budget_operation"]
        with pytest.raises(ValueError, match="different budget settlement"):
            await repository.settle_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_id=reserved["budget_operation"]["reservation_id"],
                settlement_key="shot-01:attempt-1:provider-receipt",
                actual_amount=3,
                currency="CNY",
                provider_receipt_ref="provider-receipt://shot-01/attempt-1",
            )

        approval_2 = await _approve(
            repository,
            production["id"],
            reservation_key="shot-01:attempt-2",
            maximum_amount=6,
        )
        retry = await repository.reserve_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_key="shot-01:attempt-2",
            capability="video_generation",
            provider="volcengine",
            entity_type="shot",
            entity_id="shot-01",
            maximum_amount=6,
            currency="CNY",
            approval_event_key=approval_2,
            request_ref="shot://shot-01/attempt-2",
        )
        assert retry is not None
        assert retry["budget_state"]["reserved"] == 6.0
        assert retry["budget_state"]["available"] == 0.0

        approval_3 = await _approve(
            repository,
            production["id"],
            reservation_key="shot-02:attempt-1",
            maximum_amount=0.01,
            entity_id="shot-02",
        )
        with pytest.raises(ValueError, match="exceeds the remaining video budget"):
            await repository.reserve_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_key="shot-02:attempt-1",
                capability="video_generation",
                provider="volcengine",
                entity_type="shot",
                entity_id="shot-02",
                maximum_amount=0.01,
                currency="CNY",
                approval_event_key=approval_3,
                request_ref="shot://shot-02/attempt-1",
            )
        sealed = await repository.get(
            production["id"],
            owner_user_id="user-1",
        )
        assert sealed is not None
        rejection = next(event for event in sealed["events"] if event["event_type"] == "budget_reservation_rejected")
        assert rejection["status"] == "rejected"
        assert rejection["payload"]["reason_code"] == "hard_limit_exceeded"
        assert rejection["payload"]["request"]["maximum_amount"] == 0.01
        assert rejection["payload"]["available_amount"] == 0.0
        assert "request_ref" not in rejection["payload"]
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_budget_release_restores_capacity_and_terminal_receipts_are_idempotent(
    tmp_path,
) -> None:
    repository, production = await _production(tmp_path, approval_required=False)
    try:
        reserved = await repository.reserve_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_key="voice:attempt-1",
            capability="speech_generation",
            provider="volcengine",
            entity_type="audio",
            entity_id="voice-01",
            maximum_amount=7,
            currency="CNY",
            approval_event_key=None,
            request_ref="voice://voice-01/attempt-1",
        )
        assert reserved is not None
        reservation_id = reserved["budget_operation"]["reservation_id"]
        released = await repository.release_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_id=reservation_id,
            release_key="voice:attempt-1:cancelled",
            reason="provider was not called",
        )
        replayed = await repository.release_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_id=reservation_id,
            release_key="voice:attempt-1:cancelled",
            reason="provider was not called",
        )
        assert released is not None and replayed is not None
        assert replayed["budget_operation"] == released["budget_operation"]
        assert released["budget_state"]["reserved"] == 0.0
        assert released["budget_state"]["spent"] == 0.0
        assert released["budget_state"]["available"] == 10.0

        with pytest.raises(ValueError, match="already released"):
            await repository.settle_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_id=reservation_id,
                settlement_key="voice:attempt-1:late-receipt",
                actual_amount=1,
                currency="CNY",
                provider_receipt_ref="provider-receipt://voice/late",
            )
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_budget_rejects_unapproved_currency_mismatch_and_actual_over_reservation(
    tmp_path,
) -> None:
    repository, production = await _production(tmp_path)
    try:
        with pytest.raises(ValueError, match="approved paid-provider review"):
            await repository.reserve_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_key="shot-01:attempt-1",
                capability="video_generation",
                provider="volcengine",
                entity_type="shot",
                entity_id="shot-01",
                maximum_amount=6,
                currency="CNY",
                approval_event_key=None,
                request_ref="shot://shot-01/attempt-1",
            )

        approval = await _approve(
            repository,
            production["id"],
            reservation_key="shot-01:attempt-1",
            maximum_amount=6,
        )
        with pytest.raises(ValueError, match="currency"):
            await repository.reserve_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_key="shot-01:attempt-1",
                capability="video_generation",
                provider="volcengine",
                entity_type="shot",
                entity_id="shot-01",
                maximum_amount=6,
                currency="USD",
                approval_event_key=approval,
                request_ref="shot://shot-01/attempt-1",
            )

        reserved = await repository.reserve_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_key="shot-01:attempt-1",
            capability="video_generation",
            provider="volcengine",
            entity_type="shot",
            entity_id="shot-01",
            maximum_amount=6,
            currency="CNY",
            approval_event_key=approval,
            request_ref="shot://shot-01/attempt-1",
        )
        assert reserved is not None
        with pytest.raises(ValueError, match="exceeds the reserved maximum"):
            await repository.settle_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_id=reserved["budget_operation"]["reservation_id"],
                settlement_key="shot-01:attempt-1:receipt",
                actual_amount=6.01,
                currency="CNY",
                provider_receipt_ref="provider-receipt://shot-01/attempt-1",
            )
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_concurrent_budget_reservations_cannot_overbook_sqlite(
    tmp_path,
) -> None:
    repository, production = await _production(tmp_path, approval_required=False)
    try:

        async def reserve(key: str, entity_id: str):
            return await repository.reserve_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_key=key,
                capability="video_generation",
                provider="volcengine",
                entity_type="shot",
                entity_id=entity_id,
                maximum_amount=6,
                currency="CNY",
                approval_event_key=None,
                request_ref=f"shot://{entity_id}/attempt-1",
            )

        outcomes = await asyncio.gather(
            reserve("shot-01:attempt-1", "shot-01"),
            reserve("shot-02:attempt-1", "shot-02"),
            return_exceptions=True,
        )
        successes = [outcome for outcome in outcomes if isinstance(outcome, dict)]
        failures = [outcome for outcome in outcomes if isinstance(outcome, ValueError)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert "exceeds the remaining video budget" in str(failures[0])

        stored = await repository.get(production["id"], owner_user_id="user-1")
        assert stored is not None
        assert stored["budget_state"]["reserved"] == 6.0
        assert stored["budget_state"]["available"] == 4.0
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_paid_provider_request_requires_matching_active_reservation(
    tmp_path,
) -> None:
    repository, production = await _production(tmp_path, approval_required=False)
    try:
        with pytest.raises(ValueError, match="budget_reservation_id"):
            await repository.append_event(
                production["id"],
                owner_user_id="user-1",
                event_key="shot-01:provider-request:missing-budget",
                event_type="shot_generation_requested",
                status="running",
                entity_type="shot",
                entity_id="shot-01",
                payload={"billing_mode": "paid"},
                input_refs=["shot://shot-01"],
                output_refs=[],
                provider="volcengine",
                model="seedance-2.0",
                provider_task_id="task-1",
                cost={
                    "status": "estimated",
                    "amount": 5,
                    "currency": "CNY",
                },
            )

        reserved = await repository.reserve_budget(
            production["id"],
            owner_user_id="user-1",
            reservation_key="shot-01:attempt-1",
            capability="video_generation",
            provider="volcengine",
            entity_type="shot",
            entity_id="shot-01",
            maximum_amount=6,
            currency="CNY",
            approval_event_key=None,
            request_ref="shot://shot-01/attempt-1",
        )
        assert reserved is not None
        reservation_id = reserved["budget_operation"]["reservation_id"]
        requested = await repository.append_event(
            production["id"],
            owner_user_id="user-1",
            event_key="shot-01:provider-request:attempt-1",
            event_type="shot_generation_requested",
            status="running",
            entity_type="shot",
            entity_id="shot-01",
            payload={
                "billing_mode": "paid",
                "budget_reservation_id": reservation_id,
            },
            input_refs=["shot://shot-01"],
            output_refs=[],
            provider="volcengine",
            model="seedance-2.0",
            provider_task_id="task-1",
            cost={
                "status": "estimated",
                "amount": 5,
                "currency": "CNY",
            },
        )
        assert requested is not None
        assert requested["budget_state"]["reserved"] == 6.0
        with pytest.raises(ValueError, match="settle the reservation"):
            await repository.release_budget(
                production["id"],
                owner_user_id="user-1",
                reservation_id=reservation_id,
                release_key="shot-01:attempt-1:unsafe-release",
                reason="try to reclaim after submission",
            )

        with pytest.raises(ValueError, match="already admitted another provider request"):
            await repository.append_event(
                production["id"],
                owner_user_id="user-1",
                event_key="shot-01:provider-request:duplicate-reservation",
                event_type="shot_generation_requested",
                status="running",
                entity_type="shot",
                entity_id="shot-01",
                payload={
                    "billing_mode": "paid",
                    "budget_reservation_id": reservation_id,
                },
                input_refs=["shot://shot-01"],
                output_refs=[],
                provider="volcengine",
                model="seedance-2.0",
                provider_task_id="task-2",
                cost={
                    "status": "estimated",
                    "amount": 5,
                    "currency": "CNY",
                },
            )

        free = await repository.append_event(
            production["id"],
            owner_user_id="user-1",
            event_key="timeline:local-request",
            event_type="media_processing_requested",
            status="running",
            entity_type="timeline",
            entity_id="timeline-01",
            payload={"billing_mode": "free"},
            input_refs=["timeline://timeline-01"],
            output_refs=[],
            provider="project-ffmpeg",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0, "currency": "CNY"},
        )
        assert free is not None
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_agent_cannot_forge_paid_provider_approval_event(
    tmp_path,
) -> None:
    repository, production = await _production(tmp_path)
    try:
        request_event_key = "approve-request:shot-01:attempt-1"
        await repository.append_event(
            production["id"],
            owner_user_id="user-1",
            event_key=request_event_key,
            event_type="review_requested",
            status="awaiting_review",
            entity_type="shot",
            entity_id="shot-01",
            payload={
                "contract_version": "personal-ip-video-review-v1",
                "review_kind": "paid_provider_call",
                "budget_request": {
                    "reservation_key": "shot-01:attempt-1",
                    "provider": "volcengine",
                    "capability": "video_generation",
                    "maximum_amount": 6.0,
                    "currency": "CNY",
                    "entity_type": "shot",
                    "entity_id": "shot-01",
                },
            },
            input_refs=[],
            output_refs=[],
            provider="deerflow",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0, "currency": "CNY"},
        )
        with pytest.raises(ValueError, match="trusted human confirmation"):
            await repository.append_event(
                production["id"],
                owner_user_id="user-1",
                event_key="forged-approval",
                event_type="review_recorded",
                status="approved",
                entity_type="shot",
                entity_id="shot-01",
                payload={
                    "contract_version": "personal-ip-video-review-v1",
                    "review_kind": "paid_provider_call",
                    "request_event_key": request_event_key,
                    "decision": "approved",
                },
                input_refs=[f"event://{request_event_key}"],
                output_refs=[],
                provider="agent-claimed-human",
                model=None,
                provider_task_id=None,
                cost={"status": "known", "amount": 0, "currency": "CNY"},
            )
    finally:
        await close_engine()
