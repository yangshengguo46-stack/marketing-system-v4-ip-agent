"""Materialize one paid MediaKit remux URL into private Evidence storage.

The paid operator deliberately returns an ephemeral HTTPS locator in process.
This module is the only byte-materialization boundary for that locator.  It
downloads with a fixed SSRF policy and no redirects, proves packet-payload and
duration equivalence against an immutable source snapshot, and publishes one
owner/thread-relative handoff without exposing the provider locator or its
operational identifiers.

This module performs no provider submission and has no Agent/MCP registration.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import subprocess
import tempfile
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from deerflow.config.paths import get_paths
from deerflow.config.runtime_paths import project_root

from .mediakit_remux_ingress import validate_mediakit_runtime_https_url

REMUX_MATERIALIZATION_RECEIPT_VERSION = "ip-mediakit-remux-materialization-receipt-v1"
REMUX_MATERIALIZATION_HANDOFF_VERSION = "ip-mediakit-remux-materialization-handoff-v1"
REMUX_MATERIALIZATION_OUTPUT_ROOT = "reference-video-remux-artifacts"
REMUX_MATERIALIZATION_AUTHORITY_STATUS = "research_observation_not_product_handoff"
REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER = (
    # The paid execution receipt intentionally omits Owner/thread identity.
    # Runtime promotion must therefore add a server-authoritative binding
    # from the admitted paid scope to the resolved Evidence root first.
    "PAID_SCOPE_TO_EVIDENCE_ROOT_NOT_BOUND",
    # root dev/inode is a same-process capability, excluded from ordinary
    # serialization and not authenticated for cross-run persistence.
    "PRIVATE_HANDOFF_PERSISTENCE_NOT_SEALED",
)
REMUX_MATERIALIZATION_PROMOTION_BLOCKERS = frozenset(REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER)

_MAX_ARTIFACT_BYTES = 200 * 1024 * 1024
_MAX_DURATION_SECONDS = 20 * 60
_MAX_FFPROBE_JSON_BYTES = 1024 * 1024
_MAX_PACKET_PROBE_BYTES = 64 * 1024 * 1024
_DOWNLOAD_TIMEOUT_SECONDS = 180
_FFPROBE_TIMEOUT_SECONDS = 180
_DURATION_TOLERANCE_SECONDS = 0.001
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_CODEC_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SAFE_SUFFIX_RE = re.compile(r"^[a-z0-9]{1,10}$")


class RemuxMaterializationError(RuntimeError):
    """A bounded failure that cannot contain a locator or provider payload."""

    def __init__(self, code: str) -> None:
        normalized = str(code or "REMUX_MATERIALIZATION_FAILED")
        self.code = normalized if re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", normalized) else "REMUX_MATERIALIZATION_FAILED"
        super().__init__(self.code)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PacketPayloadFingerprint(_StrictModel):
    packet_count: int = Field(strict=True, gt=0)
    total_bytes: int = Field(strict=True, gt=0, le=_MAX_ARTIFACT_BYTES)
    payload_sequence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PacketPayloadEquivalence(_StrictModel):
    verdict: Literal["equivalent"] = "equivalent"
    comparison_key: Literal["codec_type_plus_packet_payload_sequence"] = "codec_type_plus_packet_payload_sequence"
    stream_index_used_as_content_identity: Literal[False] = False
    duration_tolerance_seconds: Literal[0.001] = _DURATION_TOLERANCE_SECONDS
    codec_types: dict[str, PacketPayloadFingerprint] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_codec_types(self) -> PacketPayloadEquivalence:
        if any(_CODEC_TYPE_RE.fullmatch(key) is None for key in self.codec_types):
            raise ValueError("packet equivalence has an invalid codec type")
        return self


class RemuxMaterializationCoverage(_StrictModel):
    source_hash: Literal["verified_before_and_after"] = "verified_before_and_after"
    candidate_hash: Literal["verified"] = "verified"
    download: Literal["complete_bounded_no_redirect"] = "complete_bounded_no_redirect"
    duration: Literal["complete"] = "complete"
    packet_payloads: Literal["complete"] = "complete"
    provider_content_attestation: Literal["unavailable"] = "unavailable"
    semantic_equivalence: Literal["not_established"] = "not_established"


class RemuxDerivation(_StrictModel):
    relationship: Literal["provider_remux_derivative_of_sealed_source"] = "provider_remux_derivative_of_sealed_source"
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RemuxMaterializationReceipt(_StrictModel):
    """Public-safe, non-authoritative byte observation with no operation ids."""

    contract_version: Literal["ip-mediakit-remux-materialization-receipt-v1"] = REMUX_MATERIALIZATION_RECEIPT_VERSION
    authority_status: Literal["research_observation_not_product_handoff"]
    promotion_blockers: tuple[str, str]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(strict=True, gt=0, le=_MAX_ARTIFACT_BYTES)
    candidate_size_bytes: int = Field(strict=True, gt=0, le=_MAX_ARTIFACT_BYTES)
    source_duration_seconds: float = Field(gt=0, le=_MAX_DURATION_SECONDS)
    candidate_duration_seconds: float = Field(gt=0, le=_MAX_DURATION_SECONDS)
    duration_delta_seconds: float
    equivalence: PacketPayloadEquivalence
    coverage: RemuxMaterializationCoverage
    derivation: RemuxDerivation

    @model_validator(mode="after")
    def validate_bindings(self) -> RemuxMaterializationReceipt:
        if self.promotion_blockers != REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER:
            raise ValueError("remux materialization promotion blockers are invalid")
        if self.derivation.source_sha256 != self.source_sha256 or self.derivation.candidate_sha256 != self.candidate_sha256:
            raise ValueError("remux derivation hashes do not match the receipt")
        measured_delta = round(self.candidate_duration_seconds - self.source_duration_seconds, 6)
        if measured_delta != self.duration_delta_seconds or abs(measured_delta) > _DURATION_TOLERANCE_SECONDS:
            raise ValueError("remux duration equivalence is invalid")
        return self


class MaterializedRemuxArtifact(_StrictModel):
    """Operator-private, owner/thread-relative handoff; never a host path."""

    contract_version: Literal["ip-mediakit-remux-materialization-handoff-v1"] = REMUX_MATERIALIZATION_HANDOFF_VERSION
    authority_status: Literal["research_observation_not_product_handoff"]
    promotion_blockers: tuple[str, str]
    candidate_relative_ref: str = Field(min_length=1, max_length=600)
    receipt_relative_ref: str = Field(min_length=1, max_length=620)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_size_bytes: int = Field(strict=True, gt=0, le=_MAX_ARTIFACT_BYTES)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    receipt: RemuxMaterializationReceipt
    # Local filesystem authority is intentionally kept out of ordinary
    # serialization/model context.  The in-process verifier requires the
    # original object (or an explicitly private mapping containing these
    # fields) so a relative ref cannot be replayed against another root.
    root_device: int = Field(strict=True, ge=0, repr=False, exclude=True)
    root_inode: int = Field(strict=True, gt=0, repr=False, exclude=True)

    @model_validator(mode="after")
    def validate_relative_refs(self) -> MaterializedRemuxArtifact:
        if self.promotion_blockers != REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER:
            raise ValueError("remux materialization promotion blockers are invalid")
        expected_base = Path("outputs", REMUX_MATERIALIZATION_OUTPUT_ROOT, self.source_sha256)
        expected_candidate = (expected_base / f"{self.candidate_sha256}.mp4").as_posix()
        expected_receipt = (expected_base / f"{self.candidate_sha256}.receipt.json").as_posix()
        if self.candidate_relative_ref != expected_candidate or self.receipt_relative_ref != expected_receipt:
            raise ValueError("remux materialization handoff path is invalid")
        if self.receipt.source_sha256 != self.source_sha256 or self.receipt.candidate_sha256 != self.candidate_sha256:
            raise ValueError("remux materialization handoff hashes do not match its receipt")
        if self.receipt.candidate_size_bytes != self.candidate_size_bytes:
            raise ValueError("remux materialization handoff size does not match its receipt")
        if _canonical_sha256(self.receipt.model_dump(mode="json")) != self.receipt_sha256:
            raise ValueError("remux materialization receipt digest is invalid")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedMaterializedRemuxArtifact:
    """Context-bound descriptor for an authorized in-process consumer."""

    candidate_file_descriptor: int = field(repr=False)
    candidate_size_bytes: int
    receipt: RemuxMaterializationReceipt


@dataclass(frozen=True, slots=True)
class PacketRecord:
    stream_index: int
    position: int
    size: int


@dataclass(frozen=True, slots=True)
class PacketEquivalenceResult:
    source_duration_seconds: float
    candidate_duration_seconds: float
    duration_delta_seconds: float
    codec_type_fingerprints: dict[str, PacketPayloadFingerprint]


class _ModelDumpable(Protocol):
    def model_dump(self, *, mode: str, exclude_none: bool = ...) -> dict[str, Any]: ...


class _PaidRemuxResult(Protocol):
    runtime_url: str
    remux_receipt: _ModelDumpable
    paid_execution_receipt: _ModelDumpable


DownloadRunner = Callable[[str, int], Awaitable[None]]
PacketComparator = Callable[[Path, Path], Awaitable[PacketEquivalenceResult]]


async def _blocking_call(function: Callable[..., Any], /, *args: Any) -> Any:
    """Finish an offloaded operation before propagating task cancellation."""

    task = asyncio.create_task(asyncio.to_thread(function, *args))
    current = asyncio.current_task()
    cancellation_count = 0
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.done() and task.cancelled() and (current is None or current.cancelling() == 0):
                break
            cancellation_count += 1
            if current is not None:
                current.uncancel()
        except BaseException:
            break

    worker_error: BaseException | None = None
    result: Any = None
    if task.cancelled():
        worker_error = RemuxMaterializationError("BLOCKING_OPERATION_CANCELLED")
    else:
        try:
            result = task.result()
        except BaseException as exc:
            worker_error = exc

    if cancellation_count:
        if current is not None:
            for _ in range(cancellation_count):
                current.cancel()
        raise asyncio.CancelledError
    if worker_error is not None:
        raise worker_error
    return result


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_fd(file_descriptor: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while chunk := os.pread(file_descriptor, 1024 * 1024, offset):
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _fsync_directory_descriptor(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError:
        raise RemuxMaterializationError("OUTPUT_DIRECTORY_FSYNC_FAILED") from None


def _require_private_directory(path: Path, *, code: str) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError:
        raise RemuxMaterializationError(code) from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise RemuxMaterializationError(code)
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise RemuxMaterializationError(code)
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise RemuxMaterializationError(code)
    return info


@dataclass(slots=True)
class _PrivateOutputDirectory:
    relative: Path
    descriptor: int
    preserve: bool = False


@contextmanager
def _private_output_directory_descriptor(
    root_fd: int,
    *components: str,
) -> Iterator[_PrivateOutputDirectory]:
    """Create/open a private tree while holding every parent descriptor."""

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    created: list[tuple[int, str]] = []
    try:
        current = os.dup(root_fd)
        descriptors.append(current)
        root_info = os.fstat(current)
        if not stat.S_ISDIR(root_info.st_mode):
            raise RemuxMaterializationError("THREAD_EVIDENCE_ROOT_UNAVAILABLE")
        relative = Path()
        for component in components:
            if not component or component in {".", ".."} or "/" in component or "\\" in component:
                raise RemuxMaterializationError("OUTPUT_DIRECTORY_COMPONENT_INVALID")
            try:
                os.mkdir(component, mode=0o700, dir_fd=current)
                created.append((current, component))
                _fsync_directory_descriptor(current)
            except FileExistsError:
                pass
            except OSError:
                raise RemuxMaterializationError("OUTPUT_DIRECTORY_UNAVAILABLE") from None
            try:
                child = os.open(component, directory_flags, dir_fd=current)
            except OSError:
                raise RemuxMaterializationError("OUTPUT_DIRECTORY_NOT_PRIVATE") from None
            descriptors.append(child)
            info = os.fstat(child)
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or (hasattr(os, "geteuid") and info.st_uid != os.geteuid()):
                raise RemuxMaterializationError("OUTPUT_DIRECTORY_NOT_PRIVATE")
            current = child
            relative /= component
        output = _PrivateOutputDirectory(relative=relative, descriptor=current)
        try:
            yield output
        finally:
            if not output.preserve:
                for parent_fd, component in reversed(created):
                    with contextlib.suppress(OSError):
                        os.rmdir(component, dir_fd=parent_fd)
                        _fsync_directory_descriptor(parent_fd)
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("OUTPUT_DIRECTORY_UNAVAILABLE") from None
    finally:
        for descriptor in reversed(descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)


def _create_private_staging_directory(output_fd: int) -> tuple[str, int]:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    for _ in range(16):
        name = f".materializing-{secrets.token_hex(16)}"
        try:
            os.mkdir(name, mode=0o700, dir_fd=output_fd)
        except FileExistsError:
            continue
        except OSError:
            raise RemuxMaterializationError("STAGING_DIRECTORY_UNAVAILABLE") from None
        try:
            descriptor = os.open(name, directory_flags, dir_fd=output_fd)
            info = os.fstat(descriptor)
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or (hasattr(os, "geteuid") and info.st_uid != os.geteuid()):
                raise RemuxMaterializationError("STAGING_DIRECTORY_NOT_PRIVATE")
            _fsync_directory_descriptor(output_fd)
            return name, descriptor
        except BaseException:
            with contextlib.suppress(OSError):
                os.rmdir(name, dir_fd=output_fd)
            raise
    raise RemuxMaterializationError("STAGING_DIRECTORY_COLLISION")


def _verify_private_directory_binding(
    root: Path,
    relative: Path,
    expected_fd: int,
    *,
    expected_root_identity: tuple[int, int] | None = None,
) -> None:
    """Prove the public relative path still reaches the held directory fd."""

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        root_info = os.fstat(current)
        if expected_root_identity is not None and (root_info.st_dev, root_info.st_ino) != expected_root_identity:
            raise RemuxMaterializationError("OUTPUT_DIRECTORY_BINDING_CHANGED")
        for component in relative.parts:
            current = os.open(component, directory_flags, dir_fd=current)
            descriptors.append(current)
        observed = os.fstat(current)
        expected = os.fstat(expected_fd)
        if (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino):
            raise RemuxMaterializationError("OUTPUT_DIRECTORY_BINDING_CHANGED")
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("OUTPUT_DIRECTORY_BINDING_CHANGED") from None
    finally:
        for descriptor in reversed(descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)


def _verify_root_directory_binding(
    root: Path,
    expected_fd: int,
    *,
    code: str,
) -> None:
    """Prove the configured root path still names the held private root."""

    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    observed_fd: int | None = None
    try:
        observed_fd = os.open(root, directory_flags)
        observed = os.fstat(observed_fd)
        expected = os.fstat(expected_fd)
        if not stat.S_ISDIR(observed.st_mode) or stat.S_IMODE(observed.st_mode) != 0o700 or (hasattr(os, "geteuid") and observed.st_uid != os.geteuid()) or (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino):
            raise RemuxMaterializationError(code)
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError(code) from None
    finally:
        if observed_fd is not None:
            with contextlib.suppress(OSError):
                os.close(observed_fd)


def _open_handoff_root_descriptor(
    root: Path,
    *,
    expected_identity: tuple[int, int],
) -> int:
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(root, directory_flags)
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or (hasattr(os, "geteuid") and info.st_uid != os.geteuid()):
            raise RemuxMaterializationError("HANDOFF_ROOT_NOT_PRIVATE")
        if (info.st_dev, info.st_ino) != expected_identity:
            raise RemuxMaterializationError("HANDOFF_ROOT_BINDING_MISMATCH")
        opened = descriptor
        descriptor = None
        return opened
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("HANDOFF_ROOT_BINDING_MISMATCH") from None
    finally:
        if descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(descriptor)


def _resolved_private_root(path: Path) -> Path:
    supplied = Path(path).expanduser()
    _require_private_directory(supplied, code="THREAD_EVIDENCE_ROOT_NOT_PRIVATE")
    try:
        resolved = supplied.resolve(strict=True)
    except (OSError, RuntimeError):
        raise RemuxMaterializationError("THREAD_EVIDENCE_ROOT_UNAVAILABLE") from None
    _require_private_directory(resolved, code="THREAD_EVIDENCE_ROOT_NOT_PRIVATE")
    return resolved


def _relative_under_root(path: Path, *, root: Path) -> Path:
    supplied = Path(path).expanduser()
    absolute = supplied if supplied.is_absolute() else root / supplied
    try:
        relative = absolute.absolute().relative_to(root)
    except (OSError, ValueError):
        raise RemuxMaterializationError("SOURCE_OUTSIDE_THREAD_ROOT") from None
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise RemuxMaterializationError("SOURCE_OUTSIDE_THREAD_ROOT")
    return relative


@contextmanager
def _open_private_source(path: Path, *, root: Path):
    relative = _relative_under_root(path, root=root)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for component in relative.parts[:-1]:
            current = os.open(component, directory_flags, dir_fd=current)
            descriptors.append(current)
            info = os.fstat(current)
            if not stat.S_ISDIR(info.st_mode) or (hasattr(os, "geteuid") and info.st_uid != os.geteuid()):
                raise RemuxMaterializationError("SOURCE_PATH_UNSAFE")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(relative.parts[-1], flags, dir_fd=current)
        descriptors.append(source_fd)
        info = os.fstat(source_fd)
        if not stat.S_ISREG(info.st_mode):
            raise RemuxMaterializationError("SOURCE_NOT_REGULAR_FILE")
        if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
            raise RemuxMaterializationError("SOURCE_OWNER_MISMATCH")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise RemuxMaterializationError("SOURCE_NOT_PRIVATE")
        if info.st_nlink != 1:
            raise RemuxMaterializationError("SOURCE_HARDLINK_FORBIDDEN")
        if not 0 < info.st_size <= _MAX_ARTIFACT_BYTES:
            raise RemuxMaterializationError("SOURCE_SIZE_OUT_OF_RANGE")
        path_info = os.stat(relative.parts[-1], dir_fd=current, follow_symlinks=False)
        if (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino):
            raise RemuxMaterializationError("SOURCE_PATH_CHANGED")
        yield source_fd, info, descriptors[0]
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("SOURCE_PATH_UNSAFE") from None
    finally:
        for descriptor in reversed(descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)


def _create_private_file_at(directory_fd: int, name: str) -> int:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        os.fchmod(descriptor, 0o600)
        return descriptor
    except OSError:
        raise RemuxMaterializationError("STAGING_FILE_UNAVAILABLE") from None


def _copy_fd_to_fd(source_fd: int, destination_fd: int) -> None:
    try:
        os.ftruncate(destination_fd, 0)
        offset = 0
        while chunk := os.pread(source_fd, 1024 * 1024, offset):
            view = memoryview(chunk)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise RemuxMaterializationError("SOURCE_SNAPSHOT_FAILED")
                view = view[written:]
            offset += len(chunk)
        os.fsync(destination_fd)
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("SOURCE_SNAPSHOT_FAILED") from None


def _require_private_regular_fd(
    descriptor: int,
    *,
    expected_size: int | None = None,
) -> os.stat_result:
    try:
        info = os.fstat(descriptor)
    except OSError:
        raise RemuxMaterializationError("ARTIFACT_FILE_UNAVAILABLE") from None
    if not stat.S_ISREG(info.st_mode):
        raise RemuxMaterializationError("ARTIFACT_FILE_UNSAFE")
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise RemuxMaterializationError("ARTIFACT_OWNER_MISMATCH")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise RemuxMaterializationError("ARTIFACT_NOT_PRIVATE")
    if info.st_nlink != 1:
        raise RemuxMaterializationError("ARTIFACT_HARDLINK_FORBIDDEN")
    if not 0 < info.st_size <= _MAX_ARTIFACT_BYTES:
        raise RemuxMaterializationError("ARTIFACT_SIZE_OUT_OF_RANGE")
    if expected_size is not None and info.st_size != expected_size:
        raise RemuxMaterializationError("ARTIFACT_SIZE_MISMATCH")
    return info


def _descriptor_path(descriptor: int) -> Path:
    candidates = (Path("/proc/self/fd") / str(descriptor), Path("/dev/fd") / str(descriptor))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RemuxMaterializationError("DESCRIPTOR_PATH_UNAVAILABLE")


def _descriptor_fds(*paths: Path) -> tuple[int, ...]:
    descriptors: set[int] = set()
    for path in paths:
        match = re.fullmatch(r"/(?:proc/self/fd|dev/fd)/([0-9]+)", str(path))
        if match is not None:
            descriptors.add(int(match.group(1)))
    return tuple(sorted(descriptors))


def _require_private_regular(path: Path, *, expected_size: int | None = None) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError:
        raise RemuxMaterializationError("ARTIFACT_FILE_UNAVAILABLE") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RemuxMaterializationError("ARTIFACT_FILE_UNSAFE")
    if hasattr(os, "geteuid") and info.st_uid != os.geteuid():
        raise RemuxMaterializationError("ARTIFACT_OWNER_MISMATCH")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise RemuxMaterializationError("ARTIFACT_NOT_PRIVATE")
    if info.st_nlink != 1:
        raise RemuxMaterializationError("ARTIFACT_HARDLINK_FORBIDDEN")
    if not 0 < info.st_size <= _MAX_ARTIFACT_BYTES:
        raise RemuxMaterializationError("ARTIFACT_SIZE_OUT_OF_RANGE")
    if expected_size is not None and info.st_size != expected_size:
        raise RemuxMaterializationError("ARTIFACT_SIZE_MISMATCH")
    return info


def _pinned_ffprobe_path() -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    paths = get_paths()
    candidates = (
        paths.base_dir / "toolchains" / "ffmpeg" / "bin" / f"ffprobe{suffix}",
        project_root() / ".deer-flow" / "toolchains" / "ffmpeg" / "bin" / f"ffprobe{suffix}",
        paths.base_dir.parent.parent / ".deer-flow" / "toolchains" / "ffmpeg" / "bin" / f"ffprobe{suffix}",
    )
    for candidate in candidates:
        try:
            info = candidate.lstat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode) and os.access(candidate, os.X_OK):
            return candidate.resolve(strict=True)
    raise RemuxMaterializationError("PINNED_FFPROBE_UNAVAILABLE")


def _run_ffprobe_json(ffprobe: Path, media: Path, entries: str) -> Mapping[str, Any]:
    pass_fds = _descriptor_fds(media)
    try:
        result = subprocess.run(
            [str(ffprobe), "-v", "error", "-show_entries", entries, "-of", "json", str(media)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            check=False,
            **({"pass_fds": pass_fds} if pass_fds else {}),
        )
    except subprocess.TimeoutExpired:
        raise RemuxMaterializationError("FFPROBE_TIMEOUT") from None
    except (OSError, subprocess.SubprocessError):
        raise RemuxMaterializationError("FFPROBE_FAILED") from None
    if result.returncode != 0 or not result.stdout or len(result.stdout) > _MAX_FFPROBE_JSON_BYTES:
        raise RemuxMaterializationError("FFPROBE_FAILED")
    try:
        payload = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RemuxMaterializationError("FFPROBE_INVALID_OUTPUT") from None
    if not isinstance(payload, Mapping):
        raise RemuxMaterializationError("FFPROBE_INVALID_OUTPUT")
    return payload


def _probe_streams_and_duration(
    ffprobe: Path,
    media: Path,
    *,
    json_runner: Callable[[Path, Path, str], Mapping[str, Any]] = _run_ffprobe_json,
) -> tuple[float, dict[int, str]]:
    payload = json_runner(ffprobe, media, "format=duration:stream=index,codec_type")
    format_payload = payload.get("format")
    streams = payload.get("streams")
    if not isinstance(format_payload, Mapping) or not isinstance(streams, list):
        raise RemuxMaterializationError("FFPROBE_INVALID_OUTPUT")
    try:
        duration = float(format_payload["duration"])
    except (KeyError, TypeError, ValueError, OverflowError):
        raise RemuxMaterializationError("FFPROBE_INVALID_OUTPUT") from None
    if not 0 < duration <= _MAX_DURATION_SECONDS:
        raise RemuxMaterializationError("MEDIA_DURATION_OUT_OF_RANGE")
    mapping: dict[int, str] = {}
    type_counts: dict[str, int] = {}
    for stream in streams:
        if not isinstance(stream, Mapping):
            raise RemuxMaterializationError("FFPROBE_INVALID_OUTPUT")
        try:
            index = int(stream["index"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise RemuxMaterializationError("FFPROBE_INVALID_OUTPUT") from None
        codec_type = str(stream.get("codec_type") or "").strip().lower()
        if index < 0 or _CODEC_TYPE_RE.fullmatch(codec_type) is None or index in mapping:
            raise RemuxMaterializationError("FFPROBE_INVALID_OUTPUT")
        mapping[index] = codec_type
        type_counts[codec_type] = type_counts.get(codec_type, 0) + 1
    if not mapping or any(count != 1 for count in type_counts.values()):
        raise RemuxMaterializationError("AMBIGUOUS_CODEC_TYPE_STREAMS")
    return duration, mapping


def _probe_packet_records(
    ffprobe: Path,
    media: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> list[PacketRecord]:
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-show_packets",
        "-show_entries",
        "packet=stream_index,pos,size:packet_side_data=",
        "-of",
        "compact=p=0:nk=0",
        str(media),
    ]
    records: list[PacketRecord] = []
    pass_fds = _descriptor_fds(media)
    try:
        with tempfile.TemporaryFile(mode="w+b") as output:
            result = runner(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=_FFPROBE_TIMEOUT_SECONDS,
                check=False,
                **({"pass_fds": pass_fds} if pass_fds else {}),
            )
            output_size = output.tell()
            if result.returncode != 0 or output_size <= 0:
                raise RemuxMaterializationError("FFPROBE_FAILED")
            if output_size > _MAX_PACKET_PROBE_BYTES:
                raise RemuxMaterializationError("FFPROBE_PACKET_OUTPUT_TOO_LARGE")
            output.seek(0)
            lines = output.readlines()
    except subprocess.TimeoutExpired:
        raise RemuxMaterializationError("FFPROBE_TIMEOUT") from None
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("FFPROBE_FAILED") from None
    for encoded_line in lines:
        try:
            line = encoded_line.decode("utf-8")
        except UnicodeDecodeError:
            raise RemuxMaterializationError("FFPROBE_INVALID_PACKET_OUTPUT") from None
        fields: dict[str, str] = {}
        for item in line.strip().split("|"):
            if not item:
                continue
            key, separator, value = item.partition("=")
            if not separator or key in fields:
                raise RemuxMaterializationError("FFPROBE_INVALID_PACKET_OUTPUT")
            fields[key] = value
        if not {"stream_index", "size", "pos"}.issubset(fields):
            raise RemuxMaterializationError("FFPROBE_INVALID_PACKET_OUTPUT")
        try:
            record = PacketRecord(
                stream_index=int(fields["stream_index"]),
                position=int(fields["pos"]),
                size=int(fields["size"]),
            )
        except (TypeError, ValueError, OverflowError):
            raise RemuxMaterializationError("FFPROBE_INVALID_PACKET_OUTPUT") from None
        if record.stream_index < 0 or record.position < 0 or record.size <= 0:
            raise RemuxMaterializationError("FFPROBE_INVALID_PACKET_OUTPUT")
        records.append(record)
    if not records:
        raise RemuxMaterializationError("FFPROBE_FAILED")
    return records


def _fingerprint_packet_payloads(
    media: Path,
    *,
    stream_types: Mapping[int, str],
    packets: Sequence[PacketRecord],
) -> dict[str, PacketPayloadFingerprint]:
    file_size = media.stat().st_size
    digests: dict[str, Any] = {}
    counts: dict[str, int] = {}
    totals: dict[str, int] = {}
    with media.open("rb") as source:
        for packet in packets:
            codec_type = stream_types.get(packet.stream_index)
            if codec_type is None:
                raise RemuxMaterializationError("PACKET_REFERENCES_UNKNOWN_STREAM")
            if packet.position + packet.size > file_size:
                raise RemuxMaterializationError("PACKET_RANGE_OUT_OF_BOUNDS")
            source.seek(packet.position)
            payload = source.read(packet.size)
            if len(payload) != packet.size:
                raise RemuxMaterializationError("PACKET_READ_FAILED")
            digest = digests.setdefault(codec_type, hashlib.sha256())
            digest.update(packet.size.to_bytes(8, "big", signed=False))
            digest.update(payload)
            counts[codec_type] = counts.get(codec_type, 0) + 1
            totals[codec_type] = totals.get(codec_type, 0) + packet.size
    return {
        codec_type: PacketPayloadFingerprint(
            packet_count=counts[codec_type],
            total_bytes=totals[codec_type],
            payload_sequence_sha256=digest.hexdigest(),
        )
        for codec_type, digest in sorted(digests.items())
    }


async def compare_packet_payloads(source: Path, candidate: Path) -> PacketEquivalenceResult:
    """Compare content identity by codec type and packet payload sequence."""

    ffprobe = _pinned_ffprobe_path()

    def compare() -> PacketEquivalenceResult:
        source_duration, source_streams = _probe_streams_and_duration(ffprobe, source)
        candidate_duration, candidate_streams = _probe_streams_and_duration(ffprobe, candidate)
        source_fingerprints = _fingerprint_packet_payloads(
            source,
            stream_types=source_streams,
            packets=_probe_packet_records(ffprobe, source),
        )
        candidate_fingerprints = _fingerprint_packet_payloads(
            candidate,
            stream_types=candidate_streams,
            packets=_probe_packet_records(ffprobe, candidate),
        )
        if source_fingerprints != candidate_fingerprints:
            raise RemuxMaterializationError("PACKET_PAYLOAD_MISMATCH")
        delta = round(candidate_duration - source_duration, 6)
        if abs(delta) > _DURATION_TOLERANCE_SECONDS:
            raise RemuxMaterializationError("DURATION_MISMATCH")
        return PacketEquivalenceResult(
            source_duration_seconds=round(source_duration, 6),
            candidate_duration_seconds=round(candidate_duration, 6),
            duration_delta_seconds=delta,
            codec_type_fingerprints=source_fingerprints,
        )

    return await _blocking_call(compare)


async def download_bounded_runtime_video(
    runtime_url: str,
    destination: Path,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Download one already authorized URL without redirects or proxy trust."""

    try:
        validated_url = validate_mediakit_runtime_https_url(runtime_url)
    except Exception:
        raise RemuxMaterializationError("UNSAFE_RUNTIME_URL") from None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
    except OSError:
        raise RemuxMaterializationError("CANDIDATE_STAGING_UNAVAILABLE") from None
    try:
        await _download_bounded_runtime_video_to_fd(
            validated_url,
            descriptor,
            transport=transport,
        )
    except BaseException:
        with contextlib.suppress(OSError):
            destination.unlink()
        raise
    finally:
        os.close(descriptor)


