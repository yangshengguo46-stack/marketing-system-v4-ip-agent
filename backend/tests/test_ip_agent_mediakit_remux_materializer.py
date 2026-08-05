from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from deerflow.ip_agent import mediakit_remux_materializer as subject
from deerflow.ip_agent.mediakit_remux_ingress import MediaKitRemuxIngressReceipt
from deerflow.ip_agent.mediakit_remux_paid_operator import (
    MediaKitRemuxPaidExecutionReceipt,
    MediaKitRemuxPaidExecutionResult,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def _private_source(root: Path, value: bytes = b"sealed-source-video") -> Path:
    uploads = _private_directory(root / "uploads")
    source = uploads / "source.mp4"
    source.write_bytes(value)
    source.chmod(0o600)
    return source


def _paid_result(
    *,
    runtime_url: str,
    source_sha256: str,
    source_size_bytes: int,
) -> MediaKitRemuxPaidExecutionResult:
    completed_at = datetime(2026, 8, 3, tzinfo=UTC)
    ingress = MediaKitRemuxIngressReceipt.model_validate(
        {
            "contract_version": "ip-mediakit-remux-https-candidate-v1",
            "adapter_version": "volcengine-mediakit-remux-https-ingress-v1",
            "provider": "volcengine-mediakit",
            "endpoint_sha256": "1" * 64,
            "derived_from_source_sha256": source_sha256,
            "source_size_bytes": source_size_bytes,
            "source_hash_checks": 2,
            "source_hash_unchanged": True,
            "container_format": "MP4",
            "candidate_kind": "provider_remux_derivative",
            "candidate_byte_identity": "not_attested_equal_to_source",
            "provider_content_attestation": "unavailable",
            "upload_file_id_sha256": "2" * 64,
            "client_token_sha256": "3" * 64,
            "task_id_sha256": "4" * 64,
            "provider_request_id_sha256s": ["5" * 64],
            "runtime_url_sha256": hashlib.sha256(runtime_url.encode()).hexdigest(),
            "request_sha256": "6" * 64,
            "provider_response_sha256s": ["7" * 64, "8" * 64, "9" * 64],
            "provider_response_sizes_bytes": [100, 101, 102],
            "status": "completed",
            "completed_at": completed_at,
            "expires_at": completed_at + timedelta(hours=24),
            "observed_ttl_seconds": 86400,
            "expiry_basis": "provider_reported",
            "poll_attempts": 1,
            "max_poll_attempts": 80,
            "poll_interval_seconds": 3.0,
            "response_size_limit_bytes": 1048576,
            "request_timeout_seconds": 120,
            "total_timeout_seconds": 600,
            "retries": 0,
            "billing_status": "provider_amount_unavailable",
        }
    )
    ingress_sha256 = subject._canonical_sha256(ingress.model_dump(mode="json", exclude_none=True))
    paid = MediaKitRemuxPaidExecutionReceipt.model_validate(
        {
            "contract_version": "ip-mediakit-remux-paid-execution-v1",
            "provider": "volcengine-mediakit",
            "capability": "managed_https_ingress_remux",
            "paid_call_scope_id": "scope-1",
            "paid_call_request_sha256": "a" * 64,
            "execution_run_id": "run-1",
            "source_sha256": source_sha256,
            "provider_request_sha256": "b" * 64,
            "client_token_sha256": "3" * 64,
            "provider_task_id_sha256": "4" * 64,
            "runtime_url_sha256": hashlib.sha256(runtime_url.encode()).hexdigest(),
            "remux_receipt_sha256": ingress_sha256,
            "provider_terminal_sha256": "c" * 64,
            "provider_task_status": "terminal",
            "provider_terminal_status": "completed",
            "paid_call_status": "reconciliation_required",
            "billing_status": "provider_amount_unavailable",
            "recovered_from_encrypted_state": False,
            "chat_authorization": "required_separate_paid_call",
            "chat_capability": "video_understanding_chat",
        }
    )
    return MediaKitRemuxPaidExecutionResult(
        runtime_url=runtime_url,
        remux_receipt=ingress,
        paid_execution_receipt=paid,
    )


def _equivalence(duration: float = 1.25) -> subject.PacketEquivalenceResult:
    return subject.PacketEquivalenceResult(
        source_duration_seconds=duration,
        candidate_duration_seconds=duration,
        duration_delta_seconds=0.0,
        codec_type_fingerprints={
            "audio": subject.PacketPayloadFingerprint(
                packet_count=2,
                total_bytes=4,
                payload_sequence_sha256="d" * 64,
            ),
            "video": subject.PacketPayloadFingerprint(
                packet_count=3,
                total_bytes=8,
                payload_sequence_sha256="e" * 64,
            ),
        },
    )


async def _materialize(
    root: Path,
    source: Path,
    candidate_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: MediaKitRemuxPaidExecutionResult | None = None,
    downloader=None,
    comparator=None,
):
    source_sha256 = _sha256_bytes(source.read_bytes())
    runtime_url = "https://output.volcvideo.com/candidate.mp4?signature=runtime-only"
    paid = result or _paid_result(
        runtime_url=runtime_url,
        source_sha256=source_sha256,
        source_size_bytes=source.stat().st_size,
    )
    monkeypatch.setattr(
        subject,
        "validate_mediakit_runtime_https_url",
        lambda value: value,
    )

    async def default_downloader(_url: str, destination_fd: int) -> None:
        os.ftruncate(destination_fd, 0)
        os.pwrite(destination_fd, candidate_bytes, 0)
        os.fsync(destination_fd)

    async def default_comparator(_source: Path, _candidate: Path):
        return _equivalence()

    return await subject.materialize_paid_remux_result(
        paid_result=paid,
        source_path=source,
        expected_source_sha256=source_sha256,
        resolved_evidence_root=root,
        downloader=downloader or default_downloader,
        packet_comparator=comparator or default_comparator,
    )


def _all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value)) if value else set()
    return set()


