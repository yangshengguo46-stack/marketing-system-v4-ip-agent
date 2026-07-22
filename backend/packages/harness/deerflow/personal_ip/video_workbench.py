"""Read-only Personal-IP video workbench derived from the event ledger."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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
    payload_shot_id = _as_dict(event.get("payload")).get("shot_id")
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
    return [
        {
            "entity_type": entity_type,
            "id": entity_id,
            "status": entity_events[-1].get("status"),
            "latest_event": entity_events[-1],
            "artifacts": _collect_artifacts(entity_events),
            "event_ids": [event.get("id") for event in entity_events],
        }
        for (entity_type, entity_id), entity_events in grouped.items()
    ]


def _candidates(events: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("entity_type") == "candidate":
            grouped[str(event.get("entity_id") or "")].append(event)
    result: list[dict[str, Any]] = []
    for candidate_id, candidate_events in grouped.items():
        consistency_events = [event for event in candidate_events if event.get("event_type") == "consistency_checked"]
        selection_events = [event for event in candidate_events if event.get("event_type") == "candidate_selected"]
        review_events = [event for event in candidate_events if event.get("event_type") in {"review_requested", "review_recorded"}]
        approved_selection_reviews = [event for event in review_events if event.get("event_type") == "review_recorded" and _as_dict(event.get("payload")).get("review_kind") == "candidate_selection" and event.get("status") == "approved"]
        candidate_tasks = [task for task in tasks if task.get("entity_type") == "candidate" and task.get("entity_id") == candidate_id]
        result.append(
            {
                "id": candidate_id,
                "shot_id": _shot_id(candidate_events[-1]),
                "status": candidate_events[-1].get("status"),
                "selected": bool(selection_events or approved_selection_reviews),
                "selection": (selection_events or approved_selection_reviews)[-1] if selection_events or approved_selection_reviews else None,
                "consistency": _as_dict(consistency_events[-1].get("payload")) if consistency_events else None,
                "review": review_events[-1] if review_events else None,
                "artifacts": _collect_artifacts(candidate_events),
                "task_ids": [task.get("id") for task in candidate_tasks],
                "event_ids": [event.get("id") for event in candidate_events],
            }
        )
    return result


def _shots(events: list[dict[str, Any]], tasks: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    shot_ids: list[str] = []
    for event in events:
        candidate = _shot_id(event)
        if candidate and candidate not in shot_ids:
            shot_ids.append(candidate)
        if event.get("event_type") == "storyboard_sealed":
            for shot in _as_list(_as_dict(event.get("payload")).get("shots")):
                if isinstance(shot, dict) and isinstance(shot.get("id"), str) and shot["id"] not in shot_ids:
                    shot_ids.append(shot["id"])
    return [
        {
            "id": shot_id,
            "task_ids": [task.get("id") for task in tasks if task.get("shot_id") == shot_id],
            "candidate_ids": [candidate["id"] for candidate in candidates if candidate.get("shot_id") == shot_id],
            "selected_candidate_id": next(
                (candidate["id"] for candidate in candidates if candidate.get("shot_id") == shot_id and candidate.get("selected")),
                None,
            ),
        }
        for shot_id in shot_ids
    ]


def _confirmations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests = [event for event in events if event.get("event_type") == "review_requested"]
    recorded = [event for event in events if event.get("event_type") == "review_recorded"]
    result: list[dict[str, Any]] = []
    for event in requests:
        payload = _as_dict(event.get("payload"))
        raw_kind = payload.get("review_kind")
        kind = raw_kind if isinstance(raw_kind, str) else None
        if kind is None and event.get("entity_type") == "candidate":
            kind = "candidate_selection"
        if kind not in _MEANINGFUL_CONFIRMATIONS:
            continue
        answered = any(
            answer.get("entity_id") == event.get("entity_id") and (_as_dict(answer.get("payload")).get("request_event_key") == event.get("event_key") or _as_dict(answer.get("payload")).get("review_kind") == kind) for answer in recorded
        )
        if answered:
            continue
        result.append(
            {
                "id": event.get("id"),
                "event_key": event.get("event_key"),
                "kind": kind,
                "entity_type": event.get("entity_type"),
                "entity_id": event.get("entity_id"),
                "reason": payload.get("reason"),
                "requested_at": event.get("occurred_at"),
            }
        )
    return result


def build_video_workbench_read_model(production: dict[str, Any]) -> dict[str, Any]:
    """Fold one owner-scoped production without writing or inventing state."""

    events = sorted(
        [_safe_value(event) for event in _as_list(production.get("events")) if isinstance(event, dict)],
        key=lambda event: int(event.get("sequence") or 0),
    )
    production_summary = _safe_value({key: value for key, value in production.items() if key != "events"})
    tasks = [_task(event) for event in events if event.get("event_type") in _TASK_EVENT_TYPES]
    candidates = _candidates(events, tasks)
    storyboard_events = [event for event in events if event.get("event_type") == "storyboard_sealed"]
    blueprint_events = [event for event in events if event.get("event_type") == "blueprint_sealed"]
    qa_events = [event for event in events if event.get("event_type") == "delivery_qa_completed"]
    delivery_events = [event for event in events if event.get("event_type") == "delivery_completed"]
    latest_qa = qa_events[-1] if qa_events else None
    latest_storyboard = storyboard_events[-1] if storyboard_events else None
    latest_storyboard_payload = _as_dict(latest_storyboard.get("payload") if latest_storyboard else {})
    storyboard_shots = _as_list(latest_storyboard_payload.get("shots"))
    storyboard_shot_count = latest_storyboard_payload.get("shot_count")
    if not isinstance(storyboard_shot_count, int):
        storyboard_shot_count = len(storyboard_shots)
    finishing_events = [event for event in events if event.get("stage") == "finishing"]
    timeline_entities = [event for event in finishing_events if event.get("entity_type") in {"audio", "timeline"}]
    return {
        "contract_version": VIDEO_WORKBENCH_CONTRACT_VERSION,
        "production": production_summary,
        "source": {"kind": production_summary.get("source_kind"), "content": _as_dict(production_summary.get("source"))},
        "stage_summary": _stage_summary(production, events),
        "blueprint": {"events": blueprint_events, "artifacts": _collect_artifacts(blueprint_events)},
        "assets": _assets(events),
        "storyboard": {
            "events": storyboard_events,
            "shot_count": storyboard_shot_count,
            "artifacts": _collect_artifacts(storyboard_events),
        },
        "shots": _shots(events, tasks, candidates),
        "tasks": tasks,
        "candidates": candidates,
        "confirmations": _confirmations(events),
        "timeline": {
            "events": finishing_events,
            "tracks": [
                {
                    "type": "audio" if event.get("entity_type") == "audio" else "video",
                    "entity_id": event.get("entity_id"),
                    "status": event.get("status"),
                    "artifacts": _event_artifacts(event),
                    "event_id": event.get("id"),
                }
                for event in timeline_entities
            ],
        },
        "delivery": {
            "qa_events": qa_events,
            "delivery_events": delivery_events,
            "qa_passed": _as_dict(latest_qa.get("payload") if latest_qa else {}).get("passed") if latest_qa else None,
            "artifacts": _collect_artifacts([*qa_events, *delivery_events]),
        },
        "events": events,
    }
