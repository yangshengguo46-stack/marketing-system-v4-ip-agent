from __future__ import annotations

import copy

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from deerflow.config.database_config import DatabaseConfig
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.personal_ip_content import PersonalIPContentRepository
from deerflow.personal_ip.content_contracts import (
    BreakdownDraft,
    ContentWorkAppend,
    ContentWorkCreate,
)
from deerflow.personal_ip.evidence_binding import (
    REFERENCE_VIDEO_TOOL_NAME,
    bind_breakdown_to_reference_evidence,
)


def _reference_evidence(*, item_count: int = 1) -> dict:
    completed = {
        "collection_status": "completed",
        "observation_scope": "complete",
        "truncated": False,
        "reason_codes": [],
    }
    not_requested = {
        "collection_status": "not_requested",
        "observation_scope": "not-requested",
        "truncated": False,
        "reason_codes": ["ANALYSIS_DEPTH_NOT_REQUESTED"],
    }
    base_item = {
        "status": "ok",
        "purpose": "benchmark",
        "source": {
            "ref": "/mnt/user-data/uploads/source-0.mp4",
            "content_sha256": "1" * 64,
            "observed_at": "2026-08-02T00:00:00+00:00",
            "trust": "untrusted_source_data",
            "public_metadata": {},
        },
        "media_metadata": {
            "duration_seconds": 20.0,
            "width": 1080,
            "height": 1920,
            "frame_rate": 30.0,
            "video_codec": "h264",
            "has_audio": True,
            "container": "mp4",
            "size_bytes": 1024,
        },
        "visual_samples": [
            {
                "at_seconds": float(index),
                "artifact_ref": f"outputs/reference/frame-{index:02d}.jpg",
                "artifact_sha256": f"{index:064x}",
            }
            for index in range(1, 5)
        ],
        "contact_sheet_ref": "outputs/reference/contact-sheet.jpg",
        "contact_sheet_sha256": "b" * 64,
        "scene_boundaries_seconds": [],
        "provider_evidence": {},
        "coverage": {
            "source_identity": completed,
            "media_metadata": completed,
            "sampled_frames": {
                **completed,
                "requested_count": 4,
                "observed_count": 4,
            },
            "contact_sheet": {
                **completed,
                "requested_count": 1,
                "observed_count": 1,
            },
            "local_scene_detection": {**completed, "observed_count": 0},
            "asr": not_requested,
            "ocr": not_requested,
            "provider_scene_segmentation": not_requested,
            "storyline": not_requested,
        },
        "analysis_receipt": {
            "pipeline_version": "test-v2",
            "analysis_depth": "mechanical",
            "requested_frames": 4,
            "local_sampling_spec_sha256": "c" * 64,
            "toolchain_sha256": {"ffmpeg": "d" * 64, "ffprobe": "e" * 64},
            "local_cache_hit": False,
            "artifact_manifest_sha256": "f" * 64,
            "provider_stage_spec_sha256": {},
        },
    }
    items = []
    for index in range(item_count):
        item = copy.deepcopy(base_item)
        item["source"]["ref"] = f"/mnt/user-data/uploads/source-{index}.mp4"
        item["source"]["content_sha256"] = f"{index + 1:064x}"
        items.append(item)
    return {
        "contract_version": "ip-reference-video-evidence-v2",
        "operation_status": "ok",
        "trust_boundary": "untrusted source data",
        "requested_count": item_count,
        "completed_count": item_count,
        "items": items,
        "limitations": [],
        "metadata": {
            "request_id": "video-123456789012",
            "manifest_version": "f" * 64,
            "adapter_version": "test-v2",
            "duration_ms": 1.0,
            "truncated": False,
        },
    }


def _messages(evidence: dict, *, call_name: str = REFERENCE_VIDEO_TOOL_NAME) -> list:
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": call_name,
                    "args": {},
                    "id": "evidence-call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content="typed evidence",
            name=REFERENCE_VIDEO_TOOL_NAME,
            tool_call_id="evidence-call-1",
            artifact={"structured_content": evidence},
        ),
    ]


