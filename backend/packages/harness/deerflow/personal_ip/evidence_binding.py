"""Bind a BreakdownVersion to a typed Evidence MCP result already in state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from deerflow.ip_agent.evidence_contracts import ReferenceVideoEvidence
from deerflow.personal_ip.content_contracts import BreakdownDraft

REFERENCE_VIDEO_TOOL_NAME = "ip_evidence_inspect_reference_videos"


@dataclass(frozen=True)
class BoundReferenceBreakdown:
    breakdown: BreakdownDraft
    evidence_snapshot: dict[str, Any]


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reference_video_results(messages: Iterable[Any]) -> list[ReferenceVideoEvidence]:
    call_ids: set[str] = set()
    results: list[ReferenceVideoEvidence] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            if not isinstance(call, dict) or call.get("name") != REFERENCE_VIDEO_TOOL_NAME:
                continue
            call_id = str(call.get("id") or "").strip()
            if call_id:
                call_ids.add(call_id)
        name = str(getattr(message, "name", None) or "")
        tool_call_id = str(getattr(message, "tool_call_id", None) or "")
        if name != REFERENCE_VIDEO_TOOL_NAME or tool_call_id not in call_ids:
            continue
        artifact = getattr(message, "artifact", None)
        structured = artifact.get("structured_content") if isinstance(artifact, dict) else None
        if not isinstance(structured, dict):
            continue
        try:
            results.append(ReferenceVideoEvidence.model_validate(structured))
        except ValueError:
            continue
    return results


def reference_evidence_refs(
    *,
    request_id: str,
    item_index: int,
    item: Mapping[str, Any],
) -> set[str]:
    """Return the only canonical refs exposed by one typed evidence item."""
    prefix = f"evidence://{request_id}/items/{item_index}/"
    refs = {
        prefix + "source",
        prefix + "media-metadata",
        prefix + "analysis-receipt",
    }
    coverage = item.get("coverage")
    if isinstance(coverage, dict):
        refs.update(prefix + f"coverage/{key}" for key in coverage)
    samples = item.get("visual_samples")
    if isinstance(samples, list):
        refs.update(prefix + f"visual-samples/{index}" for index in range(len(samples)))
    if item.get("contact_sheet_ref"):
        refs.add(prefix + "contact-sheet")
    boundaries = item.get("scene_boundaries_seconds")
    if isinstance(boundaries, list):
        refs.update(prefix + f"scene-boundaries/{index}" for index in range(len(boundaries)))
    providers = item.get("provider_evidence")
    if isinstance(providers, dict):
        refs.update(prefix + f"provider/{key}" for key in providers)
    if item.get("derived_artifacts") is not None:
        refs.add(prefix + "derived-artifacts")
    if item.get("provider_inferences") is not None:
        refs.add(prefix + "provider-inferences")
    return refs


def bind_breakdown_to_reference_evidence(
    breakdown: BreakdownDraft,
    *,
    messages: Iterable[Any],
) -> BoundReferenceBreakdown:
    """Return a server-derived binding or fail before persistence."""
    if breakdown.source_kind == "owner_material":
        raise ValueError("owner_material does not use a ReferenceVideoEvidence binding")
    request_id = str(breakdown.evidence_request_id or "")
    item_index = breakdown.evidence_item_index
    matched = next(
        (evidence for evidence in reversed(_reference_video_results(messages)) if evidence.metadata.request_id == request_id),
        None,
    )
    if matched is None:
        raise ValueError("matching typed Evidence MCP result is not present in this task")
    if item_index is None or item_index >= len(matched.items):
        raise ValueError("Evidence MCP item index is out of range")
    item_model = matched.items[item_index]
    if item_model.status == "failed":
        raise ValueError("failed video evidence cannot become a BreakdownVersion")

    structured = matched.model_dump(mode="json", exclude_none=True)
    item = structured["items"][item_index]
    source = item["source"]
    actual_source_digest = str(source.get("content_sha256") or "")
    if len(actual_source_digest) != 64:
        raise ValueError("Evidence MCP item does not contain a sealed content digest")
    if breakdown.source_digest is not None and breakdown.source_digest != actual_source_digest:
        raise ValueError("breakdown source digest does not match the Evidence MCP result")
    claimed_ref = str(breakdown.source_identity.get("ref") or breakdown.source_identity.get("source_ref") or "").strip()
    actual_ref = str(source.get("ref") or "").strip()
    expected_source_kind = "uploaded_file" if actual_ref.startswith("/mnt/user-data/uploads/") else "platform_content"
    if breakdown.source_kind != expected_source_kind:
        raise ValueError("breakdown source_kind does not match the Evidence MCP source")
    if claimed_ref and claimed_ref != actual_ref:
        raise ValueError("breakdown source identity does not match the Evidence MCP result")

    allowed_refs = reference_evidence_refs(
        request_id=request_id,
        item_index=item_index,
        item=item,
    )
    unknown_refs = sorted({ref for observation in breakdown.observations for ref in observation.evidence_refs if ref not in allowed_refs})
    if unknown_refs:
        raise ValueError(f"breakdown contains an evidence_ref absent from the typed Evidence MCP result; unknown refs: {unknown_refs}; allowed refs: {sorted(allowed_refs)}")

    analysis_receipt = item.get("analysis_receipt") or {}
    canonical_identity = {
        "ref": actual_ref,
        "observed_at": source.get("observed_at"),
        "trust": source.get("trust"),
        "evidence_request_id": request_id,
        "evidence_item_index": item_index,
        "analysis_receipt_sha256": _canonical_digest(analysis_receipt),
    }
    limitations = list(
        dict.fromkeys(
            [
                *breakdown.limitations,
                *matched.limitations,
                *([] if item_model.status == "ok" else ["EVIDENCE_ITEM_PARTIAL"]),
            ]
        )
    )[:100]
    bound = breakdown.model_copy(
        update={
            "source_identity": canonical_identity,
            "source_digest": actual_source_digest,
            "evidence_contract_version": matched.contract_version,
            "evidence_payload_digest": _canonical_digest(structured),
            "limitations": limitations,
        }
    )
    return BoundReferenceBreakdown(
        breakdown=bound,
        evidence_snapshot=structured,
    )


__all__ = [
    "BoundReferenceBreakdown",
    "REFERENCE_VIDEO_TOOL_NAME",
    "bind_breakdown_to_reference_evidence",
    "reference_evidence_refs",
]
