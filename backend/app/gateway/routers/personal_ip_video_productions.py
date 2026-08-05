"""Auditable Personal-IP video production orchestration endpoints."""

from __future__ import annotations

import asyncio
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, unquote, urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.gateway.deps import get_current_user_from_request, get_personal_ip_video_production_repo
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths, make_safe_user_id
from deerflow.personal_ip.video_acceptance import artifact_for_path
from deerflow.personal_ip.video_contracts import (
    compile_final_edit_lock,
    compile_timeline_revision,
    resolve_video_production_mode,
)
from deerflow.personal_ip.video_workbench import build_video_workbench_read_model

router = APIRouter(prefix="/api/personal-ip/video-productions", tags=["personal-ip"])

VOLCENGINE_ARK_DEFAULT_HOST = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_IMAGE_MODEL = "doubao-seedream-5-0-260128"
DEFAULT_VIDEO_MODEL = "doubao-seedance-2-0-260128"
KNOWN_IMAGE_MODELS = (
    "doubao-seedream-5-0-pro-260628",
    "doubao-seedream-5-0-260128",
    "doubao-seedream-4-5-251128",
    "doubao-seedream-4-0-250828",
    "doubao-seedream-3-0-t2i-250415",
)
KNOWN_VIDEO_MODELS = (
    "doubao-seedance-2-0-260128",
    "doubao-seedance-2-0-fast-260128",
    "doubao-seedance-2-0-mini-260615",
    "doubao-seedance-1-5-pro-251215",
    "doubao-seedance-1-0-pro-250528",
    "doubao-seedance-1-0-pro-fast-251015",
    "doubao-seedance-1-0-lite-i2v-250428",
    "doubao-seedance-1-0-lite-t2v-250428",
)
MEDIA_MODEL_NAMES = {
    "doubao-seedream-5-0-pro-260628": "Seedream 5.0 Pro",
    "doubao-seedream-5-0-260128": "Seedream 5.0",
    "doubao-seedream-4-5-251128": "Seedream 4.5",
    "doubao-seedream-4-0-250828": "Seedream 4.0",
    "doubao-seedream-3-0-t2i-250415": "Seedream 3.0（文生图）",
    "doubao-seedance-2-0-260128": "Seedance 2.0",
    "doubao-seedance-2-0-fast-260128": "Seedance 2.0 Fast",
    "doubao-seedance-2-0-mini-260615": "Seedance 2.0 Mini",
    "doubao-seedance-1-5-pro-251215": "Seedance 1.5 Pro",
    "doubao-seedance-1-0-pro-250528": "Seedance 1.0 Pro",
    "doubao-seedance-1-0-pro-fast-251015": "Seedance 1.0 Pro Fast",
    "doubao-seedance-1-0-lite-i2v-250428": "Seedance 1.0 Lite（图生视频）",
    "doubao-seedance-1-0-lite-t2v-250428": "Seedance 1.0 Lite（文生视频）",
}

VideoEventType = Literal[
    "video_plan_compiled",
    "blueprint_sealed",
    "asset_registered",
    "asset_manifest_compiled",
    "material_inspection_compiled",
    "material_selection_compiled",
    "asset_generation_requested",
    "asset_generation_completed",
    "asset_generation_failed",
    "storyboard_sealed",
    "storyboard_compiled",
    "continuity_compiled",
    "generated_shot_qa_compiled",
    "shot_generation_requested",
    "shot_generation_completed",
    "shot_generation_failed",
    "consistency_checked",
    "candidate_selected",
    "review_requested",
    "review_recorded",
    "voice_generated",
    "narration_contract_compiled",
    "narration_timing_compiled",
    "voice_generation_requested",
    "media_processing_requested",
    "media_processing_completed",
    "media_processing_failed",
    "edit_completed",
    "assembly_admitted",
    "timeline_revision_compiled",
    "final_edit_locked",
    "delivery_qa_completed",
    "delivery_completed",
]


class PersonalIPVideoProductionBeginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_key: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=256)
    subject_id: str | None = Field(default=None, max_length=64)
    content_work_id: str | None = Field(default=None, min_length=1, max_length=64)
    script_version_id: str | None = Field(default=None, min_length=1, max_length=64)
    target_account_ids: list[str] = Field(default_factory=list, max_length=200)
    production_mode: Literal["faceless_material", "generative_cinematic"]
    source_kind: Literal["idea", "script"]
    source: dict[str, Any] = Field(default_factory=dict)
    delivery_spec: dict[str, Any]
    provider_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)

    @field_validator("operation_key", "title")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("content_work_id", "script_version_id")
    @classmethod
    def strip_link_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("linked content ids cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_linked_script_source(self):
        linked = self.content_work_id is not None or self.script_version_id is not None
        if (self.content_work_id is None) != (self.script_version_id is None):
            raise ValueError("content_work_id and script_version_id must be provided together")
        if linked and self.source_kind != "script":
            raise ValueError("linked ScriptVersion production requires source_kind=script")
        if linked and self.source:
            raise ValueError("linked ScriptVersion production source is server-derived and must be empty")
        return self


class PersonalIPVideoProductionEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(min_length=1, max_length=256)
    event_type: VideoEventType
    status: Literal["planned", "running", "succeeded", "failed", "awaiting_review", "approved", "rejected"]
    entity_type: Literal["production", "character", "scene", "prop", "shot", "candidate", "audio", "timeline", "delivery", "asset"]
    entity_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    input_refs: list[str] = Field(default_factory=list, max_length=500)
    output_refs: list[str] = Field(default_factory=list, max_length=500)
    provider: str = Field(default="deerflow", min_length=1, max_length=80)
    model: str | None = Field(default=None, max_length=160)
    provider_task_id: str | None = Field(default=None, max_length=256)
    cost: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None

    @field_validator("event_key", "entity_id", "provider")
    @classmethod
    def strip_event_text(cls, value: str) -> str:
        return value.strip()


class PersonalIPVideoProductionThreadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(min_length=1, max_length=64)

    @field_validator("thread_id")
    @classmethod
    def strip_thread_id(cls, value: str) -> str:
        return value.strip()


class PersonalIPVideoTimelineRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(min_length=1, max_length=256)
    revision_id: str = Field(min_length=1, max_length=128)
    base_revision_id: str | None = Field(default=None, max_length=128)
    author_kind: Literal["human", "agent"]
    intent: str = Field(min_length=1, max_length=8_000)
    fps: int = Field(ge=1, le=120)
    tracks: list[dict[str, Any]] = Field(min_length=1, max_length=32)
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=500)
    strategy_confirmed: bool = True

    @field_validator("event_key", "revision_id", "intent")
    @classmethod
    def strip_revision_text(cls, value: str) -> str:
        return value.strip()


class PersonalIPVideoFinalEditLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_key: str = Field(min_length=1, max_length=256)
    lock_id: str = Field(min_length=1, max_length=128)
    locked_by: Literal["human", "agent"]
    note: str = Field(min_length=1, max_length=8_000)

    @field_validator("event_key", "lock_id", "note")
    @classmethod
    def strip_lock_text(cls, value: str) -> str:
        return value.strip()


async def _current_user_id(request: Request) -> str:
    user = await get_current_user_from_request(request)
    return str(user.id)


def _repository_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "already records" in detail or "terminal" in detail:
        return HTTPException(status_code=409, detail=detail)
    if "not found" in detail:
        return HTTPException(status_code=404, detail=detail)
    return HTTPException(status_code=422, detail=detail)


def _ordered_media_models(
    discovered: list[str],
    *,
    known: tuple[str, ...],
    default_model: str,
) -> list[dict[str, Any]]:
    discovered_set = set(discovered)
    ordered = [model_id for model_id in known if model_id in discovered_set]
    ordered.extend(sorted(model_id for model_id in discovered_set if model_id not in set(ordered)))
    return [
        {
            "id": model_id,
            "display_name": MEDIA_MODEL_NAMES.get(
                model_id,
                model_id.removeprefix("doubao-").rsplit("-", 1)[0],
            ),
            "is_default": model_id == default_model,
        }
        for model_id in ordered
    ]