def test_success_publishes_private_safe_relative_handoff_and_reopens_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    candidate_bytes = b"materialized-remux-candidate"

    handoff = asyncio.run(_materialize(root, source, candidate_bytes, monkeypatch))

    assert not Path(handoff.candidate_relative_ref).is_absolute()
    assert not Path(handoff.receipt_relative_ref).is_absolute()
    candidate = root / handoff.candidate_relative_ref
    receipt_file = root / handoff.receipt_relative_ref
    assert candidate.read_bytes() == candidate_bytes
    assert stat.S_IMODE(candidate.stat().st_mode) == 0o600
    assert candidate.stat().st_nlink == 1
    assert stat.S_IMODE(receipt_file.stat().st_mode) == 0o600
    for parent in candidate.parents:
        if parent == root.parent:
            break
        assert stat.S_IMODE(parent.stat().st_mode) == 0o700
        if parent == root:
            break

    serialized = handoff.model_dump(mode="json")
    assert "root_device" not in serialized
    assert "root_inode" not in serialized
    assert serialized["authority_status"] == "research_observation_not_product_handoff"
    assert tuple(serialized["promotion_blockers"]) == subject.REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER
    assert serialized["receipt"]["authority_status"] == "research_observation_not_product_handoff"
    assert tuple(serialized["receipt"]["promotion_blockers"]) == subject.REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER
    assert subject.REMUX_MATERIALIZATION_PROMOTION_BLOCKERS == {
        "PAID_SCOPE_TO_EVIDENCE_ROOT_NOT_BOUND",
        "PRIVATE_HANDOFF_PERSISTENCE_NOT_SEALED",
    }
    forbidden_fragments = (
        "url",
        "task",
        "file_id",
        "request_id",
        "credential",
        "token",
        "scope_id",
        "run_id",
    )
    assert not any(fragment in key.lower() for key in _all_keys(serialized) for fragment in forbidden_fragments)
    serialized_text = json.dumps(serialized, ensure_ascii=False)
    for forbidden in (
        "runtime-only",
        "scope-1",
        "run-1",
        "volcvideo.com",
    ):
        assert forbidden not in serialized_text

    with subject.verify_materialized_remux_artifact(
        resolved_evidence_root=root,
        handoff=handoff,
    ) as reopened:
        candidate_fd = reopened.candidate_file_descriptor
        assert os.pread(candidate_fd, reopened.candidate_size_bytes, 0) == candidate_bytes
        assert reopened.receipt == handoff.receipt
        assert reopened.receipt.coverage.semantic_equivalence == "not_established"
    with pytest.raises(OSError):
        os.fstat(candidate_fd)

    # The public-safe projection is intentionally not a cross-run authority.
    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=json.loads(json.dumps(serialized)),
        ):
            pass
    assert error.value.code == "HANDOFF_INVALID"


