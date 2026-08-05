from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import subprocess
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from deerflow.ip_agent import (
    douyin_adapter,
    evidence_mcp,
    mediakit_adapter,
    reference_evidence,
)
from deerflow.ip_agent.evidence_contracts import (
    CoverageRecord,
    ProviderExecutionReceipt,
    ReferenceVideoEvidence,
    VideoSource,
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _media_metadata(size_bytes: int) -> dict[str, Any]:
    return {
        "duration_seconds": 20.0,
        "width": 1080,
        "height": 1920,
        "frame_rate": 30.0,
        "video_codec": "h264",
        "has_audio": True,
        "container": "mp4",
        "size_bytes": size_bytes,
    }


def _completed_record(
    scope: str,
    *,
    requested_count: int | None = None,
    observed_count: int | None = None,
) -> dict[str, Any]:
    return {
        "collection_status": "completed",
        "observation_scope": scope,
        "truncated": False,
        "requested_count": requested_count,
        "observed_count": observed_count,
        "reason_codes": [],
    }


def _not_requested_record(scope: str) -> dict[str, Any]:
    return {
        "collection_status": "not_requested",
        "observation_scope": scope,
        "truncated": False,
        "requested_count": None,
        "observed_count": None,
        "reason_codes": ["ANALYSIS_DEPTH_NOT_REQUESTED"],
    }


def _valid_reference_item(
    *,
    analysis_depth: str = "mechanical",
    requested_frames: int = 8,
) -> dict[str, Any]:
    provider_requested = analysis_depth in {"speech_text", "full"}
    scene_provider_requested = analysis_depth == "full"
    coverage = {
        "source_identity": _completed_record("source_reference_and_content_hash"),
        "media_metadata": _completed_record("full_container_and_stream_probe"),
        "sampled_frames": _completed_record(
            "uniform_point_samples",
            requested_count=requested_frames,
            observed_count=requested_frames,
        ),
        "contact_sheet": _completed_record(
            "all_observed_uniform_samples",
            requested_count=1,
            observed_count=1,
        ),
        "local_scene_detection": _completed_record(
            "full_timeline_scene_threshold_scan",
            observed_count=0,
        ),
        "asr": (_completed_record("full_audio_track_asr") if provider_requested else _not_requested_record("full_audio_track_asr")),
        "ocr": (_completed_record("provider_subtitle_ocr") if provider_requested else _not_requested_record("provider_subtitle_ocr")),
        "provider_scene_segmentation": (_completed_record("provider_full_video_scene_analysis") if scene_provider_requested else _not_requested_record("provider_full_video_scene_analysis")),
        "storyline": (_completed_record("provider_full_video_storyline_analysis") if scene_provider_requested else _not_requested_record("provider_full_video_storyline_analysis")),
    }
    provider_evidence: dict[str, Any] = {}
    provider_specs: dict[str, str] = {}
    if provider_requested:
        provider_evidence.update(
            {
                "asr": {
                    "trust": "untrusted_source_data",
                    "provider": "test-provider",
                    "input_binding": "content_sha256_verified",
                    "input_content_sha256": "a" * 64,
                    "payload": {"transcript": "第一句真实台词"},
                },
                "ocr": {
                    "trust": "untrusted_source_data",
                    "provider": "test-provider",
                    "input_binding": "content_sha256_verified",
                    "input_content_sha256": "a" * 64,
                    "payload": {"texts": ["门店字幕"]},
                },
            }
        )
        provider_specs.update({"asr": "1" * 64, "ocr": "2" * 64})
    if scene_provider_requested:
        provider_evidence.update(
            {
                "scene_segmentation": {
                    "trust": "untrusted_source_data",
                    "provider": "test-provider",
                    "input_binding": "content_sha256_verified",
                    "input_content_sha256": "a" * 64,
                    "payload": {"segments": [{"start_time": 0, "end_time": 2}]},
                },
                "storyline": {
                    "trust": "untrusted_source_data",
                    "provider": "test-provider",
                    "input_binding": "content_sha256_verified",
                    "input_content_sha256": "a" * 64,
                    "payload": {"summary": "人物目标发生变化"},
                },
            }
        )
        provider_specs.update(
            {
                "provider_scene_segmentation": "3" * 64,
                "storyline": "4" * 64,
            }
        )
    return {
        "status": "ok",
        "purpose": "benchmark",
        "source": {
            "ref": "/mnt/user-data/uploads/source.mp4",
            "content_sha256": "a" * 64,
            "observed_at": "2026-08-02T00:00:00+00:00",
            "trust": "untrusted_source_data",
            "public_metadata": {},
        },
        "media_metadata": _media_metadata(1_024),
        "visual_samples": [
            {
                "at_seconds": float(index),
                "artifact_ref": f"outputs/reference/frame-{index:02d}.jpg",
                "artifact_sha256": f"{index:064x}",
            }
            for index in range(1, requested_frames + 1)
        ],
        "contact_sheet_ref": "outputs/reference/contact-sheet.jpg",
        "contact_sheet_sha256": "b" * 64,
        "scene_boundaries_seconds": [],
        "provider_evidence": provider_evidence,
        "coverage": coverage,
        "analysis_receipt": {
            "pipeline_version": "test-v2",
            "analysis_depth": analysis_depth,
            "requested_frames": requested_frames,
            "local_sampling_spec_sha256": "c" * 64,
            "toolchain_sha256": {"ffmpeg": "d" * 64, "ffprobe": "e" * 64},
            "local_cache_hit": False,
            "artifact_manifest_sha256": "f" * 64,
            "provider_stage_spec_sha256": provider_specs,
        },
    }


def _valid_reference_evidence(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": "ip-reference-video-evidence-v2",
        "operation_status": "ok",
        "trust_boundary": "untrusted source data",
        "requested_count": 1,
        "completed_count": 1,
        "items": [item],
        "limitations": [],
        "metadata": {
            "request_id": "video-123456789012",
            "manifest_version": "f" * 64,
            "adapter_version": "test-v2",
            "duration_ms": 1.0,
            "truncated": False,
        },
    }


def _realistic_mediakit_asr_evidence() -> ReferenceVideoEvidence:
    payload = {
        "duration": 3.793,
        "subtitles": [
            {
                "start_time": 0.44,
                "end_time": 2.72,
                "subtitle_text": "每一次生成都有回执",
                "confidence": 0.9775220685535007,
            },
            {
                "start_time": 2.72,
                "end_time": 3.842,
                "subtitle_text": "也能被验证",
                "confidence": 1,
            },
        ],
    }
    encoded_result = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    item = _valid_reference_item(analysis_depth="speech_text")
    item["status"] = "partial"
    item["coverage"]["asr"] = {
        "collection_status": "partial",
        "observation_scope": "full_audio_track_asr",
        "truncated": False,
        "requested_count": None,
        "observed_count": None,
        "reason_codes": ["PROVIDER_CONTENT_HASH_NOT_ATTESTED"],
    }
    item["provider_evidence"]["asr"] = {
        "trust": "untrusted_source_data",
        "provider": "volcengine-mediakit",
        "input_binding": "sealed_local_snapshot_provider_unattested",
        "input_content_sha256": "a" * 64,
        "payload": payload,
        "execution_receipt": {
            "adapter_version": "official-mediakit-cloud-video-v1",
            "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
            "executor": "official-mediakit-cli",
            "execution_mode": "cloud",
            "capability": "asr",
            "source_sha256": "a" * 64,
            "mediakit_sha256": "b" * 64,
            "stage_spec_sha256": "1" * 64,
            "submission_sha256": "c" * 64,
            "result_sha256": _canonical_sha256(payload),
            "task_id_sha256": "d" * 64,
            "request_id_sha256": "e" * 64,
            "provider_input_attestation": "not_provided",
            "polling_mode": "caller_deadline_single_query",
            "result_transport": "bounded_provider_https",
            "result_file_sha256": hashlib.sha256(encoded_result).hexdigest(),
            "result_file_size_bytes": len(encoded_result),
            "result_file_content_type": "application/json",
        },
    }
    aggregate = _valid_reference_evidence(item)
    aggregate["operation_status"] = "partial_or_failed"
    aggregate["completed_count"] = 0
    aggregate["limitations"] = ["provider content hash not attested"]
    return ReferenceVideoEvidence.model_validate(aggregate)


def _install_local_video_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    observed_frames: int,
    provider_coverage: dict[str, str] | None = None,
) -> tuple[dict[str, Path], list[Path]]:
    root = tmp_path / "user-data"
    upload = root / "uploads" / "source.mp4"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"sealed-video-content")
    tools = {
        "ffmpeg": tmp_path / "toolchain-a" / "ffmpeg",
        "ffprobe": tmp_path / "toolchain-a" / "ffprobe",
    }
    for path in tools.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    output_dirs: list[Path] = []

    monkeypatch.setenv("IP_AGENT_EVIDENCE_USER_DATA_ROOT", str(root))
    monkeypatch.setattr(
        reference_evidence,
        "_toolchain_paths",
        lambda: (tools["ffmpeg"], tools["ffprobe"], None),
    )
    original_sha256_file = reference_evidence._sha256_file
    monkeypatch.setattr(
        reference_evidence,
        "_sha256_file",
        lambda path: "a" * 64 if path.name == "source.mp4" else original_sha256_file(path),
    )
    monkeypatch.setattr(
        reference_evidence,
        "_probe_video",
        lambda source, _ffprobe: _media_metadata(source.stat().st_size),
    )

    def extract(**kwargs: Any):
        output_dirs.append(kwargs["output_dir"])
        frames = [
            {
                "at_seconds": float(index),
                "artifact_ref": f"{kwargs['artifact_ref_prefix']}/frame-{index:02d}.jpg",
                "artifact_sha256": "e" * 64,
            }
            for index in range(1, observed_frames + 1)
        ]
        return (
            frames,
            [1.0],
            tmp_path / "contact-sheet.jpg",
            f"{kwargs['artifact_ref_prefix']}/contact-sheet.jpg",
            {
                "cache_hit": False,
                "requested_frames": kwargs["max_frames"],
                "observed_frames": len(frames),
                "sampling_truncated": len(frames) < kwargs["max_frames"],
                "contact_sheet_completed": True,
                "contact_sheet_sha256": "f" * 64,
                "scene_detection_completed": True,
                "scene_boundaries_truncated": False,
                "analysis_spec_sha256": kwargs["analysis_spec"]["spec_sha256"],
                "artifact_manifest_sha256": "d" * 64,
            },
        )

    async def provider(**kwargs: Any):
        raw_coverage = provider_coverage or {
            "asr": "completed",
            "ocr": "completed",
            "provider_scene_segmentation": "completed",
            "storyline": "completed",
        }
        evidence: dict[str, Any] = {}
        specs: dict[str, str] = {}
        for coverage_key, status in raw_coverage.items():
            if status not in {"completed", "partial_truncated"}:
                continue
            provider_key = "scene_segmentation" if coverage_key == "provider_scene_segmentation" else coverage_key
            evidence[provider_key] = {
                "trust": "untrusted_source_data",
                "provider": "test-provider",
                "input_binding": "content_sha256_verified",
                "input_content_sha256": kwargs["content_sha256"],
                "payload": {},
            }
            specs[coverage_key] = hashlib.sha256(coverage_key.encode()).hexdigest()
        return (
            evidence,
            raw_coverage,
            specs,
        )

    monkeypatch.setattr(reference_evidence, "_extract_visual_evidence", extract)
    monkeypatch.setattr(reference_evidence, "_provider_evidence", provider)
    return tools, output_dirs


