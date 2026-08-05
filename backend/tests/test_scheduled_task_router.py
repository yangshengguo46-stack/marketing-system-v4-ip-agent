from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.gateway.routers import scheduled_tasks


def test_router_registers_list_endpoint():
    app = FastAPI()
    app.include_router(scheduled_tasks.router)
    client = TestClient(app)
    response = client.get("/api/scheduled-tasks")
    assert response.status_code != 404


def test_router_registers_trigger_route():
    app = FastAPI()
    app.include_router(scheduled_tasks.router)
    client = TestClient(app)
    response = client.post("/api/scheduled-tasks/task-1/trigger")
    assert response.status_code != 404


def test_router_registers_create_route():
    app = FastAPI()
    app.include_router(scheduled_tasks.router)
    client = TestClient(app)
    response = client.post(
        "/api/scheduled-tasks",
        json={
            "thread_id": "thread-1",
            "title": "Daily summary",
            "prompt": "Summarize thread",
            "schedule_type": "cron",
            "schedule_spec": {"cron": "0 9 * * *"},
            "timezone": "UTC",
        },
    )
    assert response.status_code != 404


@pytest.mark.asyncio
async def test_create_is_fail_closed_when_scheduler_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scheduled_tasks,
        "get_config",
        lambda: SimpleNamespace(scheduler=SimpleNamespace(enabled=False)),
    )
    monkeypatch.setattr(
        scheduled_tasks,
        "get_scheduled_task_repo",
        lambda _request: (_ for _ in ()).throw(AssertionError("disabled create must not access the task repository")),
    )

    body = scheduled_tasks.ScheduledTaskCreateRequest(
        title="must not be created",
        prompt="must not run",
        schedule_type="cron",
        schedule_spec={"cron": "0 9 * * *"},
        timezone="UTC",
    )
    with pytest.raises(HTTPException) as exc_info:
        await scheduled_tasks.create_scheduled_task(body=body)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Scheduled tasks are disabled"


@pytest.mark.asyncio
async def test_manual_trigger_is_fail_closed_when_scheduler_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scheduled_tasks,
        "get_config",
        lambda: SimpleNamespace(scheduler=SimpleNamespace(enabled=False)),
    )
    monkeypatch.setattr(
        scheduled_tasks,
        "get_scheduled_task_repo",
        lambda _request: (_ for _ in ()).throw(AssertionError("disabled trigger must not access the task repository")),
    )
    monkeypatch.setattr(
        scheduled_tasks,
        "get_scheduled_task_service",
        lambda _request: (_ for _ in ()).throw(AssertionError("disabled trigger must not dispatch a run")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await scheduled_tasks.trigger_scheduled_task(task_id="task-1")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Scheduled tasks are disabled"