async def _download_bounded_runtime_video_to_fd(
    runtime_url: str,
    descriptor: int,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    try:
        validated_url = validate_mediakit_runtime_https_url(runtime_url)
    except Exception:
        raise RemuxMaterializationError("UNSAFE_RUNTIME_URL") from None
    observed = 0
    try:
        os.fchmod(descriptor, 0o600)
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        async with (
            httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(_DOWNLOAD_TIMEOUT_SECONDS, connect=15.0),
                transport=transport,
            ) as client,
            client.stream("GET", validated_url) as response,
        ):
            if 300 <= response.status_code < 400:
                raise RemuxMaterializationError("CANDIDATE_REDIRECT_FORBIDDEN")
            if response.status_code != 200:
                raise RemuxMaterializationError("CANDIDATE_DOWNLOAD_FAILED")
            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    declared_size = int(declared)
                except ValueError:
                    raise RemuxMaterializationError("CANDIDATE_DOWNLOAD_FAILED") from None
                if not 0 < declared_size <= _MAX_ARTIFACT_BYTES:
                    raise RemuxMaterializationError("CANDIDATE_SIZE_OUT_OF_RANGE")
            async for chunk in response.aiter_bytes(1024 * 1024):
                observed += len(chunk)
                if observed > _MAX_ARTIFACT_BYTES:
                    raise RemuxMaterializationError("CANDIDATE_SIZE_OUT_OF_RANGE")
                view = memoryview(chunk)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise RemuxMaterializationError("CANDIDATE_DOWNLOAD_FAILED")
                    view = view[written:]
            if observed <= 0:
                raise RemuxMaterializationError("CANDIDATE_DOWNLOAD_FAILED")
            os.fsync(descriptor)
    except RemuxMaterializationError:
        raise
    except (OSError, httpx.HTTPError):
        raise RemuxMaterializationError("CANDIDATE_DOWNLOAD_FAILED") from None


