from __future__ import annotations

import base64
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from deerflow.ip_agent import evidence_mcp, reference_evidence
from deerflow.ip_agent.account_binding import (
    BindingKeyring,
    issue_account_binding,
    verify_account_binding,
    verify_video_against_binding,
)
from deerflow.ip_agent.evidence_contracts import InspectReferenceVideosInput

_ACCOUNT_UID = "MS4wLjABAAAAaccount-sec-uid-123456"
_WORK_ID = "7531000000000000001"
_OTHER_WORK_ID = "7531000000000000002"


def _keyring() -> BindingKeyring:
    return BindingKeyring(active_kid="test-a", keys={"test-a": b"a" * 32})


def _install_binding_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IP_AGENT_EVIDENCE_BINDING_ACTIVE_KID", "test-a")
    monkeypatch.setenv(
        "IP_AGENT_EVIDENCE_BINDING_KEYS_JSON",
        json.dumps({"test-a": base64.urlsafe_b64encode(b"a" * 32).decode("ascii").rstrip("=")}),
    )


def _account_observation() -> dict[str, object]:
    return {
        "contract_version": "ip-benchmark-account-evidence-v2",
        "operation_status": "ok",
        "platform": "douyin",
        "source": {
            "input_ref": "https://v.douyin.com/example/",
            "canonical_profile_ref": f"https://www.douyin.com/user/{_ACCOUNT_UID}",
            "account_sec_uid": _ACCOUNT_UID,
            "observed_at": "2026-08-02T00:00:00+00:00",
            "trust": "untrusted_public_source",
        },
        "profile": {"display_name": "真实账号", "visible_profile_text": None},
        "works": [
            {
                "work_id": _WORK_ID,
                "work_url": f"https://www.douyin.com/video/{_WORK_ID}",
                "ownership_evidence": "api_author_match",
            }
        ],
        "coverage": {
            "requested_posts": 12,
            "observed_posts": 1,
            "profile_identity": "observed",
            "public_work_inventory": "partial",
            "ownership_verification": "api_author_match",
            "metrics": "unavailable",
        },
        "limitations": [],
        "metadata": {
            "request_id": "acct-123456789012",
            "manifest_version": "f" * 64,
            "adapter_version": "test-v2",
            "duration_ms": 1.0,
            "truncated": False,
        },
    }


def test_binding_survives_a_new_verifier_with_the_same_configured_key() -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
        ttl_seconds=1_800,
    )

    verified = verify_account_binding(
        issued.receipt,
        keyring=BindingKeyring(active_kid="test-a", keys={"test-a": b"a" * 32}),
        now=1_785_680_100,
    )

    assert verified.account_sec_uid == _ACCOUNT_UID
    assert [work.work_id for work in verified.works] == [_WORK_ID]
    assert verified.identity_claims_sha256 == issued.identity_claims_sha256


@pytest.mark.parametrize("segment", [1, 2, 3])
def test_binding_rejects_tampered_kid_payload_or_signature(segment: int) -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    parts = issued.receipt.split(".")
    parts[segment] = parts[segment][:-1] + ("A" if parts[segment][-1] != "A" else "B")

    with pytest.raises(ValueError, match="binding"):
        verify_account_binding(".".join(parts), keyring=_keyring(), now=1_785_680_100)


def test_binding_rejects_noncanonical_equivalent_signature_segment() -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    parts = issued.receipt.split(".")
    signature = parts[3]
    decoded = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    equivalent = next(candidate for character in alphabet if (candidate := signature[:-1] + character) != signature and base64.urlsafe_b64decode(candidate + "=" * (-len(candidate) % 4)) == decoded)
    parts[3] = equivalent

    with pytest.raises(ValueError, match="invalid encoded segment"):
        verify_account_binding(".".join(parts), keyring=_keyring(), now=1_785_680_100)


def test_binding_rejects_expiry_and_cannot_downgrade_to_unbound() -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
        ttl_seconds=60,
    )

    with pytest.raises(ValueError, match="expired"):
        verify_account_binding(
            issued.receipt,
            keyring=_keyring(),
            now=1_785_680_091,
        )