def test_non_authoritative_status_and_blockers_are_required_and_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))

    receipt_payload = handoff.receipt.model_dump(mode="json")
    for field_name in ("authority_status", "promotion_blockers"):
        missing = dict(receipt_payload)
        missing.pop(field_name)
        with pytest.raises(ValueError):
            subject.RemuxMaterializationReceipt.model_validate(missing)
    altered_receipt = dict(receipt_payload)
    altered_receipt["promotion_blockers"] = ["PRIVATE_HANDOFF_PERSISTENCE_NOT_SEALED", "PAID_SCOPE_TO_EVIDENCE_ROOT_NOT_BOUND"]
    with pytest.raises(ValueError):
        subject.RemuxMaterializationReceipt.model_validate(altered_receipt)

    private_handoff = handoff.model_dump(mode="json") | {
        "root_device": handoff.root_device,
        "root_inode": handoff.root_inode,
    }
    for field_name in ("authority_status", "promotion_blockers"):
        missing = dict(private_handoff)
        missing.pop(field_name)
        with pytest.raises(ValueError):
            subject.MaterializedRemuxArtifact.model_validate(missing)
    altered_handoff = dict(private_handoff)
    altered_handoff["promotion_blockers"] = ["PRIVATE_HANDOFF_PERSISTENCE_NOT_SEALED", "PAID_SCOPE_TO_EVIDENCE_ROOT_NOT_BOUND"]
    with pytest.raises(ValueError):
        subject.MaterializedRemuxArtifact.model_validate(altered_handoff)


def test_ssrf_is_rejected_before_downloader(
    tmp_path: Path,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    source_sha256 = _sha256_bytes(source.read_bytes())
    runtime_url = "https://127.0.0.1/private"
    result = _paid_result(
        runtime_url=runtime_url,
        source_sha256=source_sha256,
        source_size_bytes=source.stat().st_size,
    )
    calls = 0

    async def forbidden(_url: str, _destination_fd: int) -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(
            subject.materialize_paid_remux_result(
                paid_result=result,
                source_path=source,
                expected_source_sha256=source_sha256,
                resolved_evidence_root=root,
                downloader=forbidden,
                packet_comparator=lambda *_args: None,
            )
        )
    assert error.value.code == "UNSAFE_RUNTIME_URL"
    assert calls == 0
    assert list(root.rglob("*.mp4")) == [source]


@pytest.mark.parametrize(
    ("status", "headers", "body", "expected_code"),
    [
        (302, {"location": "https://output.volcvideo.com/other.mp4"}, b"", "CANDIDATE_REDIRECT_FORBIDDEN"),
        (200, {"content-length": str(200 * 1024 * 1024 + 1)}, b"x", "CANDIDATE_SIZE_OUT_OF_RANGE"),
    ],
)
def test_downloader_rejects_redirect_and_declared_oversize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    headers: dict[str, str],
    body: bytes,
    expected_code: str,
) -> None:
    monkeypatch.setattr(
        subject,
        "validate_mediakit_runtime_https_url",
        lambda value: value,
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(status, headers=headers, content=body, request=request))
    destination = tmp_path / "candidate.mp4"
    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(
            subject.download_bounded_runtime_video(
                "https://output.volcvideo.com/candidate.mp4",
                destination,
                transport=transport,
            )
        )
    assert error.value.code == expected_code
    assert not destination.exists()


def test_downloader_rejects_streamed_oversize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(subject, "_MAX_ARTIFACT_BYTES", 4)
    monkeypatch.setattr(
        subject,
        "validate_mediakit_runtime_https_url",
        lambda value: value,
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"12345", request=request))
    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(
            subject.download_bounded_runtime_video(
                "https://output.volcvideo.com/candidate.mp4",
                tmp_path / "candidate.mp4",
                transport=transport,
            )
        )
    assert error.value.code == "CANDIDATE_SIZE_OUT_OF_RANGE"
    assert not (tmp_path / "candidate.mp4").exists()