def _paid_result_bindings(
    paid_result: _PaidRemuxResult,
    *,
    expected_source_sha256: str,
    source_size_bytes: int,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    try:
        runtime_url = paid_result.runtime_url
        ingress = paid_result.remux_receipt.model_dump(mode="json", exclude_none=True)
        paid = paid_result.paid_execution_receipt.model_dump(mode="json", exclude_none=True)
    except (AttributeError, TypeError):
        raise RemuxMaterializationError("INVALID_PAID_REMUX_RESULT") from None
    if not isinstance(runtime_url, str) or not isinstance(ingress, dict) or not isinstance(paid, dict):
        raise RemuxMaterializationError("INVALID_PAID_REMUX_RESULT")
    runtime_url_sha256 = _sha256_text(runtime_url)
    expected_receipt_sha256 = _canonical_sha256(ingress)
    bindings = (
        ingress.get("provider") == "volcengine-mediakit",
        ingress.get("derived_from_source_sha256") == expected_source_sha256,
        ingress.get("source_size_bytes") == source_size_bytes,
        ingress.get("runtime_url_sha256") == runtime_url_sha256,
        paid.get("provider") == "volcengine-mediakit",
        paid.get("capability") == "managed_https_ingress_remux",
        paid.get("source_sha256") == expected_source_sha256,
        paid.get("runtime_url_sha256") == runtime_url_sha256,
        paid.get("remux_receipt_sha256") == expected_receipt_sha256,
        paid.get("client_token_sha256") == ingress.get("client_token_sha256"),
        paid.get("provider_task_id_sha256") == ingress.get("task_id_sha256"),
        paid.get("provider_terminal_status") == "completed",
    )
    if not all(bindings):
        raise RemuxMaterializationError("PAID_REMUX_BINDING_MISMATCH")
    return runtime_url, ingress, paid


def _safe_suffix(source_path: Path) -> str:
    suffix = source_path.suffix.lower().lstrip(".")
    return suffix if _SAFE_SUFFIX_RE.fullmatch(suffix) else "mp4"


def _write_private_json_fd(descriptor: int, payload: Mapping[str, Any]) -> None:
    encoded = _canonical_json_bytes(payload)
    try:
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RemuxMaterializationError("RECEIPT_WRITE_FAILED")
            view = view[written:]
        os.fsync(descriptor)
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("RECEIPT_WRITE_FAILED") from None


def _publish_no_clobber_at(
    *,
    staging_fd: int,
    staged_name: str,
    output_fd: int,
    destination_name: str,
    collision_code: str,
) -> tuple[int, int]:
    try:
        staged_info = os.stat(staged_name, dir_fd=staging_fd, follow_symlinks=False)
    except OSError:
        raise RemuxMaterializationError("INVALID_STAGED_OUTPUT") from None
    if not stat.S_ISREG(staged_info.st_mode) or stat.S_IMODE(staged_info.st_mode) != 0o600 or staged_info.st_nlink != 1:
        raise RemuxMaterializationError("INVALID_STAGED_OUTPUT")
    try:
        os.link(
            staged_name,
            destination_name,
            src_dir_fd=staging_fd,
            dst_dir_fd=output_fd,
            follow_symlinks=False,
        )
    except FileExistsError:
        raise RemuxMaterializationError(collision_code) from None
    except OSError:
        raise RemuxMaterializationError(collision_code) from None
    identity = (staged_info.st_dev, staged_info.st_ino)
    try:
        published_fd = os.open(
            destination_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=output_fd,
        )
        try:
            published = os.fstat(published_fd)
        finally:
            os.close(published_fd)
        if (published.st_dev, published.st_ino) != identity:
            raise RemuxMaterializationError("PUBLISHED_ARTIFACT_IDENTITY_MISMATCH")
        os.unlink(staged_name, dir_fd=staging_fd)
        published = os.stat(destination_name, dir_fd=output_fd, follow_symlinks=False)
        if published.st_nlink != 1 or stat.S_IMODE(published.st_mode) != 0o600:
            raise RemuxMaterializationError("PUBLISHED_ARTIFACT_UNSAFE")
        _fsync_directory_descriptor(output_fd)
        return identity
    except BaseException:
        _unlink_if_owned_at(output_fd, destination_name, identity)
        raise


def _unlink_if_owned_at(
    directory_fd: int,
    name: str,
    identity: tuple[int, int] | None,
) -> None:
    if identity is None:
        return
    with contextlib.suppress(OSError):
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) == identity:
            os.unlink(name, dir_fd=directory_fd)
            _fsync_directory_descriptor(directory_fd)