@pytest.mark.asyncio
async def test_artifact_cache_key_binds_analysis_contract_and_toolchain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tools, output_dirs = _install_local_video_fakes(
        monkeypatch,
        tmp_path,
        observed_frames=4,
    )

    await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="mechanical",
        max_frames=4,
    )
    await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="full",
        max_frames=8,
    )

    ffmpeg_b = tmp_path / "toolchain-b" / "ffmpeg"
    ffprobe_b = tmp_path / "toolchain-b" / "ffprobe"
    ffmpeg_b.parent.mkdir(parents=True)
    ffmpeg_b.write_bytes(b"different-ffmpeg-build")
    ffprobe_b.write_bytes(b"different-ffprobe-build")
    tools.update({"ffmpeg": ffmpeg_b, "ffprobe": ffprobe_b})
    await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="full",
        max_frames=8,
    )

    assert len(set(output_dirs)) == 3


@pytest.mark.asyncio
async def test_tampered_cached_frame_is_regenerated_from_exact_spec(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    upload = root / "uploads" / "source.mp4"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"sealed-video-content")
    ffmpeg = tmp_path / "toolchain" / "ffmpeg"
    ffprobe = tmp_path / "toolchain" / "ffprobe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"ffmpeg-build")
    ffprobe.write_bytes(b"ffprobe-build")
    monkeypatch.setenv("IP_AGENT_EVIDENCE_USER_DATA_ROOT", str(root))
    monkeypatch.setattr(
        reference_evidence,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, None),
    )
    monkeypatch.setattr(
        reference_evidence,
        "_probe_video",
        lambda source, _tool: _media_metadata(source.stat().st_size),
    )

    def run(command: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        if "-ss" in command:
            timestamp = command[command.index("-ss") + 1]
            destination = Path(command[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(f"frame-at-{timestamp}", encoding="utf-8")
        elif "-filter_complex" in command:
            destination = Path(command[-1])
            destination.write_text("contact-sheet", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

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

    monkeypatch.setattr(reference_evidence, "_run", run)
    monkeypatch.setattr(reference_evidence, "_provider_evidence", provider)

    first = await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="mechanical",
        max_frames=4,
    )
    frame_ref = first["visual_samples"][0]["artifact_ref"]
    frame_path = root / frame_ref
    frame_path.write_text("tampered", encoding="utf-8")

    second = await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="mechanical",
        max_frames=4,
    )

    assert frame_path.read_text(encoding="utf-8") != "tampered"
    assert second["visual_samples"][0]["artifact_sha256"] == reference_evidence._sha256_file(frame_path)


@pytest.mark.asyncio
async def test_consistently_rewritten_frame_and_manifest_cannot_become_cache_hit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    upload = root / "uploads" / "source.mp4"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"sealed-video-content")
    ffmpeg = tmp_path / "toolchain" / "ffmpeg"
    ffprobe = tmp_path / "toolchain" / "ffprobe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"ffmpeg-build")
    ffprobe.write_bytes(b"ffprobe-build")
    monkeypatch.setenv("IP_AGENT_EVIDENCE_USER_DATA_ROOT", str(root))
    monkeypatch.setattr(
        reference_evidence,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, None),
    )
    monkeypatch.setattr(
        reference_evidence,
        "_probe_video",
        lambda source, _tool: _media_metadata(source.stat().st_size),
    )

    def run(command: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        if "-ss" in command:
            destination = Path(command[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                f"frame-at-{command[command.index('-ss') + 1]}",
                encoding="utf-8",
            )
        elif "-filter_complex" in command:
            Path(command[-1]).write_text("contact-sheet", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

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

    monkeypatch.setattr(reference_evidence, "_run", run)
    monkeypatch.setattr(reference_evidence, "_provider_evidence", provider)

    first = await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="mechanical",
        max_frames=4,
    )
    frame_path = root / first["visual_samples"][0]["artifact_ref"]
    manifest_path = frame_path.parent / "artifact-manifest.json"
    frame_path.write_text("coordinated-tamper", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frames"][0]["sha256"] = reference_evidence._sha256_file(frame_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    second = await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="mechanical",
        max_frames=4,
    )

    assert second["analysis_receipt"]["local_cache_hit"] is False
    assert frame_path.read_text(encoding="utf-8") != "coordinated-tamper"


@pytest.mark.asyncio
async def test_uploaded_source_is_snapshotted_before_hash_and_analysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "user-data"
    upload = root / "uploads" / "source.mp4"
    upload.parent.mkdir(parents=True)
    original = b"original-upload-bytes"
    upload.write_bytes(original)
    expected_sha = hashlib.sha256(original).hexdigest()
    ffmpeg = tmp_path / "toolchain" / "ffmpeg"
    ffprobe = tmp_path / "toolchain" / "ffprobe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    monkeypatch.setenv("IP_AGENT_EVIDENCE_USER_DATA_ROOT", str(root))
    monkeypatch.setattr(
        reference_evidence,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, None),
    )

    def probe(source: Path, _tool: Path) -> dict[str, Any]:
        upload.write_bytes(b"mutated-after-snapshot")
        return _media_metadata(source.stat().st_size)

    def extract(**kwargs: Any):
        assert reference_evidence._sha256_file(kwargs["source"]) == expected_sha
        frames = [
            {
                "at_seconds": float(index),
                "artifact_ref": f"{kwargs['artifact_ref_prefix']}/frame-{index:02d}.jpg",
                "artifact_sha256": f"{index:064x}",
            }
            for index in range(1, 5)
        ]
        return (
            frames,
            [],
            tmp_path / "contact-sheet.jpg",
            f"{kwargs['artifact_ref_prefix']}/contact-sheet.jpg",
            {
                "cache_hit": False,
                "requested_frames": 4,
                "observed_frames": 4,
                "sampling_truncated": False,
                "contact_sheet_completed": True,
                "contact_sheet_sha256": "b" * 64,
                "scene_detection_completed": True,
                "scene_boundaries_truncated": False,
                "analysis_spec_sha256": kwargs["analysis_spec"]["spec_sha256"],
                "artifact_manifest_sha256": "c" * 64,
            },
        )

    async def provider(**kwargs: Any):
        assert kwargs["source"].read_bytes() == original
        assert kwargs["content_sha256"] == expected_sha
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

    monkeypatch.setattr(reference_evidence, "_probe_video", probe)
    monkeypatch.setattr(reference_evidence, "_extract_visual_evidence", extract)
    monkeypatch.setattr(reference_evidence, "_provider_evidence", provider)

    item = await reference_evidence._inspect_one_video(
        reference="/mnt/user-data/uploads/source.mp4",
        purpose="benchmark",
        analysis_depth="mechanical",
        max_frames=4,
    )

    assert item["source"]["content_sha256"] == expected_sha


def test_partial_artifact_retention_is_bounded_without_deleting_current_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_bytes(b"ffmpeg")
    output_dir = tmp_path / "outputs" / ("a" * 64)
    output_dir.mkdir(parents=True)
    (output_dir / "keep.txt").write_text("canonical", encoding="utf-8")
    for index in range(6):
        old = output_dir.parent / f"{output_dir.name}-partial-old-{index}"
        old.mkdir()
        (old / "frame.jpg").write_bytes(b"old")
        os.utime(old, (1, 1))

    def run(command: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        del timeout
        destination = Path(command[-1])
        if "-ss" in command and destination.name == "frame-01.jpg":
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"current-frame")
        elif "-filter_complex" in command:
            destination.write_bytes(b"current-contact")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(reference_evidence, "_run", run)
    spec = {
        "manifest_version": "ip-reference-video-artifacts-v1",
        "pipeline_version": "test",
        "evidence_contract": "ip-reference-video-evidence-v2",
        "analysis_depth": "mechanical",
        "content_sha256": "1" * 64,
        "duration_seconds": 10.0,
        "requested_frames": 4,
        "timestamps_seconds": [1.0, 3.0, 5.0, 7.0],
        "sampling_revision": "test",
        "contact_sheet_revision": "test",
        "scene_detection_revision": "test",
        "toolchain_sha256": {"ffmpeg": "2" * 64, "ffprobe": "3" * 64},
        "spec_sha256": "4" * 64,
    }

    _frames, _scenes, contact_path, _contact_ref, _receipt = reference_evidence._extract_visual_evidence(
        source=source,
        output_dir=output_dir,
        artifact_ref_prefix=f"outputs/{output_dir.name}",
        ffmpeg=ffmpeg,
        duration_seconds=10.0,
        max_frames=4,
        analysis_spec=spec,
    )

    assert contact_path is not None and contact_path.is_file()
    assert (output_dir / "keep.txt").read_text(encoding="utf-8") == "canonical"
    assert len(list(output_dir.parent.glob(f"{output_dir.name}-partial-*"))) <= 4


def test_tool_hash_cache_cannot_be_reused_after_same_size_same_mtime_replacement(
    tmp_path: Path,
) -> None:
    tool = tmp_path / "tool"
    tool.write_bytes(b"build-a")
    fixed_ns = 1_700_000_000_000_000_000
    os.utime(tool, ns=(fixed_ns, fixed_ns))
    reference_evidence._cached_tool_sha256.cache_clear()
    first = reference_evidence._tool_sha256(tool)
    tool.write_bytes(b"build-b")
    os.utime(tool, ns=(fixed_ns, fixed_ns))

    second = reference_evidence._tool_sha256(tool)

    assert first != second


@pytest.mark.asyncio
async def test_incomplete_frame_sampling_downgrades_item_and_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_local_video_fakes(monkeypatch, tmp_path, observed_frames=1)

    result = await reference_evidence.inspect_reference_videos(
        ["/mnt/user-data/uploads/source.mp4"],
        analysis_depth="full",
        max_frames=8,
    )

    assert result["items"][0]["status"] == "partial"
    assert result["items"][0]["coverage"]["sampled_frames"] == {
        "collection_status": "partial",
        "observation_scope": "uniform_point_samples",
        "truncated": True,
        "requested_count": 8,
        "observed_count": 1,
        "reason_codes": ["FRAME_EXTRACTION_INCOMPLETE"],
    }
    assert result["completed_count"] == 0
    assert result["operation_status"] == "partial_or_failed"
    assert result["metadata"]["truncated"] is True


@pytest.mark.asyncio
async def test_full_depth_unavailable_provider_is_partial_without_claiming_truncation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_local_video_fakes(
        monkeypatch,
        tmp_path,
        observed_frames=8,
        provider_coverage={
            "asr": "unavailable_provider_not_configured",
            "ocr": "unavailable_provider_not_configured",
            "provider_scene_segmentation": "unavailable_provider_not_configured",
            "storyline": "unavailable_provider_not_configured",
        },
    )

    result = await reference_evidence.inspect_reference_videos(
        ["/mnt/user-data/uploads/source.mp4"],
        analysis_depth="full",
        max_frames=8,
    )

    assert result["items"][0]["status"] == "partial"
    assert result["items"][0]["coverage"]["asr"]["collection_status"] == "unavailable"
    assert result["operation_status"] == "partial_or_failed"
    assert result["completed_count"] == 0
    assert result["metadata"]["truncated"] is False


@pytest.mark.asyncio
async def test_mechanical_depth_does_not_require_provider_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _install_local_video_fakes(
        monkeypatch,
        tmp_path,
        observed_frames=8,
        provider_coverage={
            "asr": "not_requested",
            "ocr": "not_requested",
            "provider_scene_segmentation": "not_requested",
            "storyline": "not_requested",
        },
    )

    result = await reference_evidence.inspect_reference_videos(
        ["/mnt/user-data/uploads/source.mp4"],
        analysis_depth="mechanical",
        max_frames=8,
    )

    assert result["items"][0]["status"] == "ok"
    assert result["items"][0]["coverage"]["asr"]["collection_status"] == "not_requested"
    assert result["operation_status"] == "ok"
    assert result["completed_count"] == 1
    assert result["metadata"]["truncated"] is False


@pytest.mark.asyncio
async def test_provider_payload_truncation_is_not_completed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-test-only")
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-source")
    content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit-test-build")

    def run_provider(
        _source: Path,
        **kwargs: Any,
    ) -> mediakit_adapter.MediaKitCloudExecution:
        return mediakit_adapter.MediaKitCloudExecution(
            payload={"truncated": True, "payload_excerpt": "bounded"},
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": kwargs["capability"],
                "source_sha256": content_sha256,
                "mediakit_sha256": hashlib.sha256(mediakit.read_bytes()).hexdigest(),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256({"truncated": True, "payload_excerpt": "bounded"}),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)

    _evidence, coverage, _specs = await reference_evidence._provider_evidence(
        source=source,
        content_sha256=content_sha256,
        analysis_depth="full",
        mediakit=mediakit,
    )

    assert coverage == {
        "asr": "partial_truncated",
        "ocr": "partial_truncated",
        "provider_scene_segmentation": "partial_truncated",
        "storyline": "partial_truncated",
    }


@pytest.mark.asyncio
async def test_provider_idempotency_token_separates_direct_executions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-test-only")
    observed_tokens: list[str] = []
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-source")
    content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()

    def run_provider(
        _source: Path,
        **kwargs: Any,
    ) -> mediakit_adapter.MediaKitCloudExecution:
        observed_tokens.append(kwargs["client_token"])
        return mediakit_adapter.MediaKitCloudExecution(
            payload={"segments": []},
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": kwargs["capability"],
                "source_sha256": content_sha256,
                "mediakit_sha256": hashlib.sha256(kwargs["mediakit"].read_bytes()).hexdigest(),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256({"segments": []}),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)
    mediakit = tmp_path / "mediakit"
    mediakit.write_bytes(b"mediakit-build")

    await reference_evidence._provider_evidence(
        source=source,
        content_sha256=content_sha256,
        analysis_depth="speech_text",
        mediakit=mediakit,
    )
    first_run = tuple(observed_tokens)
    observed_tokens.clear()
    await reference_evidence._provider_evidence(
        source=source,
        content_sha256=content_sha256,
        analysis_depth="speech_text",
        mediakit=mediakit,
    )

    assert first_run
    assert set(first_run).isdisjoint(observed_tokens)


def test_direct_provider_client_token_is_retry_stable_within_one_execution() -> None:
    first = reference_evidence._mediakit_client_token(
        stage_spec_sha256="1" * 64,
        provider_execution_scope="video-request-a",
    )
    retry = reference_evidence._mediakit_client_token(
        stage_spec_sha256="1" * 64,
        provider_execution_scope="video-request-a",
    )
    next_execution = reference_evidence._mediakit_client_token(
        stage_spec_sha256="1" * 64,
        provider_execution_scope="video-request-b",
    )
    next_stage = reference_evidence._mediakit_client_token(
        stage_spec_sha256="2" * 64,
        provider_execution_scope="video-request-a",
    )

    assert first == retry
    assert len({first, next_execution, next_stage}) == 3


@pytest.mark.asyncio
async def test_full_provider_stages_execute_in_parallel_with_isolated_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-test-only")
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-source")
    content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit-build")
    barrier = threading.Barrier(4)
    session_roots: set[Path] = set()
    session_roots_lock = threading.Lock()

    def run_provider(
        _source: Path,
        **kwargs: Any,
    ) -> mediakit_adapter.MediaKitCloudExecution:
        with session_roots_lock:
            session_roots.add(kwargs["session_root"])
        barrier.wait(timeout=2)
        payload = {"segments": []}
        return mediakit_adapter.MediaKitCloudExecution(
            payload=payload,
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": kwargs["capability"],
                "source_sha256": content_sha256,
                "mediakit_sha256": hashlib.sha256(mediakit.read_bytes()).hexdigest(),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256(payload),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)

    _evidence, coverage, _specs = await reference_evidence._provider_evidence(
        source=source,
        content_sha256=content_sha256,
        analysis_depth="full",
        mediakit=mediakit,
    )

    assert coverage == {
        "asr": "completed",
        "ocr": "completed",
        "provider_scene_segmentation": "completed",
        "storyline": "completed",
    }
    assert len(session_roots) == 4


@pytest.mark.asyncio
async def test_transient_provider_stage_failure_is_retried_inside_one_agent_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-test-only")
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-source")
    content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit-build")
    attempts: dict[str, int] = {}

    def run_provider(
        _source: Path,
        **kwargs: Any,
    ) -> mediakit_adapter.MediaKitCloudExecution:
        capability = kwargs["capability"]
        attempts[capability] = attempts.get(capability, 0) + 1
        if capability == "scene_segmentation" and attempts[capability] == 1:
            raise mediakit_adapter.MediaKitAdapterError("transient provider failure")
        payload = {"segments": []}
        return mediakit_adapter.MediaKitCloudExecution(
            payload=payload,
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v3",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": capability,
                "source_sha256": content_sha256,
                "mediakit_sha256": hashlib.sha256(mediakit.read_bytes()).hexdigest(),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256(payload),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)

    _evidence, coverage, _specs = await reference_evidence._provider_evidence(
        source=source,
        content_sha256=content_sha256,
        analysis_depth="full",
        mediakit=mediakit,
    )

    assert coverage == {
        "asr": "completed",
        "ocr": "completed",
        "provider_scene_segmentation": "completed",
        "storyline": "completed",
    }
    assert attempts == {
        "asr": 1,
        "ocr": 1,
        "scene_segmentation": 2,
        "storyline": 1,
    }


def test_local_probe_uses_video_track_duration_for_frame_sampling(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    ffprobe = tmp_path / "ffprobe"
    ffprobe.write_bytes(b"tool")
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "duration": "3.500000",
                "avg_frame_rate": "24/1",
                "width": 1080,
                "height": 1920,
                "codec_name": "h264",
            },
            {"codec_type": "audio", "duration": "3.648000"},
        ],
        "format": {"duration": "3.648000", "format_name": "mov,mp4"},
    }
    monkeypatch.setattr(
        reference_evidence,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, json.dumps(payload), ""),
    )

    metadata = reference_evidence._probe_video(source, ffprobe)

    assert metadata["duration_seconds"] == 3.5