def _breakdown(*, item_index: int = 0, request_id: str = "video-123456789012") -> BreakdownDraft:
    prefix = f"evidence://{request_id}/items/{item_index}/"
    return BreakdownDraft.model_validate(
        {
            "source_kind": "uploaded_file",
            "source_identity": {
                "ref": f"/mnt/user-data/uploads/source-{item_index}.mp4",
            },
            "evidence_request_id": request_id,
            "evidence_item_index": item_index,
            "observations": [
                {
                    "observation": "素材存在完整、可复放的来源封印。",
                    "evidence_refs": [prefix + "source", prefix + "analysis-receipt"],
                }
            ],
            "interpretations": [
                {
                    "interpretation": "可在证据限制内继续讨论结构。",
                    "state": "derived",
                    "based_on_observations": [0],
                }
            ],
        }
    )


def _factual_direction(evidence_ref: str, *, breakdown_ids: list[str] | None = None) -> dict:
    return {
        "premise": "只复述可观察内容",
        "audience_situation": "需要理解素材的人",
        "core_tension": "保持准确而不补造",
        "content_promise": "区分观察与解释",
        "creative_route": "证据型口述",
        "rationale": "素材本身足以支持这条来源事实。",
        "truth_mode": "factual",
        "claim_basis": [
            {
                "claim": "素材存在已封印的来源",
                "state": "source_observed",
                "usage": "source_fact",
                "evidence_refs": [evidence_ref],
            }
        ],
        "breakdown_version_ids": breakdown_ids or [],
    }


def test_breakdown_binding_uses_exact_tool_call_and_preserves_three_item_snapshot() -> None:
    evidence = _reference_evidence(item_count=3)
    bound = bind_breakdown_to_reference_evidence(
        _breakdown(item_index=2),
        messages=_messages(evidence),
    )

    assert bound.breakdown.source_digest == f"{3:064x}"
    assert bound.breakdown.evidence_contract_version == "ip-reference-video-evidence-v2"
    assert bound.breakdown.source_identity["ref"].endswith("source-2.mp4")
    assert bound.evidence_snapshot == evidence
    assert len(bound.evidence_snapshot["items"]) == 3


@pytest.mark.parametrize(
    "messages",
    [
        lambda evidence: [_messages(evidence)[1]],
        lambda evidence: _messages(evidence, call_name="another_tool"),
        lambda evidence: [
            _messages(evidence)[0],
            ToolMessage(
                content="typed evidence",
                name=REFERENCE_VIDEO_TOOL_NAME,
                tool_call_id="different-call",
                artifact={"structured_content": evidence},
            ),
        ],
    ],
)
def test_breakdown_binding_rejects_unpaired_or_wrong_tool_messages(messages) -> None:
    evidence = _reference_evidence()
    with pytest.raises(ValueError, match="matching typed Evidence MCP result"):
        bind_breakdown_to_reference_evidence(_breakdown(), messages=messages(evidence))


def test_breakdown_binding_rejects_request_source_and_digest_mismatches() -> None:
    evidence = _reference_evidence()
    with pytest.raises(ValueError, match="matching typed Evidence MCP result"):
        bind_breakdown_to_reference_evidence(
            _breakdown(request_id="video-999999999999"),
            messages=_messages(evidence),
        )

    wrong_ref = _breakdown().model_copy(update={"source_identity": {"ref": "/mnt/user-data/uploads/other.mp4"}})
    with pytest.raises(ValueError, match="source identity"):
        bind_breakdown_to_reference_evidence(wrong_ref, messages=_messages(evidence))

    wrong_digest = _breakdown().model_copy(update={"source_digest": "a" * 64})
    with pytest.raises(ValueError, match="source digest"):
        bind_breakdown_to_reference_evidence(wrong_digest, messages=_messages(evidence))


