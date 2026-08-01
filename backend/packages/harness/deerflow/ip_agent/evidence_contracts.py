"""Versioned semantic contracts for the IP Agent evidence MCP.

These models are the single source of truth shared by collectors, MCP output
schemas and tests.  They describe observations only; no field is allowed to
carry positioning, virality predictions or creative conclusions.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BENCHMARK_ACCOUNT_CONTRACT_VERSION = "ip-benchmark-account-evidence-v1"
REFERENCE_VIDEO_CONTRACT_VERSION = "ip-reference-video-evidence-v1"
EVIDENCE_ADAPTER_VERSION = "douyin-public-web-v1"


class EvidenceModel(BaseModel):
    """Strict base class so collectors cannot silently add semantic claims."""

    model_config = ConfigDict(extra="forbid")


class EvidenceError(EvidenceModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class EvidenceMetadata(EvidenceModel):
    request_id: str = Field(min_length=12, max_length=80)
    manifest_version: str = Field(min_length=16, max_length=80)
    adapter_version: str = Field(min_length=1, max_length=80)
    duration_ms: float = Field(ge=0)
    truncated: bool = False


class BenchmarkSource(EvidenceModel):
    input_ref: str | None = None
    canonical_profile_ref: str | None = None
    account_sec_uid: str | None = None
    observed_at: str
    trust: Literal["untrusted_public_source"] = "untrusted_public_source"


class BenchmarkProfile(EvidenceModel):
    display_name: str | None = None
    visible_profile_text: str | None = None


class PublicEngagement(EvidenceModel):
    likes: int | float | None = None
    comments: int | float | None = None
    shares: int | float | None = None
    collects: int | float | None = None
    plays: int | float | None = None


class BenchmarkWork(EvidenceModel):
    work_id: str = Field(min_length=8, max_length=40)
    work_url: str
    visible_label: str | None = None
    title: str | None = None
    is_pinned: bool | None = None
    published_label: str | None = None
    published_at: str | None = None
    public_engagement: PublicEngagement | None = None
    ownership_evidence: Literal["api_author_match", "profile_dom_scope"]


class BenchmarkCoverage(EvidenceModel):
    requested_posts: int = Field(ge=1, le=12)
    observed_posts: int = Field(ge=0, le=12)
    profile_identity: Literal["observed", "unavailable"]
    public_work_inventory: Literal["partial", "unavailable"]
    ownership_verification: Literal["api_author_match", "profile_dom_scope", "unavailable"]
    metrics: Literal["partial", "unavailable"]


class BenchmarkAccountEvidence(EvidenceModel):
    contract_version: Literal["ip-benchmark-account-evidence-v1"]
    operation_status: Literal["ok", "needs_user_input", "failed"]
    platform: Literal["douyin"] = "douyin"
    source: BenchmarkSource
    profile: BenchmarkProfile
    works: list[BenchmarkWork] = Field(max_length=12)
    coverage: BenchmarkCoverage
    limitations: list[str] = Field(default_factory=list, max_length=20)
    next_action: str | None = None
    error: EvidenceError | None = None
    metadata: EvidenceMetadata


class CollectBenchmarkAccountInput(EvidenceModel):
    profile_url: str = Field(min_length=10, max_length=2_000)
    max_posts: int = Field(default=12, ge=1, le=12)


class VideoSource(EvidenceModel):
    ref: str
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observed_at: str
    trust: Literal["untrusted_source_data"] = "untrusted_source_data"
    public_metadata: dict[str, Any] = Field(default_factory=dict)


class MediaMetadata(EvidenceModel):
    duration_seconds: float = Field(gt=0, le=1200)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    frame_rate: float | None = Field(default=None, gt=0)
    video_codec: str | None = None
    has_audio: bool
    container: str | None = None
    size_bytes: int = Field(gt=0, le=209_715_200)


class VisualSample(EvidenceModel):
    at_seconds: float = Field(ge=0, le=1200)
    artifact_ref: str


class ProviderEvidence(EvidenceModel):
    trust: Literal["untrusted_source_data"] = "untrusted_source_data"
    provider: str
    payload: dict[str, Any] | None = None
    error: str | None = None


class ReferenceVideoItem(EvidenceModel):
    status: Literal["ok", "failed"]
    purpose: Literal["benchmark", "performance_test"]
    source: VideoSource
    media_metadata: MediaMetadata | None = None
    visual_samples: list[VisualSample] = Field(default_factory=list, max_length=12)
    contact_sheet_ref: str | None = None
    scene_boundaries_seconds: list[float] = Field(default_factory=list, max_length=100)
    provider_evidence: dict[str, ProviderEvidence] = Field(default_factory=dict)
    coverage: dict[str, str] = Field(default_factory=dict)
    error: EvidenceError | None = None
    next_action: str | None = None


class ReferenceVideoEvidence(EvidenceModel):
    contract_version: Literal["ip-reference-video-evidence-v1"]
    operation_status: Literal["ok", "partial_or_failed", "failed"]
    trust_boundary: str
    requested_count: int = Field(ge=1, le=3)
    completed_count: int = Field(ge=0, le=3)
    items: list[ReferenceVideoItem] = Field(min_length=1, max_length=3)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    metadata: EvidenceMetadata


class InspectReferenceVideosInput(EvidenceModel):
    video_refs: list[str] = Field(min_length=1, max_length=3)
    purpose: Literal["benchmark", "performance_test"] = "benchmark"
    analysis_depth: Literal["mechanical", "speech_text", "full"] = "full"
    max_frames: int = Field(default=8, ge=4, le=12)