def test_paid_runtime_hash_binding_mismatch_fails_without_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    source_sha256 = _sha256_bytes(source.read_bytes())
    result = _paid_result(
        runtime_url="https://output.volcvideo.com/a.mp4?signature=one",
        source_sha256=source_sha256,
        source_size_bytes=source.stat().st_size,
    )
    object.__setattr__(
        result,
        "runtime_url",
        "https://output.volcvideo.com/b.mp4?signature=two",
    )

    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(
            _materialize(
                root,
                source,
                b"candidate",
                monkeypatch,
                result=result,
            )
        )
    assert error.value.code == "PAID_REMUX_BINDING_MISMATCH"
    assert list(root.rglob("*.receipt.json")) == []


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("client_token_sha256", "f" * 64),
        ("provider_task_id_sha256", "e" * 64),
    ],
)
def test_paid_identity_hashes_must_cross_bind_to_ingress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    value: str,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    source_sha256 = _sha256_bytes(source.read_bytes())
    result = _paid_result(
        runtime_url="https://output.volcvideo.com/a.mp4?signature=one",
        source_sha256=source_sha256,
        source_size_bytes=source.stat().st_size,
    )
    setattr(result.paid_execution_receipt, field_name, value)

    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(
            _materialize(
                root,
                source,
                b"candidate",
                monkeypatch,
                result=result,
            )
        )
    assert error.value.code == "PAID_REMUX_BINDING_MISMATCH"
    assert list(root.rglob("*.receipt.json")) == []


def test_packet_comparison_rejects_payload_and_duration_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.mp4"
    candidate = tmp_path / "candidate.mp4"
    source.write_bytes(b"A")
    candidate.write_bytes(b"B")
    monkeypatch.setattr(subject, "_pinned_ffprobe_path", lambda: Path("ffprobe"))
    monkeypatch.setattr(
        subject,
        "_probe_streams_and_duration",
        lambda _ffprobe, _media: (1.0, {0: "video"}),
    )
    monkeypatch.setattr(
        subject,
        "_probe_packet_records",
        lambda _ffprobe, _media: [subject.PacketRecord(0, 0, 1)],
    )
    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(subject.compare_packet_payloads(source, candidate))
    assert error.value.code == "PACKET_PAYLOAD_MISMATCH"

    candidate.write_bytes(b"A")

    def durations(_ffprobe, media):
        return (1.0 if media == source else 1.01, {0: "video"})

    monkeypatch.setattr(subject, "_probe_streams_and_duration", durations)
    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(subject.compare_packet_payloads(source, candidate))
    assert error.value.code == "DURATION_MISMATCH"


def test_comparator_failure_and_cancellation_leave_no_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)

    async def mismatch(_source: Path, _candidate: Path):
        raise subject.RemuxMaterializationError("PACKET_PAYLOAD_MISMATCH")

    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(
            _materialize(
                root,
                source,
                b"candidate",
                monkeypatch,
                comparator=mismatch,
            )
        )
    assert error.value.code == "PACKET_PAYLOAD_MISMATCH"
    assert list(root.rglob(".materializing-*")) == []
    assert list(root.rglob("*.receipt.json")) == []
    assert list(root.rglob("*.mp4")) == [source]


def test_cancellation_waits_for_inflight_source_copy_before_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    started = threading.Event()
    release = threading.Event()
    original_copy = subject._copy_fd_to_fd
    finished = threading.Event()

    def slow_copy(source_fd: int, destination_fd: int) -> None:
        original_copy(source_fd, destination_fd)
        started.set()
        release.wait(timeout=5)
        finished.set()

    monkeypatch.setattr(subject, "_copy_fd_to_fd", slow_copy)

    async def cancel_during_copy() -> None:
        task = asyncio.create_task(_materialize(root, source, b"candidate", monkeypatch))
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_during_copy())
    assert finished.is_set()
    assert list(root.rglob(".materializing-*")) == []
    assert list(root.rglob("*.receipt.json")) == []
    assert list(root.rglob("*.mp4")) == [source]


def test_blocking_worker_self_cancellation_is_a_stable_internal_failure() -> None:
    def canceled_worker() -> None:
        raise asyncio.CancelledError

    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(subject._blocking_call(canceled_worker))
    assert error.value.code == "BLOCKING_OPERATION_CANCELLED"


def test_downloader_cancellation_leaves_no_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)

    async def canceled(_url: str, destination_fd: int) -> None:
        os.pwrite(destination_fd, b"partial", 0)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            _materialize(
                root,
                source,
                b"candidate",
                monkeypatch,
                downloader=canceled,
            )
        )
    assert list(root.rglob(".materializing-*")) == []
    assert list(root.rglob("*.receipt.json")) == []
    assert list(root.rglob("*.mp4")) == [source]


