from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_video_productions as router_module
from deerflow.config.paths import Paths


@pytest.mark.asyncio
async def test_video_model_catalog_lists_ark_image_and_video_models(
    monkeypatch,
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "data": [
                    {"id": "doubao-seedream-5-0-pro-260628"},
                    {"id": "doubao-seedream-4-5-251128"},
                    {"id": "doubao-seedance-2-0-260128"},
                    {"id": "doubao-seedance-2-0-fast-260128"},
                    {"id": "doubao-seed-2-0-pro-260215"},
                ]
            }

    class FakeAsyncClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def get(self, url: str, *, headers: dict[str, str]):
            assert url == "https://ark.example.test/api/v3/models"
            assert headers["Authorization"].startswith("Bearer ")
            return FakeResponse()

    monkeypatch.setenv("VOLCENGINE_API_KEY", "test-key")
    monkeypatch.setenv(
        "VOLCENGINE_ARK_BASE_URL",
        "https://ark.example.test/api/v3",
    )
    monkeypatch.setattr(router_module.httpx, "AsyncClient", FakeAsyncClient)

    catalog = await router_module._volcengine_media_model_catalog()

    assert catalog["source"] == "live"
    assert [item["display_name"] for item in catalog["image_models"]] == [
        "Seedream 5.0 Pro",
        "Seedream 5.0",
        "Seedream 4.5",
    ]
    assert [item["display_name"] for item in catalog["video_models"]] == [
        "Seedance 2.0",
        "Seedance 2.0 Fast",
    ]
    assert os.environ["VOLCENGINE_API_KEY"] == "test-key"


@pytest.mark.asyncio
async def test_video_artifact_stream_is_owner_scoped_hash_verified_and_seekable(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    artifact_path = paths.user_dir("user-1") / "video-deliveries" / "delivery.mp4"
    artifact_path.parent.mkdir(parents=True)
    artifact_bytes = b"0123456789-video-payload"
    artifact_path.write_bytes(artifact_bytes)
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "events": [
                    {
                        "status": "succeeded",
                        "payload": {
                            "artifact": {
                                "ref": artifact_path.resolve().as_uri(),
                                "sha256": digest,
                                "size_bytes": len(artifact_bytes),
                                "mime_type": "video/mp4",
                            }
                        },
                    }
                ],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "get_paths", lambda: paths)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get(
            f"/api/personal-ip/video-productions/video-production-1/artifacts/{digest}",
            headers={"Range": "bytes=3-8"},
        )
        missing = await client.get(f"/api/personal-ip/video-productions/video-production-1/artifacts/{'0' * 64}")

    assert response.status_code == 206
    assert response.content == artifact_bytes[3:9]
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.headers["content-range"] == f"bytes 3-8/{len(artifact_bytes)}"
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert missing.status_code == 404
    repository.get.assert_awaited_with("video-production-1", owner_user_id="user-1")