async def materialize_paid_remux_result(
    *,
    paid_result: _PaidRemuxResult,
    source_path: str | Path,
    expected_source_sha256: str,
    resolved_evidence_root: Path,
    downloader: DownloadRunner = _download_bounded_runtime_video_to_fd,
    packet_comparator: PacketComparator = compare_packet_payloads,
) -> MaterializedRemuxArtifact:
    """Create one immutable private handoff from an existing paid result.

    The caller must supply a server-resolved owner/thread root.  This function
    never submits, retries, or reconciles a provider call.
    """

    source_sha256 = str(expected_source_sha256 or "").strip().lower()
    if _HEX64_RE.fullmatch(source_sha256) is None:
        raise RemuxMaterializationError("INVALID_SOURCE_SHA256")
    root = _resolved_private_root(resolved_evidence_root)
    candidate_identity: tuple[int, int] | None = None
    receipt_identity: tuple[int, int] | None = None
    committed = False
    with _open_private_source(Path(source_path), root=root) as (
        source_fd,
        source_info,
        root_fd,
    ):
        try:
            root_info = os.fstat(root_fd)
            root_identity = (root_info.st_dev, root_info.st_ino)
            initial_source_sha256 = await _blocking_call(_sha256_fd, source_fd)
            if not hmac.compare_digest(initial_source_sha256, source_sha256):
                raise RemuxMaterializationError("SOURCE_HASH_MISMATCH")
            runtime_url, _ingress, _paid = _paid_result_bindings(
                paid_result,
                expected_source_sha256=source_sha256,
                source_size_bytes=source_info.st_size,
            )
            try:
                validated_runtime_url = validate_mediakit_runtime_https_url(runtime_url)
            except Exception:
                raise RemuxMaterializationError("UNSAFE_RUNTIME_URL") from None

            with _private_output_directory_descriptor(
                root_fd,
                "outputs",
                REMUX_MATERIALIZATION_OUTPUT_ROOT,
                source_sha256,
            ) as output:
                staging_name, staging_fd = _create_private_staging_directory(output.descriptor)
                snapshot_fd: int | None = None
                candidate_fd: int | None = None
                receipt_fd: int | None = None
                staged_names = (
                    f"source-snapshot.{_safe_suffix(Path(source_path))}",
                    "candidate.mp4",
                    "receipt.json",
                )
                candidate_name: str | None = None
                receipt_name: str | None = None
                try:
                    snapshot_fd = _create_private_file_at(staging_fd, staged_names[0])
                    candidate_fd = _create_private_file_at(staging_fd, staged_names[1])
                    receipt_fd = _create_private_file_at(staging_fd, staged_names[2])
                    await _blocking_call(_copy_fd_to_fd, source_fd, snapshot_fd)
                    _require_private_regular_fd(
                        snapshot_fd,
                        expected_size=source_info.st_size,
                    )
                    if not hmac.compare_digest(
                        await _blocking_call(_sha256_fd, snapshot_fd),
                        source_sha256,
                    ):
                        raise RemuxMaterializationError("SOURCE_SNAPSHOT_HASH_MISMATCH")
                    try:
                        await downloader(validated_runtime_url, candidate_fd)
                    except asyncio.CancelledError:
                        raise
                    except RemuxMaterializationError:
                        raise
                    except Exception:
                        raise RemuxMaterializationError("CANDIDATE_DOWNLOAD_FAILED") from None
                    candidate_info = _require_private_regular_fd(candidate_fd)
                    candidate_sha256 = await _blocking_call(_sha256_fd, candidate_fd)
                    try:
                        equivalence = await packet_comparator(
                            _descriptor_path(snapshot_fd),
                            _descriptor_path(candidate_fd),
                        )
                    except asyncio.CancelledError:
                        raise
                    except RemuxMaterializationError:
                        raise
                    except Exception:
                        raise RemuxMaterializationError("PACKET_EQUIVALENCE_FAILED") from None
                    if not isinstance(equivalence, PacketEquivalenceResult):
                        raise RemuxMaterializationError("INVALID_PACKET_EQUIVALENCE_RESULT")
                    if not hmac.compare_digest(
                        await _blocking_call(_sha256_fd, source_fd),
                        source_sha256,
                    ):
                        raise RemuxMaterializationError("SOURCE_CHANGED_DURING_MATERIALIZATION")
                    receipt = RemuxMaterializationReceipt.model_validate(
                        {
                            "authority_status": REMUX_MATERIALIZATION_AUTHORITY_STATUS,
                            "promotion_blockers": REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER,
                            "source_sha256": source_sha256,
                            "candidate_sha256": candidate_sha256,
                            "source_size_bytes": source_info.st_size,
                            "candidate_size_bytes": candidate_info.st_size,
                            "source_duration_seconds": equivalence.source_duration_seconds,
                            "candidate_duration_seconds": equivalence.candidate_duration_seconds,
                            "duration_delta_seconds": equivalence.duration_delta_seconds,
                            "equivalence": {
                                "codec_types": equivalence.codec_type_fingerprints,
                            },
                            "coverage": {},
                            "derivation": {
                                "source_sha256": source_sha256,
                                "candidate_sha256": candidate_sha256,
                            },
                        }
                    )
                    receipt_payload = receipt.model_dump(mode="json")
                    receipt_sha256 = _canonical_sha256(receipt_payload)
                    _write_private_json_fd(receipt_fd, receipt_payload)
                    _require_private_regular_fd(receipt_fd)

                    candidate_name = f"{candidate_sha256}.mp4"
                    receipt_name = f"{candidate_sha256}.receipt.json"
                    candidate_identity = _publish_no_clobber_at(
                        staging_fd=staging_fd,
                        staged_name=staged_names[1],
                        output_fd=output.descriptor,
                        destination_name=candidate_name,
                        collision_code="ARTIFACT_OUTPUT_EXISTS",
                    )
                    try:
                        receipt_identity = _publish_no_clobber_at(
                            staging_fd=staging_fd,
                            staged_name=staged_names[2],
                            output_fd=output.descriptor,
                            destination_name=receipt_name,
                            collision_code="RECEIPT_OUTPUT_EXISTS",
                        )
                    except BaseException:
                        _unlink_if_owned_at(
                            output.descriptor,
                            candidate_name,
                            candidate_identity,
                        )
                        candidate_identity = None
                        raise
                    handoff = MaterializedRemuxArtifact.model_validate(
                        {
                            "authority_status": REMUX_MATERIALIZATION_AUTHORITY_STATUS,
                            "promotion_blockers": REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER,
                            "candidate_relative_ref": (output.relative / candidate_name).as_posix(),
                            "receipt_relative_ref": (output.relative / receipt_name).as_posix(),
                            "source_sha256": source_sha256,
                            "candidate_sha256": candidate_sha256,
                            "candidate_size_bytes": candidate_info.st_size,
                            "receipt_sha256": receipt_sha256,
                            "receipt": receipt,
                            "root_device": root_identity[0],
                            "root_inode": root_identity[1],
                        }
                    )
                    _verify_private_directory_binding(
                        root,
                        output.relative,
                        output.descriptor,
                        expected_root_identity=root_identity,
                    )
                    committed = True
                    output.preserve = True
                    return handoff
                finally:
                    if not committed:
                        if receipt_name is not None:
                            _unlink_if_owned_at(
                                output.descriptor,
                                receipt_name,
                                receipt_identity,
                            )
                        if candidate_name is not None:
                            _unlink_if_owned_at(
                                output.descriptor,
                                candidate_name,
                                candidate_identity,
                            )
                    for descriptor in (receipt_fd, candidate_fd, snapshot_fd):
                        if descriptor is not None:
                            with contextlib.suppress(OSError):
                                os.close(descriptor)
                    for staged_name in staged_names:
                        with contextlib.suppress(OSError):
                            os.unlink(staged_name, dir_fd=staging_fd)
                    with contextlib.suppress(OSError):
                        os.close(staging_fd)
                    with contextlib.suppress(OSError):
                        os.rmdir(staging_name, dir_fd=output.descriptor)
                        _fsync_directory_descriptor(output.descriptor)
        except asyncio.CancelledError:
            raise
        except RemuxMaterializationError:
            raise
        except Exception:
            raise RemuxMaterializationError("REMUX_MATERIALIZATION_FAILED") from None


