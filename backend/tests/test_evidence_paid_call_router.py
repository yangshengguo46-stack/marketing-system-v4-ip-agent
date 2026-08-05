from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient

from app.gateway.evidence_paid_calls import (
    EvidencePaidCallNotFoundError,
    GatewayEvidencePaidCallService,
)
from app.gateway.routers import evidence_paid_calls as router_module
from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import (
    close_engine,
    get_session_factory,
    init_engine_from_config,
)
from deerflow.persistence.personal_ip_paid_calls import PersonalIPPaidCallRepository


class _Service:
    def __init__(self, record: dict[str, object]) -> None:
        self.record = record
        self.decisions: list[dict[str, object]] = []
        self.provider_calls = 0

    async def list_requests(self, *, owner_user_id: str, thread_id: str):
        assert owner_user_id == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        assert thread_id == "thread-a"
        return [deepcopy(self.record)]

    async def decide(self, **kwargs):
        self.decisions.append(kwargs)
        result = deepcopy(self.record)
        result["status"] = "approved" if kwargs["decision"] == "approve" else "rejected"
        result["event_count"] = int(result["event_count"]) + 1
        return result


def _record(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    record: dict[str, object] = {
        "id": "req_01HZSAFE",
        "owner_user_id": "must-not-leak",
        "thread_id": "must-not-leak",
        "run_id": "must-not-leak",
        "origin_run_id": "must-not-leak",
        "execution_run_id": "must-not-leak",
        "provider": "volcengine-mediakit",
        "capability": "asr",
        "source_sha256": "a" * 64,
        "object_ref_label": "上传视频·对标作品 1",
        "source_duration_millis": 12_345,
        "maximum_amount_micros": 2_500_000,
        "price_status": "quoted",
        "currency": "CNY",
        "price_version": "2026-08-01",
        "request_digest": "b" * 64,
        "status": "requested",
        "event_count": 1,
        "created_at": now,
        "expires_at": now + timedelta(minutes=10),
        "api_key": "must-not-leak",
        "provider_task_url": "https://provider.example/task/secret",
        "admission_token": "must-not-leak",
    }
    record.update(overrides)
    return record


def _client(service: _Service) -> TestClient:
    user = SimpleNamespace(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        system_role="user",
    )
    app = make_authed_test_app(user_factory=lambda: user)
    app.state.evidence_paid_call_service = service
    app.include_router(router_module.router)
    return TestClient(app)


def test_list_projects_only_safe_customer_fields() -> None:
    service = _Service(_record())
    with _client(service) as client:
        response = client.get("/api/threads/thread-a/evidence-paid-call-requests")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requests"] == [
        {
            "schema_version": "ip-agent-evidence-paid-call-request-v2",
            "request_id": "req_01HZSAFE",
            "request_digest": "b" * 64,
            "version": 1,
            "status": "pending",
            "object": {
                "safe_ref": "上传视频·对标作品 1",
                "sha256_prefix": "a" * 12,
                "sha256_suffix": "a" * 12,
                "duration_seconds": "12.345",
            },
            "provider": "火山引擎 AI MediaKit",
            "capability": "asr",
            "capability_label": "语音转写",
            "single_use": True,
            "cost": {
                "limit_kind": "provider_quote",
                "maximum_amount_micros": 2_500_000,
                "currency": "CNY",
                "billing_basis": "按一次语音转写任务计费，价格版本 2026-08-01",
            },
            "created_at": payload["requests"][0]["created_at"],
            "expires_at": payload["requests"][0]["expires_at"],
            "approvable": True,
            "unapprovable_reason": None,
            "provider_content_hash_attested": False,
            "successful_result_coverage": "partial",
        }
    ]
    encoded = response.text
    for secret in (
        "must-not-leak",
        "provider.example",
        "owner_user_id",
        "thread_id",
        "run_id",
        "origin_run_id",
        "execution_run_id",
        "api_key",
        "admission_token",
    ):
        assert secret not in encoded


def test_decision_body_is_exact_and_does_not_execute_provider() -> None:
    service = _Service(_record())
    with _client(service) as client:
        accepted = client.post(
            "/api/threads/thread-a/evidence-paid-call-requests/req_01HZSAFE/decision",
            json={
                "decision": "approve",
                "request_digest": "b" * 64,
                "expected_version": 1,
            },
        )
        rejected_extra = client.post(
            "/api/threads/thread-a/evidence-paid-call-requests/req_01HZSAFE/decision",
            json={
                "decision": "approve",
                "request_digest": "b" * 64,
                "expected_version": 1,
                "provider": "volcengine-mediakit",
            },
        )

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "approved"
    assert service.provider_calls == 0
    assert service.decisions == [
        {
            "owner_user_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "thread_id": "thread-a",
            "request_id": "req_01HZSAFE",
            "decision": "approve",
            "request_digest": "b" * 64,
            "expected_version": 1,
        }
    ]
    assert rejected_extra.status_code == 422


