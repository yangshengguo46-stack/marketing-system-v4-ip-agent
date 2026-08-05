from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.config.paths import Paths
from deerflow.personal_ip.final_artifacts import (
    commit_owner_final_artifact_deletion,
    delete_owner_final_artifacts,
    normalize_storage_key,
    prepare_owner_final_artifact_deletion,
    public_artifact_metadata,
    remove_unsealed_final_artifact,
    rollback_owner_final_artifact_deletion,
    seal_final_artifact,
    storage_key_for_owner_file,
    verify_final_artifact,
    verify_final_artifact_record,
)


def _write_owner_file(paths: Paths, key: str, payload: bytes = b"verified-video"):
    target = paths.user_dir("owner-1").joinpath(*key.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target, hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    "storage_key",
    [
        "file:///tmp/final.mp4",
        "https://example.test/final.mp4",
        "/tmp/final.mp4",
        "../final.mp4",
        "deliveries/../../final.mp4",
        "deliveries//final.mp4",
        "deliveries/./final.mp4",
        r"C:\\tmp\\final.mp4",
        r"deliveries\\final.mp4",
        "threads/thread-1/final.mp4",
    ],
)
def test_storage_key_rejects_url_absolute_and_traversal(storage_key: str) -> None:
    with pytest.raises(ValueError):
        normalize_storage_key(storage_key)