@pytest.mark.asyncio
async def test_legacy_video_artifact_route_rejects_file_uri_outside_owner_root(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    outside = tmp_path / "outside.mp4"
    payload = b"outside-owner-video"
    outside.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "events": [
                    {
                        "status": "succeeded",
                        "payload": {
                            "artifact": {
                                "ref": outside.resolve().as_uri(),
                                "sha256": digest,
                                "size_bytes": len(payload),
                                "mime_type": "video/mp4",
                            }
                        },
                    }
                ],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "get_paths", lambda: paths)
    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        response = await client.get(f"/api/personal-ip/video-productions/video-production-1/artifacts/{digest}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_linked_v2_video_artifact_route_never_falls_back_to_event_refs(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    artifact_path = paths.user_dir("user-1") / "video-deliveries" / "delivery.mp4"
    artifact_path.parent.mkdir(parents=True)
    payload = b"linked-v2-video"
    artifact_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "contract_version": "personal-ip-video-production-v2",
                "events": [
                    {
                        "status": "succeeded",
                        "payload": {
                            "artifact": {
                                "ref": artifact_path.resolve().as_uri(),
                                "sha256": digest,
                                "size_bytes": len(payload),
                                "mime_type": "video/mp4",
                            }
                        },
                    }
                ],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(
        router_module,
        "get_current_user_from_request",
        current_user,
    )
    monkeypatch.setattr(router_module, "get_paths", lambda: paths)
    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        response = await client.get(f"/api/personal-ip/video-productions/video-production-1/artifacts/{digest}")

    assert response.status_code == 404
    assert artifact_path.read_bytes() == payload


@pytest.mark.asyncio
async def test_video_artifact_stream_resolves_owner_scoped_virtual_ref_across_threads(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    artifact_path = paths.sandbox_uploads_dir("thread-1", user_id="user-1") / "candidate.mp4"
    artifact_path.parent.mkdir(parents=True)
    artifact_bytes = b"owner-scoped-virtual-video"
    artifact_path.write_bytes(artifact_bytes)
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    other_owner_path = paths.sandbox_uploads_dir("thread-2", user_id="user-2") / "candidate.mp4"
    other_owner_path.parent.mkdir(parents=True)
    other_owner_path.write_bytes(artifact_bytes)
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "owner_user_id": "user-1",
                "events": [
                    {
                        "status": "succeeded",
                        "payload": {
                            "outputs": [
                                {
                                    "ref": "/mnt/user-data/uploads/candidate.mp4",
                                    "sha256": digest,
                                    "size_bytes": len(artifact_bytes),
                                    "mime_type": "video/mp4",
                                }
                            ]
                        },
                    }
                ],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "get_paths", lambda: paths)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get(
            f"/api/personal-ip/video-productions/video-production-1/artifacts/{digest}",
            headers={"Range": "bytes=6-11"},
        )

    assert response.status_code == 206
    assert response.content == artifact_bytes[6:12]
    assert response.headers["content-type"].startswith("video/mp4")


@pytest.mark.asyncio
async def test_video_artifact_stream_resolves_asset_manifest_image_without_mime_type(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    artifact_path = paths.sandbox_uploads_dir("thread-1", user_id="user-1") / "character-reference.png"
    artifact_path.parent.mkdir(parents=True)
    artifact_bytes = b"\x89PNG\r\n\x1a\nmanifest-image"
    artifact_path.write_bytes(artifact_bytes)
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "owner_user_id": "user-1",
                "events": [
                    {
                        "status": "succeeded",
                        "payload": {
                            "assets": [
                                {
                                    "id": "character-reference",
                                    "type": "image",
                                    "source_ref": "/mnt/user-data/uploads/character-reference.png",
                                    "sha256": digest,
                                }
                            ]
                        },
                    }
                ],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "get_paths", lambda: paths)
    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        response = await client.get(f"/api/personal-ip/video-productions/video-production-1/artifacts/{digest}")

    assert response.status_code == 200
    assert response.content == artifact_bytes
    assert response.headers["content-type"].startswith("image/png")


@pytest.mark.asyncio
async def test_video_production_router_begins_and_appends_stage_receipt(monkeypatch) -> None:
    repository = SimpleNamespace(
        begin=AsyncMock(return_value={"id": "video-production-1", "status": "draft"}),
        append_event=AsyncMock(return_value={"id": "video-production-1", "status": "running"}),
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        created = await client.post(
            "/api/personal-ip/video-productions",
            json={
                "operation_key": "video:1",
                "title": "一句话微电影",
                "subject_id": None,
                "target_account_ids": [],
                "production_mode": "generative_cinematic",
                "source_kind": "idea",
                "source": {"idea": "一个智能体学会理解人"},
                "delivery_spec": {"aspect_ratio": "16:9"},
                "provider_policy": {"video": ["seedance"]},
                "budget": {"currency": "CNY", "hard_limit": 100},
            },
        )
        event = await client.post(
            "/api/personal-ip/video-productions/video-production-1/events",
            json={
                "event_key": "storyboard:v1",
                "event_type": "storyboard_sealed",
                "status": "succeeded",
                "entity_type": "production",
                "entity_id": "video-production-1",
                "payload": {"shots": 12},
                "input_refs": ["artifact://blueprint-v1.json"],
                "output_refs": ["artifact://storyboard-v1.json"],
                "provider": "doubao",
                "model": "doubao-seed-1-8",
                "cost": {"currency": "CNY", "amount": 0.1},
                "occurred_at": "2026-07-22T05:00:00Z",
            },
        )

    assert created.status_code == 201
    assert event.status_code == 200
    assert repository.begin.await_args.kwargs["owner_user_id"] == "user-1"
    assert repository.begin.await_args.kwargs["production_mode"] == "generative_cinematic"
    assert repository.append_event.await_args.kwargs["event_type"] == "storyboard_sealed"


@pytest.mark.asyncio
async def test_video_production_router_rejects_unknown_event_type(monkeypatch) -> None:
    repository = SimpleNamespace(append_event=AsyncMock())
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/video-productions/video-production-1/events",
            json={
                "event_key": "unsafe",
                "event_type": "run_arbitrary_shell",
                "status": "succeeded",
                "entity_type": "production",
                "entity_id": "video-production-1",
                "payload": {},
            },
        )

    assert response.status_code == 422
    repository.append_event.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["delivery_qa_completed", "delivery_completed"])