async def _volcengine_media_model_catalog() -> dict[str, Any]:
    default_image_model = os.getenv("VOLCENGINE_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    default_video_model = os.getenv("VOLCENGINE_VIDEO_MODEL", DEFAULT_VIDEO_MODEL)
    image_models = list(KNOWN_IMAGE_MODELS)
    video_models = list(KNOWN_VIDEO_MODELS)
    source = "fallback"
    api_key = os.getenv("VOLCENGINE_API_KEY", "").strip()
    if api_key:
        host = os.getenv(
            "VOLCENGINE_ARK_BASE_URL",
            VOLCENGINE_ARK_DEFAULT_HOST,
        ).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{host}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                response.raise_for_status()
            payload = response.json()
            discovered = [str(item.get("id") or item.get("model") or "").strip() for item in payload.get("data", []) if isinstance(item, dict)]
            discovered_images = [model_id for model_id in discovered if "seedream" in model_id]
            discovered_videos = [model_id for model_id in discovered if "seedance" in model_id]
            if discovered_images:
                image_models = discovered_images
            if discovered_videos:
                video_models = discovered_videos
            source = "live"
        except (httpx.HTTPError, ValueError, TypeError):
            pass
    if default_image_model not in image_models:
        image_models.insert(0, default_image_model)
    if default_video_model not in video_models:
        video_models.insert(0, default_video_model)
    return {
        "source": source,
        "default_image_model": default_image_model,
        "default_video_model": default_video_model,
        "image_models": _ordered_media_models(
            image_models,
            known=KNOWN_IMAGE_MODELS,
            default_model=default_image_model,
        ),
        "video_models": _ordered_media_models(
            video_models,
            known=KNOWN_VIDEO_MODELS,
            default_model=default_video_model,
        ),
    }


def _recorded_local_artifact(
    production: dict[str, Any],
    artifact_sha256: str,
    *,
    owner_user_id: str,
) -> tuple[Path, dict[str, Any]] | None:
    expected_sha = str(artifact_sha256 or "").strip().lower()
    if len(expected_sha) != 64 or any(char not in "0123456789abcdef" for char in expected_sha):
        return None
    for event in reversed(production.get("events") or []):
        if not isinstance(event, dict) or event.get("status") != "succeeded":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        candidates: list[Any] = []
        for field in ("artifact", "final_artifact"):
            if payload.get(field) is not None:
                candidates.append(payload[field])
        for field in ("artifacts", "outputs", "assets"):
            value = payload.get(field)
            if isinstance(value, list):
                candidates.extend(value)
        for candidate in reversed(candidates):
            if not isinstance(candidate, dict) or str(candidate.get("sha256") or "").lower() != expected_sha:
                continue
            ref = str(candidate.get("ref") or candidate.get("source_ref") or "").strip()
            parsed = urlsplit(ref)
            paths: list[Path] = []
            if parsed.scheme == "file" and parsed.netloc in {"", "localhost"}:
                paths.append(Path(unquote(parsed.path)).resolve())
            elif parsed.scheme == "" and parsed.netloc == "":
                virtual_path = unquote(parsed.path)
                stripped = virtual_path.lstrip("/")
                prefix = VIRTUAL_PATH_PREFIX.lstrip("/")
                if stripped == prefix or stripped.startswith(prefix + "/"):
                    relative = stripped[len(prefix) :].lstrip("/")
                    threads_root = get_paths().user_dir(make_safe_user_id(owner_user_id)) / "threads"
                    if threads_root.is_dir():
                        for thread_dir in threads_root.iterdir():
                            if not thread_dir.is_dir():
                                continue
                            user_data_root = (thread_dir / "user-data").resolve()
                            resolved = (user_data_root / relative).resolve()
                            try:
                                resolved.relative_to(user_data_root)
                            except ValueError:
                                continue
                            paths.append(resolved)
            for path in paths:
                if not path.is_file():
                    continue
                verified = artifact_for_path(path)
                if verified["sha256"] != expected_sha:
                    continue
                recorded_size = candidate.get("size_bytes")
                if isinstance(recorded_size, int) and verified["size_bytes"] != recorded_size:
                    continue
                return path, {**candidate, **verified}
    return None


@router.post("", status_code=201)
async def begin_personal_ip_video_production(
    body: PersonalIPVideoProductionBeginRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        return await get_personal_ip_video_production_repo(request).begin(
            owner_user_id=await _current_user_id(request),
            **body.model_dump(),
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc


@router.post("/{production_id}/events")
async def append_personal_ip_video_production_event(
    production_id: str,
    body: PersonalIPVideoProductionEventRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        production = await get_personal_ip_video_production_repo(request).append_event(
            production_id,
            owner_user_id=await _current_user_id(request),
            trusted_human_confirmation=(body.event_type == "review_recorded"),
            **body.model_dump(),
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return production


@router.post("/{production_id}/timeline-revisions")
async def append_personal_ip_video_timeline_revision(
    production_id: str,
    body: PersonalIPVideoTimelineRevisionRequest,
    request: Request,
) -> dict[str, Any]:
    owner_user_id = await _current_user_id(request)
    repository = get_personal_ip_video_production_repo(request)
    production = await repository.get(production_id, owner_user_id=owner_user_id)
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    mode = resolve_video_production_mode(production)
    try:
        contract = compile_timeline_revision(
            production_id=production_id,
            production_mode=str(mode or ""),
            revision_id=body.revision_id,
            base_revision_id=body.base_revision_id,
            author_kind=body.author_kind,
            intent=body.intent,
            fps=body.fps,
            tracks=body.tracks,
            operations=body.operations,
            strategy_confirmed=body.strategy_confirmed,
        )
        updated = await repository.append_event(
            production_id,
            owner_user_id=owner_user_id,
            event_key=body.event_key,
            event_type="timeline_revision_compiled",
            status="succeeded",
            entity_type="timeline",
            entity_id=body.revision_id,
            payload=contract,
            input_refs=([f"timeline-revision://{body.base_revision_id}"] if body.base_revision_id else [f"video-production://{production_id}/assembly"]),
            output_refs=[f"contract://personal-ip-video-timeline-revision-v1/{contract['sha256']}"],
            provider="human-workbench" if body.author_kind == "human" else "deerflow",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0, "currency": "CNY", "basis": "edit decision"},
            occurred_at=None,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return {"compiled_contract": contract, "production": updated}


@router.post("/{production_id}/final-edit-lock")
async def lock_personal_ip_video_final_edit(
    production_id: str,
    body: PersonalIPVideoFinalEditLockRequest,
    request: Request,
) -> dict[str, Any]:
    owner_user_id = await _current_user_id(request)
    repository = get_personal_ip_video_production_repo(request)
    production = await repository.get(production_id, owner_user_id=owner_user_id)
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    revision_events = [event for event in production.get("events") or [] if event.get("event_type") == "timeline_revision_compiled" and isinstance(event.get("payload"), dict)]
    if not revision_events:
        raise HTTPException(status_code=422, detail="Final edit lock requires a timeline revision")
    latest_revision = revision_events[-1]["payload"]
    mode = resolve_video_production_mode(production, contract=latest_revision)
    try:
        contract = compile_final_edit_lock(
            production_id=production_id,
            production_mode=str(mode or ""),
            lock_id=body.lock_id,
            timeline_revision=latest_revision,
            locked_by=body.locked_by,
            note=body.note,
        )
        updated = await repository.append_event(
            production_id,
            owner_user_id=owner_user_id,
            event_key=body.event_key,
            event_type="final_edit_locked",
            status="succeeded",
            entity_type="timeline",
            entity_id=body.lock_id,
            payload=contract,
            input_refs=[f"timeline-revision://{contract['source_revision_id']}"],
            output_refs=[f"contract://personal-ip-video-final-edit-lock-v1/{contract['sha256']}"],
            provider="human-workbench" if body.locked_by == "human" else "deerflow",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0, "currency": "CNY", "basis": "edit lock"},
            occurred_at=None,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return {"compiled_contract": contract, "production": updated}


@router.get("")
async def list_personal_ip_video_productions(
    request: Request,
    status: Literal["draft", "running", "awaiting_review", "blocked", "completed", "cancelled"] | None = Query(default=None),
    thread_id: str | None = Query(default=None, min_length=1, max_length=64),
    content_work_id: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return await get_personal_ip_video_production_repo(request).list(
        await _current_user_id(request),
        status=status,
        thread_id=thread_id,
        content_work_id=content_work_id,
        limit=limit,
    )


@router.get("/models")
async def get_personal_ip_video_models(request: Request) -> dict[str, Any]:
    """Return the image/video models visible to the configured Ark API key."""

    await _current_user_id(request)
    return await _volcengine_media_model_catalog()


@router.get("/{production_id}")
async def get_personal_ip_video_production(production_id: str, request: Request) -> dict[str, Any]:
    production = await get_personal_ip_video_production_repo(request).get(
        production_id,
        owner_user_id=await _current_user_id(request),
    )
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return production


@router.post("/{production_id}/thread")
async def bind_personal_ip_video_production_thread(
    production_id: str,
    body: PersonalIPVideoProductionThreadRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        production = await get_personal_ip_video_production_repo(request).bind_thread(
            production_id,
            owner_user_id=await _current_user_id(request),
            thread_id=body.thread_id,
        )
    except ValueError as exc:
        raise _repository_error(exc) from exc
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return production


@router.get("/{production_id}/workbench")
async def get_personal_ip_video_workbench(production_id: str, request: Request) -> dict[str, Any]:
    production = await get_personal_ip_video_production_repo(request).get(
        production_id,
        owner_user_id=await _current_user_id(request),
    )
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    return build_video_workbench_read_model(production)


@router.get("/{production_id}/artifacts/{artifact_sha256}")
async def get_personal_ip_video_artifact(
    production_id: str,
    artifact_sha256: str,
    request: Request,
) -> FileResponse:
    """Stream one checksummed local artifact recorded in an owner-scoped production."""

    owner_user_id = await _current_user_id(request)
    production = await get_personal_ip_video_production_repo(request).get(
        production_id,
        owner_user_id=owner_user_id,
    )
    if production is None:
        raise HTTPException(status_code=404, detail="Personal-IP video production not found")
    resolved = await asyncio.to_thread(
        _recorded_local_artifact,
        production,
        artifact_sha256,
        owner_user_id=owner_user_id,
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="Recorded video artifact not found")
    path, artifact = resolved
    media_type = str(artifact.get("mime_type") or "").strip()
    if not media_type:
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path=path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(path.name)}",
        },
    )