def _open_verified_relative_file_descriptor(
    root_fd: int,
    relative_ref: str,
    *,
    expected_sha256: str,
    expected_size: int | None = None,
) -> int:
    relative = Path(relative_ref)
    if relative.is_absolute() or "\\" in relative_ref or any(part in {"", ".", ".."} for part in relative.parts):
        raise RemuxMaterializationError("HANDOFF_PATH_INVALID")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_descriptors: list[int] = []
    file_descriptor: int | None = None
    opened_successfully = False
    try:
        current = os.dup(root_fd)
        directory_descriptors.append(current)
        for component in relative.parts[:-1]:
            current = os.open(component, directory_flags, dir_fd=current)
            directory_descriptors.append(current)
            directory_info = os.fstat(current)
            if not stat.S_ISDIR(directory_info.st_mode) or stat.S_IMODE(directory_info.st_mode) != 0o700 or (hasattr(os, "geteuid") and directory_info.st_uid != os.geteuid()):
                raise RemuxMaterializationError("HANDOFF_PATH_INVALID")
        path_info = os.stat(relative.parts[-1], dir_fd=current, follow_symlinks=False)
        if stat.S_ISLNK(path_info.st_mode) or not stat.S_ISREG(path_info.st_mode):
            raise RemuxMaterializationError("ARTIFACT_FILE_UNSAFE")
        file_descriptor = os.open(
            relative.parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=current,
        )
        opened_info = os.fstat(file_descriptor)
        if (opened_info.st_dev, opened_info.st_ino) != (path_info.st_dev, path_info.st_ino):
            raise RemuxMaterializationError("HANDOFF_PATH_CHANGED")
        _require_private_regular_fd(file_descriptor, expected_size=expected_size)
        if not hmac.compare_digest(_sha256_fd(file_descriptor), expected_sha256):
            raise RemuxMaterializationError("HANDOFF_HASH_MISMATCH")
        final_info = os.fstat(file_descriptor)
        if final_info.st_size != opened_info.st_size or final_info.st_mtime_ns != opened_info.st_mtime_ns or final_info.st_ctime_ns != opened_info.st_ctime_ns:
            raise RemuxMaterializationError("HANDOFF_FILE_CHANGED")
        opened_successfully = True
        return file_descriptor
    except RemuxMaterializationError:
        raise
    except OSError:
        raise RemuxMaterializationError("HANDOFF_PATH_INVALID") from None
    finally:
        if file_descriptor is not None and not opened_successfully:
            with contextlib.suppress(OSError):
                os.close(file_descriptor)
        for descriptor in reversed(directory_descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)