def test_owner_file_is_rehashed_and_uses_only_relative_storage_key(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(paths, "video-deliveries/job/final.mp4")

    storage_key = storage_key_for_owner_file("owner-1", target, paths=paths)
    verified = verify_final_artifact(
        "owner-1",
        storage_key,
        expected_sha256=digest,
        expected_size_bytes=target.stat().st_size,
        expected_mime_type="video/mp4",
        paths=paths,
    )

    assert storage_key == "video-deliveries/job/final.mp4"
    assert verified.storage_key == storage_key
    assert verified.path == target
    assert verified.sha256 == digest
    assert verified.mime_type == "video/mp4"


def test_owner_file_rejects_outside_hash_drift_and_non_video(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(paths, "video-deliveries/job/final.mp4")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")

    with pytest.raises(ValueError, match="Owner user root"):
        storage_key_for_owner_file("owner-1", outside, paths=paths)
    with pytest.raises(ValueError, match="SHA-256"):
        verify_final_artifact(
            "owner-1",
            "video-deliveries/job/final.mp4",
            expected_sha256="0" * 64,
            expected_size_bytes=target.stat().st_size,
            expected_mime_type="video/mp4",
            paths=paths,
        )

    image, image_digest = _write_owner_file(paths, "video-deliveries/job/frame.png")
    with pytest.raises(ValueError, match=r"video/\*"):
        verify_final_artifact(
            "owner-1",
            "video-deliveries/job/frame.png",
            expected_sha256=image_digest,
            expected_size_bytes=image.stat().st_size,
            expected_mime_type="image/png",
            paths=paths,
        )
    assert digest != image_digest or target != image


def test_owner_file_rejects_symlink_and_non_regular_target(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    root = paths.user_dir("owner-1")
    root.mkdir(parents=True)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside-video")
    delivery_root = root / "video-deliveries"
    delivery_root.mkdir()
    link = delivery_root / "linked.mp4"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    with pytest.raises(ValueError, match="linked"):
        verify_final_artifact("owner-1", "video-deliveries/linked.mp4", paths=paths)
    outside_directory = tmp_path / "outside-directory"
    outside_directory.mkdir()
    (outside_directory / "nested.mp4").write_bytes(b"outside-video")
    linked_directory = delivery_root / "linked-directory"
    linked_directory.symlink_to(outside_directory, target_is_directory=True)
    with pytest.raises(ValueError, match="linked"):
        verify_final_artifact(
            "owner-1",
            "video-deliveries/linked-directory/nested.mp4",
            paths=paths,
        )
    directory = delivery_root / "directory.mp4"
    directory.mkdir()
    with pytest.raises(ValueError, match="ordinary file"):
        verify_final_artifact("owner-1", "video-deliveries/directory.mp4", paths=paths)


@pytest.mark.asyncio
async def test_seal_final_artifact_recomputes_identity_before_repository_call(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(paths, "video-deliveries/job/final.mp4")
    repository = SimpleNamespace(complete_delivery_and_seal_artifact=AsyncMock(return_value={"id": "video-production-1", "status": "completed"}))

    result = await seal_final_artifact(
        repository,
        "video-production-1",
        owner_user_id="owner-1",
        event_key="delivery:1",
        qa_event_key="qa:1",
        source_execution_event_keys=["render:1"],
        source_ref=target.as_uri(),
        local_path=target,
        expected_sha256=digest,
        expected_size_bytes=target.stat().st_size,
        expected_mime_type="video/mp4",
        metadata={"lock_id": "lock-1"},
        provider="project-ffmpeg",
        cost={"status": "known", "amount": 0, "currency": "CNY"},
        paths=paths,
    )

    assert result == {"id": "video-production-1", "status": "completed"}
    kwargs = repository.complete_delivery_and_seal_artifact.await_args.kwargs
    assert kwargs["storage_key"] == "video-deliveries/job/final.mp4"
    assert kwargs["sha256"] == digest
    assert kwargs["size_bytes"] == target.stat().st_size
    assert kwargs["mime_type"] == "video/mp4"
    assert kwargs["source_ref"] == target.as_uri()


@pytest.mark.asyncio
async def test_seal_final_artifact_removes_exact_file_only_when_repo_returns_none(
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(
        paths,
        "video-deliveries/job/final.mp4",
    )
    repository = SimpleNamespace(complete_delivery_and_seal_artifact=AsyncMock(return_value=None))

    result = await seal_final_artifact(
        repository,
        "video-production-1",
        owner_user_id="owner-1",
        event_key="delivery:1",
        qa_event_key="qa:1",
        source_execution_event_keys=["render:1"],
        source_ref=target.as_uri(),
        local_path=target,
        expected_sha256=digest,
        expected_size_bytes=target.stat().st_size,
        expected_mime_type="video/mp4",
        metadata={"lock_id": "lock-1"},
        provider="project-ffmpeg",
        cost={"status": "known", "amount": 0, "currency": "CNY"},
        paths=paths,
    )

    assert result is None
    assert not target.exists()


@pytest.mark.asyncio
async def test_seal_final_artifact_preserves_exact_file_on_ambiguous_repo_error(
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(
        paths,
        "video-deliveries/job/final.mp4",
    )
    repository = SimpleNamespace(complete_delivery_and_seal_artifact=AsyncMock(side_effect=RuntimeError("commit result unknown")))

    with pytest.raises(RuntimeError, match="commit result unknown"):
        await seal_final_artifact(
            repository,
            "video-production-1",
            owner_user_id="owner-1",
            event_key="delivery:1",
            qa_event_key="qa:1",
            source_execution_event_keys=["render:1"],
            source_ref=target.as_uri(),
            local_path=target,
            expected_sha256=digest,
            expected_size_bytes=target.stat().st_size,
            expected_mime_type="video/mp4",
            metadata={"lock_id": "lock-1"},
            provider="project-ffmpeg",
            cost={"status": "known", "amount": 0, "currency": "CNY"},
            paths=paths,
        )

    assert target.read_bytes() == b"verified-video"


def test_remove_unsealed_final_artifact_requires_exact_immutable_identity(
    tmp_path,
) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(
        paths,
        "video-deliveries/job/final.mp4",
    )

    with pytest.raises(ValueError, match="SHA-256"):
        remove_unsealed_final_artifact(
            "owner-1",
            target,
            expected_sha256="0" * 64,
            expected_size_bytes=target.stat().st_size,
            expected_mime_type="video/mp4",
            paths=paths,
        )
    assert target.is_file()
    assert remove_unsealed_final_artifact(
        "owner-1",
        target,
        expected_sha256=digest,
        expected_size_bytes=target.stat().st_size,
        expected_mime_type="video/mp4",
        paths=paths,
    )
    assert not target.exists()


def test_artifact_record_verification_accepts_public_hash_name_and_projection_hides_storage(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(paths, "video-deliveries/job/final.mp4")
    record = {
        "id": "artifact-1",
        "content_sha256": digest,
        "size_bytes": target.stat().st_size,
        "mime_type": "video/mp4",
        "storage_key": "video-deliveries/job/final.mp4",
        "source_ref": target.as_uri(),
    }

    verified = verify_final_artifact_record("owner-1", record, paths=paths)
    assert verified.sha256 == digest
    assert public_artifact_metadata(record) == {
        "id": "artifact-1",
        "content_sha256": digest,
        "size_bytes": target.stat().st_size,
        "mime_type": "video/mp4",
    }


def test_batch_delete_is_owner_scoped_idempotent_and_rejects_symlink(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    first, _ = _write_owner_file(paths, "video-deliveries/job/first.mp4")
    second, _ = _write_owner_file(paths, "video-deliveries/job/second.mp4")

    records = [
        {
            "id": "artifact-1",
            "storage_key": "video-deliveries/job/first.mp4",
            "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
            "size_bytes": first.stat().st_size,
            "mime_type": "video/mp4",
        },
        {
            "id": "artifact-2",
            "storage_key": "video-deliveries/job/second.mp4",
            "sha256": hashlib.sha256(second.read_bytes()).hexdigest(),
            "size_bytes": second.stat().st_size,
            "mime_type": "video/mp4",
        },
    ]
    assert delete_owner_final_artifacts("owner-1", records, paths=paths) == 2
    assert not first.exists() and not second.exists()
    assert delete_owner_final_artifacts("owner-1", records, paths=paths) == 0

    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    link = paths.user_dir("owner-1") / "video-deliveries" / "linked.mp4"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    with pytest.raises(ValueError, match="linked"):
        delete_owner_final_artifacts(
            "owner-1",
            [
                {
                    "id": "artifact-linked",
                    "storage_key": "video-deliveries/linked.mp4",
                    "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                    "size_bytes": outside.stat().st_size,
                    "mime_type": "video/mp4",
                }
            ],
            paths=paths,
        )
    assert outside.read_bytes() == b"outside"


def test_two_phase_artifact_deletion_rolls_back_or_commits_exact_files(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(
        paths,
        "video-deliveries/job/final.mp4",
        b"two-phase-video",
    )
    record = {
        "id": "artifact-1",
        "storage_key": "video-deliveries/job/final.mp4",
        "content_sha256": digest,
        "size_bytes": target.stat().st_size,
        "mime_type": "video/mp4",
    }

    prepared = prepare_owner_final_artifact_deletion(
        "owner-1",
        [record],
        paths=paths,
    )
    quarantine = paths.user_dir("owner-1").joinpath(*prepared.entries[0].quarantine_key.split("/"))
    assert not target.exists()
    assert quarantine.is_file()
    assert rollback_owner_final_artifact_deletion(prepared) == 1
    assert target.read_bytes() == b"two-phase-video"
    assert not quarantine.exists()
    assert rollback_owner_final_artifact_deletion(prepared) == 1

    prepared = prepare_owner_final_artifact_deletion(
        "owner-1",
        [record],
        paths=paths,
    )
    quarantine = paths.user_dir("owner-1").joinpath(*prepared.entries[0].quarantine_key.split("/"))
    assert commit_owner_final_artifact_deletion(prepared) == 1
    assert not target.exists()
    assert not quarantine.exists()
    assert commit_owner_final_artifact_deletion(prepared) == 1


def test_artifact_deletion_preflights_all_records_before_quarantine(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    first, first_digest = _write_owner_file(
        paths,
        "video-deliveries/job/first.mp4",
        b"first-video",
    )
    second, _ = _write_owner_file(
        paths,
        "video-deliveries/job/second.mp4",
        b"second-video",
    )
    records = [
        {
            "id": "artifact-1",
            "storage_key": "video-deliveries/job/first.mp4",
            "content_sha256": first_digest,
            "size_bytes": first.stat().st_size,
            "mime_type": "video/mp4",
        },
        {
            "id": "artifact-2",
            "storage_key": "video-deliveries/job/second.mp4",
            "content_sha256": "0" * 64,
            "size_bytes": second.stat().st_size,
            "mime_type": "video/mp4",
        },
    ]

    with pytest.raises(ValueError, match="SHA-256"):
        prepare_owner_final_artifact_deletion(
            "owner-1",
            records,
            paths=paths,
        )

    assert first.read_bytes() == b"first-video"
    assert second.read_bytes() == b"second-video"
    assert not (paths.user_dir("owner-1") / ".artifact-quarantine").exists()


def test_artifact_deletion_rejects_arbitrary_owner_file_record(tmp_path) -> None:
    paths = Paths(tmp_path / ".deer-flow")
    target, digest = _write_owner_file(paths, "threads/thread-1/private.mp4")
    record = {
        "id": "artifact-unsafe",
        "storage_key": "threads/thread-1/private.mp4",
        "content_sha256": digest,
        "size_bytes": target.stat().st_size,
        "mime_type": "video/mp4",
    }

    with pytest.raises(ValueError, match="video-deliveries"):
        prepare_owner_final_artifact_deletion(
            "owner-1",
            [record],
            paths=paths,
        )
    assert target.is_file()
