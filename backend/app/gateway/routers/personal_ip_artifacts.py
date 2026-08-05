"""Owner-scoped metadata and byte-range delivery for final IP artifacts."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.gateway.deps import get_current_user_from_request, get_personal_ip_video_production_repo
from deerflow.config.paths import get_paths
from deerflow.personal_ip.final_artifacts import (
    FinalArtifactContentConflict,
    FinalArtifactContentError,
    FinalArtifactContentTooLarge,
    OpenedFinalArtifact,
    public_artifact_metadata,
    reattach_final_artifact_content,
    verify_final_artifact_record,
)

router = APIRouter(prefix="/api/personal-ip/artifacts", tags=["personal-ip"])

_STREAM_CHUNK_SIZE = 1024 * 1024
_SAFE_EXTENSION_RE = re.compile(r"^\.[A-Za-z0-9]{1,16}$")


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _content_range(range_header: str | None, size: int) -> tuple[int, int, int]:
    """Return ``(status, start, end)`` for one RFC 7233 byte range."""

    if not range_header:
        return 200, 0, max(0, size - 1)
    value = range_header.strip()
    if not value.lower().startswith("bytes="):
        raise ValueError("unsupported Range unit")
    specification = value[6:].strip()
    if not specification or "," in specification or "-" not in specification or size <= 0:
        raise ValueError("invalid or unsatisfiable byte Range")
    start_text, end_text = (part.strip() for part in specification.split("-", 1))
    if not start_text:
        if not end_text.isdigit():
            raise ValueError("invalid suffix byte Range")
        suffix_length = int(end_text)
        if suffix_length <= 0:
            raise ValueError("invalid suffix byte Range")
        start = max(0, size - suffix_length)
        return 206, start, size - 1
    if not start_text.isdigit() or (end_text and not end_text.isdigit()):
        raise ValueError("invalid byte Range")
    start = int(start_text)
    if start >= size:
        raise ValueError("unsatisfiable byte Range")
    end = size - 1 if not end_text else min(int(end_text), size - 1)
    if end < start:
        raise ValueError("unsatisfiable byte Range")
    return 206, start, end


async def _stream_descriptor(
    opened: OpenedFinalArtifact,
    *,
    start: int,
    length: int,
) -> AsyncIterator[bytes]:
    remaining = length
    try:
        await asyncio.to_thread(os.lseek, opened.descriptor, start, os.SEEK_SET)
        while remaining > 0:
            chunk = await asyncio.to_thread(
                os.read,
                opened.descriptor,
                min(_STREAM_CHUNK_SIZE, remaining),
            )
            if not chunk:
                raise RuntimeError("final artifact changed during content delivery")
            remaining -= len(chunk)
            yield chunk
    finally:
        await asyncio.to_thread(opened.close)


def _download_name(artifact_id: str, storage_key: str) -> str:
    suffix = PurePosixPath(storage_key).suffix
    if not _SAFE_EXTENSION_RE.fullmatch(suffix):
        suffix = ""
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "-", artifact_id)[:160] or "artifact"
    return f"{safe_id}{suffix}"


def _request_content_length(request: Request) -> int | None:
    value = request.headers.get("content-length")
    if value is None:
        return None
    if not value.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Final Artifact Content-Length is invalid",
        )
    return int(value)


@router.get("/{artifact_id}")
async def get_personal_ip_final_artifact_metadata(
    artifact_id: str,
    request: Request,
) -> dict[str, Any]:
    """Return the customer-safe immutable metadata for one Owner artifact."""

    try:
        artifact = await get_personal_ip_video_production_repo(request).get_artifact(
            artifact_id,
            owner_user_id=await _current_user_id(request),
        )
    except ValueError:
        artifact = None
    if artifact is None:
        raise HTTPException(status_code=404, detail="Personal-IP artifact not found")
    return public_artifact_metadata(artifact)


@router.get("/{artifact_id}/content")
async def get_personal_ip_final_artifact_content(
    artifact_id: str,
    request: Request,
) -> StreamingResponse:
    """Re-verify and stream one immutable artifact, including single ranges."""

    owner_user_id = await _current_user_id(request)
    try:
        artifact = await get_personal_ip_video_production_repo(request).get_artifact(
            artifact_id,
            owner_user_id=owner_user_id,
            include_storage_key=True,
        )
    except ValueError:
        artifact = None
    if artifact is None:
        raise HTTPException(status_code=404, detail="Personal-IP artifact not found")
    if artifact.get("content_available") is not True:
        raise HTTPException(
            status_code=404,
            detail="Personal-IP artifact content not found",
        )
    try:
        verified = await asyncio.to_thread(
            verify_final_artifact_record,
            owner_user_id,
            artifact,
            paths=get_paths(),
            keep_open=True,
        )
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="Personal-IP artifact content not found") from None
    if not isinstance(verified, OpenedFinalArtifact):
        raise HTTPException(status_code=500, detail="Personal-IP artifact verification failed")

    size = verified.artifact.size_bytes
    try:
        status_code, start, end = _content_range(request.headers.get("range"), size)
    except ValueError:
        verified.close()
        raise HTTPException(
            status_code=416,
            detail="Requested byte Range is not satisfiable",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes */{size}",
            },
        ) from None

    length = 0 if size == 0 else end - start + 1
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": f'inline; filename="{_download_name(artifact_id, verified.artifact.storage_key)}"',
        "Content-Length": str(length),
        "ETag": f'"{verified.artifact.sha256}"',
        "X-Content-Type-Options": "nosniff",
    }
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _stream_descriptor(verified, start=start, length=length),
        status_code=status_code,
        media_type=verified.artifact.mime_type,
        headers=headers,
    )


@router.put("/{artifact_id}/content")
async def put_personal_ip_final_artifact_content(
    artifact_id: str,
    request: Request,
) -> dict[str, Any]:
    """Reattach exact restored bytes without changing Artifact identity."""

    owner_user_id = await _current_user_id(request)
    repository = get_personal_ip_video_production_repo(request)
    try:
        artifact = await repository.get_artifact(
            artifact_id,
            owner_user_id=owner_user_id,
            include_storage_key=True,
        )
    except ValueError:
        artifact = None
    if artifact is None:
        raise HTTPException(status_code=404, detail="Personal-IP artifact not found")

    try:
        result = await reattach_final_artifact_content(
            repository,
            artifact_id,
            owner_user_id=owner_user_id,
            artifact=artifact,
            chunks=request.stream(),
            content_type=request.headers.get("content-type", ""),
            content_length=_request_content_length(request),
            paths=get_paths(),
        )
    except FinalArtifactContentTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from None
    except FinalArtifactContentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except FinalArtifactContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    if result is None:
        raise HTTPException(status_code=404, detail="Personal-IP artifact not found")
    return public_artifact_metadata(result)


__all__ = ["router"]