async def test_public_video_event_endpoint_rejects_server_owned_delivery_events(
    monkeypatch,
    event_type: str,
) -> None:
    repository = SimpleNamespace(append_event=AsyncMock())
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    body = {
        "event_key": f"{event_type}:1",
        "event_type": event_type,
        "status": "succeeded",
        "entity_type": "artifact" if event_type == "delivery_completed" else "delivery",
        "entity_id": "artifact-1" if event_type == "delivery_completed" else "delivery-1",
        "payload": {},
        "input_refs": [],
        "output_refs": ["artifact://artifact-1"],
        "provider": "caller",
        "cost": {},
    }
    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        response = await client.post(
            "/api/personal-ip/video-productions/video-production-1/events",
            json=body,
        )

    assert response.status_code == 422
    repository.append_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_video_production_router_returns_ledger_derived_workbench(monkeypatch) -> None:
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "title": "本地回执验收",
                "status": "running",
                "current_stage": "blueprint",
                "source_kind": "script",
                "source": {"script": "test"},
                "delivery_spec": {},
                "provider_policy": {},
                "budget": {},
                "events": [],
            }
        )
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get("/api/personal-ip/video-productions/video-production-1/workbench")

    assert response.status_code == 200
    assert response.json()["contract_version"] == "personal-ip-video-workbench-v1"
    repository.get.assert_awaited_once_with("video-production-1", owner_user_id="user-1")


@pytest.mark.asyncio
async def test_video_production_router_compiles_manual_timeline_revision(monkeypatch) -> None:
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "production_mode": "generative_cinematic",
                "source": {"production_mode": "generative_cinematic"},
            }
        ),
        append_event=AsyncMock(return_value={"id": "video-production-1", "status": "running"}),
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/video-productions/video-production-1/timeline-revisions",
            json={
                "event_key": "timeline-revision:r2",
                "revision_id": "r2",
                "base_revision_id": "r1",
                "author_kind": "human",
                "intent": "把镜头一缩短半秒",
                "fps": 24,
                "tracks": [
                    {
                        "id": "video",
                        "type": "video",
                        "clips": [
                            {
                                "id": "clip-1",
                                "shot_id": "shot-1",
                                "start_sec": 0,
                                "duration_sec": 3.5,
                                "source_in_sec": 0.5,
                            }
                        ],
                    }
                ],
                "operations": [
                    {
                        "id": "edit-1",
                        "type": "trim",
                        "clip_id": "clip-1",
                        "source_in_sec": 0.5,
                        "duration_sec": 3.5,
                    }
                ],
                "strategy_confirmed": True,
            },
        )

    assert response.status_code == 200
    kwargs = repository.append_event.await_args.kwargs
    assert kwargs["event_type"] == "timeline_revision_compiled"
    assert kwargs["entity_type"] == "timeline"
    assert kwargs["payload"]["author_kind"] == "human"
    assert kwargs["payload"]["editing_policy"]["subtitles_applied_last"] is True