@pytest.mark.asyncio
async def test_provider_cancellation_waits_for_cloud_workers_before_session_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-test-only")
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-source")
    content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit-build")
    all_started = threading.Event()
    release = threading.Event()
    state_lock = threading.Lock()
    session_roots: list[Path] = []

    def run_provider(
        _source: Path,
        **kwargs: Any,
    ) -> mediakit_adapter.MediaKitCloudExecution:
        with state_lock:
            session_roots.append(kwargs["session_root"])
            if len(session_roots) == 2:
                all_started.set()
        release.wait(timeout=5)
        payload = {"segments": []}
        return mediakit_adapter.MediaKitCloudExecution(
            payload=payload,
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": kwargs["capability"],
                "source_sha256": content_sha256,
                "mediakit_sha256": hashlib.sha256(mediakit.read_bytes()).hexdigest(),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256(payload),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)
    task = asyncio.create_task(
        reference_evidence._provider_evidence(
            source=source,
            content_sha256=content_sha256,
            analysis_depth="speech_text",
            mediakit=mediakit,
        )
    )
    try:
        assert await asyncio.to_thread(all_started.wait, 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert all(path.is_dir() for path in session_roots)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert all(not path.exists() for path in session_roots)
    finally:
        release.set()
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_sealed_snapshot_submission_is_not_provider_hash_attestation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-test-only")
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-source")
    content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit-test-build")

    def run_provider(
        _source: Path,
        **kwargs: Any,
    ) -> mediakit_adapter.MediaKitCloudExecution:
        return mediakit_adapter.MediaKitCloudExecution(
            payload={"transcript": "这段语义来自已封存的本地快照"},
            receipt={
                "adapter_version": "official-mediakit-cloud-video-v1",
                "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
                "executor": "official-mediakit-cli",
                "execution_mode": "cloud",
                "capability": kwargs["capability"],
                "source_sha256": content_sha256,
                "mediakit_sha256": hashlib.sha256(mediakit.read_bytes()).hexdigest(),
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "submission_sha256": "1" * 64,
                "result_sha256": _canonical_sha256({"transcript": "这段语义来自已封存的本地快照"}),
                "task_id_sha256": "3" * 64,
                "provider_input_attestation": "not_provided",
                "polling_mode": "caller_deadline_single_query",
                "result_transport": "inline",
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)

    evidence, coverage, _specs = await reference_evidence._provider_evidence(
        source=source,
        content_sha256=content_sha256,
        analysis_depth="speech_text",
        mediakit=mediakit,
    )

    assert coverage["asr"] == "completed"
    assert coverage["ocr"] == "completed"
    assert evidence["asr"]["input_binding"] == "sealed_local_snapshot_provider_unattested"


@pytest.mark.asyncio
async def test_configured_key_alone_executes_every_full_provider_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MEDIAKIT_API_KEY", "configured-in-test-only")
    source = tmp_path / "sealed.mp4"
    source.write_bytes(b"sealed-source")
    content_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    mediakit = tmp_path / "mediakit-cli"
    mediakit.write_bytes(b"mediakit")
    observed: list[str] = []

    def run_provider(_source: Path, **kwargs: Any) -> mediakit_adapter.MediaKitCloudExecution:
        capability = kwargs["capability"]
        observed.append(capability)
        payload = {"segments": []}
        return mediakit_adapter.MediaKitCloudExecution(
            payload=payload,
            receipt={
                "capability": capability,
                "source_sha256": content_sha256,
                "stage_spec_sha256": kwargs["stage_spec_sha256"],
                "result_sha256": _canonical_sha256(payload),
            },
        )

    monkeypatch.setattr(reference_evidence, "run_cloud_video_capability", run_provider)

    evidence, coverage, specs = await reference_evidence._provider_evidence(
        source=source,
        content_sha256=content_sha256,
        analysis_depth="full",
        mediakit=mediakit,
    )

    assert set(evidence) == {"asr", "ocr", "scene_segmentation", "storyline"}
    assert set(observed) == {"asr", "ocr", "scene_segmentation", "storyline"}
    assert set(specs) == {
        "asr",
        "ocr",
        "provider_scene_segmentation",
        "storyline",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in specs.values())
    assert set(coverage.values()) == {"completed"}


class _FakeDetailResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        url: str = "https://www.douyin.com/aweme/v1/web/aweme/detail/",
        status: int = 200,
    ):
        self.url = url
        self.status = status
        self.headers: dict[str, str] = {"content-length": str(len(json.dumps(payload, ensure_ascii=False).encode("utf-8")))}
        self._payload = payload

    async def json(self) -> dict[str, Any]:
        return self._payload


class _FakeResponseInfo:
    def __init__(self, response: _FakeDetailResponse):
        self._response = response

    @property
    def value(self):
        async def resolve() -> _FakeDetailResponse:
            return self._response

        return resolve()


class _FakeExpectResponse:
    def __init__(self, response: _FakeDetailResponse):
        self._info = _FakeResponseInfo(response)

    async def __aenter__(self) -> _FakeResponseInfo:
        return self._info

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _FakeVideoPage:
    def __init__(
        self,
        *,
        final_url: str,
        detail_payload: dict[str, Any],
        dom_media_url: str,
        response_url: str,
        response_status: int,
    ):
        self.url = final_url
        self._final_url = final_url
        self._response = _FakeDetailResponse(
            detail_payload,
            url=response_url,
            status=response_status,
        )
        self._dom_media_url = dom_media_url

    def on(self, *_args: Any) -> None:
        return None

    def remove_listener(self, *_args: Any) -> None:
        return None

    async def route(self, *_args: Any) -> None:
        return None

    def expect_response(self, *_args: Any, **_kwargs: Any) -> _FakeExpectResponse:
        return _FakeExpectResponse(self._response)

    async def goto(self, *_args: Any, **_kwargs: Any) -> None:
        self.url = self._final_url

    async def wait_for_timeout(self, *_args: Any) -> None:
        return None

    async def evaluate(self, *_args: Any) -> str:
        return self._dom_media_url


class _FakeVideoContext:
    def __init__(self, page: _FakeVideoPage):
        self.pages = [page]

    async def cookies(self, *_args: Any) -> list[dict[str, Any]]:
        return []


def _aweme(
    work_id: str,
    media_url: str,
    *,
    author_sec_uid: str = "author-sec-uid",
) -> dict[str, Any]:
    return {
        "aweme_id": work_id,
        "author": {"sec_uid": author_sec_uid, "nickname": "精确作者"},
        "video": {"play_addr": {"url_list": [media_url]}},
    }


def _install_video_page(
    monkeypatch: pytest.MonkeyPatch,
    *,
    final_url: str,
    detail_payload: dict[str, Any],
    dom_media_url: str,
    resolved_url: str | None = None,
    response_url: str = "https://www.douyin.com/aweme/v1/web/aweme/detail/",
    response_status: int = 200,
) -> None:
    page = _FakeVideoPage(
        final_url=final_url,
        detail_payload=detail_payload,
        dom_media_url=dom_media_url,
        response_url=response_url,
        response_status=response_status,
    )

    async def resolved(value: str) -> str:
        return resolved_url or value

    async def launched(*, headless: bool):
        del headless
        return object(), _FakeVideoContext(page), None

    async def closed(*_args: Any) -> None:
        return None

    monkeypatch.setattr(douyin_adapter, "validate_douyin_reference", lambda value: value)
    monkeypatch.setattr(douyin_adapter, "validate_public_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(douyin_adapter, "_resolve_bounded_redirects", resolved)
    monkeypatch.setattr(douyin_adapter, "_launch_context", launched)
    monkeypatch.setattr(douyin_adapter, "_close_context", closed)


@pytest.mark.asyncio
async def test_direct_work_link_rejects_redirect_to_a_different_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    wrong = "2222222222222222222"
    media_url = "https://media.example.com/wrong.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{wrong}",
        detail_payload={"aweme_detail": _aweme(wrong, media_url)},
        dom_media_url=media_url,
    )

    with pytest.raises(ValueError, match="exact work identity"):
        await douyin_adapter.resolve_douyin_video(f"https://www.douyin.com/video/{requested}")


@pytest.mark.asyncio
async def test_generic_first_video_dom_fallback_cannot_prove_exact_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={},
        dom_media_url="https://media.example.com/recommended-first-video.mp4",
    )

    with pytest.raises(ValueError, match="exact work identity"):
        await douyin_adapter.resolve_douyin_video(f"https://www.douyin.com/video/{requested}")


