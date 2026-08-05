from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from mcp.types import ResourceLink, TextContent

from deerflow.ip_agent import evidence_mcp, reference_evidence
from deerflow.mcp.tools import _convert_call_tool_result


def _media_metadata(size_bytes: int) -> dict[str, Any]:
    return {
        "duration_seconds": 12.0,
        "width": 720,
        "height": 1280,
        "frame_rate": 25.0,
        "video_codec": "h264",
        "has_audio": True,
        "container": "mp4",
        "size_bytes": size_bytes,
    }


def _install_inspection_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    source_bytes: bytes,
    work_id: str,
) -> Path:
    root = tmp_path / "user-data"
    root.mkdir()
    ffmpeg = tmp_path / "tools" / "ffmpeg"
    ffprobe = tmp_path / "tools" / "ffprobe"
    ffmpeg.parent.mkdir()
    ffmpeg.write_bytes(b"ffmpeg-build")
    ffprobe.write_bytes(b"ffprobe-build")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    monkeypatch.setenv("IP_AGENT_EVIDENCE_USER_DATA_ROOT", str(root))
    monkeypatch.setattr(
        reference_evidence,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, None),
    )
    monkeypatch.setattr(reference_evidence, "_validate_public_url", lambda *_args, **_kwargs: None)

    async def resolve(
        _reference: str,
        *,
        expected_account_sec_uid: str | None = None,
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        del expected_account_sec_uid
        return (
            "https://media.example.test/exact.mp4",
            {
                "requested_work_id": work_id,
                "resolved_work_id": work_id,
                "observed_work_id": work_id,
                "author_sec_uid": "author-sec-uid-exact-work",
                "canonical_work_ref": f"https://www.douyin.com/video/{work_id}",
                "identity_verification": "api_work_id_match",
            },
            [],
        )

    def download(
        _url: str,
        destination: Path,
        **_kwargs: Any,
    ) -> None:
        destination.write_bytes(source_bytes)

    def probe(
        source: Path,
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        return (
            _media_metadata(source.stat().st_size),
            {
                "adapter_version": "test-probe-v1",
                "executor": "test-ffprobe",
                "execution_mode": "local",
                "source_sha256": source_sha256,
                "result_sha256": "1" * 64,
            },
        )

    def extract(**kwargs: Any):
        output_dir: Path = kwargs["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)
        frames: list[dict[str, Any]] = []
        for index in range(1, 5):
            frame = output_dir / f"frame-{index:02d}.jpg"
            frame.write_bytes(f"frame-{index}".encode())
            frames.append(
                {
                    "at_seconds": float(index),
                    "artifact_ref": f"{kwargs['artifact_ref_prefix']}/{frame.name}",
                    "artifact_sha256": hashlib.sha256(frame.read_bytes()).hexdigest(),
                }
            )
        contact = output_dir / "contact-sheet.jpg"
        contact.write_bytes(b"contact-sheet")
        return (
            frames,
            [],
            contact,
            f"{kwargs['artifact_ref_prefix']}/{contact.name}",
            {
                "cache_hit": False,
                "requested_frames": 4,
                "observed_frames": 4,
                "sampling_truncated": False,
                "contact_sheet_completed": True,
                "contact_sheet_sha256": hashlib.sha256(contact.read_bytes()).hexdigest(),
                "scene_detection_completed": True,
                "scene_boundaries_truncated": False,
                "analysis_spec_sha256": kwargs["analysis_spec"]["spec_sha256"],
                "artifact_manifest_sha256": "2" * 64,
            },
        )

    async def provider(**_kwargs: Any):
        return (
            {},
            {
                "asr": "not_requested",
                "ocr": "not_requested",
                "provider_scene_segmentation": "not_requested",
                "storyline": "not_requested",
            },
            {},
        )

    monkeypatch.setattr(reference_evidence, "_resolve_douyin_video_with_retry", resolve)
    monkeypatch.setattr(reference_evidence, "_download_public_media", download)
    monkeypatch.setattr(reference_evidence, "_probe_video_with_fallback", probe)
    monkeypatch.setattr(reference_evidence, "_extract_visual_evidence", extract)
    monkeypatch.setattr(reference_evidence, "_provider_evidence", provider)
    return root


@pytest.mark.asyncio
async def test_exact_public_work_creates_private_0600_hash_bound_handoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_bytes = b"exact-public-douyin-work"
    work_id = "7658501922794432731"
    root = _install_inspection_fakes(
        monkeypatch,
        tmp_path,
        source_bytes=source_bytes,
        work_id=work_id,
    )

    with reference_evidence.capture_sealed_source_handoffs() as collector:
        payload = await reference_evidence.inspect_reference_videos(
            [f"https://www.douyin.com/video/{work_id}"],
            analysis_depth="mechanical",
            max_frames=4,
        )

    assert payload["operation_status"] == "ok"
    assert "sealed" not in json.dumps(payload, ensure_ascii=False).lower()
    handoffs = collector.snapshot()
    assert len(handoffs) == 1
    handoff = handoffs[0]
    expected_sha256 = hashlib.sha256(source_bytes).hexdigest()
    assert handoff.source_sha256 == expected_sha256
    assert handoff.size_bytes == len(source_bytes)
    assert handoff.work_id == work_id
    assert handoff.relative_ref.startswith(f"outputs/reference-video-sealed-sources/{expected_sha256}/")
    sealed = root / handoff.relative_ref
    assert sealed.read_bytes() == source_bytes
    assert stat.S_IMODE(sealed.lstat().st_mode) == 0o600
    assert sealed.lstat().st_uid == root.lstat().st_uid
    assert sealed.lstat().st_nlink == 1
    private_directories = [root]
    current = root
    for part in Path(handoff.relative_ref).parts[:-1]:
        current /= part
        private_directories.append(current)
    for directory in private_directories:
        assert stat.S_IMODE(directory.lstat().st_mode) == 0o700
        assert directory.lstat().st_uid == root.lstat().st_uid
    assert hashlib.sha256(sealed.read_bytes()).hexdigest() == expected_sha256
    first_stat = sealed.lstat()

    with reference_evidence.capture_sealed_source_handoffs() as reused_collector:
        reused_payload = await reference_evidence.inspect_reference_videos(
            [f"https://www.douyin.com/video/{work_id}"],
            analysis_depth="mechanical",
            max_frames=4,
        )

    assert reused_payload["operation_status"] == "ok"
    assert reused_collector.snapshot() == (handoff,)
    assert sealed.lstat().st_ino == first_stat.st_ino
    assert sealed.read_bytes() == source_bytes


@pytest.mark.asyncio
async def test_private_upload_never_creates_operator_handoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_bytes = b"owner-private-upload"
    root = _install_inspection_fakes(
        monkeypatch,
        tmp_path,
        source_bytes=source_bytes,
        work_id="7658501922794432731",
    )
    upload = root / "uploads" / "private.mp4"
    upload.parent.mkdir()
    upload.write_bytes(source_bytes)

    with reference_evidence.capture_sealed_source_handoffs() as collector:
        payload = await reference_evidence.inspect_reference_videos(
            ["/mnt/user-data/uploads/private.mp4"],
            analysis_depth="mechanical",
            max_frames=4,
        )

    assert payload["operation_status"] == "ok"
    assert collector.snapshot() == ()
    assert not (root / "outputs" / "reference-video-sealed-sources").exists()


@pytest.mark.parametrize(
    "existing_kind",
    ["symlink", "wrong_regular_file", "hardlink", "wrong_permissions"],
)
def test_existing_unsafe_or_mismatched_snapshot_fails_closed_without_overwrite(
    existing_kind: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir()
    source = tmp_path / "download.mp4"
    source_bytes = b"verified-source"
    source.write_bytes(source_bytes)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    analysis_sha256 = "a" * 64
    target = root / "outputs" / "reference-video-sealed-sources" / source_sha256 / analysis_sha256 / "source.mp4"
    target.parent.mkdir(parents=True)
    if existing_kind == "symlink":
        foreign = tmp_path / "foreign.mp4"
        foreign.write_bytes(b"foreign")
        target.symlink_to(foreign)
    elif existing_kind == "wrong_regular_file":
        target.write_bytes(b"wrong")
        target.chmod(0o600)
    elif existing_kind == "hardlink":
        foreign = tmp_path / "foreign.mp4"
        foreign.write_bytes(source_bytes)
        foreign.chmod(0o600)
        target.hardlink_to(foreign)
    else:
        target.write_bytes(source_bytes)
        target.chmod(0o644)
    before = target.read_bytes()

    with pytest.raises(ValueError, match="sealed source snapshot"):
        reference_evidence._seal_exact_public_source_for_handoff(
            source=source,
            user_data_root=root,
            canonical_ref="https://www.douyin.com/video/7658501922794432731",
            source_metadata={
                "requested_work_id": "7658501922794432731",
                "resolved_work_id": "7658501922794432731",
                "observed_work_id": "7658501922794432731",
                "author_sec_uid": "author-sec-uid",
                "identity_verification": "api_work_id_match",
            },
            source_sha256=source_sha256,
            analysis_spec_sha256=analysis_sha256,
        )

    assert target.read_bytes() == before


def test_fd_verification_rejects_path_swap_during_hash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    source_bytes = b"verified-source"
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    relative = Path("outputs") / "reference-video-sealed-sources" / source_sha256 / ("a" * 64) / "source.mp4"
    target = root / relative
    target.parent.mkdir(parents=True)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        current.chmod(0o700)
    target.write_bytes(source_bytes)
    target.chmod(0o600)
    displaced = target.with_name("displaced.mp4")
    original_read = reference_evidence.os.read
    swapped = False

    def swap_path(file_descriptor: int, count: int) -> bytes:
        nonlocal swapped
        if not swapped:
            swapped = True
            target.replace(displaced)
            target.write_bytes(b"different-source")
            target.chmod(0o600)
        return original_read(file_descriptor, count)

    monkeypatch.setattr(reference_evidence.os, "read", swap_path)
    with pytest.raises(ValueError, match="changed"):
        reference_evidence.verify_sealed_source_handoff_file(
            user_data_root=root,
            relative_ref=relative.as_posix(),
            expected_sha256=source_sha256,
            expected_size_bytes=len(source_bytes),
            expected_work_id="7658501922794432731",
        )

    assert swapped is True
    assert displaced.read_bytes() == source_bytes


def test_publish_failure_removes_owned_target_and_temporary_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    source = tmp_path / "download.mp4"
    source_bytes = b"verified-source"
    source.write_bytes(source_bytes)
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    analysis_sha256 = "a" * 64
    relative = Path("outputs") / "reference-video-sealed-sources" / source_sha256 / analysis_sha256 / "source.mp4"
    target = root / relative
    original_fsync = reference_evidence.os.fsync

    def fail_directory_fsync(file_descriptor: int) -> None:
        if stat.S_ISDIR(reference_evidence.os.fstat(file_descriptor).st_mode):
            raise OSError("simulated directory fsync failure")
        original_fsync(file_descriptor)

    monkeypatch.setattr(reference_evidence.os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError, match="directory fsync failure"):
        reference_evidence._seal_exact_public_source_for_handoff(
            source=source,
            user_data_root=root,
            canonical_ref="https://www.douyin.com/video/7658501922794432731",
            source_metadata={
                "requested_work_id": "7658501922794432731",
                "resolved_work_id": "7658501922794432731",
                "observed_work_id": "7658501922794432731",
                "author_sec_uid": "author-sec-uid",
                "identity_verification": "api_work_id_match",
            },
            source_sha256=source_sha256,
            analysis_spec_sha256=analysis_sha256,
        )

    assert not target.exists()
    assert list(target.parent.glob(".sealed-source-*.tmp")) == []


@pytest.mark.asyncio
async def test_analysis_failure_does_not_leave_an_orphaned_sealed_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    work_id = "7658501922794432731"
    root = _install_inspection_fakes(
        monkeypatch,
        tmp_path,
        source_bytes=b"exact-public-douyin-work",
        work_id=work_id,
    )

    def fail_extraction(**_kwargs: Any):
        raise ValueError("simulated extraction failure")

    monkeypatch.setattr(
        reference_evidence,
        "_extract_visual_evidence",
        fail_extraction,
    )
    with reference_evidence.capture_sealed_source_handoffs() as collector:
        payload = await reference_evidence.inspect_reference_videos(
            [f"https://www.douyin.com/video/{work_id}"],
            analysis_depth="mechanical",
            max_frames=4,
        )

    assert payload["operation_status"] == "failed"
    assert collector.snapshot() == ()
    assert not (root / "outputs" / "reference-video-sealed-sources").exists()


class _StructuredResult:
    def __init__(self, work_id: str, source_sha256: str) -> None:
        self._payload = {
            "contract_version": "ip-reference-video-evidence-v2",
            "operation_status": "failed",
            "trust_boundary": "untrusted source data",
            "requested_count": 1,
            "completed_count": 0,
            "items": [
                {
                    "status": "failed",
                    "purpose": "benchmark",
                    "source": {
                        "ref": f"https://www.douyin.com/video/{work_id}",
                        "content_sha256": source_sha256,
                        "requested_work_id": work_id,
                        "resolved_work_id": work_id,
                        "observed_work_id": work_id,
                        "author_sec_uid": "MS4wLjABAAAAexact-author",
                        "identity_verification": "api_work_id_match",
                        "observed_at": "2026-08-03T00:00:00+00:00",
                        "trust": "untrusted_source_data",
                    },
                    "error": {
                        "code": "TEST_FAILURE",
                        "message": "test-only failed item",
                        "retryable": False,
                    },
                }
            ],
            "limitations": [f"work {work_id} test projection"],
            "metadata": {
                "request_id": f"handoff-{work_id}",
                "manifest_version": "9" * 64,
                "adapter_version": "test-handoff-v1",
                "duration_ms": 1.0,
                "truncated": False,
            },
        }

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return self._payload


def _materialize_handoff(
    root: Path,
    *,
    work_id: str,
    source_bytes: bytes,
    analysis_sha256: str,
) -> reference_evidence.SealedSourceHandoff:
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    relative = Path("outputs") / "reference-video-sealed-sources" / source_sha256 / analysis_sha256 / "source.mp4"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        current.chmod(0o700)
    path.write_bytes(source_bytes)
    path.chmod(0o600)
    return reference_evidence.SealedSourceHandoff(
        relative_ref=relative.as_posix(),
        source_sha256=source_sha256,
        size_bytes=len(source_bytes),
        work_id=work_id,
    )


def _assert_descriptor_closed(file_descriptor: int) -> None:
    with pytest.raises(OSError):
        os.fstat(file_descriptor)


def test_context_owned_verifier_holds_exact_source_open_until_exit(
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    source_bytes = b"context-owned-exact-source"
    handoff = _materialize_handoff(
        root,
        work_id="7658501922794432731",
        source_bytes=source_bytes,
        analysis_sha256="a" * 64,
    )

    with reference_evidence.open_verified_sealed_source_handoff(
        user_data_root=root,
        handoff=handoff,
    ) as opened:
        descriptor = opened.file_descriptor
        assert opened.source_sha256 == handoff.source_sha256
        assert opened.size_bytes == handoff.size_bytes
        assert opened.work_id == handoff.work_id
        assert os.pread(descriptor, len(source_bytes), 0) == source_bytes
        assert os.fstat(descriptor).st_nlink == 1

    _assert_descriptor_closed(descriptor)


@pytest.mark.parametrize("invalid_field", ["work_id", "path"])
def test_context_owned_verifier_rejects_invalid_work_or_path_contract(
    invalid_field: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    handoff = _materialize_handoff(
        root,
        work_id="7658501922794432731",
        source_bytes=b"contract-bound-source",
        analysis_sha256="9" * 64,
    )
    invalid = reference_evidence.SealedSourceHandoff(
        relative_ref=(handoff.relative_ref.replace("reference-video-sealed-sources", "foreign-sources") if invalid_field == "path" else handoff.relative_ref),
        source_sha256=handoff.source_sha256,
        size_bytes=handoff.size_bytes,
        work_id="not-a-work" if invalid_field == "work_id" else handoff.work_id,
    )

    with pytest.raises(ValueError, match="handoff (work identity|path) is invalid"):
        with reference_evidence.open_verified_sealed_source_handoff(
            user_data_root=root,
            handoff=invalid,
        ):
            pytest.fail("invalid handoff must not enter the consumption window")


@pytest.mark.parametrize("swap_scope", ["root", "parent"])
def test_context_owned_verifier_rejects_root_or_parent_swap(
    swap_scope: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    handoff = _materialize_handoff(
        root,
        work_id="7658501922794432731",
        source_bytes=b"root-and-parent-binding",
        analysis_sha256="b" * 64,
    )
    displaced = tmp_path / f"displaced-{swap_scope}"

    with pytest.raises(ValueError, match="binding changed"):
        with reference_evidence.open_verified_sealed_source_handoff(
            user_data_root=root,
            handoff=handoff,
        ) as opened:
            descriptor = opened.file_descriptor
            if swap_scope == "root":
                root.rename(displaced)
                root.mkdir(mode=0o700)
            else:
                parent = root / "outputs"
                parent.rename(displaced)
                parent.mkdir(mode=0o700)

    _assert_descriptor_closed(descriptor)


@pytest.mark.parametrize("mutation", ["replace", "modify"])
def test_context_owned_verifier_rejects_file_replacement_or_modification(
    mutation: str,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    source_bytes = b"immutable-sealed-source"
    handoff = _materialize_handoff(
        root,
        work_id="7658501922794432731",
        source_bytes=source_bytes,
        analysis_sha256="c" * 64,
    )
    source = root / handoff.relative_ref

    with pytest.raises(ValueError, match="changed"):
        with reference_evidence.open_verified_sealed_source_handoff(
            user_data_root=root,
            handoff=handoff,
        ) as opened:
            descriptor = opened.file_descriptor
            if mutation == "replace":
                replacement = source.with_name("replacement.mp4")
                replacement.write_bytes(source_bytes)
                replacement.chmod(0o600)
                replacement.replace(source)
            else:
                writable = os.open(source, os.O_WRONLY)
                try:
                    os.pwrite(writable, b"X", 0)
                finally:
                    os.close(writable)

    _assert_descriptor_closed(descriptor)


def test_context_owned_verifier_preserves_consumer_exception_and_closes_fd(
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    handoff = _materialize_handoff(
        root,
        work_id="7658501922794432731",
        source_bytes=b"consumer-exception-source",
        analysis_sha256="d" * 64,
    )
    consumer_error = RuntimeError("consumer failed")

    with pytest.raises(RuntimeError) as caught:
        with reference_evidence.open_verified_sealed_source_handoff(
            user_data_root=root,
            handoff=handoff,
        ) as opened:
            descriptor = opened.file_descriptor
            raise consumer_error

    assert caught.value is consumer_error
    _assert_descriptor_closed(descriptor)


def test_context_owned_verifier_rejects_consumer_closing_owned_fd(
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    handoff = _materialize_handoff(
        root,
        work_id="7658501922794432731",
        source_bytes=b"consumer-must-not-close",
        analysis_sha256="e" * 64,
    )

    with pytest.raises(ValueError, match="descriptor is closed"):
        with reference_evidence.open_verified_sealed_source_handoff(
            user_data_root=root,
            handoff=handoff,
        ) as opened:
            descriptor = opened.file_descriptor
            os.close(descriptor)

    _assert_descriptor_closed(descriptor)


@pytest.mark.asyncio
async def test_context_owned_verifier_repeated_cancellation_closes_all_owned_fds(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir(mode=0o700)
    handoff = _materialize_handoff(
        root,
        work_id="7658501922794432731",
        source_bytes=b"cancelled-consumer-source",
        analysis_sha256="f" * 64,
    )
    original_open = reference_evidence.os.open
    owned_descriptors: list[int] = []

    def tracked_open(*args: Any, **kwargs: Any) -> int:
        descriptor = original_open(*args, **kwargs)
        owned_descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(reference_evidence.os, "open", tracked_open)
    entered = asyncio.Event()
    never = asyncio.Event()

    async def consume() -> None:
        with reference_evidence.open_verified_sealed_source_handoff(
            user_data_root=root,
            handoff=handoff,
        ) as opened:
            assert os.pread(opened.file_descriptor, handoff.size_bytes, 0)
            entered.set()
            await never.wait()

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert owned_descriptors
    for descriptor in owned_descriptors:
        _assert_descriptor_closed(descriptor)


@pytest.mark.asyncio
async def test_two_concurrent_mcp_calls_keep_private_handoffs_isolated_and_out_of_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    root.mkdir()
    work_ids = ("7658501922794432731", "7658501922794432732")
    handoffs = {
        work_id: _materialize_handoff(
            root,
            work_id=work_id,
            source_bytes=f"source-{work_id}".encode(),
            analysis_sha256=str(index) * 64,
        )
        for index, work_id in enumerate(work_ids, start=1)
    }
    monkeypatch.setenv("IP_AGENT_EVIDENCE_USER_DATA_ROOT", str(root))

    arrived = 0
    both_arrived = asyncio.Event()

    async def dispatch(**kwargs: Any):
        nonlocal arrived
        reference = kwargs["arguments"]["video_refs"][0]
        work_id = reference.rsplit("/", 1)[-1]
        arrived += 1
        if arrived == 2:
            both_arrived.set()

        async def child_execution() -> None:
            await both_arrived.wait()
            reference_evidence._record_sealed_source_handoff(handoffs[work_id])

        await asyncio.wait_for(child_execution(), timeout=1)
        return _StructuredResult(work_id, handoffs[work_id].source_sha256)

    monkeypatch.setattr(evidence_mcp.capability_dispatcher, "dispatch", dispatch)

    results = await asyncio.gather(
        *(
            evidence_mcp.inspect_reference_videos_tool(
                [f"https://www.douyin.com/video/{work_id}"],
                ctx=object(),
            )
            for work_id in work_ids
        )
    )

    for work_id, result in zip(work_ids, results, strict=True):
        assert result.meta is not None
        private = result.meta[reference_evidence.SEALED_SOURCE_HANDOFF_META_KEY]
        assert private == {
            "contract_version": reference_evidence.SEALED_SOURCE_HANDOFF_CONTRACT_VERSION,
            "items": [handoffs[work_id].as_meta()],
        }
        forbidden_path = handoffs[work_id].relative_ref
        assert forbidden_path not in json.dumps(result.structuredContent, ensure_ascii=False)
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        assert forbidden_path not in text
        assert all(forbidden_path not in str(block.uri) for block in result.content if isinstance(block, ResourceLink))
        assert handoffs[work_ids[1] if work_id == work_ids[0] else work_ids[0]].relative_ref not in json.dumps(
            private,
            ensure_ascii=False,
        )
        gateway_content, gateway_artifact = _convert_call_tool_result(result)
        assert forbidden_path not in json.dumps(gateway_content, ensure_ascii=False)
        assert "mcp_metadata" not in gateway_artifact