def _read_bounded_descriptor(file_descriptor: int, *, maximum_bytes: int) -> bytes:
    try:
        info = os.fstat(file_descriptor)
    except OSError:
        raise RemuxMaterializationError("HANDOFF_FILE_UNAVAILABLE") from None
    if not 0 < info.st_size <= maximum_bytes:
        raise RemuxMaterializationError("HANDOFF_RECEIPT_SIZE_OUT_OF_RANGE")
    payload = os.pread(file_descriptor, info.st_size + 1, 0)
    if len(payload) != info.st_size:
        raise RemuxMaterializationError("HANDOFF_FILE_CHANGED")
    return payload


@contextmanager
def verify_materialized_remux_artifact(
    *,
    resolved_evidence_root: Path,
    handoff: MaterializedRemuxArtifact | Mapping[str, Any],
) -> Iterator[VerifiedMaterializedRemuxArtifact]:
    """Hold one verified candidate fd open for the complete consumption window."""

    root = _resolved_private_root(resolved_evidence_root)
    try:
        artifact = MaterializedRemuxArtifact.model_validate(handoff)
    except Exception:
        raise RemuxMaterializationError("HANDOFF_INVALID") from None
    root_fd = _open_handoff_root_descriptor(
        root,
        expected_identity=(artifact.root_device, artifact.root_inode),
    )
    candidate_fd: int | None = None
    receipt_fd: int | None = None
    try:
        candidate_fd = _open_verified_relative_file_descriptor(
            root_fd,
            artifact.candidate_relative_ref,
            expected_sha256=artifact.candidate_sha256,
            expected_size=artifact.candidate_size_bytes,
        )
        _verify_root_directory_binding(
            root,
            root_fd,
            code="HANDOFF_ROOT_BINDING_CHANGED",
        )
        receipt_fd = _open_verified_relative_file_descriptor(
            root_fd,
            artifact.receipt_relative_ref,
            expected_sha256=artifact.receipt_sha256,
        )
        _verify_root_directory_binding(
            root,
            root_fd,
            code="HANDOFF_ROOT_BINDING_CHANGED",
        )
        receipt_bytes = _read_bounded_descriptor(receipt_fd, maximum_bytes=64 * 1024)
        receipt_payload = json.loads(receipt_bytes.decode("utf-8"))
        receipt = RemuxMaterializationReceipt.model_validate(receipt_payload)
    except RemuxMaterializationError:
        if candidate_fd is not None:
            with contextlib.suppress(OSError):
                os.close(candidate_fd)
            candidate_fd = None
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        if candidate_fd is not None:
            with contextlib.suppress(OSError):
                os.close(candidate_fd)
            candidate_fd = None
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise RemuxMaterializationError("HANDOFF_RECEIPT_INVALID") from None
    finally:
        if receipt_fd is not None:
            with contextlib.suppress(OSError):
                os.close(receipt_fd)
    if receipt != artifact.receipt:
        if candidate_fd is not None:
            with contextlib.suppress(OSError):
                os.close(candidate_fd)
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise RemuxMaterializationError("HANDOFF_RECEIPT_MISMATCH")
    if candidate_fd is None:
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise RemuxMaterializationError("HANDOFF_FILE_UNAVAILABLE")
    try:
        before = os.fstat(candidate_fd)
        _verify_root_directory_binding(
            root,
            root_fd,
            code="HANDOFF_ROOT_BINDING_CHANGED",
        )
    except OSError:
        with contextlib.suppress(OSError):
            os.close(candidate_fd)
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise RemuxMaterializationError("HANDOFF_CLOSED_DURING_CONSUMPTION") from None
    except RemuxMaterializationError:
        with contextlib.suppress(OSError):
            os.close(candidate_fd)
        with contextlib.suppress(OSError):
            os.close(root_fd)
        raise
    try:
        yield VerifiedMaterializedRemuxArtifact(
            candidate_file_descriptor=candidate_fd,
            candidate_size_bytes=artifact.candidate_size_bytes,
            receipt=receipt,
        )
    finally:
        post_error: RemuxMaterializationError | None = None
        try:
            after = os.fstat(candidate_fd)
            if (
                (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
                or after.st_nlink != 1
                or after.st_size != before.st_size
                or after.st_mtime_ns != before.st_mtime_ns
                or after.st_ctime_ns != before.st_ctime_ns
                or not hmac.compare_digest(_sha256_fd(candidate_fd), artifact.candidate_sha256)
            ):
                post_error = RemuxMaterializationError("HANDOFF_CHANGED_DURING_CONSUMPTION")
        except OSError:
            post_error = RemuxMaterializationError("HANDOFF_CLOSED_DURING_CONSUMPTION")
        try:
            _verify_root_directory_binding(
                root,
                root_fd,
                code="HANDOFF_ROOT_BINDING_CHANGED",
            )
        except RemuxMaterializationError as exc:
            if post_error is None:
                post_error = exc
        finally:
            with contextlib.suppress(OSError):
                os.close(candidate_fd)
            with contextlib.suppress(OSError):
                os.close(root_fd)
        if post_error is not None:
            raise post_error


# The operator canary imports these mechanical primitives instead of carrying
# a second implementation.  Their leading-underscore implementations remain
# module-private so product callers use the complete materialization boundary.
pinned_ffprobe_path = _pinned_ffprobe_path
run_ffprobe_json = _run_ffprobe_json
probe_streams_and_duration = _probe_streams_and_duration
probe_packet_records = _probe_packet_records
fingerprint_packet_payloads = _fingerprint_packet_payloads


__all__ = [
    "MaterializedRemuxArtifact",
    "PacketEquivalenceResult",
    "PacketPayloadFingerprint",
    "PacketRecord",
    "REMUX_MATERIALIZATION_AUTHORITY_STATUS",
    "REMUX_MATERIALIZATION_HANDOFF_VERSION",
    "REMUX_MATERIALIZATION_OUTPUT_ROOT",
    "REMUX_MATERIALIZATION_PROMOTION_BLOCKER_ORDER",
    "REMUX_MATERIALIZATION_PROMOTION_BLOCKERS",
    "REMUX_MATERIALIZATION_RECEIPT_VERSION",
    "RemuxMaterializationError",
    "RemuxMaterializationReceipt",
    "VerifiedMaterializedRemuxArtifact",
    "compare_packet_payloads",
    "download_bounded_runtime_video",
    "fingerprint_packet_payloads",
    "materialize_paid_remux_result",
    "pinned_ffprobe_path",
    "probe_packet_records",
    "probe_streams_and_duration",
    "run_ffprobe_json",
    "verify_materialized_remux_artifact",
]
