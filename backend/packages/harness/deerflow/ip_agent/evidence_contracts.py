"""Versioned semantic contracts for the IP Agent evidence MCP.

These models are the single source of truth shared by collectors, MCP output
schemas and tests.  They describe observations only; no field is allowed to
carry positioning, virality predictions or creative conclusions.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .account_binding import AccountBindingEnvelope
from .mediakit_remux_ingress import MediaKitRemuxIngressReceipt
from .mediakit_video_understanding import VideoUnderstandingObservation

BENCHMARK_ACCOUNT_CONTRACT_VERSION = "ip-benchmark-account-evidence-v2"
REFERENCE_VIDEO_CONTRACT_VERSION = "ip-reference-video-evidence-v2"
EVIDENCE_ADAPTER_VERSION = "douyin-public-web-v1"

_PROVIDER_LOCATOR_RE = re.compile(r"(?i)(?:https?|mediakit|tos)://")
_CREDENTIAL_ASSIGNMENT_RE = re.compile(
    r"(?i)(?:\bbearer\s+\S+|\b(?:api[_-]?key|authorization|access[_-]?token|"
    r"refresh[_-]?token|token|cookies?|password|passwd|secret|signature|credential)"
    r"\b\s*[:=]\s*\S+)"
)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    contract_version: Literal["ip-benchmark-account-evidence-v2"]
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
    account_binding: AccountBindingEnvelope | None = None

    @model_validator(mode="after")
    def validate_account_binding(self) -> BenchmarkAccountEvidence:
        if self.coverage.observed_posts != len(self.works):
            raise ValueError("observed account work count must match the inventory")
        if self.operation_status == "ok":
            if not self.works or self.source.account_sec_uid is None:
                raise ValueError("successful account evidence requires an identified account inventory")
            if self.account_binding is None:
                raise ValueError("successful account evidence requires a server binding receipt")
        elif self.account_binding is not None:
            raise ValueError("incomplete account evidence cannot carry a binding receipt")
        return self


class CollectBenchmarkAccountInput(EvidenceModel):
    profile_url: str = Field(min_length=10, max_length=2_000)
    max_posts: int = Field(default=12, ge=1, le=12)


class VideoSource(EvidenceModel):
    ref: str
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    requested_work_id: str | None = Field(default=None, pattern=r"^[0-9]{8,40}$")
    resolved_work_id: str | None = Field(default=None, pattern=r"^[0-9]{8,40}$")
    observed_work_id: str | None = Field(default=None, pattern=r"^[0-9]{8,40}$")
    author_sec_uid: str | None = Field(default=None, min_length=16, max_length=200)
    bound_account_sec_uid: str | None = Field(default=None, min_length=16, max_length=200)
    account_binding_verification: Literal["hmac_account_work_binding_v1"] | None = None
    account_binding_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    account_identity_claims_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    identity_verification: Literal["api_work_id_match", "api_work_and_author_match"] | None = None
    observed_at: str
    trust: Literal["untrusted_source_data"] = "untrusted_source_data"
    public_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity_binding(self) -> VideoSource:
        work_ids = (
            self.requested_work_id,
            self.resolved_work_id,
            self.observed_work_id,
        )
        if any(work_ids):
            if not all(work_ids) or len(set(work_ids)) != 1:
                raise ValueError("video work identity must match across request, page and observation")
            parsed = urlsplit(self.ref)
            canonical_path = re.fullmatch(r"/video/([0-9]{8,40})", parsed.path)
            if (
                parsed.scheme != "https"
                or (parsed.hostname or "").lower() not in {"douyin.com", "www.douyin.com"}
                or parsed.port is not None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or canonical_path is None
                or canonical_path.group(1) != self.observed_work_id
            ):
                raise ValueError("video work identity must match the canonical source reference")
            if self.author_sec_uid is None or self.identity_verification is None:
                raise ValueError("video work identity requires an observed account author")
            binding_fields = (
                self.bound_account_sec_uid,
                self.account_binding_verification,
                self.account_binding_id,
                self.account_identity_claims_sha256,
            )
            if self.identity_verification == "api_work_and_author_match":
                if not all(binding_fields):
                    raise ValueError("video account-author match requires a verified account binding")
                if self.author_sec_uid != self.bound_account_sec_uid:
                    raise ValueError("video work identity does not match the expected account author")
            elif self.identity_verification == "api_work_id_match":
                if any(binding_fields):
                    raise ValueError("standalone video identity cannot claim an account binding")
            else:
                raise ValueError("video work identity requires an explicit verification level")
        elif any(
            value is not None
            for value in (
                self.author_sec_uid,
                self.bound_account_sec_uid,
                self.account_binding_verification,
                self.account_binding_id,
                self.account_identity_claims_sha256,
                self.identity_verification,
            )
        ):
            raise ValueError("video work identity fields require three matching work ids")
        return self


class MediaMetadata(EvidenceModel):
    duration_seconds: float = Field(gt=0, le=1200)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    frame_rate: float | None = Field(default=None, gt=0)
    video_codec: str | None = None
    has_audio: bool
    container: str | None = None
    size_bytes: int = Field(gt=0, le=209_715_200)


class RemuxArtifactCandidate(EvidenceModel):
    """A hash-bound derivative; it never replaces the original source fact."""

    contract_version: Literal["ip-remux-artifact-candidate-v1"] = "ip-remux-artifact-candidate-v1"
    artifact_kind: Literal["provider_remux_derivative"] = "provider_remux_derivative"
    derived_from_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_size_bytes: int = Field(strict=True, gt=0, le=209_715_200)
    media_metadata: MediaMetadata
    transform_receipt: MediaKitRemuxIngressReceipt
    transform_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_url_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: str
    provider_content_attestation: Literal["unavailable"] = "unavailable"
    semantic_equivalence: Literal["not_established"] = "not_established"

    @model_validator(mode="after")
    def validate_transform_bindings(self) -> RemuxArtifactCandidate:
        receipt = self.transform_receipt
        if receipt.derived_from_source_sha256 != self.derived_from_source_sha256:
            raise ValueError("remux transform receipt must bind the original source hash")
        if receipt.runtime_url_sha256 != self.runtime_url_sha256:
            raise ValueError("remux artifact must bind the provider input-reference hash")
        if receipt.expires_at.isoformat() != self.expires_at:
            raise ValueError("remux artifact expiry must match the transform receipt")
        if self.media_metadata.size_bytes != self.artifact_size_bytes:
            raise ValueError("remux artifact size must match its measured metadata")
        receipt_sha256 = _canonical_sha256(receipt.model_dump(mode="json", exclude_none=True))
        if receipt_sha256 != self.transform_receipt_sha256:
            raise ValueError("remux artifact transform receipt digest is invalid")
        return self


class VideoUnderstandingProviderInference(EvidenceModel):
    """A partial provider inference bound through one remux candidate."""

    contract_version: Literal["ip-video-understanding-provider-inference-v1"] = "ip-video-understanding-provider-inference-v1"
    trust: Literal["untrusted_source_data"] = "untrusted_source_data"
    observation_kind: Literal["provider_inference"] = "provider_inference"
    provider: Literal["volcengine-mediakit-video-understanding-chat"] = "volcengine-mediakit-video-understanding-chat"
    collection_status: Literal["partial"] = "partial"
    input_binding: Literal["remux_runtime_url_provider_unattested"] = "remux_runtime_url_provider_unattested"
    original_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    remux_transform_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_input_ref_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation: VideoUnderstandingObservation

    @model_validator(mode="after")
    def validate_inference_bindings(self) -> VideoUnderstandingProviderInference:
        if self.observation.source_sha256 != self.candidate_artifact_sha256:
            raise ValueError("video understanding must bind the remux artifact hash")
        if self.observation.receipt.provider_input_ref_sha256 != self.provider_input_ref_sha256:
            raise ValueError("video understanding must bind the remux provider-reference hash")
        serialized_content = json.dumps(
            self.observation.content.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if _PROVIDER_LOCATOR_RE.search(serialized_content) or _CREDENTIAL_ASSIGNMENT_RE.search(serialized_content):
            raise ValueError("video understanding content cannot expose a provider locator or credential fragment")
        return self


class ReferenceVideoDerivedArtifacts(EvidenceModel):
    remux: RemuxArtifactCandidate | None = None


class ReferenceVideoProviderInferences(EvidenceModel):
    video_understanding: VideoUnderstandingProviderInference | None = None


class VisualSample(EvidenceModel):
    at_seconds: float = Field(ge=0, le=1200)
    artifact_ref: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VideoAnalysisReceipt(EvidenceModel):
    pipeline_version: str = Field(min_length=1, max_length=80)
    analysis_depth: Literal["mechanical", "speech_text", "full"]
    requested_frames: int = Field(ge=4, le=12)
    local_sampling_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    toolchain_sha256: dict[str, str] = Field(min_length=2, max_length=3)
    local_cache_hit: bool
    artifact_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_stage_spec_sha256: dict[str, str] = Field(default_factory=dict, max_length=4)


class ProviderExecutionReceipt(EvidenceModel):
    adapter_version: str = Field(min_length=1, max_length=80)
    result_normalization_version: str = Field(min_length=1, max_length=80)
    executor: Literal["official-mediakit-cli"]
    execution_mode: Literal["cloud"]
    capability: Literal["asr", "ocr", "scene_segmentation", "storyline"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mediakit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    submission_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_id_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_input_attestation: Literal["not_provided"]
    polling_mode: Literal["caller_deadline_single_query"]
    result_transport: Literal[
        "inline",
        "inline_result",
        "isolated_local_path",
        "bounded_provider_https",
    ]
    result_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    result_file_size_bytes: int | None = Field(
        default=None,
        strict=True,
        gt=0,
        le=2 * 1024 * 1024,
    )
    result_file_content_type: (
        Literal[
            "application/json",
            "application/octet-stream",
            "application/x-subrip",
            "text/plain",
            "text/vtt",
            "unknown",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_result_transport(self) -> ProviderExecutionReceipt:
        metadata = (
            self.result_file_sha256,
            self.result_file_size_bytes,
            self.result_file_content_type,
        )
        has_metadata = tuple(value is not None for value in metadata)
        if any(has_metadata) and not all(has_metadata):
            raise ValueError("provider result-file metadata must be present as one complete set")
        file_transports = {"isolated_local_path", "bounded_provider_https"}
        if self.result_transport in file_transports and not all(has_metadata):
            raise ValueError("provider file transport requires bounded result-file metadata")
        if self.result_transport not in file_transports and any(has_metadata):
            raise ValueError("inline provider result cannot carry result-file metadata")
        return self


class ProviderEvidence(EvidenceModel):
    trust: Literal["untrusted_source_data"] = "untrusted_source_data"
    provider: str
    input_binding: (
        Literal[
            "content_sha256_verified",
            "public_url_unverified",
            "sealed_local_snapshot_provider_unattested",
        ]
        | None
    ) = None
    input_content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any] | None = None
    error: str | None = Field(default=None, min_length=1, max_length=240)
    execution_receipt: ProviderExecutionReceipt | None = None

    @model_validator(mode="after")
    def validate_payload_or_error(self) -> ProviderEvidence:
        if self.error is not None:
            if self.error != self.error.strip() or "\n" in self.error or "\r" in self.error:
                raise ValueError("provider error must be one bounded line")
            if _PROVIDER_LOCATOR_RE.search(self.error) or _CREDENTIAL_ASSIGNMENT_RE.search(self.error):
                raise ValueError("provider error cannot expose a locator or credential fragment")
        if self.payload is not None and self.error is not None:
            raise ValueError("provider evidence cannot contain both payload and error")
        if self.error is not None and self.execution_receipt is not None:
            raise ValueError("failed provider evidence cannot claim a completed execution receipt")
        if self.provider == "volcengine-mediakit" and self.payload is not None:
            if self.execution_receipt is None:
                raise ValueError("MediaKit payload requires an execution receipt")
            if self.input_binding != "sealed_local_snapshot_provider_unattested":
                raise ValueError("MediaKit payload requires the sealed-snapshot binding")
        if self.execution_receipt is not None:
            if self.execution_receipt.source_sha256 != self.input_content_sha256:
                raise ValueError("provider receipt must match the declared input content hash")
            if self.payload is not None and self.execution_receipt.result_sha256 != _canonical_sha256(self.payload):
                raise ValueError("provider receipt must bind the exposed evidence payload")
        return self


class CoverageRecord(EvidenceModel):
    collection_status: Literal["completed", "partial", "unavailable", "failed", "not_requested"]
    observation_scope: str = Field(min_length=1, max_length=120)
    truncated: bool = False
    requested_count: int | None = Field(default=None, ge=0)
    observed_count: int | None = Field(default=None, ge=0)
    reason_codes: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_collection_claim(self) -> CoverageRecord:
        if self.requested_count is not None and self.observed_count is None:
            raise ValueError("coverage requested_count requires observed_count")
        if self.requested_count is not None and self.observed_count is not None and self.observed_count > self.requested_count:
            raise ValueError("coverage observed_count cannot exceed requested_count")
        if self.collection_status == "completed" and self.requested_count is not None and self.observed_count != self.requested_count:
            raise ValueError("completed coverage must observe every requested item")
        if self.collection_status == "completed" and (self.truncated or self.reason_codes):
            raise ValueError("completed coverage cannot be truncated or carry failure reasons")
        if self.collection_status != "completed" and not self.reason_codes:
            raise ValueError("non-complete coverage requires a reason code")
        if self.collection_status == "not_requested" and (self.requested_count is not None or self.observed_count is not None or self.truncated):
            raise ValueError("not-requested coverage cannot report observations")
        return self


class ReferenceVideoCoverage(EvidenceModel):
    source_identity: CoverageRecord
    media_metadata: CoverageRecord
    sampled_frames: CoverageRecord
    contact_sheet: CoverageRecord
    local_scene_detection: CoverageRecord
    asr: CoverageRecord
    ocr: CoverageRecord
    provider_scene_segmentation: CoverageRecord
    storyline: CoverageRecord


class ReferenceVideoItem(EvidenceModel):
    status: Literal["ok", "partial", "failed"]
    purpose: Literal["benchmark", "performance_test"]
    source: VideoSource
    media_metadata: MediaMetadata | None = None
    visual_samples: list[VisualSample] = Field(default_factory=list, max_length=12)
    contact_sheet_ref: str | None = None
    contact_sheet_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    scene_boundaries_seconds: list[float] = Field(default_factory=list, max_length=100)
    provider_evidence: dict[str, ProviderEvidence] = Field(default_factory=dict)
    derived_artifacts: ReferenceVideoDerivedArtifacts | None = None
    provider_inferences: ReferenceVideoProviderInferences | None = None
    coverage: ReferenceVideoCoverage | None = None
    analysis_receipt: VideoAnalysisReceipt | None = None
    error: EvidenceError | None = None
    next_action: str | None = None

    @model_validator(mode="after")
    def validate_status_against_coverage(self) -> ReferenceVideoItem:
        remux = self.derived_artifacts.remux if self.derived_artifacts is not None else None
        visual = self.provider_inferences.video_understanding if self.provider_inferences is not None else None
        if self.status == "failed" and (remux is not None or visual is not None):
            raise ValueError("failed source evidence cannot carry derived provider results")
        if remux is not None:
            if self.source.content_sha256 != remux.derived_from_source_sha256:
                raise ValueError("remux artifact must derive from the preserved source fact")
            if self.source.identity_verification not in {
                "api_work_id_match",
                "api_work_and_author_match",
            }:
                raise ValueError("remux artifact requires an exact verified public work")
        if visual is not None:
            if remux is None:
                raise ValueError("video understanding inference requires a remux artifact")
            if self.status != "partial":
                raise ValueError("video understanding inference requires partial item status")
            if visual.original_source_sha256 != self.source.content_sha256:
                raise ValueError("video understanding must preserve the original source hash")
            if visual.candidate_artifact_sha256 != remux.artifact_sha256:
                raise ValueError("video understanding must use the declared remux artifact")
            if visual.remux_transform_receipt_sha256 != remux.transform_receipt_sha256:
                raise ValueError("video understanding must bind the remux transform receipt")
            if visual.provider_input_ref_sha256 != remux.runtime_url_sha256:
                raise ValueError("video understanding must use the remux provider reference")
        if self.status == "failed":
            if self.error is None:
                raise ValueError("failed video evidence requires an error")
            return self
        if self.coverage is None or self.analysis_receipt is None:
            raise ValueError("non-failed video evidence requires coverage and an analysis receipt")
        if self.error is not None:
            raise ValueError("non-failed video evidence cannot carry an error")
        if self.source.content_sha256 is None:
            raise ValueError("non-failed video evidence requires a verified content hash")
        if self.coverage.source_identity.collection_status != "completed":
            raise ValueError("non-failed video evidence requires completed source identity coverage")
        if self.coverage.media_metadata.collection_status != "completed" or self.media_metadata is None:
            raise ValueError("completed coverage for media metadata requires media metadata")

        frame_coverage = self.coverage.sampled_frames
        frame_count = len(self.visual_samples)
        if frame_coverage.collection_status not in {"completed", "partial", "failed"}:
            raise ValueError("sampled frame coverage has an unsupported status")
        if frame_coverage.requested_count != self.analysis_receipt.requested_frames:
            raise ValueError("sampled frame coverage must match the receipt frame request")
        if frame_coverage.observed_count != frame_count:
            raise ValueError("sampled frame coverage must match the observed frame count")
        frame_refs = [sample.artifact_ref for sample in self.visual_samples]
        if len(frame_refs) != len(set(frame_refs)):
            raise ValueError("sampled frame artifact references must be unique")
        if any(sample.at_seconds > self.media_metadata.duration_seconds for sample in self.visual_samples):
            raise ValueError("sampled frame timestamp exceeds media duration")
        if frame_coverage.collection_status == "completed" and frame_count != self.analysis_receipt.requested_frames:
            raise ValueError("completed frame coverage requires every requested frame")
        if frame_coverage.collection_status == "partial" and not (0 < frame_count < self.analysis_receipt.requested_frames and frame_coverage.truncated):
            raise ValueError("partial frame coverage requires a truncated non-empty subset")
        if frame_coverage.collection_status == "failed" and frame_count != 0:
            raise ValueError("failed frame coverage cannot carry frame artifacts")

        contact_coverage = self.coverage.contact_sheet
        has_contact_ref = self.contact_sheet_ref is not None
        has_contact_hash = self.contact_sheet_sha256 is not None
        if has_contact_ref != has_contact_hash:
            raise ValueError("contact-sheet reference and hash must be present together")
        contact_count = 1 if has_contact_ref else 0
        if contact_coverage.collection_status not in {"completed", "failed"}:
            raise ValueError("contact-sheet coverage has an unsupported status")
        if contact_coverage.requested_count != 1 or contact_coverage.observed_count != contact_count:
            raise ValueError("contact-sheet coverage must match the sealed artifact")
        if contact_coverage.collection_status == "completed" and not has_contact_ref:
            raise ValueError("completed coverage requires a contact-sheet artifact")
        if contact_coverage.collection_status == "failed" and has_contact_ref:
            raise ValueError("failed contact-sheet coverage cannot carry an artifact")

        scene_coverage = self.coverage.local_scene_detection
        if scene_coverage.collection_status not in {"completed", "partial", "failed"}:
            raise ValueError("local scene coverage has an unsupported status")
        if scene_coverage.requested_count is not None:
            raise ValueError("local scene coverage is a full-timeline scan, not a requested sample")
        if scene_coverage.observed_count != len(self.scene_boundaries_seconds):
            raise ValueError("local scene coverage must match observed boundaries")
        if any(point > self.media_metadata.duration_seconds for point in self.scene_boundaries_seconds):
            raise ValueError("scene boundary exceeds media duration")
        if self.scene_boundaries_seconds != sorted(set(self.scene_boundaries_seconds)):
            raise ValueError("scene boundaries must be unique and ordered")
        if scene_coverage.collection_status == "partial" and not (scene_coverage.truncated and len(self.scene_boundaries_seconds) == 100 and "SCENE_BOUNDARY_LIMIT_REACHED" in scene_coverage.reason_codes):
            raise ValueError("partial local scene coverage requires the declared boundary cap")
        if scene_coverage.collection_status == "failed" and self.scene_boundaries_seconds:
            raise ValueError("failed local scene coverage cannot carry boundaries")

        provider_keys = {
            "asr": "asr",
            "ocr": "ocr",
            "provider_scene_segmentation": "scene_segmentation",
            "storyline": "storyline",
        }
        provider_coverages = {
            "asr": self.coverage.asr,
            "ocr": self.coverage.ocr,
            "provider_scene_segmentation": self.coverage.provider_scene_segmentation,
            "storyline": self.coverage.storyline,
        }
        depth_keys = set() if self.analysis_receipt.analysis_depth == "mechanical" else {"asr", "ocr"} if self.analysis_receipt.analysis_depth == "speech_text" else set(provider_keys)
        allowed_evidence_keys = {provider_keys[key] for key in depth_keys}
        if set(self.provider_evidence) - allowed_evidence_keys:
            raise ValueError("provider evidence contains a stage outside the requested analysis depth")
        if set(self.analysis_receipt.provider_stage_spec_sha256) - depth_keys:
            raise ValueError("provider stage receipt contains a stage outside the requested analysis depth")
        for coverage_key, evidence_key in provider_keys.items():
            record = provider_coverages[coverage_key]
            evidence = self.provider_evidence.get(evidence_key)
            spec = self.analysis_receipt.provider_stage_spec_sha256.get(coverage_key)
            if coverage_key not in depth_keys:
                if record.collection_status != "not_requested" or evidence is not None or spec is not None:
                    raise ValueError(f"{coverage_key} must be absent when not requested")
                continue
            if record.collection_status == "not_requested":
                raise ValueError(f"{coverage_key} cannot be not_requested at this analysis depth")
            if record.collection_status in {"completed", "partial"}:
                if evidence is None or evidence.payload is None or evidence.error is not None or spec is None:
                    raise ValueError(f"{coverage_key} coverage requires matching provider payload and receipt")
                if evidence.input_content_sha256 != self.source.content_sha256:
                    raise ValueError(f"{coverage_key} provider evidence must bind the observed content hash")
                if evidence.execution_receipt is not None:
                    if evidence.execution_receipt.capability != evidence_key:
                        raise ValueError(f"{coverage_key} provider receipt names a different capability")
                    if evidence.execution_receipt.stage_spec_sha256 != spec:
                        raise ValueError(f"{coverage_key} provider receipt must match the stage specification")
                if record.collection_status == "completed" and evidence.input_binding not in {
                    "content_sha256_verified",
                    "sealed_local_snapshot_provider_unattested",
                }:
                    raise ValueError(f"{coverage_key} completed coverage requires a verified or sealed local input")
            elif record.collection_status == "failed":
                if evidence is None or evidence.error is None or evidence.payload is not None or spec is None:
                    raise ValueError(f"{coverage_key} failure requires matching provider error and receipt")
            elif record.collection_status == "unavailable":
                proposal_prepared = record.reason_codes == ["UNAVAILABLE_PROVIDER_EXECUTION_NOT_AUTHORIZED"]
                if evidence is not None or (spec is not None and not proposal_prepared):
                    raise ValueError(f"{coverage_key} unavailable coverage cannot carry provider evidence")

        required = [
            self.coverage.source_identity,
            self.coverage.media_metadata,
            self.coverage.sampled_frames,
            self.coverage.contact_sheet,
            self.coverage.local_scene_detection,
        ]
        if self.analysis_receipt.analysis_depth in {"speech_text", "full"}:
            required.extend([self.coverage.asr, self.coverage.ocr])
        if self.analysis_receipt.analysis_depth == "full":
            required.extend(
                [
                    self.coverage.provider_scene_segmentation,
                    self.coverage.storyline,
                ]
            )
        complete = visual is None and all(item.collection_status == "completed" and not item.truncated for item in required)
        if self.status == "ok" and not complete:
            raise ValueError("ok video evidence requires complete requested coverage")
        if self.status == "partial" and complete:
            raise ValueError("partial video evidence requires incomplete requested coverage")
        return self


class ReferenceVideoEvidence(EvidenceModel):
    contract_version: Literal["ip-reference-video-evidence-v2"]
    operation_status: Literal["ok", "partial_or_failed", "failed"]
    trust_boundary: str
    requested_count: int = Field(ge=1, le=3)
    completed_count: int = Field(ge=0, le=3)
    items: list[ReferenceVideoItem] = Field(min_length=1, max_length=3)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    metadata: EvidenceMetadata

    @model_validator(mode="after")
    def validate_aggregate_claim(self) -> ReferenceVideoEvidence:
        if self.requested_count != len(self.items):
            raise ValueError("requested_count must equal the number of video evidence items")
        completed = sum(item.status == "ok" for item in self.items)
        if self.completed_count != completed:
            raise ValueError("completed_count must count only fully complete video evidence items")
        failed = sum(item.status == "failed" for item in self.items)
        expected_status = "ok" if completed == len(self.items) else "failed" if failed == len(self.items) else "partial_or_failed"
        if self.operation_status != expected_status:
            raise ValueError("operation_status does not match child video evidence status")
        child_truncated = any(
            record.truncated
            for item in self.items
            if item.coverage is not None
            for record in (
                item.coverage.source_identity,
                item.coverage.media_metadata,
                item.coverage.sampled_frames,
                item.coverage.contact_sheet,
                item.coverage.local_scene_detection,
                item.coverage.asr,
                item.coverage.ocr,
                item.coverage.provider_scene_segmentation,
                item.coverage.storyline,
            )
        )
        if self.metadata.truncated != child_truncated:
            raise ValueError("top-level truncated must be derived from child coverage")
        return self


class InspectReferenceVideosInput(EvidenceModel):
    video_refs: list[str] = Field(min_length=1, max_length=3)
    reference_context: Literal["standalone_reference", "account_inventory_item"] = "standalone_reference"
    purpose: Literal["benchmark", "performance_test"] = "benchmark"
    analysis_depth: Literal["mechanical", "speech_text", "full"] = Field(
        default="full",
        description=("完整分析或涉及场景切分、故事线时必须使用 full；只有用户明确仅需语音、台词或画面文字时才使用 speech_text。"),
    )
    max_frames: int = Field(default=8, ge=4, le=12)
    account_binding_receipt: str | None = Field(default=None, min_length=32, max_length=8_192)

    @model_validator(mode="after")
    def validate_reference_context(self) -> InspectReferenceVideosInput:
        if self.reference_context == "account_inventory_item" and self.account_binding_receipt is None:
            raise ValueError("account_inventory_item requires account_binding_receipt")
        if self.reference_context == "standalone_reference" and self.account_binding_receipt is not None:
            raise ValueError("standalone_reference cannot carry account_binding_receipt")
        return self
