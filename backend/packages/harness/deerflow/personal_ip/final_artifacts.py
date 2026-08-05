"""Owner-scoped filesystem boundary for immutable final video artifacts.

The persistence layer stores only a path relative to the current Owner's
DeerFlow user root.  This module is the sole translator between that private
``storage_key`` and a local file.  It deliberately does not import Gateway or
persistence implementations; callers inject the video-production repository.
"""

from __future__ import annotations

import asyncio
import errno
import hashlib
import mimetypes
import os
import stat
import uuid
from collections.abc import AsyncIterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol
from urllib.parse import urlsplit

from deerflow.config.paths import Paths, get_paths, make_safe_user_id

_MAX_STORAGE_KEY_LENGTH = 1_024
_READ_CHUNK_SIZE = 1024 * 1024
_QUARANTINE_DIRECTORY = ".artifact-quarantine"


class FinalArtifactRepository(Protocol):
    """Repository surface needed to atomically finish linked delivery."""

    async def complete_delivery_and_seal_artifact(
        self,
        production_id: str,
        *,
        owner_user_id: str,
        event_key: str,
        qa_event_key: str,
        source_execution_event_keys: Sequence[str],
        source_ref: str,
        storage_key: str,
        sha256: str,
        size_bytes: int,
        mime_type: str,
        metadata: dict[str, Any],
        provider: str,
        model: str | None = None,
        provider_task_id: str | None = None,
        cost: dict[str, Any],
        occurred_at: Any = None,
    ) -> dict[str, Any] | None: ...

    async def mark_artifact_content_available(
        self,
        artifact_id: str,
        *,
        owner_user_id: str,
        expected_sha256: str,
        expected_size_bytes: int,
        expected_mime_type: str,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class VerifiedFinalArtifact:
    """Server-derived identity for one ordinary file below an Owner root."""

    path: Path
    storage_key: str
    sha256: str
    size_bytes: int
    mime_type: str


@dataclass(slots=True)
class OpenedFinalArtifact:
    """A verified file descriptor kept open to avoid a path-swap race."""

    artifact: VerifiedFinalArtifact
    descriptor: int

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1


@dataclass(frozen=True, slots=True)
class QuarantinedFinalArtifact:
    """One exact verified Artifact moved out of its public storage key."""

    artifact_id: str | None
    storage_key: str
    quarantine_key: str
    content_sha256: str
    size_bytes: int
    mime_type: str
    device: int
    inode: int


@dataclass(slots=True)
class PreparedFinalArtifactDeletion:
    """Opaque two-phase deletion token owned by one Owner lifecycle call."""

    owner_user_id: str
    owner_root: Path
    operation_id: str | None
    entries: tuple[QuarantinedFinalArtifact, ...]
    missing_count: int
    state: str = "prepared"


class FinalArtifactContentError(ValueError):
    """Base class for safe reattachment failures."""


class FinalArtifactContentConflict(FinalArtifactContentError):
    """The immutable destination is linked or already contains other bytes."""


class FinalArtifactContentTooLarge(FinalArtifactContentError):
    """The streamed body exceeds the immutable Artifact size."""


@dataclass(slots=True)
class _PendingFinalArtifactContent:
    artifact_id: str
    owner_user_id: str
    owner_root: Path
    storage_key: str
    content_sha256: str
    size_bytes: int
    mime_type: str
    parent_descriptor: int | None
    parent_path: Path
    final_name: str
    temporary_name: str | None
    temporary_descriptor: int
    existing_descriptor: int
    installed_by_request: bool = False

    def close_descriptors(self) -> None:
        for field in (
            "temporary_descriptor",
            "existing_descriptor",
            "parent_descriptor",
        ):
            descriptor = getattr(self, field)
            if descriptor is not None and descriptor >= 0:
                os.close(descriptor)
                setattr(self, field, -1)


def _normalize_owner_storage_key(
    storage_key: str,
    *,
    require_final_namespace: bool,
) -> str:
    if not isinstance(storage_key, str):
        raise ValueError("final artifact storage key must be a string")
    key = storage_key.strip()
    if not key or len(key) > _MAX_STORAGE_KEY_LENGTH:
        raise ValueError("final artifact storage key is empty or too long")
    if key != storage_key or any(ord(char) < 32 or ord(char) == 127 for char in key):
        raise ValueError("final artifact storage key must be canonical text")
    if "\\" in key:
        raise ValueError("final artifact storage key must use POSIX separators")
    parsed = urlsplit(key)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or key.startswith("//"):
        raise ValueError("final artifact storage key must not be a URL")
    if PurePosixPath(key).is_absolute() or PureWindowsPath(key).is_absolute() or PureWindowsPath(key).drive:
        raise ValueError("final artifact storage key must be relative")
    raw_parts = key.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("final artifact storage key contains an unsafe path segment")
    normalized = PurePosixPath(*raw_parts).as_posix()
    if normalized != key:
        raise ValueError("final artifact storage key must be canonical")
    if require_final_namespace and (len(raw_parts) < 2 or raw_parts[0] != "video-deliveries"):
        raise ValueError("final artifact storage key must be inside video-deliveries/")
    return normalized


def normalize_storage_key(storage_key: str) -> str:
    """Validate one formal Artifact key in the ``video-deliveries/`` namespace."""

    return _normalize_owner_storage_key(
        storage_key,
        require_final_namespace=True,
    )


def _owner_root(owner_user_id: str, *, paths: Paths | None = None) -> Path:
    owner = str(owner_user_id or "").strip()
    if not owner:
        raise ValueError("owner_user_id is required")
    configured_paths = paths or get_paths()
    return configured_paths.user_dir(make_safe_user_id(owner))


def storage_key_for_owner_file(
    owner_user_id: str,
    local_path: str | Path,
    *,
    paths: Paths | None = None,
    require_final_namespace: bool = True,
) -> str:
    """Convert an internal absolute file path into an Owner-relative key.

    The path is handled lexically here; symlink and file-type checks happen
    when the key is opened by :func:`open_verified_final_artifact`.
    """

    raw_path = os.fspath(local_path)
    windows_absolute = PureWindowsPath(raw_path).is_absolute()
    parsed_path = urlsplit(raw_path)
    if not raw_path or (parsed_path.scheme and not windows_absolute) or parsed_path.netloc:
        raise ValueError("final artifact local path must be an absolute filesystem path, not a URL")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise ValueError("final artifact local path must be absolute")
    root = _owner_root(owner_user_id, paths=paths)
    candidate_absolute = Path(os.path.abspath(candidate))
    root_absolute = Path(os.path.abspath(root))
    try:
        relative = candidate_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise ValueError("final artifact must be stored below the current Owner user root") from exc
    return _normalize_owner_storage_key(
        relative.as_posix(),
        require_final_namespace=require_final_namespace,
    )


def _open_without_symlinks(
    root: Path,
    storage_key: str,
    *,
    require_final_namespace: bool,
    missing_ok: bool = False,
) -> int | None:
    """Open a regular file below ``root`` without following key symlinks."""

    key = _normalize_owner_storage_key(
        storage_key,
        require_final_namespace=require_final_namespace,
    )
    try:
        root_metadata = root.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        raise ValueError("final artifact Owner root is unavailable") from None
    except OSError as exc:
        raise ValueError("final artifact Owner root is unavailable") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError("final artifact Owner root must be an ordinary directory")

    parts = key.split("/")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    nonblock = getattr(os, "O_NONBLOCK", 0)
    supports_openat = os.open in getattr(os, "supports_dir_fd", set())

    if supports_openat and directory:
        current_fd = -1
        try:
            current_fd = os.open(root, os.O_RDONLY | directory | nofollow)
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | directory | nofollow, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
            descriptor = os.open(parts[-1], os.O_RDONLY | nonblock | nofollow, dir_fd=current_fd)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise ValueError("final artifact path is missing, linked, or inaccessible") from None
        except OSError as exc:
            raise ValueError("final artifact path is missing, linked, or inaccessible") from exc
        finally:
            if current_fd >= 0:
                os.close(current_fd)
    else:
        # Windows lacks portable openat/O_NOFOLLOW support.  Walk with lstat,
        # open once, and validate the resulting descriptor and resolved path.
        candidate = root.joinpath(*parts)
        current = root
        try:
            for part in parts:
                current = current / part
                metadata = current.lstat()
                if stat.S_ISLNK(metadata.st_mode):
                    raise ValueError("final artifact path must not contain symlinks")
            resolved_root = root.resolve(strict=True)
            resolved_candidate = candidate.resolve(strict=True)
            resolved_candidate.relative_to(resolved_root)
            descriptor = os.open(candidate, os.O_RDONLY | nonblock)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise ValueError("final artifact path is missing, linked, outside the Owner root, or inaccessible") from None
        except (OSError, ValueError) as exc:
            raise ValueError("final artifact path is missing, linked, outside the Owner root, or inaccessible") from exc

    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise ValueError("final artifact must be an ordinary file")
    return descriptor


def _verified_opened_descriptor(
    *,
    root: Path,
    key: str,
    descriptor: int,
    expected_sha256: Any,
    expected_size_bytes: Any,
    expected_mime_type: Any,
    require_video: bool,
) -> OpenedFinalArtifact:
    try:
        digest, size = _hash_descriptor(descriptor)
        recorded_digest = _expected_sha256(expected_sha256)
        recorded_size = _expected_size(expected_size_bytes)
        mime_type = mimetypes.guess_type(PurePosixPath(key).name)[0] or "application/octet-stream"
        recorded_mime = str(expected_mime_type or "").strip().lower() or None
        if size <= 0:
            raise ValueError("final artifact must not be empty")
        if require_video and not mime_type.lower().startswith("video/"):
            raise ValueError("final artifact MIME type must be video/*")
        if recorded_digest is not None and digest != recorded_digest:
            raise ValueError("final artifact SHA-256 does not match its immutable record")
        if recorded_size is not None and size != recorded_size:
            raise ValueError("final artifact size does not match its immutable record")
        if recorded_mime is not None and mime_type.lower() != recorded_mime:
            raise ValueError("final artifact MIME type does not match its immutable record")
        return OpenedFinalArtifact(
            artifact=VerifiedFinalArtifact(
                path=root.joinpath(*key.split("/")),
                storage_key=key,
                sha256=digest,
                size_bytes=size,
                mime_type=mime_type,
            ),
            descriptor=descriptor,
        )
    except Exception:
        os.close(descriptor)
        raise


def _hash_descriptor(descriptor: int) -> tuple[str, int]:
    before = os.fstat(descriptor)
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, _READ_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    after = os.fstat(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        getattr(before, "st_mtime_ns", None),
        getattr(before, "st_ctime_ns", None),
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        getattr(after, "st_mtime_ns", None),
        getattr(after, "st_ctime_ns", None),
    )
    if identity_before != identity_after or total != after.st_size:
        raise ValueError("final artifact changed while it was being verified")
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest(), total


def _expected_sha256(value: Any) -> str | None:
    if value is None:
        return None
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("final artifact recorded SHA-256 is invalid")
    return digest


def _expected_size(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("final artifact recorded size is invalid")
    return value


def open_verified_final_artifact(
    owner_user_id: str,
    storage_key: str,
    *,
    expected_sha256: Any = None,
    expected_size_bytes: Any = None,
    expected_mime_type: Any = None,
    paths: Paths | None = None,
    require_video: bool = True,
    require_final_namespace: bool = True,
) -> OpenedFinalArtifact:
    """Open and re-hash a stored Artifact, retaining its verified descriptor."""

    key = _normalize_owner_storage_key(
        storage_key,
        require_final_namespace=require_final_namespace,
    )
    root = _owner_root(owner_user_id, paths=paths)
    descriptor = _open_without_symlinks(
        root,
        key,
        require_final_namespace=require_final_namespace,
    )
    if descriptor is None:  # pragma: no cover - missing_ok is false above
        raise ValueError("final artifact path is missing")
    return _verified_opened_descriptor(
        root=root,
        key=key,
        descriptor=descriptor,
        expected_sha256=expected_sha256,
        expected_size_bytes=expected_size_bytes,
        expected_mime_type=expected_mime_type,
        require_video=require_video,
    )


def verify_final_artifact(
    owner_user_id: str,
    storage_key: str,
    *,
    expected_sha256: Any = None,
    expected_size_bytes: Any = None,
    expected_mime_type: Any = None,
    paths: Paths | None = None,
    require_video: bool = True,
    require_final_namespace: bool = True,
) -> VerifiedFinalArtifact:
    """Open, re-hash and close one Owner-scoped final artifact."""

    opened = open_verified_final_artifact(
        owner_user_id,
        storage_key,
        expected_sha256=expected_sha256,
        expected_size_bytes=expected_size_bytes,
        expected_mime_type=expected_mime_type,
        paths=paths,
        require_video=require_video,
        require_final_namespace=require_final_namespace,
    )
    try:
        return opened.artifact
    finally:
        opened.close()


def verify_final_artifact_record(
    owner_user_id: str,
    record: Mapping[str, Any],
    *,
    paths: Paths | None = None,
    keep_open: bool = False,
) -> VerifiedFinalArtifact | OpenedFinalArtifact:
    """Verify the private storage fields returned by ``repo.get_artifact``."""

    storage_key = record.get("storage_key")
    if not isinstance(storage_key, str):
        raise ValueError("final artifact storage key is unavailable")
    opened = open_verified_final_artifact(
        owner_user_id,
        storage_key,
        expected_sha256=record.get("content_sha256", record.get("sha256")),
        expected_size_bytes=record.get("size_bytes"),
        expected_mime_type=record.get("mime_type"),
        paths=paths,
        require_video=True,
    )
    if keep_open:
        return opened
    try:
        return opened.artifact
    finally:
        opened.close()


async def seal_final_artifact(
    repository: FinalArtifactRepository,
    production_id: str,
    *,
    owner_user_id: str,
    event_key: str,
    qa_event_key: str,
    source_execution_event_keys: Sequence[str],
    source_ref: str,
    local_path: str | Path,
    expected_sha256: Any,
    expected_size_bytes: Any,
    expected_mime_type: Any,
    metadata: dict[str, Any],
    provider: str,
    model: str | None = None,
    provider_task_id: str | None = None,
    cost: dict[str, Any],
    occurred_at: Any = None,
    paths: Paths | None = None,
) -> dict[str, Any] | None:
    """Verify a local final file off-loop and atomically seal its DB record."""

    storage_key = storage_key_for_owner_file(
        owner_user_id,
        local_path,
        paths=paths,
    )
    opened = await asyncio.to_thread(
        open_verified_final_artifact,
        owner_user_id,
        storage_key,
        expected_sha256=expected_sha256,
        expected_size_bytes=expected_size_bytes,
        expected_mime_type=expected_mime_type,
        paths=paths,
        require_video=True,
    )
    try:
        result = await repository.complete_delivery_and_seal_artifact(
            production_id,
            owner_user_id=owner_user_id,
            event_key=event_key,
            qa_event_key=qa_event_key,
            source_execution_event_keys=list(source_execution_event_keys),
            source_ref=source_ref,
            storage_key=opened.artifact.storage_key,
            sha256=opened.artifact.sha256,
            size_bytes=opened.artifact.size_bytes,
            mime_type=opened.artifact.mime_type,
            metadata=metadata,
            provider=provider,
            model=model,
            provider_task_id=provider_task_id,
            cost=cost,
            occurred_at=occurred_at,
        )
        if result is None:
            await asyncio.to_thread(
                _unlink_opened_key,
                _owner_root(owner_user_id, paths=paths),
                opened,
                require_final_namespace=True,
            )
            return None
        await asyncio.to_thread(
            _reverify_opened_final_artifact_name,
            _owner_root(owner_user_id, paths=paths),
            opened,
        )
        return result
    finally:
        await asyncio.to_thread(opened.close)


def _reverify_opened_final_artifact_name(
    root: Path,
    opened: OpenedFinalArtifact,
) -> None:
    descriptor = _open_without_symlinks(
        root,
        opened.artifact.storage_key,
        require_final_namespace=True,
        missing_ok=False,
    )
    if descriptor is None:  # pragma: no cover - missing_ok is false above
        raise ValueError("final artifact path is missing after repository commit")
    verified = _verified_opened_descriptor(
        root=root,
        key=opened.artifact.storage_key,
        descriptor=descriptor,
        expected_sha256=opened.artifact.sha256,
        expected_size_bytes=opened.artifact.size_bytes,
        expected_mime_type=opened.artifact.mime_type,
        require_video=True,
    )
    try:
        original = os.fstat(opened.descriptor)
        current = os.fstat(verified.descriptor)
        if not _same_inode(
            current,
            device=original.st_dev,
            inode=original.st_ino,
        ):
            raise ValueError("final artifact pathname changed after repository commit")
    finally:
        verified.close()


def remove_unsealed_final_artifact(
    owner_user_id: str,
    local_path: str | Path,
    *,
    expected_sha256: Any,
    expected_size_bytes: Any,
    expected_mime_type: Any,
    paths: Paths | None = None,
) -> bool:
    """Unlink one exact, unrecorded render without following path links."""

    storage_key = storage_key_for_owner_file(
        owner_user_id,
        local_path,
        paths=paths,
    )
    root = _owner_root(owner_user_id, paths=paths)
    descriptor = _open_without_symlinks(
        root,
        storage_key,
        require_final_namespace=True,
        missing_ok=True,
    )
    if descriptor is None:
        return False
    opened = _verified_opened_descriptor(
        root=root,
        key=storage_key,
        descriptor=descriptor,
        expected_sha256=expected_sha256,
        expected_size_bytes=expected_size_bytes,
        expected_mime_type=expected_mime_type,
        require_video=True,
    )
    try:
        _unlink_opened_key(
            root,
            opened,
            require_final_namespace=True,
        )
        return True
    finally:
        opened.close()


def _supports_secure_dir_fd_operations() -> bool:
    supported = getattr(os, "supports_dir_fd", set())
    return bool(getattr(os, "O_DIRECTORY", 0)) and all(
        operation in supported
        for operation in (
            os.link,
            os.mkdir,
            os.open,
            os.rename,
            os.rmdir,
            os.stat,
            os.unlink,
        )
    )


def _open_directory_fd(root: Path, relative_parts: Sequence[str]) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(root, os.O_RDONLY | directory | nofollow)
    try:
        for part in relative_parts:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | directory | nofollow,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _ensure_final_parent_directory(
    root: Path,
    storage_key: str,
) -> tuple[int | None, Path, str]:
    key = normalize_storage_key(storage_key)
    parts = key.split("/")
    final_name = parts[-1]
    parent_parts = parts[:-1]
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise FinalArtifactContentConflict("final artifact Owner root is unavailable") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise FinalArtifactContentConflict("final artifact Owner root must be an ordinary directory")

    parent_path = root.joinpath(*parent_parts)
    if _supports_secure_dir_fd_operations():
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory = getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(root, os.O_RDONLY | directory | nofollow)
        try:
            for part in parent_parts:
                try:
                    next_descriptor = os.open(
                        part,
                        os.O_RDONLY | directory | nofollow,
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                    next_descriptor = os.open(
                        part,
                        os.O_RDONLY | directory | nofollow,
                        dir_fd=descriptor,
                    )
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor, parent_path, final_name
        except OSError as exc:
            os.close(descriptor)
            raise FinalArtifactContentConflict("final artifact storage directory is linked or inaccessible") from exc

    current = root
    try:
        for part in parent_parts:
            current = current / part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise FinalArtifactContentConflict("final artifact storage directory must not contain symlinks")
    except OSError as exc:
        raise FinalArtifactContentConflict("final artifact storage directory is linked or inaccessible") from exc
    return None, parent_path, final_name


def _required_reattach_identity(
    artifact_id: str,
    record: Mapping[str, Any],
    *,
    content_type: str,
    content_length: int | None,
) -> tuple[str, str, int, str]:
    """Validate a restored receipt before creating or opening any content."""

    if not isinstance(record, Mapping):
        raise FinalArtifactContentError("final artifact receipt is unavailable")
    record_id = record.get("id")
    if not isinstance(record_id, str) or record_id != artifact_id:
        raise FinalArtifactContentError("final artifact receipt identity is invalid")
    if record.get("content_available") is not False:
        raise FinalArtifactContentConflict("final artifact content is not awaiting reattachment")

    try:
        storage_key = normalize_storage_key(record.get("storage_key"))
        content_sha256 = _expected_sha256(record.get("content_sha256", record.get("sha256")))
        size_bytes = _expected_size(record.get("size_bytes"))
    except ValueError as exc:
        raise FinalArtifactContentError(str(exc)) from exc
    if content_sha256 is None or record.get("content_sha256", record.get("sha256")) != content_sha256:
        raise FinalArtifactContentError("final artifact receipt must contain a canonical SHA-256")
    if size_bytes is None:
        raise FinalArtifactContentError("final artifact receipt must contain a positive size")

    mime_type = record.get("mime_type")
    if not isinstance(mime_type, str) or mime_type != mime_type.strip().lower() or not mime_type.startswith("video/") or len(mime_type) > 255 or any(character.isspace() for character in mime_type):
        raise FinalArtifactContentError("final artifact receipt must contain a canonical video MIME type")
    inferred_mime = (mimetypes.guess_type(PurePosixPath(storage_key).name)[0] or "application/octet-stream").lower()
    if inferred_mime != mime_type:
        raise FinalArtifactContentError("final artifact MIME type does not match its storage key")
    if content_type != mime_type:
        raise FinalArtifactContentError("uploaded Content-Type does not match the immutable Artifact")
    if content_length is not None:
        if isinstance(content_length, bool) or content_length < 0:
            raise FinalArtifactContentError("uploaded Content-Length is invalid")
        if content_length > size_bytes:
            raise FinalArtifactContentTooLarge("uploaded content exceeds the immutable Artifact size")
        if content_length < size_bytes:
            raise FinalArtifactContentError("uploaded Content-Length does not match the immutable Artifact")
    return storage_key, content_sha256, size_bytes, mime_type


def _create_pending_final_artifact_content(
    artifact_id: str,
    *,
    owner_user_id: str,
    record: Mapping[str, Any],
    content_type: str,
    content_length: int | None,
    paths: Paths | None,
) -> _PendingFinalArtifactContent:
    storage_key, content_sha256, size_bytes, mime_type = _required_reattach_identity(
        artifact_id,
        record,
        content_type=content_type,
        content_length=content_length,
    )
    root = _owner_root(owner_user_id, paths=paths)
    parent_descriptor, parent_path, final_name = _ensure_final_parent_directory(
        root,
        storage_key,
    )
    pending = _PendingFinalArtifactContent(
        artifact_id=artifact_id,
        owner_user_id=str(owner_user_id),
        owner_root=root,
        storage_key=storage_key,
        content_sha256=content_sha256,
        size_bytes=size_bytes,
        mime_type=mime_type,
        parent_descriptor=parent_descriptor,
        parent_path=parent_path,
        final_name=final_name,
        temporary_name=None,
        temporary_descriptor=-1,
        existing_descriptor=-1,
    )
    try:
        try:
            descriptor = _open_without_symlinks(
                root,
                storage_key,
                require_final_namespace=True,
                missing_ok=True,
            )
        except ValueError as exc:
            raise FinalArtifactContentConflict("final artifact destination is linked or inaccessible") from exc
        if descriptor is not None:
            try:
                opened = _verified_opened_descriptor(
                    root=root,
                    key=storage_key,
                    descriptor=descriptor,
                    expected_sha256=content_sha256,
                    expected_size_bytes=size_bytes,
                    expected_mime_type=mime_type,
                    require_video=True,
                )
            except ValueError as exc:
                raise FinalArtifactContentConflict("final artifact destination already contains different content") from exc
            pending.existing_descriptor = opened.descriptor
            opened.descriptor = -1
            return pending

        nofollow = getattr(os, "O_NOFOLLOW", 0)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow
        for _attempt in range(10):
            temporary_name = f".artifact-upload-{uuid.uuid4().hex}.tmp"
            try:
                if parent_descriptor is not None:
                    descriptor = os.open(
                        temporary_name,
                        flags,
                        0o600,
                        dir_fd=parent_descriptor,
                    )
                else:
                    descriptor = os.open(
                        parent_path / temporary_name,
                        flags,
                        0o600,
                    )
            except FileExistsError:
                continue
            except OSError as exc:
                raise FinalArtifactContentConflict("final artifact temporary storage is inaccessible") from exc
            pending.temporary_name = temporary_name
            pending.temporary_descriptor = descriptor
            return pending
        raise FinalArtifactContentConflict("could not allocate final artifact temporary storage")
    except Exception:
        pending.close_descriptors()
        raise


def _write_all(descriptor: int, chunk: bytes) -> None:
    view = memoryview(chunk)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count <= 0:
            raise OSError("could not write final artifact content")
        written += count


def _append_reattach_chunk(
    pending: _PendingFinalArtifactContent,
    digest: Any,
    chunk: bytes,
) -> None:
    digest.update(chunk)
    if pending.temporary_descriptor >= 0:
        _write_all(pending.temporary_descriptor, chunk)


def _open_and_verify_pending_destination(
    pending: _PendingFinalArtifactContent,
) -> int:
    try:
        descriptor = _open_without_symlinks(
            pending.owner_root,
            pending.storage_key,
            require_final_namespace=True,
            missing_ok=False,
        )
    except ValueError as exc:
        raise FinalArtifactContentConflict("final artifact destination is linked or inaccessible") from exc
    if descriptor is None:  # pragma: no cover - missing_ok is false above
        raise FinalArtifactContentConflict("final artifact destination is missing")
    try:
        opened = _verified_opened_descriptor(
            root=pending.owner_root,
            key=pending.storage_key,
            descriptor=descriptor,
            expected_sha256=pending.content_sha256,
            expected_size_bytes=pending.size_bytes,
            expected_mime_type=pending.mime_type,
            require_video=True,
        )
    except ValueError as exc:
        raise FinalArtifactContentConflict("final artifact destination already contains different content") from exc
    descriptor = opened.descriptor
    opened.descriptor = -1
    return descriptor


def _unlink_pending_name(
    pending: _PendingFinalArtifactContent,
    *,
    name: str,
    descriptor: int,
) -> None:
    """Unlink only when the name still identifies the held regular inode."""

    held = os.fstat(descriptor)
    try:
        if pending.parent_descriptor is not None:
            named = os.stat(
                name,
                dir_fd=pending.parent_descriptor,
                follow_symlinks=False,
            )
        else:
            named = (pending.parent_path / name).lstat()
    except FileNotFoundError:
        return
    if not _same_inode(named, device=held.st_dev, inode=held.st_ino):
        raise FinalArtifactContentConflict("final artifact cleanup target changed after verification")
    if pending.parent_descriptor is not None:
        os.unlink(name, dir_fd=pending.parent_descriptor)
    else:
        (pending.parent_path / name).unlink()


def _finish_pending_final_artifact_content(
    pending: _PendingFinalArtifactContent,
) -> None:
    if pending.existing_descriptor >= 0:
        digest, size = _hash_descriptor(pending.existing_descriptor)
        if digest != pending.content_sha256 or size != pending.size_bytes:
            raise FinalArtifactContentConflict("final artifact destination changed during reattachment")
        return

    descriptor = pending.temporary_descriptor
    temporary_name = pending.temporary_name
    if descriptor < 0 or temporary_name is None:
        raise FinalArtifactContentError("final artifact temporary content is unavailable")
    os.fsync(descriptor)
    digest, size = _hash_descriptor(descriptor)
    if digest != pending.content_sha256 or size != pending.size_bytes:
        raise FinalArtifactContentError("uploaded bytes do not match the immutable Artifact")

    try:
        if pending.parent_descriptor is not None:
            os.link(
                temporary_name,
                pending.final_name,
                src_dir_fd=pending.parent_descriptor,
                dst_dir_fd=pending.parent_descriptor,
                follow_symlinks=False,
            )
        else:
            os.link(
                pending.parent_path / temporary_name,
                pending.parent_path / pending.final_name,
                follow_symlinks=False,
            )
    except FileExistsError:
        existing_descriptor = _open_and_verify_pending_destination(pending)
        _unlink_pending_name(
            pending,
            name=temporary_name,
            descriptor=descriptor,
        )
        os.close(descriptor)
        pending.temporary_descriptor = -1
        pending.temporary_name = None
        pending.existing_descriptor = existing_descriptor
        return
    except OSError as exc:
        raise FinalArtifactContentConflict("final artifact content could not be installed") from exc

    try:
        if pending.parent_descriptor is not None:
            installed = os.stat(
                pending.final_name,
                dir_fd=pending.parent_descriptor,
                follow_symlinks=False,
            )
        else:
            installed = (pending.parent_path / pending.final_name).lstat()
        temporary = os.fstat(descriptor)
        if not _same_inode(
            installed,
            device=temporary.st_dev,
            inode=temporary.st_ino,
        ):
            raise FinalArtifactContentConflict("installed final artifact identity does not match its upload")
        _unlink_pending_name(
            pending,
            name=temporary_name,
            descriptor=descriptor,
        )
        pending.temporary_name = None
        pending.installed_by_request = True
        if pending.parent_descriptor is not None:
            os.fsync(pending.parent_descriptor)
    except Exception:
        try:
            _unlink_pending_name(
                pending,
                name=pending.final_name,
                descriptor=descriptor,
            )
        finally:
            raise


def _reverify_pending_final_artifact_name(
    pending: _PendingFinalArtifactContent,
) -> None:
    """Require the installed name to remain exact after the DB commit."""

    descriptor = _open_and_verify_pending_destination(pending)
    try:
        if pending.installed_by_request and pending.temporary_descriptor >= 0:
            installed = os.fstat(descriptor)
            held = os.fstat(pending.temporary_descriptor)
            if not _same_inode(
                installed,
                device=held.st_dev,
                inode=held.st_ino,
            ):
                raise FinalArtifactContentConflict("final artifact destination changed after availability commit")
    finally:
        os.close(descriptor)


def _cleanup_pending_final_artifact_content(
    pending: _PendingFinalArtifactContent,
    *,
    remove_installed: bool,
) -> None:
    cleanup_error: Exception | None = None
    try:
        if pending.temporary_name is not None and pending.temporary_descriptor >= 0:
            _unlink_pending_name(
                pending,
                name=pending.temporary_name,
                descriptor=pending.temporary_descriptor,
            )
            pending.temporary_name = None
        if remove_installed and pending.installed_by_request and pending.temporary_descriptor >= 0:
            _unlink_pending_name(
                pending,
                name=pending.final_name,
                descriptor=pending.temporary_descriptor,
            )
            pending.installed_by_request = False
    except Exception as exc:
        cleanup_error = exc
    finally:
        pending.close_descriptors()
    if cleanup_error is not None:
        raise cleanup_error


async def reattach_final_artifact_content(
    repository: FinalArtifactRepository,
    artifact_id: str,
    *,
    owner_user_id: str,
    artifact: Mapping[str, Any],
    chunks: AsyncIterable[bytes],
    content_type: str,
    content_length: int | None = None,
    paths: Paths | None = None,
) -> dict[str, Any] | None:
    """Stream, verify and install restored bytes before enabling playback."""

    pending = await asyncio.to_thread(
        _create_pending_final_artifact_content,
        artifact_id,
        owner_user_id=owner_user_id,
        record=artifact,
        content_type=content_type,
        content_length=content_length,
        paths=paths,
    )
    try:
        digest = hashlib.sha256()
        total = 0
        async for raw_chunk in chunks:
            if not isinstance(raw_chunk, bytes):
                raise FinalArtifactContentError("uploaded final artifact body must contain bytes")
            if not raw_chunk:
                continue
            total += len(raw_chunk)
            if total > pending.size_bytes:
                raise FinalArtifactContentTooLarge("uploaded content exceeds the immutable Artifact size")
            await asyncio.to_thread(
                _append_reattach_chunk,
                pending,
                digest,
                raw_chunk,
            )
        if total != pending.size_bytes:
            raise FinalArtifactContentError("uploaded content size does not match the immutable Artifact")
        if digest.hexdigest() != pending.content_sha256:
            raise FinalArtifactContentError("uploaded content SHA-256 does not match the immutable Artifact")
        await asyncio.to_thread(_finish_pending_final_artifact_content, pending)
    except BaseException:
        await asyncio.shield(
            asyncio.to_thread(
                _cleanup_pending_final_artifact_content,
                pending,
                remove_installed=True,
            )
        )
        raise

    try:
        result = await repository.mark_artifact_content_available(
            artifact_id,
            owner_user_id=owner_user_id,
            expected_sha256=pending.content_sha256,
            expected_size_bytes=pending.size_bytes,
            expected_mime_type=pending.mime_type,
        )
    except BaseException:
        # A repository exception is not proof that its transaction lost.  Keep
        # the exact, verified bytes so a concurrent successful reattachment
        # cannot lose its pathname and so an unavailable receipt can retry.
        await asyncio.shield(
            asyncio.to_thread(
                _cleanup_pending_final_artifact_content,
                pending,
                remove_installed=False,
            )
        )
        raise

    if result is None:
        await asyncio.shield(
            asyncio.to_thread(
                _cleanup_pending_final_artifact_content,
                pending,
                remove_installed=True,
            )
        )
        return None
    try:
        await asyncio.to_thread(_reverify_pending_final_artifact_name, pending)
    except BaseException:
        await asyncio.shield(
            asyncio.to_thread(
                _cleanup_pending_final_artifact_content,
                pending,
                remove_installed=False,
            )
        )
        raise
    await asyncio.shield(
        asyncio.to_thread(
            _cleanup_pending_final_artifact_content,
            pending,
            remove_installed=False,
        )
    )
    return result


def _ensure_quarantine_operation(root: Path) -> str:
    """Create one private, empty Owner quarantine directory."""

    if _supports_secure_dir_fd_operations():
        root_fd = _open_directory_fd(root, [])
        quarantine_fd = -1
        try:
            try:
                os.mkdir(_QUARANTINE_DIRECTORY, mode=0o700, dir_fd=root_fd)
            except FileExistsError:
                pass
            quarantine_fd = os.open(
                _QUARANTINE_DIRECTORY,
                os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_fd,
            )
            for _attempt in range(10):
                operation_id = uuid.uuid4().hex
                try:
                    os.mkdir(operation_id, mode=0o700, dir_fd=quarantine_fd)
                except FileExistsError:
                    continue
                return operation_id
            raise RuntimeError("could not allocate a final artifact quarantine")
        except OSError as exc:
            raise ValueError("final artifact quarantine is linked or inaccessible") from exc
        finally:
            if quarantine_fd >= 0:
                os.close(quarantine_fd)
            os.close(root_fd)

    try:
        root_metadata = root.lstat()
        if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
            raise ValueError("final artifact Owner root must be an ordinary directory")
        quarantine_root = root / _QUARANTINE_DIRECTORY
        try:
            quarantine_root.mkdir(mode=0o700)
        except FileExistsError:
            metadata = quarantine_root.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("final artifact quarantine must be an ordinary directory")
        for _attempt in range(10):
            operation_id = uuid.uuid4().hex
            try:
                (quarantine_root / operation_id).mkdir(mode=0o700)
            except FileExistsError:
                continue
            return operation_id
    except OSError as exc:
        raise ValueError("final artifact quarantine is linked or inaccessible") from exc
    raise RuntimeError("could not allocate a final artifact quarantine")


def _quarantine_key(operation_id: str, index: int, storage_key: str) -> str:
    suffix = PurePosixPath(storage_key).suffix
    return _normalize_owner_storage_key(
        f"{_QUARANTINE_DIRECTORY}/{operation_id}/{index:08d}{suffix}",
        require_final_namespace=False,
    )


def _same_inode(metadata: os.stat_result, *, device: int, inode: int) -> bool:
    return stat.S_ISREG(metadata.st_mode) and (
        metadata.st_dev,
        metadata.st_ino,
    ) == (device, inode)


def _rename_opened_to_quarantine(
    root: Path,
    opened: OpenedFinalArtifact,
    quarantine_key: str,
) -> tuple[int, int]:
    source_parts = opened.artifact.storage_key.split("/")
    quarantine_parts = _normalize_owner_storage_key(
        quarantine_key,
        require_final_namespace=False,
    ).split("/")
    opened_metadata = os.fstat(opened.descriptor)
    device, inode = opened_metadata.st_dev, opened_metadata.st_ino

    if _supports_secure_dir_fd_operations():
        source_parent_fd = _open_directory_fd(root, source_parts[:-1])
        quarantine_parent_fd = _open_directory_fd(root, quarantine_parts[:-1])
        try:
            source_metadata = os.stat(
                source_parts[-1],
                dir_fd=source_parent_fd,
                follow_symlinks=False,
            )
            if not _same_inode(source_metadata, device=device, inode=inode):
                raise ValueError("final artifact changed after deletion verification")
            try:
                os.stat(
                    quarantine_parts[-1],
                    dir_fd=quarantine_parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise ValueError("final artifact quarantine destination already exists")
            os.rename(
                source_parts[-1],
                quarantine_parts[-1],
                src_dir_fd=source_parent_fd,
                dst_dir_fd=quarantine_parent_fd,
            )
            quarantined_metadata = os.stat(
                quarantine_parts[-1],
                dir_fd=quarantine_parent_fd,
                follow_symlinks=False,
            )
            if not _same_inode(quarantined_metadata, device=device, inode=inode):
                raise ValueError("final artifact quarantine identity mismatch")
            return device, inode
        finally:
            os.close(source_parent_fd)
            os.close(quarantine_parent_fd)

    source = root.joinpath(*source_parts)
    destination = root.joinpath(*quarantine_parts)
    metadata = source.lstat()
    if not _same_inode(metadata, device=device, inode=inode):
        raise ValueError("final artifact changed after deletion verification")
    if destination.exists() or destination.is_symlink():
        raise ValueError("final artifact quarantine destination already exists")
    source.rename(destination)
    quarantined_metadata = destination.lstat()
    if not _same_inode(quarantined_metadata, device=device, inode=inode):
        raise ValueError("final artifact quarantine identity mismatch")
    return device, inode


def _open_expected_entry(
    root: Path,
    entry: QuarantinedFinalArtifact,
    *,
    quarantine: bool,
    missing_ok: bool,
) -> OpenedFinalArtifact | None:
    key = entry.quarantine_key if quarantine else entry.storage_key
    descriptor = _open_without_symlinks(
        root,
        key,
        require_final_namespace=not quarantine,
        missing_ok=missing_ok,
    )
    if descriptor is None:
        return None
    opened = _verified_opened_descriptor(
        root=root,
        key=key,
        descriptor=descriptor,
        expected_sha256=entry.content_sha256,
        expected_size_bytes=entry.size_bytes,
        expected_mime_type=entry.mime_type,
        require_video=True,
    )
    metadata = os.fstat(opened.descriptor)
    if not _same_inode(metadata, device=entry.device, inode=entry.inode):
        opened.close()
        raise ValueError("quarantined final artifact inode does not match its prepared deletion")
    return opened


def _unlink_opened_key(
    root: Path,
    opened: OpenedFinalArtifact,
    *,
    require_final_namespace: bool,
) -> None:
    key = _normalize_owner_storage_key(
        opened.artifact.storage_key,
        require_final_namespace=require_final_namespace,
    )
    parts = key.split("/")
    opened_metadata = os.fstat(opened.descriptor)
    if _supports_secure_dir_fd_operations():
        parent_fd = _open_directory_fd(root, parts[:-1])
        try:
            named_metadata = os.stat(
                parts[-1],
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if not _same_inode(
                named_metadata,
                device=opened_metadata.st_dev,
                inode=opened_metadata.st_ino,
            ):
                raise ValueError("final artifact deletion target changed after verification")
            os.unlink(parts[-1], dir_fd=parent_fd)
            return
        finally:
            os.close(parent_fd)
    target = root.joinpath(*parts)
    named_metadata = target.lstat()
    if not _same_inode(
        named_metadata,
        device=opened_metadata.st_dev,
        inode=opened_metadata.st_ino,
    ):
        raise ValueError("final artifact deletion target changed after verification")
    target.unlink()


def _restore_opened_quarantine(
    root: Path,
    entry: QuarantinedFinalArtifact,
    opened: OpenedFinalArtifact,
) -> None:
    source_parts = entry.quarantine_key.split("/")
    destination_parts = entry.storage_key.split("/")
    opened_metadata = os.fstat(opened.descriptor)
    if not _same_inode(
        opened_metadata,
        device=entry.device,
        inode=entry.inode,
    ):
        raise ValueError("quarantined final artifact changed before rollback")
    if _supports_secure_dir_fd_operations():
        source_parent_fd = _open_directory_fd(root, source_parts[:-1])
        destination_parent_fd = _open_directory_fd(root, destination_parts[:-1])
        try:
            source_metadata = os.stat(
                source_parts[-1],
                dir_fd=source_parent_fd,
                follow_symlinks=False,
            )
            if not _same_inode(source_metadata, device=entry.device, inode=entry.inode):
                raise ValueError("quarantined final artifact changed before rollback")
            os.link(
                source_parts[-1],
                destination_parts[-1],
                src_dir_fd=source_parent_fd,
                dst_dir_fd=destination_parent_fd,
                follow_symlinks=False,
            )
            restored_metadata = os.stat(
                destination_parts[-1],
                dir_fd=destination_parent_fd,
                follow_symlinks=False,
            )
            if not _same_inode(restored_metadata, device=entry.device, inode=entry.inode):
                raise ValueError("restored final artifact identity mismatch")
            os.unlink(source_parts[-1], dir_fd=source_parent_fd)
            return
        finally:
            os.close(source_parent_fd)
            os.close(destination_parent_fd)

    source = root.joinpath(*source_parts)
    destination = root.joinpath(*destination_parts)
    os.link(source, destination, follow_symlinks=False)
    restored_metadata = destination.lstat()
    if not _same_inode(restored_metadata, device=entry.device, inode=entry.inode):
        raise ValueError("restored final artifact identity mismatch")
    source.unlink()


def _cleanup_quarantine_operation(root: Path, operation_id: str | None) -> None:
    if operation_id is None:
        return
    if _supports_secure_dir_fd_operations():
        root_fd = _open_directory_fd(root, [])
        quarantine_fd = -1
        try:
            try:
                quarantine_fd = os.open(
                    _QUARANTINE_DIRECTORY,
                    os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=root_fd,
                )
            except FileNotFoundError:
                return
            try:
                os.rmdir(operation_id, dir_fd=quarantine_fd)
            except FileNotFoundError:
                pass
            try:
                os.rmdir(_QUARANTINE_DIRECTORY, dir_fd=root_fd)
            except OSError as exc:
                if exc.errno not in {errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST}:
                    raise
            return
        finally:
            if quarantine_fd >= 0:
                os.close(quarantine_fd)
            os.close(root_fd)
    operation = root / _QUARANTINE_DIRECTORY / operation_id
    try:
        operation.rmdir()
    except FileNotFoundError:
        pass
    quarantine_root = root / _QUARANTINE_DIRECTORY
    try:
        quarantine_root.rmdir()
    except OSError as exc:
        if exc.errno not in {errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST}:
            raise


def prepare_owner_final_artifact_deletion(
    owner_user_id: str,
    artifact_records: Sequence[Mapping[str, Any]],
    *,
    paths: Paths | None = None,
) -> PreparedFinalArtifactDeletion:
    """Verify every formal Artifact, then atomically move each to quarantine."""

    if isinstance(artifact_records, (str, bytes)):
        raise ValueError("final artifact deletion requires full Artifact records")
    root = _owner_root(owner_user_id, paths=paths)
    verified: list[tuple[Mapping[str, Any], OpenedFinalArtifact]] = []
    seen_keys: set[str] = set()
    missing_count = 0
    try:
        for record in artifact_records:
            if not isinstance(record, Mapping):
                raise ValueError("final artifact deletion requires full Artifact records")
            storage_key = normalize_storage_key(record.get("storage_key"))
            if storage_key in seen_keys:
                raise ValueError("final artifact deletion contains a duplicate storage key")
            seen_keys.add(storage_key)
            descriptor = _open_without_symlinks(
                root,
                storage_key,
                require_final_namespace=True,
                missing_ok=True,
            )
            if descriptor is None:
                missing_count += 1
                continue
            opened = _verified_opened_descriptor(
                root=root,
                key=storage_key,
                descriptor=descriptor,
                expected_sha256=record.get("content_sha256", record.get("sha256")),
                expected_size_bytes=record.get("size_bytes"),
                expected_mime_type=record.get("mime_type"),
                require_video=True,
            )
            verified.append((record, opened))
    except Exception:
        for _record, opened in verified:
            opened.close()
        raise

    if not verified:
        return PreparedFinalArtifactDeletion(
            owner_user_id=str(owner_user_id),
            owner_root=root,
            operation_id=None,
            entries=(),
            missing_count=missing_count,
        )

    operation_id = _ensure_quarantine_operation(root)
    entries: list[QuarantinedFinalArtifact] = []
    try:
        for index, (record, opened) in enumerate(verified):
            quarantine_key = _quarantine_key(
                operation_id,
                index,
                opened.artifact.storage_key,
            )
            device, inode = _rename_opened_to_quarantine(
                root,
                opened,
                quarantine_key,
            )
            entries.append(
                QuarantinedFinalArtifact(
                    artifact_id=(str(record.get("id")) if record.get("id") is not None else None),
                    storage_key=opened.artifact.storage_key,
                    quarantine_key=quarantine_key,
                    content_sha256=opened.artifact.sha256,
                    size_bytes=opened.artifact.size_bytes,
                    mime_type=opened.artifact.mime_type,
                    device=device,
                    inode=inode,
                )
            )
    except Exception:
        for entry in reversed(entries):
            quarantined = _open_expected_entry(
                root,
                entry,
                quarantine=True,
                missing_ok=False,
            )
            assert quarantined is not None
            try:
                _restore_opened_quarantine(root, entry, quarantined)
            finally:
                quarantined.close()
        _cleanup_quarantine_operation(root, operation_id)
        raise
    finally:
        for _record, opened in verified:
            opened.close()

    return PreparedFinalArtifactDeletion(
        owner_user_id=str(owner_user_id),
        owner_root=root,
        operation_id=operation_id,
        entries=tuple(entries),
        missing_count=missing_count,
    )


def commit_owner_final_artifact_deletion(
    prepared: PreparedFinalArtifactDeletion,
) -> int:
    """Purge a prepared quarantine after the database transaction commits."""

    if prepared.state == "committed":
        return len(prepared.entries)
    if prepared.state != "prepared":
        raise ValueError("final artifact deletion is not pending commit")
    opened_entries: list[OpenedFinalArtifact] = []
    try:
        for entry in prepared.entries:
            opened = _open_expected_entry(
                prepared.owner_root,
                entry,
                quarantine=True,
                missing_ok=True,
            )
            if opened is not None:
                opened_entries.append(opened)
        for opened in opened_entries:
            _unlink_opened_key(
                prepared.owner_root,
                opened,
                require_final_namespace=False,
            )
    finally:
        for opened in opened_entries:
            opened.close()
    _cleanup_quarantine_operation(prepared.owner_root, prepared.operation_id)
    prepared.state = "committed"
    return len(prepared.entries)


def rollback_owner_final_artifact_deletion(
    prepared: PreparedFinalArtifactDeletion,
) -> int:
    """Restore an exact prepared quarantine after a database rollback."""

    if prepared.state == "rolled_back":
        return len(prepared.entries)
    if prepared.state != "prepared":
        raise ValueError("final artifact deletion is not pending rollback")
    actions: list[tuple[str, QuarantinedFinalArtifact, OpenedFinalArtifact | None]] = []
    opened_handles: list[OpenedFinalArtifact] = []
    try:
        for entry in prepared.entries:
            quarantined = _open_expected_entry(
                prepared.owner_root,
                entry,
                quarantine=True,
                missing_ok=True,
            )
            original = _open_expected_entry(
                prepared.owner_root,
                entry,
                quarantine=False,
                missing_ok=True,
            )
            if quarantined is None:
                if original is None:
                    raise ValueError("prepared final artifact is missing from quarantine and original storage")
                opened_handles.append(original)
                actions.append(("already_restored", entry, None))
                continue
            opened_handles.append(quarantined)
            if original is None:
                actions.append(("restore", entry, quarantined))
                continue
            opened_handles.append(original)
            if os.fstat(original.descriptor).st_ino != os.fstat(quarantined.descriptor).st_ino:
                raise ValueError("rollback destination already contains another file")
            actions.append(("unlink_quarantine", entry, quarantined))

        for action, entry, quarantined in actions:
            if action == "restore":
                assert quarantined is not None
                _restore_opened_quarantine(
                    prepared.owner_root,
                    entry,
                    quarantined,
                )
            elif action == "unlink_quarantine":
                assert quarantined is not None
                _unlink_opened_key(
                    prepared.owner_root,
                    quarantined,
                    require_final_namespace=False,
                )
    finally:
        for opened in opened_handles:
            opened.close()
    _cleanup_quarantine_operation(prepared.owner_root, prepared.operation_id)
    prepared.state = "rolled_back"
    return len(prepared.entries)


def delete_owner_final_artifacts(
    owner_user_id: str,
    artifact_records: Sequence[Mapping[str, Any]],
    *,
    paths: Paths | None = None,
) -> int:
    """Convenience helper for verified prepare+purge outside a DB transaction."""

    prepared = prepare_owner_final_artifact_deletion(
        owner_user_id,
        artifact_records,
        paths=paths,
    )
    return commit_owner_final_artifact_deletion(prepared)


def public_artifact_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive public projection with no filesystem locator."""

    def without_private_locators(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: without_private_locators(item) for key, item in value.items() if key not in {"storage_key", "source_ref", "path", "local_path"}}
        if isinstance(value, list):
            return [without_private_locators(item) for item in value]
        return value

    result = {
        key: without_private_locators(value)
        for key, value in record.items()
        if key
        not in {
            "storage_key",
            "source_ref",
            "path",
            "local_path",
            "ref",
            "sha256",
        }
    }
    if "content_sha256" not in result and record.get("sha256") is not None:
        result["content_sha256"] = record["sha256"]
    return result


__all__ = [
    "FinalArtifactContentConflict",
    "FinalArtifactContentError",
    "FinalArtifactContentTooLarge",
    "FinalArtifactRepository",
    "OpenedFinalArtifact",
    "PreparedFinalArtifactDeletion",
    "QuarantinedFinalArtifact",
    "VerifiedFinalArtifact",
    "commit_owner_final_artifact_deletion",
    "delete_owner_final_artifacts",
    "normalize_storage_key",
    "open_verified_final_artifact",
    "prepare_owner_final_artifact_deletion",
    "public_artifact_metadata",
    "reattach_final_artifact_content",
    "remove_unsealed_final_artifact",
    "rollback_owner_final_artifact_deletion",
    "seal_final_artifact",
    "storage_key_for_owner_file",
    "verify_final_artifact",
    "verify_final_artifact_record",
]