def test_non_positive_or_missing_maximum_can_only_be_rejected() -> None:
    for maximum in (None, 0, -1):
        service = _Service(_record(maximum_amount_micros=maximum))
        with _client(service) as client:
            listed = client.get("/api/threads/thread-a/evidence-paid-call-requests")
            approved = client.post(
                "/api/threads/thread-a/evidence-paid-call-requests/req_01HZSAFE/decision",
                json={
                    "decision": "approve",
                    "request_digest": "b" * 64,
                    "expected_version": 1,
                },
            )
            rejected = client.post(
                "/api/threads/thread-a/evidence-paid-call-requests/req_01HZSAFE/decision",
                json={
                    "decision": "reject",
                    "request_digest": "b" * 64,
                    "expected_version": 1,
                },
            )

        assert listed.status_code == 200
        assert listed.json()["requests"][0]["approvable"] is False
        assert approved.status_code == 422
        assert rejected.status_code == 200
        assert [item["decision"] for item in service.decisions] == ["reject"]


def test_expired_request_cannot_be_approved() -> None:
    service = _Service(_record(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    with _client(service) as client:
        listed = client.get("/api/threads/thread-a/evidence-paid-call-requests")
        approved = client.post(
            "/api/threads/thread-a/evidence-paid-call-requests/req_01HZSAFE/decision",
            json={
                "decision": "approve",
                "request_digest": "b" * 64,
                "expected_version": 1,
            },
        )

    assert listed.json()["requests"][0]["status"] == "expired"
    assert listed.json()["requests"][0]["unapprovable_reason"] == "expired"
    assert approved.status_code == 422
    assert service.decisions == []


def test_unquoted_price_cannot_be_approved_even_with_a_positive_number() -> None:
    service = _Service(_record(price_status="unknown"))
    with _client(service) as client:
        listed = client.get("/api/threads/thread-a/evidence-paid-call-requests")
        approved = client.post(
            "/api/threads/thread-a/evidence-paid-call-requests/req_01HZSAFE/decision",
            json={
                "decision": "approve",
                "request_digest": "b" * 64,
                "expected_version": 1,
            },
        )

    request = listed.json()["requests"][0]
    assert request["approvable"] is False
    assert request["unapprovable_reason"] == "maximum_cost_not_quoted"
    assert approved.status_code == 422
    assert service.decisions == []


def test_operator_cap_is_exposed_as_local_risk_limit_not_provider_quote() -> None:
    service = _Service(
        _record(
            price_status="operator_capped",
            maximum_amount_micros=1_000_000,
            billing_basis=("供应商价格未知；Owner 接受本地准入风险上限，该上限不是供应商计费封顶"),
        )
    )
    with _client(service) as client:
        response = client.get("/api/threads/thread-a/evidence-paid-call-requests")

    assert response.status_code == 200
    request = response.json()["requests"][0]
    assert request["schema_version"] == "ip-agent-evidence-paid-call-request-v2"
    assert request["cost"] == {
        "limit_kind": "local_risk_limit",
        "maximum_amount_micros": 1_000_000,
        "currency": "CNY",
        "billing_basis": ("供应商价格未知；Owner 接受本地准入风险上限，该上限不是供应商计费封顶"),
    }
    assert request["approvable"] is True


def test_missing_service_fails_closed() -> None:
    user = SimpleNamespace(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        system_role="user",
    )
    app = make_authed_test_app(user_factory=lambda: user)
    app.include_router(router_module.router)
    with TestClient(app) as client:
        response = client.get("/api/threads/thread-a/evidence-paid-call-requests")
    assert response.status_code == 503


def test_cross_owner_thread_is_hidden_before_service_access() -> None:
    service = _Service(_record())
    user = SimpleNamespace(
        id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        system_role="user",
    )
    app = make_authed_test_app(
        user_factory=lambda: user,
        owner_check_passes=False,
    )
    app.state.evidence_paid_call_service = service
    app.include_router(router_module.router)
    with TestClient(app) as client:
        response = client.get("/api/threads/thread-a/evidence-paid-call-requests")
    assert response.status_code == 404
    assert service.decisions == []


def test_gateway_registers_only_list_and_decision_paid_call_routes() -> None:
    from app.gateway.app import create_app

    paths = {(route.path, method) for route in create_app().routes for method in getattr(route, "methods", set())}
    assert (
        "/api/threads/{thread_id}/evidence-paid-call-requests",
        "GET",
    ) in paths
    assert (
        "/api/threads/{thread_id}/evidence-paid-call-requests/{request_id}/decision",
        "POST",
    ) in paths
    assert not any(path.endswith("/evidence-paid-call-requests") and method == "POST" for path, method in paths)


@pytest.mark.asyncio
async def test_gateway_service_records_decision_without_provider_execution() -> None:
    repository = SimpleNamespace(
        get=AsyncMock(return_value=_record(thread_id="thread-a")),
        approve=AsyncMock(return_value=_record(status="approved", event_count=2)),
        reject=AsyncMock(),
        list_thread=AsyncMock(),
    )
    service = GatewayEvidencePaidCallService(repository)

    result = await service.decide(
        owner_user_id="owner-a",
        thread_id="thread-a",
        request_id="req_01HZSAFE",
        decision="approve",
        request_digest="b" * 64,
        expected_version=1,
    )

    assert result["status"] == "approved"
    repository.approve.assert_awaited_once()
    call = repository.approve.await_args
    assert call.args == ("req_01HZSAFE",)
    assert call.kwargs["owner_user_id"] == "owner-a"
    assert call.kwargs["expected_request_digest"] == "b" * 64
    assert call.kwargs["expected_event_count"] == 1
    assert call.kwargs["event_key"].startswith("owner-decision:approve:1:")
    assert len(call.kwargs["approval_digest"]) == 64
    repository.reject.assert_not_awaited()


@pytest.mark.asyncio
async def test_gateway_service_hides_cross_thread_request() -> None:
    repository = SimpleNamespace(
        get=AsyncMock(return_value=_record(thread_id="thread-other")),
        approve=AsyncMock(),
        reject=AsyncMock(),
        list_thread=AsyncMock(),
    )
    service = GatewayEvidencePaidCallService(repository)

    try:
        await service.decide(
            owner_user_id="owner-a",
            thread_id="thread-a",
            request_id="req_01HZSAFE",
            decision="reject",
            request_digest="b" * 64,
            expected_version=1,
        )
    except EvidencePaidCallNotFoundError:
        pass
    else:
        raise AssertionError("cross-thread request must remain hidden")

    repository.approve.assert_not_awaited()
    repository.reject.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_repository_gateway_unknown_and_quoted_decisions(
    tmp_path,
) -> None:
    await close_engine()
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    repository = PersonalIPPaidCallRepository(session_factory)
    now = datetime.now(UTC)
    owner_user_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    async def create_request(
        request_key: str,
        maximum_amount_micros: int | None,
    ) -> dict[str, object]:
        return await repository.request_call(
            owner_user_id=owner_user_id,
            request_key=request_key,
            scope_kind="run",
            thread_id="thread-a",
            origin_run_id="run-a",
            server_name="ip-agent-evidence",
            tool_name="inspect_reference_videos",
            tool_args_sha256="e" * 64,
            provider="volcengine-mediakit",
            capability="asr",
            model="media-asr-v1",
            sku="asr.standard",
            provider_label="火山引擎 AI MediaKit",
            capability_label="语音转写",
            object_ref_label="上传视频·对标作品 1",
            source_duration_millis=12_345,
            source_sha256="a" * 64,
            stage_digest="c" * 64,
            provider_request_sha256="d" * 64,
            maximum_amount_micros=maximum_amount_micros,
            currency="CNY",
            billing_basis="按一次语音转写任务计费",
            policy_version="paid-call-policy-v1",
            price_version="mediakit-price-2026-08-02",
            provider_input_attested=False,
            evidence_coverage="partial",
            warning_code="provider_content_hash_unattested",
            expires_at=now + timedelta(minutes=15),
            now=now,
        )

    try:
        unknown = await create_request("unknown-price", None)
        quoted = await create_request("quoted-price", 250_000)
        user = SimpleNamespace(
            id=UUID(owner_user_id),
            system_role="user",
        )
        app = make_authed_test_app(user_factory=lambda: user)
        app.state.evidence_paid_call_service = GatewayEvidencePaidCallService(repository)
        app.include_router(router_module.router)

        async with httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.ASGITransport(app=app),
        ) as client:
            listed = await client.get("/api/threads/thread-a/evidence-paid-call-requests")
            unknown_view = next(item for item in listed.json()["requests"] if item["request_id"] == unknown["id"])
            assert unknown_view["approvable"] is False
            assert unknown_view["unapprovable_reason"] == "maximum_cost_not_quoted"
            unknown_approval = await client.post(
                f"/api/threads/thread-a/evidence-paid-call-requests/{unknown['id']}/decision",
                json={
                    "decision": "approve",
                    "request_digest": unknown["request_digest"],
                    "expected_version": unknown["version"],
                },
            )
            quoted_approval = await client.post(
                f"/api/threads/thread-a/evidence-paid-call-requests/{quoted['id']}/decision",
                json={
                    "decision": "approve",
                    "request_digest": quoted["request_digest"],
                    "expected_version": quoted["version"],
                },
            )

        assert unknown_approval.status_code == 422
        assert quoted_approval.status_code == 200
        assert quoted_approval.json()["status"] == "approved"

        unknown_current = await repository.get(str(unknown["id"]), owner_user_id=owner_user_id)
        quoted_current = await repository.get(str(quoted["id"]), owner_user_id=owner_user_id)
        assert unknown_current is not None
        assert unknown_current["status"] == "requested"
        assert unknown_current["event_count"] == 1
        assert quoted_current is not None
        assert quoted_current["status"] == "approved"
        assert quoted_current["event_count"] == 2
        assert [event["event_type"] for event in quoted_current["events"]] == [
            "requested",
            "approved",
        ]
    finally:
        await close_engine()