@pytest.mark.asyncio
async def test_error_page_cannot_promote_an_unrelated_captured_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    unrelated = "2222222222222222222"
    media_url = "https://media.example.com/unrelated.mp4"
    _install_video_page(
        monkeypatch,
        final_url="https://www.douyin.com/",
        detail_payload={"aweme_detail": _aweme(unrelated, media_url)},
        dom_media_url=media_url,
    )

    with pytest.raises(ValueError, match="exact work identity"):
        await douyin_adapter.resolve_douyin_video(f"https://www.douyin.com/video/{requested}")


@pytest.mark.asyncio
async def test_expected_account_author_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    media_url = "https://media.example.com/exact.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={
            "aweme_detail": _aweme(
                requested,
                media_url,
                author_sec_uid="observed-wrong-author",
            )
        },
        dom_media_url=media_url,
    )

    with pytest.raises(ValueError, match="account author"):
        await douyin_adapter.resolve_douyin_video(
            f"https://www.douyin.com/video/{requested}",
            expected_account_sec_uid="expected-author",
        )


@pytest.mark.asyncio
async def test_successful_resolution_emits_three_way_identity_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    media_url = "https://media.example.com/exact.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={"aweme_detail": _aweme(requested, media_url)},
        dom_media_url="https://media.example.com/irrelevant-dom-video.mp4",
    )

    resolved_media, metadata, _cookies = await douyin_adapter.resolve_douyin_video(
        f"https://www.douyin.com/video/{requested}",
        expected_account_sec_uid="author-sec-uid",
    )

    assert resolved_media == media_url
    assert metadata["requested_work_id"] == requested
    assert metadata["resolved_work_id"] == requested
    assert metadata["observed_work_id"] == requested
    assert metadata["author_sec_uid"] == "author-sec-uid"
    assert metadata["identity_verification"] == "api_work_and_author_match"


