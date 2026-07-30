"""Read-only Personal-IP video workbench derived from the event ledger."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from deerflow.personal_ip.video_contracts import resolve_video_production_mode

VIDEO_WORKBENCH_CONTRACT_VERSION = "personal-ip-video-workbench-v1"

VIDEO_WORKBENCH_STAGES: tuple[tuple[str, str], ...] = (
    ("intake", "剧本理解"),
    ("blueprint", "影视蓝图"),
    ("assets", "资产建档"),
    ("storyboard", "分镜"),
    ("generation", "逐镜生成"),
    ("consistency", "一致性检查"),
    ("selection", "选片 / 确认"),
    ("finishing", "配音剪辑"),
    ("delivery", "交付"),
)

_TASK_EVENT_TYPES = {
    "asset_generation_requested",
    "asset_generation_completed",
    "asset_generation_failed",
    "shot_generation_requested",
    "shot_generation_completed",
    "shot_generation_failed",
    "voice_generation_requested",
    "voice_generated",
    "media_processing_requested",
    "media_processing_completed",
    "media_processing_failed",
}
_ASSET_ENTITY_TYPES = {"character", "scene", "prop"}
_MEANINGFUL_CONFIRMATIONS = {"candidate_selection", "paid_provider_call", "real_publish"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item for item in _as_list(value) if isinstance(item, str) and item.strip()]


def _first_value(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _safe_ref(value: str) -> str:
    """Strip URL credentials, queries and fragments from read-model evidence."""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return value.split("?", 1)[0].split("#", 1)[0]
    if not parsed.scheme:
        return value.split("?", 1)[0].split("#", 1)[0]
    netloc = parsed.netloc
    if parsed.username is not None or parsed.password is not None:
        hostname = parsed.hostname or "redacted-host"
        netloc = f"[{hostname}]" if ":" in hostname else hostname
        try:
            if parsed.port is not None:
                netloc = f"{netloc}:{parsed.port}"
        except ValueError:
            pass
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _safe_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_safe_value(child) for child in value]
    if isinstance(value, str) and "://" in value:
        return _safe_ref(value)
    return value


def _artifact(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    ref = value.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        return None
    result: dict[str, Any] = {"ref": _safe_ref(ref.strip())}
    for field in ("sha256", "size_bytes", "mime_type", "source_ref", "downloaded_at"):
        if value.get(field) is not None:
            result[field] = _safe_value(value[field])
    return result


def _event_artifacts(event: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _as_dict(event.get("payload"))
    candidates: list[Any] = []
    for field in ("artifact", "final_artifact"):
        if payload.get(field) is not None:
            candidates.append(payload[field])
    for field in ("artifacts", "inputs", "outputs"):
        candidates.extend(_as_list(payload.get(field)))
    candidates.extend({"ref": ref} for ref in _as_list(event.get("output_refs")) if isinstance(ref, str))

    by_ref: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for candidate in candidates:
        normalized = _artifact(candidate)
        if normalized is None:
            continue
        ref = normalized["ref"]
        if ref not in by_ref:
            order.append(ref)
            by_ref[ref] = normalized
        else:
            by_ref[ref].update(normalized)
    return [by_ref[ref] for ref in order]


def _collect_artifacts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ref: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in events:
        for artifact in _event_artifacts(event):
            ref = artifact["ref"]
            if ref not in by_ref:
                order.append(ref)
                by_ref[ref] = artifact
            else:
                by_ref[ref].update(artifact)
    return [by_ref[ref] for ref in order]


def _shot_id(event: dict[str, Any]) -> str | None:
    entity_id = str(event.get("entity_id") or "").strip()
    if event.get("entity_type") == "shot":
        return entity_id or None
    if event.get("entity_type") != "candidate":
        return None
    payload = _as_dict(event.get("payload"))
    payload_shot_id = _first_value(
        payload.get("shot_id"),
        _as_dict(payload.get("parameters")).get("shot_id"),
    )
    if isinstance(payload_shot_id, str) and payload_shot_id.strip():
        return payload_shot_id.strip()
    if ":candidate" in entity_id:
        return entity_id.split(":candidate", 1)[0]
    return None


def _failure(payload: dict[str, Any]) -> dict[str, Any] | None:
    failure = payload.get("failure")
    if isinstance(failure, dict):
        return failure
    category = payload.get("error_category")
    if isinstance(category, str) and category.strip():
        result = {"category": category.strip()}
        if payload.get("error_message") is not None:
            result["message"] = payload["error_message"]
        if isinstance(payload.get("retryable"), bool):
            result["retryable"] = payload["retryable"]
        return result
    return None


def _task(event: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(event.get("payload"))
    parameters = _as_dict(payload.get("parameters"))
    return {
        "id": event.get("id"),
        "event_key": event.get("event_key"),
        "sequence": event.get("sequence"),
        "event_type": event.get("event_type"),
        "stage": event.get("stage"),
        "status": event.get("status"),
        "entity_type": event.get("entity_type"),
        "entity_id": event.get("entity_id"),
        "shot_id": _shot_id(event),
        "provider": event.get("provider"),
        "model": event.get("model"),
        "provider_task_id": event.get("provider_task_id"),
        "attempt": parameters.get("attempt"),
        "retry_of": parameters.get("retry_of"),
        "cost": _as_dict(event.get("cost")),
        "failure": _failure(payload),
        "input_refs": [_safe_ref(ref) for ref in _as_list(event.get("input_refs")) if isinstance(ref, str)],
        "output_refs": [_safe_ref(ref) for ref in _as_list(event.get("output_refs")) if isinstance(ref, str)],
        "artifacts": _event_artifacts(event),
        "occurred_at": event.get("occurred_at"),
    }


def _stage_summary(production: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_stage = str(production.get("current_stage") or "intake")
    production_status = str(production.get("status") or "draft")
    current_index = next((index for index, (stage_id, _) in enumerate(VIDEO_WORKBENCH_STAGES) if stage_id == current_stage), 0)
    summary: list[dict[str, Any]] = []
    for index, (stage_id, label) in enumerate(VIDEO_WORKBENCH_STAGES):
        stage_events = [event for event in events if event.get("stage") == stage_id]
        if production_status == "completed" and index <= current_index:
            ledger_state = "complete"
        elif index < current_index:
            ledger_state = "recorded"
        elif index == current_index and production_status in {"blocked", "awaiting_review"}:
            ledger_state = "attention"
        elif index == current_index:
            ledger_state = "current"
        elif stage_events:
            ledger_state = "recorded"
        else:
            ledger_state = "not_started"
        summary.append(
            {
                "id": stage_id,
                "label": label,
                "ledger_state": ledger_state,
                "event_count": len(stage_events),
                "latest_event": stage_events[-1] if stage_events else None,
            }
        )
    return summary


def _assets(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("entity_type") in _ASSET_ENTITY_TYPES and str(event.get("event_type") or "").startswith("asset_"):
            grouped[(str(event["entity_type"]), str(event.get("entity_id") or ""))].append(event)
    result: list[dict[str, Any]] = []
    manifest_events = [event for event in events if event.get("event_type") == "asset_manifest_compiled"]
    if manifest_events:
        manifest_event = manifest_events[-1]
        for asset in _as_list(_as_dict(manifest_event.get("payload")).get("assets")):
            if not isinstance(asset, dict) or not isinstance(asset.get("id"), str):
                continue
            artifact = _artifact(
                {
                    "ref": asset.get("source_ref"),
                    "sha256": asset.get("sha256"),
                    "mime_type": asset.get("mime_type"),
                }
            )
            result.append(
                {
                    "entity_type": str(asset.get("type") or "asset"),
                    "id": asset["id"],
                    "name": asset.get("name"),
                    "status": manifest_event.get("status"),
                    "latest_event": manifest_event,
                    "version": asset.get("version"),
                    "source_sha256": asset.get("sha256"),
                    "source_ref": _safe_ref(asset["source_ref"]) if isinstance(asset.get("source_ref"), str) else None,
                    "license": asset.get("license"),
                    "allowed_for_use": asset.get("allowed_for_use"),
                    "generation_route": asset.get("generation_route"),
                    "projection_mode": asset.get("projection_mode"),
                    "coverage": _as_dict(asset.get("coverage")) or None,
                    "lineage": _as_dict(asset.get("lineage")) or None,
                    "artifacts": [artifact] if artifact else [],
                    "event_ids": [manifest_event.get("id")],
                }
            )
    for (entity_type, entity_id), entity_events in grouped.items():
        latest_event = entity_events[-1]
        payload = _as_dict(latest_event.get("payload"))
        parameters = _as_dict(payload.get("parameters"))
        artifacts = _collect_artifacts(entity_events)
        source_sha256 = _first_value(
            payload.get("source_sha256"),
            payload.get("content_sha256"),
            artifacts[-1].get("sha256") if artifacts else None,
        )
        generated = {
            "entity_type": entity_type,
            "id": entity_id,
            "status": latest_event.get("status"),
            "latest_event": latest_event,
            "version": _first_value(payload.get("asset_version"), payload.get("version"), parameters.get("asset_version")),
            "source_sha256": source_sha256,
            "generation_route": _first_value(payload.get("generation_route"), parameters.get("generation_route")),
            "projection_mode": _first_value(payload.get("projection_mode"), parameters.get("projection_mode")),
            "coverage": _as_dict(payload.get("coverage")) or None,
            "lineage": _as_dict(payload.get("lineage")) or None,
            "artifacts": artifacts,
            "event_ids": [event.get("id") for event in entity_events],
        }
        existing = next(
            (item for item in result if item.get("entity_type") == entity_type and item.get("id") == entity_id),
            None,
        )
        if existing is None:
            result.append(generated)
            continue
        for field in (
            "status",
            "latest_event",
            "version",
            "source_sha256",
            "generation_route",
            "projection_mode",
            "coverage",
            "lineage",
        ):
            if generated.get(field) is not None:
                existing[field] = generated[field]
        artifact_by_ref = {artifact["ref"]: artifact for artifact in [*existing.get("artifacts", []), *generated["artifacts"]]}
        existing["artifacts"] = list(artifact_by_ref.values())
        existing["event_ids"] = [*existing.get("event_ids", []), *generated["event_ids"]]
    return result


def _candidates(events: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("entity_type") == "candidate":
            grouped[str(event.get("entity_id") or "")].append(event)
    result: list[dict[str, Any]] = []
    for candidate_id, candidate_events in grouped.items():
        consistency_events = [event for event in candidate_events if event.get("event_type") == "consistency_checked"]
        qa_events = [event for event in candidate_events if event.get("event_type") == "generated_shot_qa_compiled"]
        selection_events = [event for event in candidate_events if event.get("event_type") == "candidate_selected"]
        review_events = [event for event in candidate_events if event.get("event_type") in {"review_requested", "review_recorded"}]
        approved_selection_reviews = [event for event in review_events if event.get("event_type") == "review_recorded" and _as_dict(event.get("payload")).get("review_kind") == "candidate_selection" and event.get("status") == "approved"]
        candidate_tasks = [task for task in tasks if task.get("entity_type") == "candidate" and task.get("entity_id") == candidate_id]
        consistency_payload = _as_dict(consistency_events[-1].get("payload")) if consistency_events else {}
        quality = _first_value(
            _as_dict(qa_events[-1].get("payload")) if qa_events else None,
            consistency_payload.get("automated_qa"),
            consistency_payload.get("qa"),
            consistency_payload.get("quality"),
        )
        result.append(
            {
                "id": candidate_id,
                "shot_id": _shot_id(candidate_events[-1]),
                "status": candidate_events[-1].get("status"),
                "selected": bool(selection_events or approved_selection_reviews),
                "selection": (selection_events or approved_selection_reviews)[-1] if selection_events or approved_selection_reviews else None,
                "consistency": consistency_payload or None,
                "quality": _as_dict(quality) or None,
                "review": review_events[-1] if review_events else None,
                "artifacts": _collect_artifacts(candidate_events),
                "task_ids": [task.get("id") for task in candidate_tasks],
                "event_ids": [event.get("id") for event in candidate_events],
            }
        )
    return result


def _shots(events: list[dict[str, Any]], tasks: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shot_ids: list[str] = []
    specs: dict[str, dict[str, Any]] = {}
    for event in events:
        candidate = _shot_id(event)
        if candidate and candidate not in shot_ids:
            shot_ids.append(candidate)
        if event.get("event_type") in {"storyboard_sealed", "storyboard_compiled"}:
            for shot in _as_list(_as_dict(event.get("payload")).get("shots")):
                if isinstance(shot, dict) and isinstance(shot.get("id"), str) and shot["id"] not in shot_ids:
                    shot_ids.append(shot["id"])
                if isinstance(shot, dict) and isinstance(shot.get("id"), str):
                    specs[shot["id"]] = {
                        "order": shot.get("order"),
                        "title": _first_value(shot.get("title"), shot.get("narrative_purpose"), shot.get("description")),
                        "scene_id": shot.get("scene_id"),
                        "duration_seconds": _first_value(shot.get("duration_seconds"), shot.get("duration_sec")),
                        "first_frame": shot.get("first_frame"),
                        "last_frame": shot.get("last_frame"),
                        "motion": shot.get("motion"),
                        "preserve_elements": _string_list(shot.get("preserve_elements")),
                        "change_elements": _string_list(shot.get("change_elements")),
                        "dialogue": shot.get("dialogue"),
                        "camera": _safe_value(shot.get("camera")),
                        "action": shot.get("action"),
                        "narration_text": shot.get("narration_text"),
                        "visual_subject": shot.get("visual_subject"),
                        "visual_query": shot.get("visual_query"),
                        "composition_strategy": shot.get("composition_strategy"),
                        "claim_evidence_refs": _string_list(shot.get("claim_evidence_refs")),
                        "pass_criteria": _string_list(shot.get("pass_criteria")),
                    }
    return [
        {
            "id": shot_id,
            "spec": specs.get(shot_id, {}),
            "task_ids": [task.get("id") for task in tasks if task.get("shot_id") == shot_id],
            "candidate_ids": [candidate["id"] for candidate in candidates if candidate.get("shot_id") == shot_id],
            "selected_candidate_id": next(
                (candidate["id"] for candidate in candidates if candidate.get("shot_id") == shot_id and candidate.get("selected")),
                None,
            ),
        }
        for shot_id in shot_ids
    ]


def _continuity(events: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> dict[str, Any]:
    bridges: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "consistency_checked":
            continue
        payload = _as_dict(event.get("payload"))
        nested = _as_dict(payload.get("continuity"))
        bridge = _first_value(
            payload.get("bridge"),
            payload.get("shot_state_bridge"),
            payload.get("continuity_bridge"),
            nested.get("bridge"),
        )
        if not isinstance(bridge, dict):
            continue
        bridges.append(
            {
                **bridge,
                "event_id": event.get("id"),
                "event_key": event.get("event_key"),
                "candidate_id": event.get("entity_id") if event.get("entity_type") == "candidate" else None,
            }
        )

    recovery_scopes: list[dict[str, Any]] = []
    for task in tasks:
        failure = _as_dict(task.get("failure"))
        if not failure:
            continue
        categories = _string_list(failure.get("categories"))
        category = failure.get("category")
        if isinstance(category, str) and category and category not in categories:
            categories.insert(0, category)
        recovery_scopes.append(
            {
                "event_id": task.get("id"),
                "event_key": task.get("event_key"),
                "entity_id": task.get("entity_id"),
                "source": failure.get("source"),
                "categories": categories,
                "affected_shot_ids": _string_list(failure.get("affected_shot_ids")),
                "affected_asset_ids": _string_list(failure.get("affected_asset_ids")),
                "retryable": failure.get("retryable"),
            }
        )
    compiled = [event for event in events if event.get("event_type") == "continuity_compiled"]
    return {
        "bridges": bridges,
        "recovery_scopes": recovery_scopes,
        "ledger": _as_dict(compiled[-1].get("payload")) if compiled else None,
    }


def _timeline(finishing_events: list[dict[str, Any]]) -> dict[str, Any]:
    timeline_entities = [event for event in finishing_events if event.get("entity_type") in {"audio", "timeline"} or event.get("event_type") == "narration_timing_compiled"]
    revision_events = [event for event in timeline_entities if event.get("event_type") == "timeline_revision_compiled"]
    if revision_events:
        latest = revision_events[-1]
        payload = _as_dict(latest.get("payload"))
        revision_tracks: list[dict[str, Any]] = []
        for track_index, raw_track in enumerate(_as_list(payload.get("tracks"))):
            if not isinstance(raw_track, dict):
                continue
            clips: list[dict[str, Any]] = []
            artifacts: list[dict[str, Any]] = []
            for raw_clip in _as_list(raw_track.get("clips")):
                if not isinstance(raw_clip, dict):
                    continue
                artifact = _artifact(
                    {
                        "ref": raw_clip.get("source_ref"),
                        "sha256": raw_clip.get("source_sha256"),
                    }
                )
                if artifact is not None:
                    artifacts.append(artifact)
                clips.append(
                    {
                        "id": raw_clip.get("id"),
                        "shot_id": raw_clip.get("shot_id"),
                        "start_sec": raw_clip.get("start_sec"),
                        "duration_sec": raw_clip.get("duration_sec"),
                        "source_in_sec": raw_clip.get("source_in_sec"),
                        "source_ref": raw_clip.get("source_ref"),
                        "source_sha256": raw_clip.get("source_sha256"),
                        "selected_candidate_id": raw_clip.get("selected_candidate_id"),
                        "text": raw_clip.get("text"),
                        "volume": raw_clip.get("volume"),
                        "transition": raw_clip.get("transition"),
                        "artifact": artifact,
                    }
                )
            revision_tracks.append(
                {
                    "id": _first_value(raw_track.get("id"), f"track-{track_index + 1}"),
                    "type": _first_value(raw_track.get("type"), "video"),
                    "entity_id": latest.get("entity_id"),
                    "status": latest.get("status"),
                    "artifacts": artifacts,
                    "clips": clips,
                    "event_id": latest.get("id"),
                }
            )
        return {
            "events": finishing_events,
            "fps": payload.get("fps"),
            "duration_sec": payload.get("duration_seconds"),
            "tracks": revision_tracks,
            "revision_id": payload.get("revision_id"),
            "revisions": [
                {
                    "event_id": event.get("id"),
                    "event_key": event.get("event_key"),
                    "revision_id": _as_dict(event.get("payload")).get("revision_id"),
                    "base_revision_id": _as_dict(event.get("payload")).get("base_revision_id"),
                    "author_kind": _as_dict(event.get("payload")).get("author_kind"),
                    "intent": _as_dict(event.get("payload")).get("intent"),
                    "sha256": _as_dict(event.get("payload")).get("sha256"),
                    "tracks": _as_list(_as_dict(event.get("payload")).get("tracks")),
                    "operations": _as_list(_as_dict(event.get("payload")).get("operations")),
                    "occurred_at": event.get("occurred_at"),
                }
                for event in revision_events
            ],
        }
    tracks: list[dict[str, Any]] = []
    fps: Any = None
    duration_sec: Any = None
    for event in timeline_entities:
        payload = _as_dict(event.get("payload"))
        if event.get("event_type") == "narration_timing_compiled":
            duration_sec = _first_value(payload.get("actual_duration_seconds"), duration_sec)
            elapsed = 0.0
            clips: list[dict[str, Any]] = []
            artifacts: list[dict[str, Any]] = []
            for segment in _as_list(payload.get("segments")):
                if not isinstance(segment, dict):
                    continue
                segment_duration = segment.get("duration_seconds")
                artifact = _artifact(
                    {
                        "ref": segment.get("audio_ref"),
                        "sha256": segment.get("audio_sha256"),
                    }
                )
                clips.append(
                    {
                        "id": segment.get("id"),
                        "shot_id": segment.get("id"),
                        "start_sec": round(elapsed, 3),
                        "duration_sec": segment_duration,
                        "source_in_sec": 0,
                        "source_sha256": segment.get("audio_sha256"),
                        "selected_candidate_id": None,
                        "artifact": artifact,
                    }
                )
                if artifact is not None:
                    artifacts.append(artifact)
                if isinstance(segment_duration, (int, float)) and not isinstance(segment_duration, bool):
                    elapsed += float(segment_duration)
            tracks.append(
                {
                    "id": "narration",
                    "type": "audio",
                    "entity_id": event.get("entity_id"),
                    "status": event.get("status"),
                    "artifacts": artifacts,
                    "clips": clips,
                    "event_id": event.get("id"),
                }
            )
            continue
        if event.get("event_type") == "assembly_admitted":
            fps = _first_value(payload.get("fps"), fps)
            duration_sec = _first_value(payload.get("duration_seconds"), duration_sec)
            clips = []
            for raw_clip in _as_list(payload.get("timeline")):
                if not isinstance(raw_clip, dict):
                    continue
                clips.append(
                    {
                        "id": _first_value(raw_clip.get("id"), raw_clip.get("shot_id")),
                        "shot_id": raw_clip.get("shot_id"),
                        "start_sec": raw_clip.get("timeline_start_seconds"),
                        "duration_sec": raw_clip.get("duration_seconds"),
                        "source_in_sec": raw_clip.get("source_in_seconds"),
                        "source_sha256": raw_clip.get("source_sha256"),
                        "selected_candidate_id": raw_clip.get("candidate_id"),
                        "artifact": _artifact(
                            {
                                "ref": raw_clip.get("source_ref"),
                                "sha256": raw_clip.get("source_sha256"),
                            }
                        ),
                    }
                )
            tracks.append(
                {
                    "id": event.get("entity_id"),
                    "type": "video",
                    "entity_id": event.get("entity_id"),
                    "status": event.get("status"),
                    "artifacts": _event_artifacts(event),
                    "clips": clips,
                    "event_id": event.get("id"),
                }
            )
            continue
        timeline_payload = _as_dict(payload.get("timeline"))
        if timeline_payload:
            fps = _first_value(timeline_payload.get("fps"), fps)
            duration_sec = _first_value(
                timeline_payload.get("duration_sec"),
                timeline_payload.get("duration_seconds"),
                duration_sec,
            )
        raw_tracks = _as_list(timeline_payload.get("tracks"))
        if not raw_tracks:
            tracks.append(
                {
                    "id": event.get("entity_id"),
                    "type": "audio" if event.get("entity_type") == "audio" else "video",
                    "entity_id": event.get("entity_id"),
                    "status": event.get("status"),
                    "artifacts": _event_artifacts(event),
                    "clips": [],
                    "event_id": event.get("id"),
                }
            )
            continue
        for index, raw_track in enumerate(raw_tracks):
            if not isinstance(raw_track, dict):
                continue
            raw_type = str(_first_value(raw_track.get("type"), raw_track.get("kind"), "video")).lower()
            clips: list[dict[str, Any]] = []
            for raw_clip in _as_list(raw_track.get("clips")):
                if not isinstance(raw_clip, dict):
                    continue
                clips.append(
                    {
                        "id": _first_value(raw_clip.get("id"), raw_clip.get("name"), raw_clip.get("shot_id")),
                        "shot_id": raw_clip.get("shot_id"),
                        "start_sec": _first_value(raw_clip.get("start_sec"), raw_clip.get("timeline_start_sec")),
                        "duration_sec": _first_value(raw_clip.get("duration_sec"), raw_clip.get("duration_seconds")),
                        "source_in_sec": raw_clip.get("source_in_sec"),
                        "source_sha256": _first_value(raw_clip.get("source_sha256"), raw_clip.get("sha256")),
                        "selected_candidate_id": raw_clip.get("selected_candidate_id"),
                        "artifact": _artifact(raw_clip.get("artifact")),
                    }
                )
            tracks.append(
                {
                    "id": _first_value(raw_track.get("id"), raw_track.get("name"), f"track-{index + 1}"),
                    "type": "audio" if "audio" in raw_type or raw_type in {"voice", "sfx", "bgm"} else "video",
                    "entity_id": event.get("entity_id"),
                    "status": event.get("status"),
                    "artifacts": _event_artifacts(event),
                    "clips": clips,
                    "event_id": event.get("id"),
                }
            )
    return {
        "events": finishing_events,
        "fps": fps,
        "duration_sec": duration_sec,
        "tracks": tracks,
        "revision_id": None,
        "revisions": [],
    }


def _confirmations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests = [event for event in events if event.get("event_type") == "review_requested"]
    recorded = [event for event in events if event.get("event_type") == "review_recorded"]
    pending_by_scope: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in reversed(requests):
        payload = _as_dict(event.get("payload"))
        raw_kind = payload.get("review_kind")
        kind = raw_kind if isinstance(raw_kind, str) else None
        if kind is None and event.get("entity_type") == "candidate":
            kind = "candidate_selection"
        if kind not in _MEANINGFUL_CONFIRMATIONS:
            continue
        scope = (
            kind,
            str(event.get("entity_type") or ""),
            str(event.get("entity_id") or ""),
        )
        if scope in pending_by_scope:
            # A newer unanswered request for the same decision supersedes this
            # one. The ledger remains append-only; the workbench shows one
            # actionable confirmation instead of duplicate buttons.
            continue
        answered = any(
            answer.get("entity_id") == event.get("entity_id")
            and (
                _as_dict(answer.get("payload")).get("request_event_key") == event.get("event_key")
                or (not _as_dict(answer.get("payload")).get("request_event_key") and _as_dict(answer.get("payload")).get("review_kind") == kind and int(answer.get("sequence") or 0) > int(event.get("sequence") or 0))
            )
            for answer in recorded
        )
        if answered:
            continue
        pending_by_scope[scope] = {
            "id": event.get("id"),
            "event_key": event.get("event_key"),
            "kind": kind,
            "entity_type": event.get("entity_type"),
            "entity_id": event.get("entity_id"),
            "reason": payload.get("reason"),
            "requested_at": event.get("occurred_at"),
            "_sequence": int(event.get("sequence") or 0),
        }
    return [{key: value for key, value in confirmation.items() if key != "_sequence"} for confirmation in sorted(pending_by_scope.values(), key=lambda item: item["_sequence"])]


def build_video_workbench_read_model(production: dict[str, Any]) -> dict[str, Any]:
    """Fold one owner-scoped production without writing or inventing state."""

    events = sorted(
        [_safe_value(event) for event in _as_list(production.get("events")) if isinstance(event, dict)],
        key=lambda event: int(event.get("sequence") or 0),
    )
    production_summary = _safe_value({key: value for key, value in production.items() if key != "events"})
    tasks = [_task(event) for event in events if event.get("event_type") in _TASK_EVENT_TYPES]
    candidates = _candidates(events, tasks)
    storyboard_events = [event for event in events if event.get("event_type") in {"storyboard_sealed", "storyboard_compiled"}]
    blueprint_events = [event for event in events if event.get("event_type") in {"blueprint_sealed", "video_plan_compiled"}]
    plan_contract_events = [event for event in events if event.get("event_type") == "video_plan_compiled"]
    asset_contract_events = [event for event in events if event.get("event_type") == "asset_manifest_compiled"]
    storyboard_contract_events = [event for event in events if event.get("event_type") == "storyboard_compiled"]
    narration_contract_events = [event for event in events if event.get("event_type") == "narration_contract_compiled"]
    material_selection_contract_events = [event for event in events if event.get("event_type") == "material_selection_compiled"]
    narration_timing_contract_events = [event for event in events if event.get("event_type") == "narration_timing_compiled"]
    continuity_contract_events = [event for event in events if event.get("event_type") == "continuity_compiled"]
    assembly_contract_events = [event for event in events if event.get("event_type") == "assembly_admitted"]
    timeline_revision_events = [event for event in events if event.get("event_type") == "timeline_revision_compiled"]
    final_edit_lock_events = [event for event in events if event.get("event_type") == "final_edit_locked"]
    qa_events = [event for event in events if event.get("event_type") == "delivery_qa_completed"]
    delivery_events = [event for event in events if event.get("event_type") == "delivery_completed"]
    latest_storyboard = storyboard_events[-1] if storyboard_events else None
    latest_storyboard_payload = _as_dict(latest_storyboard.get("payload") if latest_storyboard else {})
    storyboard_shots = _as_list(latest_storyboard_payload.get("shots"))
    storyboard_shot_count = latest_storyboard_payload.get("shot_count")
    if not isinstance(storyboard_shot_count, int):
        storyboard_shot_count = len(storyboard_shots)
    finishing_events = [event for event in events if event.get("stage") == "finishing"]
    timeline = _timeline(finishing_events)
    latest_revision_payload = _as_dict(timeline_revision_events[-1].get("payload")) if timeline_revision_events else {}
    latest_lock_payload = _as_dict(final_edit_lock_events[-1].get("payload")) if final_edit_lock_events else {}
    latest_lock_event = final_edit_lock_events[-1] if final_edit_lock_events else None
    timeline["final_edit_lock"] = latest_lock_payload or None
    timeline["locked"] = bool(latest_revision_payload and latest_lock_payload.get("source_timeline_sha256") == latest_revision_payload.get("sha256"))
    current_qa_events = qa_events
    if timeline_revision_events:
        if timeline["locked"] and latest_lock_event is not None:
            lock_sequence = int(latest_lock_event.get("sequence") or 0)
            current_qa_events = [event for event in qa_events if int(event.get("sequence") or 0) > lock_sequence]
        else:
            current_qa_events = []
    current_qa = current_qa_events[-1] if current_qa_events else None
    qa_stale = bool(qa_events and timeline_revision_events and current_qa is None)
    return {
        "contract_version": VIDEO_WORKBENCH_CONTRACT_VERSION,
        "production_mode": resolve_video_production_mode(
            production_summary,
            contract=latest_revision_payload,
        ),
        "production": production_summary,
        "source": {"kind": production_summary.get("source_kind"), "content": _as_dict(production_summary.get("source"))},
        "stage_summary": _stage_summary(production, events),
        "domain_contracts": {
            "plan": _as_dict(plan_contract_events[-1].get("payload")) if plan_contract_events else None,
            "asset_manifest": _as_dict(asset_contract_events[-1].get("payload")) if asset_contract_events else None,
            "storyboard": _as_dict(storyboard_contract_events[-1].get("payload")) if storyboard_contract_events else None,
            "narration": _as_dict(narration_contract_events[-1].get("payload")) if narration_contract_events else None,
            "material_selection": _as_dict(material_selection_contract_events[-1].get("payload")) if material_selection_contract_events else None,
            "narration_timing": _as_dict(narration_timing_contract_events[-1].get("payload")) if narration_timing_contract_events else None,
            "continuity": _as_dict(continuity_contract_events[-1].get("payload")) if continuity_contract_events else None,
            "assembly": _as_dict(assembly_contract_events[-1].get("payload")) if assembly_contract_events else None,
            "timeline_revision": _as_dict(timeline_revision_events[-1].get("payload")) if timeline_revision_events else None,
            "final_edit_lock": latest_lock_payload or None,
        },
        "blueprint": {
            "events": blueprint_events,
            "artifacts": _collect_artifacts(blueprint_events),
            "contract": _as_dict(plan_contract_events[-1].get("payload")) if plan_contract_events else None,
        },
        "assets": _assets(events),
        "storyboard": {
            "events": storyboard_events,
            "shot_count": storyboard_shot_count,
            "artifacts": _collect_artifacts(storyboard_events),
            "contract": _as_dict(storyboard_contract_events[-1].get("payload")) if storyboard_contract_events else None,
        },
        "shots": _shots(events, tasks, candidates),
        "tasks": tasks,
        "candidates": candidates,
        "continuity": _continuity(events, tasks),
        "confirmations": _confirmations(events),
        "timeline": timeline,
        "delivery": {
            "qa_events": qa_events,
            "current_qa_event": current_qa,
            "delivery_events": delivery_events,
            "qa_passed": _as_dict(current_qa.get("payload")).get("passed") if current_qa else None,
            "qa_stale": qa_stale,
            "qa_stale_reason": "timeline_changed_after_delivery_qa" if qa_stale else None,
            "artifacts": _collect_artifacts([*qa_events, *delivery_events]),
        },
        "events": events,
    }