@pytest.mark.asyncio
async def test_video_production_router_keeps_legacy_mode_less_production_editable(
    monkeypatch,
) -> None:
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-legacy",
                "source": {"script": "旧制作仍然可以继续剪辑"},
            }
        ),
        append_event=AsyncMock(return_value={"id": "video-production-legacy", "status": "running"}),
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/video-productions/video-production-legacy/timeline-revisions",
            json={
                "event_key": "timeline-revision:legacy-r1",
                "revision_id": "legacy-r1",
                "base_revision_id": None,
                "author_kind": "human",
                "intent": "把旧制作的镜头缩短半秒",
                "fps": 24,
                "tracks": [
                    {
                        "id": "video",
                        "type": "video",
                        "clips": [
                            {
                                "id": "clip-1",
                                "start_sec": 0,
                                "duration_sec": 1.5,
                                "source_in_sec": 0,
                            }
                        ],
                    }
                ],
                "operations": [
                    {
                        "id": "edit-1",
                        "type": "trim",
                        "clip_id": "clip-1",
                        "source_in_sec": 0,
                        "duration_sec": 1.5,
                    }
                ],
                "strategy_confirmed": True,
            },
        )

    assert response.status_code == 200
    assert repository.append_event.await_args.kwargs["payload"]["production_mode"] == "faceless_material"


@pytest.mark.asyncio
async def test_video_production_router_locks_latest_timeline_revision(monkeypatch) -> None:
    from deerflow.personal_ip.video_contracts import compile_timeline_revision

    timeline_revision = compile_timeline_revision(
        production_id="video-production-1",
        production_mode="generative_cinematic",
        revision_id="r2",
        base_revision_id="r1",
        author_kind="human",
        intent="锁定前的最后一次裁切",
        fps=24,
        tracks=[
            {
                "id": "video",
                "type": "video",
                "clips": [
                    {
                        "id": "clip-1",
                        "start_sec": 0,
                        "duration_sec": 3.5,
                        "source_in_sec": 0.5,
                    }
                ],
            }
        ],
        operations=[
            {
                "id": "edit-1",
                "type": "trim",
                "clip_id": "clip-1",
                "source_in_sec": 0.5,
                "duration_sec": 3.5,
            }
        ],
        strategy_confirmed=True,
    )
    repository = SimpleNamespace(
        get=AsyncMock(
            return_value={
                "id": "video-production-1",
                "production_mode": "generative_cinematic",
                "source": {"production_mode": "generative_cinematic"},
                "events": [
                    {
                        "event_type": "timeline_revision_compiled",
                        "payload": timeline_revision,
                    }
                ],
            }
        ),
        append_event=AsyncMock(return_value={"id": "video-production-1", "status": "running"}),
    )
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id="user-1")

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.post(
            "/api/personal-ip/video-productions/video-production-1/final-edit-lock",
            json={
                "event_key": "final-lock:1",
                "lock_id": "final-lock-1",
                "locked_by": "human",
                "note": "用户确认进入最终渲染和交付 QA",
            },
        )

    assert response.status_code == 200
    kwargs = repository.append_event.await_args.kwargs
    assert kwargs["event_type"] == "final_edit_locked"
    assert kwargs["payload"]["source_timeline_sha256"] == timeline_revision["sha256"]