@pytest.mark.asyncio
async def test_foreign_origin_detail_response_cannot_prove_douyin_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    media_url = "https://media.example.com/exact.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={"aweme_detail": _aweme(requested, media_url)},
        dom_media_url=media_url,
        response_url="https://evil.example/aweme/v1/web/aweme/detail/",
    )

    with pytest.raises(ValueError, match="exact work identity"):
        await douyin_adapter.resolve_douyin_video(f"https://www.douyin.com/video/{requested}")


@pytest.mark.asyncio
async def test_non_success_detail_response_cannot_prove_douyin_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    media_url = "https://media.example.com/exact.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={"aweme_detail": _aweme(requested, media_url)},
        dom_media_url=media_url,
        response_status=500,
    )

    with pytest.raises(ValueError, match="exact work identity"):
        await douyin_adapter.resolve_douyin_video(f"https://www.douyin.com/video/{requested}")


@pytest.mark.asyncio
async def test_douyin_business_error_payload_cannot_prove_work_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    media_url = "https://media.example.com/exact.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={
            "status_code": 10001,
            "aweme_detail": _aweme(requested, media_url),
        },
        dom_media_url=media_url,
    )

    with pytest.raises(ValueError, match="exact work identity"):
        await douyin_adapter.resolve_douyin_video(f"https://www.douyin.com/video/{requested}")