def test_source_symlink_hardlink_and_outside_root_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    source_sha256 = _sha256_bytes(source.read_bytes())
    result = _paid_result(
        runtime_url="https://output.volcvideo.com/a.mp4?signature=one",
        source_sha256=source_sha256,
        source_size_bytes=source.stat().st_size,
    )
    link = root / "uploads" / "source-link.mp4"
    link.symlink_to(source)

    for unsafe, expected in (
        (link, "SOURCE_PATH_UNSAFE"),
        (tmp_path / "outside.mp4", "SOURCE_OUTSIDE_THREAD_ROOT"),
    ):
        if unsafe.name == "outside.mp4":
            unsafe.write_bytes(source.read_bytes())
            unsafe.chmod(0o600)
        with pytest.raises(subject.RemuxMaterializationError) as error:
            asyncio.run(
                _materialize(
                    root,
                    unsafe,
                    b"candidate",
                    monkeypatch,
                    result=result,
                )
            )
        assert error.value.code == expected

    hardlink = root / "uploads" / "hardlink.mp4"
    hardlink.hardlink_to(source)
    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(
            _materialize(
                root,
                source,
                b"candidate",
                monkeypatch,
                result=result,
            )
        )
    assert error.value.code == "SOURCE_HARDLINK_FORBIDDEN"


def test_output_directory_symlink_is_rejected_without_touching_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    outside = _private_directory(tmp_path / "outside")
    marker = outside / "preserve"
    marker.write_text("unchanged", encoding="utf-8")
    (root / "outputs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    assert error.value.code == "OUTPUT_DIRECTORY_NOT_PRIVATE"
    assert marker.read_text(encoding="utf-8") == "unchanged"
    assert sorted(path.name for path in outside.iterdir()) == ["preserve"]


def test_parent_path_swap_after_dirfd_open_fails_without_writing_swap_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    outside = _private_directory(tmp_path / "outside")
    marker = outside / "preserve"
    marker.write_text("unchanged", encoding="utf-8")
    original_create = subject._create_private_staging_directory

    def swap_parent_after_open(output_fd: int):
        staging = original_create(output_fd)
        outputs = root / "outputs"
        moved = root / "outputs-moved"
        outputs.rename(moved)
        outputs.symlink_to(outside, target_is_directory=True)
        return staging

    monkeypatch.setattr(
        subject,
        "_create_private_staging_directory",
        swap_parent_after_open,
    )
    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    assert error.value.code == "OUTPUT_DIRECTORY_BINDING_CHANGED"
    assert marker.read_text(encoding="utf-8") == "unchanged"
    assert sorted(path.name for path in outside.iterdir()) == ["preserve"]
    assert list((root / "outputs-moved").rglob("*.mp4")) == []
    assert list((root / "outputs-moved").rglob("*.receipt.json")) == []


def test_root_swap_after_source_open_uses_original_root_fd_and_fails_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    moved_root = tmp_path / "user-data-moved"
    original_output_context = subject._private_output_directory_descriptor

    @contextmanager
    def swap_root_before_output(root_fd: int, *components: str):
        root.rename(moved_root)
        _private_directory(root)
        with original_output_context(root_fd, *components) as output:
            yield output

    monkeypatch.setattr(
        subject,
        "_private_output_directory_descriptor",
        swap_root_before_output,
    )
    with pytest.raises(subject.RemuxMaterializationError) as error:
        asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    assert error.value.code == "OUTPUT_DIRECTORY_BINDING_CHANGED"
    assert list(root.rglob("*.mp4")) == []
    assert list(root.rglob("*.receipt.json")) == []
    assert list(moved_root.rglob("*.receipt.json")) == []
    assert [path.name for path in moved_root.rglob("*.mp4")] == ["source.mp4"]


def test_concurrent_identical_publish_has_one_winner_and_never_overwrites(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    candidate_bytes = b"same-candidate"
    ready = 0
    release = asyncio.Event()

    async def racing_download(_url: str, destination_fd: int) -> None:
        nonlocal ready
        os.pwrite(destination_fd, candidate_bytes, 0)
        os.fsync(destination_fd)
        ready += 1
        if ready == 2:
            release.set()
        await release.wait()

    async def run_both():
        return await asyncio.gather(
            _materialize(
                root,
                source,
                candidate_bytes,
                monkeypatch,
                downloader=racing_download,
            ),
            _materialize(
                root,
                source,
                candidate_bytes,
                monkeypatch,
                downloader=racing_download,
            ),
            return_exceptions=True,
        )

    results = asyncio.run(run_both())
    winners = [item for item in results if isinstance(item, subject.MaterializedRemuxArtifact)]
    failures = [item for item in results if isinstance(item, subject.RemuxMaterializationError)]
    assert len(winners) == 1
    assert [failure.code for failure in failures] == ["ARTIFACT_OUTPUT_EXISTS"]
    candidate_files = [path for path in root.rglob("*.mp4") if path != source]
    receipt_files = list(root.rglob("*.receipt.json"))
    assert len(candidate_files) == 1
    assert len(receipt_files) == 1
    assert candidate_files[0].read_bytes() == candidate_bytes


def test_verifier_rejects_symlink_and_hardlinked_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    candidate = root / handoff.candidate_relative_ref
    extra_link = root / "uploads" / "candidate-copy.mp4"
    extra_link.hardlink_to(candidate)
    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ):
            pass
    assert error.value.code == "ARTIFACT_HARDLINK_FORBIDDEN"
    extra_link.unlink()

    candidate.unlink()
    candidate.symlink_to(source)
    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ):
            pass
    assert error.value.code == "ARTIFACT_FILE_UNSAFE"


