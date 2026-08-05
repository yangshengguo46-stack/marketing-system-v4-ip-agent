from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.gateway.routers import personal_ip_artifacts as router_module
from deerflow.config.paths import Paths


def _artifact_record(
    payload: bytes,
    *,
    storage_key: str,
    content_available: bool = True,
) -> dict:
    return {
        "id": "artifact-1",
        "contract_version": "personal-ip-final-artifact-v1",
        "role": "final_video",
        "production_id": "video-production-1",
        "content_sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "mime_type": "video/mp4",
        "content_available": content_available,
        "metadata": {"lock_id": "lock-1"},
        "storage_key": storage_key,
    }


def _app(repository, monkeypatch, paths: Paths, *, owner_user_id: str = "owner-1") -> FastAPI:
    app = FastAPI()
    app.state.personal_ip_video_production_repo = repository
    app.include_router(router_module.router)

    async def current_user(_request):
        return SimpleNamespace(id=owner_user_id)

    monkeypatch.setattr(router_module, "get_current_user_from_request", current_user)
    monkeypatch.setattr(router_module, "get_paths", lambda: paths)
    return app


@pytest.mark.asyncio
async def test_final_artifact_metadata_is_owner_scoped_and_hides_storage(monkeypatch, tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    record = {
        **_artifact_record(b"video", storage_key="video-deliveries/job/final.mp4"),
        "source_ref": "file:///private/final.mp4",
    }
    repository = SimpleNamespace(get_artifact=AsyncMock(return_value=record))
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get("/api/personal-ip/artifacts/artifact-1")

    assert response.status_code == 200
    assert response.json()["content_sha256"] == record["content_sha256"]
    assert "storage_key" not in response.json()
    assert "source_ref" not in response.json()
    assert "ref" not in response.json()
    repository.get_artifact.assert_awaited_once_with(
        "artifact-1",
        owner_user_id="owner-1",
    )


@pytest.mark.asyncio
async def test_final_artifact_content_rehashes_and_supports_ranges(monkeypatch, tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    payload = b"0123456789-video-payload"
    storage_key = "video-deliveries/job/final.mp4"
    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    record = _artifact_record(payload, storage_key=storage_key)
    repository = SimpleNamespace(get_artifact=AsyncMock(return_value=record))
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get(
            "/api/personal-ip/artifacts/artifact-1/content",
            headers={"Range": "bytes=3-8"},
        )
        suffix = await client.get(
            "/api/personal-ip/artifacts/artifact-1/content",
            headers={"Range": "bytes=-5"},
        )

    assert response.status_code == 206
    assert response.content == payload[3:9]
    assert response.headers["content-range"] == f"bytes 3-8/{len(payload)}"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["etag"] == f'"{record["content_sha256"]}"'
    assert response.headers["content-type"].startswith("video/mp4")
    assert suffix.status_code == 206
    assert suffix.content == payload[-5:]


@pytest.mark.asyncio
async def test_final_artifact_content_fails_closed_on_owner_hash_and_symlink(monkeypatch, tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    payload = b"video-payload"
    storage_key = "video-deliveries/job/final.mp4"
    owner_two_target = paths.user_dir("owner-2").joinpath(*storage_key.split("/"))
    owner_two_target.parent.mkdir(parents=True)
    owner_two_target.write_bytes(payload)
    record = _artifact_record(payload, storage_key=storage_key)
    repository = SimpleNamespace(get_artifact=AsyncMock(return_value=record))
    app = _app(repository, monkeypatch, paths, owner_user_id="owner-1")

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        wrong_owner = await client.get("/api/personal-ip/artifacts/artifact-1/content")
    assert wrong_owner.status_code == 404

    owner_one_target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    owner_one_target.parent.mkdir(parents=True)
    owner_one_target.write_bytes(b"tampered")
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        hash_drift = await client.get("/api/personal-ip/artifacts/artifact-1/content")
    assert hash_drift.status_code == 404

    owner_one_target.unlink()
    try:
        owner_one_target.symlink_to(owner_two_target)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        linked = await client.get("/api/personal-ip/artifacts/artifact-1/content")
    assert linked.status_code == 404


@pytest.mark.asyncio
async def test_final_artifact_content_rejects_unsatisfiable_range(monkeypatch, tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    payload = b"video-payload"
    storage_key = "video-deliveries/job/final.mp4"
    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    repository = SimpleNamespace(get_artifact=AsyncMock(return_value=_artifact_record(payload, storage_key=storage_key)))
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.ASGITransport(app=app)) as client:
        response = await client.get(
            "/api/personal-ip/artifacts/artifact-1/content",
            headers={"Range": "bytes=999-1000"},
        )

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(payload)}"


@pytest.mark.asyncio
async def test_unavailable_artifact_metadata_remains_visible_but_content_fails_closed(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    payload = b"restored-video"
    storage_key = "video-deliveries/job/final.mp4"
    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    record = _artifact_record(
        payload,
        storage_key=storage_key,
        content_available=False,
    )
    repository = SimpleNamespace(get_artifact=AsyncMock(return_value=record))
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        metadata = await client.get("/api/personal-ip/artifacts/artifact-1")
        content = await client.get("/api/personal-ip/artifacts/artifact-1/content")

    assert metadata.status_code == 200
    assert metadata.json()["content_available"] is False
    assert content.status_code == 404


@pytest.mark.asyncio
async def test_final_artifact_put_streams_exact_content_and_marks_available(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.user_dir("owner-1").mkdir(parents=True)
    payload = b"restored-video"
    storage_key = "video-deliveries/job/final.mp4"
    record = _artifact_record(
        payload,
        storage_key=storage_key,
        content_available=False,
    )
    available = {**record, "content_available": True}
    repository = SimpleNamespace(
        get_artifact=AsyncMock(return_value=record),
        mark_artifact_content_available=AsyncMock(return_value=available),
    )
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        response = await client.put(
            "/api/personal-ip/artifacts/artifact-1/content",
            content=payload,
            headers={"Content-Type": "video/mp4"},
        )

    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    assert response.status_code == 200
    assert response.json()["content_available"] is True
    assert "storage_key" not in response.json()
    assert target.read_bytes() == payload
    assert not list(target.parent.glob(".artifact-upload-*.tmp"))
    repository.get_artifact.assert_awaited_once_with(
        "artifact-1",
        owner_user_id="owner-1",
        include_storage_key=True,
    )
    repository.mark_artifact_content_available.assert_awaited_once_with(
        "artifact-1",
        owner_user_id="owner-1",
        expected_sha256=record["content_sha256"],
        expected_size_bytes=len(payload),
        expected_mime_type="video/mp4",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("uploaded", "expected_status"),
    [
        (b"wrong---video-", 422),
        (b"restored-video-too-large", 413),
    ],
)
async def test_final_artifact_put_rejects_wrong_or_oversized_bytes_without_files(
    monkeypatch,
    tmp_path,
    uploaded: bytes,
    expected_status: int,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.user_dir("owner-1").mkdir(parents=True)
    payload = b"restored-video"
    storage_key = "video-deliveries/job/final.mp4"
    record = _artifact_record(
        payload,
        storage_key=storage_key,
        content_available=False,
    )
    repository = SimpleNamespace(
        get_artifact=AsyncMock(return_value=record),
        mark_artifact_content_available=AsyncMock(),
    )
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        response = await client.put(
            "/api/personal-ip/artifacts/artifact-1/content",
            content=uploaded,
            headers={"Content-Type": "video/mp4"},
        )

    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    assert response.status_code == expected_status
    assert not target.exists()
    assert not list(target.parent.glob(".artifact-upload-*.tmp"))
    repository.mark_artifact_content_available.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_artifact_put_never_overwrites_mismatched_destination(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    expected = b"expected-video"
    existing = b"existing-video"
    storage_key = "video-deliveries/job/final.mp4"
    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    target.parent.mkdir(parents=True)
    target.write_bytes(existing)
    record = _artifact_record(
        expected,
        storage_key=storage_key,
        content_available=False,
    )
    repository = SimpleNamespace(
        get_artifact=AsyncMock(return_value=record),
        mark_artifact_content_available=AsyncMock(),
    )
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app),
    ) as client:
        response = await client.put(
            "/api/personal-ip/artifacts/artifact-1/content",
            content=expected,
            headers={"Content-Type": "video/mp4"},
        )

    assert response.status_code == 409
    assert target.read_bytes() == existing
    repository.mark_artifact_content_available.assert_not_awaited()


@pytest.mark.asyncio
async def test_final_artifact_put_cleans_new_content_when_repository_returns_none(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.user_dir("owner-1").mkdir(parents=True)
    payload = b"restored-video"
    storage_key = "video-deliveries/job/final.mp4"
    record = _artifact_record(
        payload,
        storage_key=storage_key,
        content_available=False,
    )
    repository = SimpleNamespace(
        get_artifact=AsyncMock(return_value=record),
        mark_artifact_content_available=AsyncMock(return_value=None),
    )
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
    ) as client:
        response = await client.put(
            "/api/personal-ip/artifacts/artifact-1/content",
            content=payload,
            headers={"Content-Type": "video/mp4"},
        )

    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    assert response.status_code == 404
    assert not target.exists()
    assert not list(target.parent.glob(".artifact-upload-*.tmp"))


@pytest.mark.asyncio
async def test_final_artifact_put_keeps_exact_content_for_retry_after_repo_error(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.user_dir("owner-1").mkdir(parents=True)
    payload = b"restored-video"
    storage_key = "video-deliveries/job/final.mp4"
    record = _artifact_record(
        payload,
        storage_key=storage_key,
        content_available=False,
    )
    available = {**record, "content_available": True}
    repository = SimpleNamespace(
        get_artifact=AsyncMock(return_value=record),
        mark_artifact_content_available=AsyncMock(side_effect=[RuntimeError("db failed"), available]),
    )
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
    ) as client:
        failed = await client.put(
            "/api/personal-ip/artifacts/artifact-1/content",
            content=payload,
            headers={"Content-Type": "video/mp4"},
        )
        retried = await client.put(
            "/api/personal-ip/artifacts/artifact-1/content",
            content=payload,
            headers={"Content-Type": "video/mp4"},
        )

    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    assert failed.status_code == 500
    assert retried.status_code == 200
    assert target.read_bytes() == payload
    assert not list(target.parent.glob(".artifact-upload-*.tmp"))


@pytest.mark.asyncio
async def test_concurrent_repo_error_cannot_unlink_another_successful_reattach(
    monkeypatch,
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    paths.user_dir("owner-1").mkdir(parents=True)
    payload = b"restored-video"
    storage_key = "video-deliveries/job/final.mp4"
    record = _artifact_record(
        payload,
        storage_key=storage_key,
        content_available=False,
    )
    available = {**record, "content_available": True}
    first_mark_started = asyncio.Event()
    second_mark_finished = asyncio.Event()
    mark_calls = 0

    async def get_artifact(*_args, **_kwargs):
        return record

    async def mark_artifact_content_available(*_args, **_kwargs):
        nonlocal mark_calls
        mark_calls += 1
        if mark_calls == 1:
            first_mark_started.set()
            await second_mark_finished.wait()
            raise RuntimeError("first transaction failed")
        second_mark_finished.set()
        return available

    repository = SimpleNamespace(
        get_artifact=get_artifact,
        mark_artifact_content_available=mark_artifact_content_available,
    )
    app = _app(repository, monkeypatch, paths)

    async with httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
    ) as client:
        first = asyncio.create_task(
            client.put(
                "/api/personal-ip/artifacts/artifact-1/content",
                content=payload,
                headers={"Content-Type": "video/mp4"},
            )
        )
        await first_mark_started.wait()
        second = await client.put(
            "/api/personal-ip/artifacts/artifact-1/content",
            content=payload,
            headers={"Content-Type": "video/mp4"},
        )
        first_response = await first

    target = paths.user_dir("owner-1").joinpath(*storage_key.split("/"))
    assert first_response.status_code == 500
    assert second.status_code == 200
    assert target.read_bytes() == payload