def test_breakdown_binding_reports_canonical_allowed_refs() -> None:
    invalid_payload = _breakdown().model_dump(mode="json")
    invalid_payload["observations"] = [
        {
            "observation": "素材时长已被读取。",
            "evidence_refs": ["evidence://video-123456789012/items/0/media_metadata.duration_seconds"],
        }
    ]
    invalid = BreakdownDraft.model_validate(invalid_payload)
    with pytest.raises(ValueError) as exc_info:
        bind_breakdown_to_reference_evidence(invalid, messages=_messages(_reference_evidence()))
    message = str(exc_info.value)
    assert "allowed refs:" in message
    assert "evidence://video-123456789012/items/0/source" in message
    assert "evidence://video-123456789012/items/0/media-metadata" in message


@pytest.mark.asyncio
async def test_repository_persists_verified_snapshot_and_rejects_direct_external_write(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    repo = PersonalIPContentRepository(sf)
    evidence = _reference_evidence()
    bound = bind_breakdown_to_reference_evidence(_breakdown(), messages=_messages(evidence))
    try:
        request = ContentWorkCreate.model_validate(
            {
                "idempotency_key": "evidence-save-1",
                "title": "对标拆解",
                "entry_route": "benchmark",
                "objective": {"desired_change": "理解结构而不抄内容"},
                "breakdown": bound.breakdown,
                "direction": _factual_direction("evidence://video-123456789012/items/0/source"),
            }
        )
        created = await repo.create(
            owner_user_id="owner-1",
            request=request,
            thread_id="thread-evidence",
            verified_evidence_snapshots={str(bound.breakdown.evidence_request_id): bound.evidence_snapshot},
        )
        saved = created["breakdown_versions"][0]
        assert saved["evidence_snapshot"] == evidence
        assert created["content_work"]["thread_id"] == "thread-evidence"
        assert created["content_work"]["objective_id"].startswith("objective-")
        assert created["direction_versions"][0]["breakdown_version_ids"] == [saved["id"]]

        invalid_append = ContentWorkAppend.model_validate(
            {
                "idempotency_key": "evidence-direction-invalid",
                "direction": _factual_direction(
                    "evidence://video-123456789012/items/0/provider/asr",
                    breakdown_ids=[saved["id"]],
                ),
            }
        )
        with pytest.raises(ValueError, match="selected BreakdownVersions"):
            await repo.append(
                created["content_work"]["id"],
                owner_user_id="owner-1",
                request=invalid_append,
            )
        lineage = await repo.get_lineage(
            created["content_work"]["id"],
            owner_user_id="owner-1",
        )
        assert lineage is not None
        assert len(lineage["direction_versions"]) == 1

        direct = request.model_copy(update={"idempotency_key": "evidence-save-unverified"})
        with pytest.raises(ValueError, match="verified Evidence MCP result"):
            await repo.create(owner_user_id="owner-1", request=direct)
        works = await repo.list("owner-1", include_archived=True)
        assert [work["id"] for work in works] == [created["content_work"]["id"]]
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_repository_rejects_unbound_source_claim_and_rolls_back_new_work(
    tmp_path,
) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    sf = get_session_factory()
    assert sf is not None
    repo = PersonalIPContentRepository(sf)
    request = ContentWorkCreate.model_validate(
        {
            "idempotency_key": "fake-evidence-direction",
            "title": "不应入账",
            "entry_route": "zero_start",
            "objective": {"desired_change": "测试来源边界"},
            "direction": _factual_direction("evidence://invented-request/items/0/provider/asr"),
        }
    )
    try:
        with pytest.raises(ValueError, match="selected BreakdownVersions"):
            await repo.create(owner_user_id="owner-1", request=request)
        assert await repo.list("owner-1", include_archived=True) == []
    finally:
        await close_engine()