def test_verifier_rejects_symlinked_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    source_directory = (root / handoff.candidate_relative_ref).parent
    moved = source_directory.with_name("moved-artifacts")
    source_directory.rename(moved)
    source_directory.symlink_to(moved, target_is_directory=True)

    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ):
            pass
    assert error.value.code == "HANDOFF_PATH_INVALID"


def test_verifier_rejects_root_replacement_after_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    root.rename(tmp_path / "original-user-data")
    _private_directory(root)

    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ):
            pass
    assert error.value.code == "HANDOFF_ROOT_BINDING_MISMATCH"


def test_verifier_detects_root_swap_between_artifact_opens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    moved_root = tmp_path / "original-user-data"
    original_open = subject._open_verified_relative_file_descriptor

    def swap_after_candidate(root_fd, relative_ref, **kwargs):
        descriptor = original_open(root_fd, relative_ref, **kwargs)
        if relative_ref == handoff.candidate_relative_ref:
            root.rename(moved_root)
            _private_directory(root)
        return descriptor

    monkeypatch.setattr(
        subject,
        "_open_verified_relative_file_descriptor",
        swap_after_candidate,
    )
    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ):
            pass
    assert error.value.code == "HANDOFF_ROOT_BINDING_CHANGED"


def test_verifier_detects_root_swap_during_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    moved_root = tmp_path / "original-user-data"

    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ) as reopened:
            assert os.pread(reopened.candidate_file_descriptor, 9, 0) == b"candidate"
            root.rename(moved_root)
            _private_directory(root)
    assert error.value.code == "HANDOFF_ROOT_BINDING_CHANGED"


def test_receipt_is_read_from_verified_descriptor_not_a_reopened_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    receipt_path = root / handoff.receipt_relative_ref
    original_open = subject._open_verified_relative_file_descriptor

    def replace_after_open(root_arg, relative_ref, **kwargs):
        descriptor = original_open(root_arg, relative_ref, **kwargs)
        if relative_ref == handoff.receipt_relative_ref:
            replacement = receipt_path.with_suffix(".replacement")
            replacement.write_text('{"untrusted":"replacement"}', encoding="utf-8")
            replacement.chmod(0o600)
            replacement.replace(receipt_path)
        return descriptor

    monkeypatch.setattr(
        subject,
        "_open_verified_relative_file_descriptor",
        replace_after_open,
    )
    with subject.verify_materialized_remux_artifact(
        resolved_evidence_root=root,
        handoff=handoff,
    ) as reopened:
        assert reopened.receipt == handoff.receipt
        assert os.pread(reopened.candidate_file_descriptor, 9, 0) == b"candidate"


def test_candidate_change_during_consumption_fails_on_context_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    candidate = root / handoff.candidate_relative_ref

    with pytest.raises(subject.RemuxMaterializationError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ) as reopened:
            assert os.pread(reopened.candidate_file_descriptor, 9, 0) == b"candidate"
            candidate.write_bytes(b"tampered!")
            candidate.chmod(0o600)
    assert error.value.code == "HANDOFF_CHANGED_DURING_CONSUMPTION"


def test_consumer_oserror_is_not_misreported_as_a_handoff_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _private_directory(tmp_path / "user-data")
    source = _private_source(root)
    handoff = asyncio.run(_materialize(root, source, b"candidate", monkeypatch))
    consumer_error = OSError("downstream local io failed")

    with pytest.raises(OSError) as error:
        with subject.verify_materialized_remux_artifact(
            resolved_evidence_root=root,
            handoff=handoff,
        ):
            raise consumer_error
    assert error.value is consumer_error