def test_binding_rejects_work_outside_inventory_before_media_download() -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    binding = verify_account_binding(
        issued.receipt,
        keyring=_keyring(),
        now=1_785_680_100,
    )

    with pytest.raises(ValueError, match="inventory"):
        verify_video_against_binding(
            binding,
            requested_work_id=_OTHER_WORK_ID,
            resolved_work_id=_OTHER_WORK_ID,
            observed_work_id=_OTHER_WORK_ID,
            observed_author_sec_uid=_ACCOUNT_UID,
            canonical_work_ref=f"https://www.douyin.com/video/{_OTHER_WORK_ID}",
        )


def test_binding_rejects_author_mismatch_even_for_inventory_work() -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    binding = verify_account_binding(
        issued.receipt,
        keyring=_keyring(),
        now=1_785_680_100,
    )

    with pytest.raises(ValueError, match="author"):
        verify_video_against_binding(
            binding,
            requested_work_id=_WORK_ID,
            resolved_work_id=_WORK_ID,
            observed_work_id=_WORK_ID,
            observed_author_sec_uid="MS4wLjABAAAAwrong-author-123456",
            canonical_work_ref=f"https://www.douyin.com/video/{_WORK_ID}",
        )


def test_account_inventory_mode_requires_binding_and_standalone_rejects_it() -> None:
    with pytest.raises(ValidationError, match="account_binding_receipt"):
        InspectReferenceVideosInput.model_validate(
            {
                "video_refs": [f"https://www.douyin.com/video/{_WORK_ID}"],
                "reference_context": "account_inventory_item",
            }
        )

    with pytest.raises(ValidationError, match="standalone_reference"):
        InspectReferenceVideosInput.model_validate(
            {
                "video_refs": [f"https://www.douyin.com/video/{_WORK_ID}"],
                "reference_context": "standalone_reference",
                "account_binding_receipt": "dfab1.test.invalid-payload.invalid-signature",
            }
        )


def test_caller_supplied_expected_author_is_no_longer_a_public_input() -> None:
    payload = {
        "video_refs": [f"https://www.douyin.com/video/{_WORK_ID}"],
        "expected_account_sec_uid": _ACCOUNT_UID,
    }

    with pytest.raises(ValidationError, match="expected_account_sec_uid"):
        InspectReferenceVideosInput.model_validate(payload)


def test_identity_projection_changes_when_inventory_changes() -> None:
    first = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    changed = deepcopy(_account_observation())
    changed["works"] = [
        {
            "work_id": _OTHER_WORK_ID,
            "work_url": f"https://www.douyin.com/video/{_OTHER_WORK_ID}",
            "ownership_evidence": "api_author_match",
        }
    ]
    second = issue_account_binding(
        changed,
        keyring=_keyring(),
        now=1_785_680_000,
    )

    assert first.identity_claims_sha256 != second.identity_claims_sha256


@pytest.mark.asyncio
async def test_successful_account_collection_issues_a_verifiable_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_binding_environment(monkeypatch)
    monkeypatch.setattr(reference_evidence, "_validate_douyin_reference", lambda value: value)

    async def fetcher(
        _profile_url: str,
        _max_posts: int,
        _session_hint: str | None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "url": f"https://www.douyin.com/user/{_ACCOUNT_UID}",
                "account_sec_uid": _ACCOUNT_UID,
                "headings": ["真实账号"],
                "visible_text": "公开简介",
                "api_works": [
                    {
                        "work_id": _WORK_ID,
                        "work_url": f"https://www.douyin.com/video/{_WORK_ID}",
                        "ownership_evidence": "api_author_match",
                    }
                ],
            }
        ]

    payload = await reference_evidence.collect_douyin_benchmark_account(
        "https://v.douyin.com/example/",
        page_fetcher=fetcher,
    )
    binding = verify_account_binding(
        payload["account_binding"]["receipt"],
        keyring=_keyring(),
    )

    assert payload["contract_version"] == "ip-benchmark-account-evidence-v2"
    assert binding.account_sec_uid == _ACCOUNT_UID
    assert binding.works[0].work_id == _WORK_ID