@pytest.mark.asyncio
async def test_short_link_binds_http_resolved_final_and_observed_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    media_url = "https://media.example.com/exact.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{requested}",
        resolved_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={"status_code": 0, "aweme_detail": _aweme(requested, media_url)},
        dom_media_url=media_url,
    )

    _media, metadata, _cookies = await douyin_adapter.resolve_douyin_video("https://v.douyin.com/short-reference")

    assert metadata["requested_work_id"] == requested
    assert metadata["resolved_work_id"] == requested
    assert metadata["observed_work_id"] == requested


@pytest.mark.asyncio
async def test_short_link_rejects_resolved_work_a_but_final_work_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested = "1111111111111111111"
    wrong = "2222222222222222222"
    media_url = "https://media.example.com/wrong.mp4"
    _install_video_page(
        monkeypatch,
        final_url=f"https://www.douyin.com/video/{wrong}",
        resolved_url=f"https://www.douyin.com/video/{requested}",
        detail_payload={"status_code": 0, "aweme_detail": _aweme(wrong, media_url)},
        dom_media_url=media_url,
    )

    with pytest.raises(ValueError, match="exact work identity"):
        await douyin_adapter.resolve_douyin_video("https://v.douyin.com/short-reference")


def test_video_source_contract_rejects_inconsistent_identity_claim() -> None:
    with pytest.raises(ValidationError, match="work identity"):
        VideoSource.model_validate(
            {
                "ref": "https://www.douyin.com/video/1111111111111111111",
                "requested_work_id": "1111111111111111111",
                "resolved_work_id": "2222222222222222222",
                "observed_work_id": "1111111111111111111",
                "author_sec_uid": "author-sec-uid-123456",
                "identity_verification": "api_work_id_match",
                "observed_at": "2026-08-02T00:00:00+00:00",
                "trust": "untrusted_source_data",
                "public_metadata": {},
            }
        )


@pytest.mark.parametrize(
    "ref",
    [
        "https://evil.example/video/1111111111111111111",
        "https://www.douyin.com/search/video/1111111111111111111",
        "https://www.douyin.com/video/1111111111111111111/extra",
        "https://www.douyin.com/search?q=/video/1111111111111111111",
    ],
)
def test_video_source_identity_requires_canonical_douyin_work_ref(ref: str) -> None:
    with pytest.raises(ValidationError, match="canonical source reference"):
        VideoSource.model_validate(
            {
                "ref": ref,
                "requested_work_id": "1111111111111111111",
                "resolved_work_id": "1111111111111111111",
                "observed_work_id": "1111111111111111111",
                "author_sec_uid": "author-sec-uid-123456",
                "identity_verification": "api_work_id_match",
                "observed_at": "2026-08-02T00:00:00+00:00",
                "trust": "untrusted_source_data",
                "public_metadata": {},
            }
        )


def test_zero_scene_boundaries_after_successful_scan_is_valid_zero() -> None:
    result = subprocess.CompletedProcess(["ffmpeg"], 0, stdout="", stderr="")

    boundaries, truncated, completed = reference_evidence._parse_scene_detection_result(
        result,
        duration_seconds=60.0,
    )

    assert boundaries == []
    assert truncated is False
    assert completed is True


def test_failed_scene_command_never_counts_parsed_timestamps() -> None:
    result = subprocess.CompletedProcess(
        ["ffmpeg"],
        1,
        stdout="",
        stderr="pts_time:1.0 pts_time:2.0",
    )

    boundaries, truncated, completed = reference_evidence._parse_scene_detection_result(
        result,
        duration_seconds=60.0,
    )

    assert boundaries == []
    assert truncated is False
    assert completed is False


def test_scene_boundary_cap_is_explicitly_truncated() -> None:
    stderr = " ".join(f"pts_time:{index / 2:.1f}" for index in range(1, 103))
    result = subprocess.CompletedProcess(["ffmpeg"], 0, stdout="", stderr=stderr)

    boundaries, truncated, completed = reference_evidence._parse_scene_detection_result(
        result,
        duration_seconds=60.0,
    )

    assert len(boundaries) == 100
    assert truncated is True
    assert completed is True


def test_external_sanitizer_reports_every_information_limit() -> None:
    deeply_nested: Any = "leaf"
    for _ in range(8):
        deeply_nested = {"child": deeply_nested}
    value = {
        "long_text": "x" * 2_500,
        "long_list": list(range(120)),
        "large_object": {f"key-{index}": index for index in range(120)},
        "deep": deeply_nested,
    }

    sanitized, reason_codes = reference_evidence._sanitize_external_with_report(value)

    assert len(sanitized["long_text"]) == 2_000
    assert len(sanitized["long_list"]) == 100
    assert len(sanitized["large_object"]) == 100
    assert set(reason_codes) == {
        "EXTERNAL_TEXT_TRUNCATED",
        "EXTERNAL_LIST_TRUNCATED",
        "EXTERNAL_OBJECT_TRUNCATED",
        "EXTERNAL_DEPTH_TRUNCATED",
    }