@pytest.mark.asyncio
async def test_account_inventory_rejects_unbound_work_before_browser_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    binding = verify_account_binding(
        issued.receipt,
        keyring=_keyring(),
        now=1_785_680_100,
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    monkeypatch.setattr(
        reference_evidence,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, None),
    )
    monkeypatch.setattr(reference_evidence, "_validate_public_url", lambda *_args, **_kwargs: None)
    called = False

    async def resolver(*_args: Any, **_kwargs: Any):
        nonlocal called
        called = True
        raise AssertionError("resolver must not run")

    monkeypatch.setattr(reference_evidence, "_resolve_douyin_video_with_retry", resolver)

    with pytest.raises(ValueError, match="outside the collected inventory"):
        await reference_evidence._inspect_one_video(
            reference=f"https://www.douyin.com/video/{_OTHER_WORK_ID}",
            purpose="benchmark",
            analysis_depth="mechanical",
            max_frames=4,
            account_binding=binding,
        )

    assert called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference",
    [
        "https://media.example.com/video.mp4",
        "/mnt/user-data/uploads/video.mp4",
    ],
)
async def test_account_binding_never_applies_to_non_douyin_or_uploaded_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reference: str,
) -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    binding = verify_account_binding(
        issued.receipt,
        keyring=_keyring(),
        now=1_785_680_100,
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffprobe = tmp_path / "ffprobe"
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    monkeypatch.setattr(
        reference_evidence,
        "_toolchain_paths",
        lambda: (ffmpeg, ffprobe, None),
    )
    monkeypatch.setattr(reference_evidence, "_validate_public_url", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="Douyin inventory"):
        await reference_evidence._inspect_one_video(
            reference=reference,
            purpose="benchmark",
            analysis_depth="mechanical",
            max_frames=4,
            account_binding=binding,
        )


@pytest.mark.asyncio
async def test_mcp_inspect_handler_derives_account_constraint_from_signed_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issued = issue_account_binding(
        _account_observation(),
        keyring=_keyring(),
        now=1_785_680_000,
    )
    monkeypatch.setattr(evidence_mcp, "keyring_from_environment", _keyring)
    monkeypatch.setattr(
        evidence_mcp,
        "verify_account_binding",
        lambda receipt, *, keyring: verify_account_binding(
            receipt,
            keyring=keyring,
            now=1_785_680_100,
        ),
    )
    captured: dict[str, Any] = {}

    async def inspect(
        _video_refs: list[str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured["binding"] = kwargs["account_binding"]
        item = {
            "status": "ok",
            "purpose": "benchmark",
            "source": {
                "ref": f"https://www.douyin.com/video/{_WORK_ID}",
                "content_sha256": "a" * 64,
                "requested_work_id": _WORK_ID,
                "resolved_work_id": _WORK_ID,
                "observed_work_id": _WORK_ID,
                "author_sec_uid": _ACCOUNT_UID,
                "bound_account_sec_uid": _ACCOUNT_UID,
                "account_binding_verification": "hmac_account_work_binding_v1",
                "account_binding_id": captured["binding"].binding_id,
                "account_identity_claims_sha256": captured["binding"].identity_claims_sha256,
                "identity_verification": "api_work_and_author_match",
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
                "size_bytes": 1_024,
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
                "source_identity": _completed("identity"),
                "media_metadata": _completed("metadata"),
                "sampled_frames": _completed("frames", requested=4, observed=4),
                "contact_sheet": _completed("contact", requested=1, observed=1),
                "local_scene_detection": _completed("scene", observed=0),
                "asr": _not_requested("asr"),
                "ocr": _not_requested("ocr"),
                "provider_scene_segmentation": _not_requested("provider_scene"),
                "storyline": _not_requested("storyline"),
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

    monkeypatch.setattr(evidence_mcp, "inspect_reference_videos", inspect)
    result = await evidence_mcp._inspect_handler(
        InspectReferenceVideosInput(
            video_refs=[f"https://www.douyin.com/video/{_WORK_ID}"],
            reference_context="account_inventory_item",
            account_binding_receipt=issued.receipt,
            analysis_depth="mechanical",
        )
    )

    assert captured["binding"].account_sec_uid == _ACCOUNT_UID
    assert result.items[0].source.identity_verification == "api_work_and_author_match"


def _completed(
    scope: str,
    *,
    requested: int | None = None,
    observed: int | None = None,
) -> dict[str, Any]:
    return {
        "collection_status": "completed",
        "observation_scope": scope,
        "truncated": False,
        "requested_count": requested,
        "observed_count": observed,
        "reason_codes": [],
    }


def _not_requested(scope: str) -> dict[str, Any]:
    return {
        "collection_status": "not_requested",
        "observation_scope": scope,
        "truncated": False,
        "requested_count": None,
        "observed_count": None,
        "reason_codes": ["ANALYSIS_DEPTH_NOT_REQUESTED"],
    }