def test_agent_view_keeps_bounded_semantic_evidence_for_completed_provider_stages() -> None:
    item = _valid_reference_item(analysis_depth="full")
    item["provider_evidence"] = {
        "asr": {
            "trust": "untrusted_source_data",
            "provider": "volcengine-mediakit",
            "input_binding": "content_sha256_verified",
            "input_content_sha256": "a" * 64,
            "payload": {
                "transcript": "第一句真实台词" + "x" * 20_000 + "TAIL_SENTINEL",
            },
        },
        "ocr": {
            "trust": "untrusted_source_data",
            "provider": "volcengine-mediakit",
            "input_binding": "content_sha256_verified",
            "input_content_sha256": "a" * 64,
            "payload": {"texts": ["门店字幕"]},
        },
        "scene_segmentation": {
            "trust": "untrusted_source_data",
            "provider": "volcengine-mediakit",
            "input_binding": "content_sha256_verified",
            "input_content_sha256": "a" * 64,
            "payload": {
                "segments": [
                    {"start_time": 0, "end_time": 2, "summary": "人物进门"},
                    {"start_time": 2, "end_time": 5, "summary": "人物转身"},
                ]
            },
        },
        "storyline": {
            "trust": "untrusted_source_data",
            "provider": "volcengine-mediakit",
            "input_binding": "content_sha256_verified",
            "input_content_sha256": "a" * 64,
            "payload": {"summary": "人物目标发生变化"},
        },
    }
    payload = _valid_reference_evidence(item)

    summary = evidence_mcp._reference_video_model_summary(payload)
    encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))

    assert "第一句真实台词" in encoded
    assert "门店字幕" in encoded
    assert "人物目标发生变化" in encoded
    assert "TAIL_SENTINEL" not in encoded
    for stage in ("asr", "ocr", "scene_segmentation", "storyline"):
        projected = summary["items"][0]["provider_evidence_summary"][stage]
        assert projected["trust"] == "untrusted_source_data"
        assert projected["semantic_content_available"] is True
        assert projected["coverage_status"] == "completed"


def test_realistic_mediakit_asr_receipt_validates_through_reference_evidence() -> None:
    evidence = _realistic_mediakit_asr_evidence()

    receipt = evidence.items[0].provider_evidence["asr"].execution_receipt

    assert receipt is not None
    assert receipt.result_normalization_version == "mediakit-cloud-semantic-allowlist-v2"
    assert receipt.result_transport == "bounded_provider_https"
    assert isinstance(receipt.result_file_size_bytes, int)
    assert receipt.result_file_content_type == "application/json"


def test_provider_result_file_metadata_is_complete_strict_and_bounded() -> None:
    receipt = _realistic_mediakit_asr_evidence().items[0].provider_evidence["asr"].execution_receipt
    assert receipt is not None
    raw = receipt.model_dump(mode="python")

    wrong_type = {**raw, "result_file_size_bytes": str(raw["result_file_size_bytes"])}
    with pytest.raises(ValidationError, match="result_file_size_bytes"):
        ProviderExecutionReceipt.model_validate(wrong_type)

    oversized = {**raw, "result_file_size_bytes": 2 * 1024 * 1024 + 1}
    with pytest.raises(ValidationError, match="result_file_size_bytes"):
        ProviderExecutionReceipt.model_validate(oversized)

    incomplete = {**raw, "result_file_content_type": None}
    with pytest.raises(ValidationError, match="complete set"):
        ProviderExecutionReceipt.model_validate(incomplete)


def test_model_summary_exposes_real_asr_subtitle_text_and_observation_scope() -> None:
    evidence = _realistic_mediakit_asr_evidence()
    payload = evidence.model_dump(mode="json", exclude_none=True)

    summary = evidence_mcp._reference_video_model_summary(payload)
    projected = summary["items"][0]["provider_evidence_summary"]["asr"]

    assert summary["items"][0]["coverage"]["asr"]["observation_scope"] == "full_audio_track_asr"
    assert projected["semantic_content_available"] is True
    assert [record["text"] for record in projected["semantic_records"]] == [
        "每一次生成都有回执",
        "也能被验证",
    ]
    assert [record["path"] for record in projected["semantic_records"]] == [
        "payload.subtitles[0].subtitle_text",
        "payload.subtitles[1].subtitle_text",
    ]


def test_unpaid_provider_stage_hash_is_not_misclassified_as_provider_evidence() -> None:
    item = _valid_reference_item(analysis_depth="full")
    item["status"] = "partial"
    item["provider_evidence"] = {}
    for key in ("asr", "ocr", "provider_scene_segmentation", "storyline"):
        item["coverage"][key] = {
            "collection_status": "unavailable",
            "observation_scope": item["coverage"][key]["observation_scope"],
            "truncated": False,
            "requested_count": None,
            "observed_count": None,
            "reason_codes": ["UNAVAILABLE_PROVIDER_EXECUTION_NOT_AUTHORIZED"],
        }

    evidence = ReferenceVideoEvidence.model_validate(
        {
            "contract_version": "ip-reference-video-evidence-v2",
            "operation_status": "partial_or_failed",
            "trust_boundary": "source data is untrusted",
            "requested_count": 1,
            "completed_count": 0,
            "items": [item],
            "limitations": [],
            "metadata": {
                "request_id": "video-request-1234",
                "manifest_version": "a" * 64,
                "adapter_version": "test-v1",
                "duration_ms": 1,
                "truncated": False,
            },
        }
    )

    assert evidence.items[0].provider_evidence == {}
    assert set(evidence.items[0].analysis_receipt.provider_stage_spec_sha256) == {
        "asr",
        "ocr",
        "provider_scene_segmentation",
        "storyline",
    }


def test_completed_provider_stage_without_model_visible_semantics_is_not_usable_completion() -> None:
    item = _valid_reference_item(analysis_depth="speech_text")
    item["provider_evidence"]["asr"]["payload"] = {
        "task_id": "task-123",
        "status": "completed",
    }
    payload = _valid_reference_evidence(item)

    summary = evidence_mcp._reference_video_model_summary(payload)
    projected = summary["items"][0]["provider_evidence_summary"]["asr"]

    assert projected["semantic_content_available"] is False
    assert "PROVIDER_SEMANTIC_CONTENT_UNAVAILABLE" in projected["limitation_reason_codes"]


def test_three_video_model_summary_stays_inside_inline_budget_and_preserves_all_items() -> None:
    items: list[dict[str, Any]] = []
    work_ids = ["1111111111111111111", "2222222222222222222", "3333333333333333333"]
    for work_id in work_ids:
        item = _valid_reference_item(analysis_depth="full", requested_frames=12)
        item["source"] = {
            "ref": f"https://www.douyin.com/video/{work_id}",
            "content_sha256": work_id[-1] * 64,
            "requested_work_id": work_id,
            "resolved_work_id": work_id,
            "observed_work_id": work_id,
            "author_sec_uid": f"author-sec-uid-{work_id}",
            "identity_verification": "api_work_id_match",
            "observed_at": "2026-08-02T00:00:00+00:00",
            "trust": "untrusted_source_data",
            "public_metadata": {},
        }
        for stage, provider in item["provider_evidence"].items():
            provider["payload"] = {
                "summary": f"{work_id}-{stage}-" + "语义" * 2_000,
            }
        items.append(item)
    payload = {
        **_valid_reference_evidence(items[0]),
        "requested_count": 3,
        "completed_count": 3,
        "items": items,
    }

    summary = evidence_mcp._reference_video_model_summary(payload)
    encoded = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))

    assert len(encoded) <= 12_000
    for work_id, item in zip(work_ids, summary["items"], strict=True):
        assert work_id in encoded
        assert item["source"]["observed_work_id"] == work_id
        assert item["status"] == "ok"
        assert item["coverage"]
        assert item["provider_evidence_summary"]


def test_completed_coverage_rejects_observed_less_than_requested() -> None:
    with pytest.raises(ValidationError, match="completed coverage"):
        CoverageRecord.model_validate(
            {
                "collection_status": "completed",
                "observation_scope": "uniform_point_samples",
                "requested_count": 8,
                "observed_count": 1,
                "truncated": False,
                "reason_codes": [],
            }
        )


def test_ok_item_requires_artifacts_claimed_by_completed_coverage() -> None:
    item = _valid_reference_item()
    item["media_metadata"] = None
    item["visual_samples"] = []
    item["contact_sheet_ref"] = None
    item["contact_sheet_sha256"] = None

    with pytest.raises(ValidationError, match="completed coverage"):
        ReferenceVideoEvidence.model_validate(_valid_reference_evidence(item))


@pytest.mark.parametrize("mutation", ["missing_frame", "receipt_count", "duplicate_frame"])
def test_completed_frame_coverage_must_match_frames_and_receipt(mutation: str) -> None:
    item = _valid_reference_item(requested_frames=8)
    if mutation == "missing_frame":
        item["visual_samples"] = item["visual_samples"][:-1]
    elif mutation == "receipt_count":
        item["analysis_receipt"]["requested_frames"] = 4
    else:
        item["visual_samples"][1] = deepcopy(item["visual_samples"][0])

    with pytest.raises(ValidationError, match="frame"):
        ReferenceVideoEvidence.model_validate(_valid_reference_evidence(item))


@pytest.mark.parametrize(
    ("coverage_key", "provider_key"),
    [
        ("asr", "asr"),
        ("ocr", "ocr"),
        ("provider_scene_segmentation", "scene_segmentation"),
        ("storyline", "storyline"),
    ],
)
def test_completed_provider_coverage_requires_matching_provider_payload(
    coverage_key: str,
    provider_key: str,
) -> None:
    item = _valid_reference_item(analysis_depth="full")
    del item["provider_evidence"][provider_key]

    with pytest.raises(ValidationError, match=coverage_key):
        ReferenceVideoEvidence.model_validate(_valid_reference_evidence(item))


def test_provider_sealed_snapshot_with_bound_receipt_can_claim_completed_coverage() -> None:
    item = _valid_reference_item(analysis_depth="speech_text")
    provider = item["provider_evidence"]["asr"]
    provider["provider"] = "volcengine-mediakit"
    provider["input_binding"] = "sealed_local_snapshot_provider_unattested"
    provider["execution_receipt"] = {
        "adapter_version": "official-mediakit-cloud-video-v1",
        "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
        "executor": "official-mediakit-cli",
        "execution_mode": "cloud",
        "capability": "asr",
        "source_sha256": "a" * 64,
        "mediakit_sha256": "b" * 64,
        "stage_spec_sha256": "1" * 64,
        "submission_sha256": "c" * 64,
        "result_sha256": _canonical_sha256(provider["payload"]),
        "task_id_sha256": "e" * 64,
        "provider_input_attestation": "not_provided",
        "polling_mode": "caller_deadline_single_query",
        "result_transport": "inline",
    }

    validated = ReferenceVideoEvidence.model_validate(_valid_reference_evidence(item))

    assert validated.operation_status == "ok"
    assert validated.items[0].coverage.asr.collection_status == "completed"


def test_provider_execution_receipt_must_match_stage_specification() -> None:
    item = _valid_reference_item(analysis_depth="speech_text")
    item["coverage"]["asr"] = {
        "collection_status": "partial",
        "observation_scope": "full_audio_track_asr",
        "truncated": False,
        "requested_count": None,
        "observed_count": None,
        "reason_codes": ["PROVIDER_CONTENT_HASH_NOT_ATTESTED"],
    }
    provider = item["provider_evidence"]["asr"]
    provider["provider"] = "volcengine-mediakit"
    provider["input_binding"] = "sealed_local_snapshot_provider_unattested"
    provider["execution_receipt"] = {
        "adapter_version": "official-mediakit-cloud-video-v1",
        "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
        "executor": "official-mediakit-cli",
        "execution_mode": "cloud",
        "capability": "asr",
        "source_sha256": "a" * 64,
        "mediakit_sha256": "b" * 64,
        "stage_spec_sha256": "9" * 64,
        "submission_sha256": "c" * 64,
        "result_sha256": _canonical_sha256(provider["payload"]),
        "task_id_sha256": "e" * 64,
        "provider_input_attestation": "not_provided",
        "polling_mode": "caller_deadline_single_query",
        "result_transport": "inline",
    }
    item["status"] = "partial"
    evidence = _valid_reference_evidence(item)
    evidence["operation_status"] = "partial_or_failed"
    evidence["completed_count"] = 0
    evidence["limitations"] = ["provider content hash not attested"]

    with pytest.raises(ValidationError, match="stage specification"):
        ReferenceVideoEvidence.model_validate(evidence)


def test_provider_execution_receipt_must_bind_exposed_payload() -> None:
    item = _valid_reference_item(analysis_depth="speech_text")
    item["coverage"]["asr"] = {
        "collection_status": "partial",
        "observation_scope": "full_audio_track_asr",
        "truncated": False,
        "requested_count": None,
        "observed_count": None,
        "reason_codes": ["PROVIDER_CONTENT_HASH_NOT_ATTESTED"],
    }
    provider = item["provider_evidence"]["asr"]
    provider["provider"] = "volcengine-mediakit"
    provider["input_binding"] = "sealed_local_snapshot_provider_unattested"
    provider["execution_receipt"] = {
        "adapter_version": "official-mediakit-cloud-video-v1",
        "result_normalization_version": "mediakit-cloud-semantic-allowlist-v2",
        "executor": "official-mediakit-cli",
        "execution_mode": "cloud",
        "capability": "asr",
        "source_sha256": "a" * 64,
        "mediakit_sha256": "b" * 64,
        "stage_spec_sha256": "1" * 64,
        "submission_sha256": "c" * 64,
        "result_sha256": "d" * 64,
        "task_id_sha256": "e" * 64,
        "provider_input_attestation": "not_provided",
        "polling_mode": "caller_deadline_single_query",
        "result_transport": "inline",
    }
    item["status"] = "partial"
    evidence = _valid_reference_evidence(item)
    evidence["operation_status"] = "partial_or_failed"
    evidence["completed_count"] = 0
    evidence["limitations"] = ["provider content hash not attested"]

    with pytest.raises(ValidationError, match="payload"):
        ReferenceVideoEvidence.model_validate(evidence)


def test_ok_public_video_requires_content_hash_and_verified_source_identity() -> None:
    work_id = "1111111111111111111"
    item = _valid_reference_item()
    item["source"] = {
        "ref": f"https://www.douyin.com/video/{work_id}",
        "content_sha256": None,
        "requested_work_id": work_id,
        "resolved_work_id": work_id,
        "observed_work_id": work_id,
        "author_sec_uid": "author-sec-uid-123456",
        "identity_verification": "api_work_id_match",
        "observed_at": "2026-08-02T00:00:00+00:00",
        "trust": "untrusted_source_data",
        "public_metadata": {},
    }

    with pytest.raises(ValidationError, match="content hash"):
        ReferenceVideoEvidence.model_validate(_valid_reference_evidence(item))


def test_contract_rejects_inconsistent_top_level_completion_claim() -> None:
    item = _valid_reference_item(requested_frames=8)
    item["status"] = "partial"
    item["visual_samples"] = item["visual_samples"][:1]
    item["coverage"]["sampled_frames"] = {
        "collection_status": "partial",
        "observation_scope": "uniform_point_samples",
        "truncated": True,
        "requested_count": 8,
        "observed_count": 1,
        "reason_codes": ["FRAME_EXTRACTION_INCOMPLETE"],
    }
    evidence = _valid_reference_evidence(item)
    evidence["operation_status"] = "ok"
    evidence["completed_count"] = 1
    evidence["limitations"] = ["partial sampling"]
    evidence["metadata"]["truncated"] = True

    with pytest.raises(ValidationError, match="completed_count"):
        ReferenceVideoEvidence.model_validate(evidence)
