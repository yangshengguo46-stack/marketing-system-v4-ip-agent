"""One-route paid evidence admission and transport dispatcher.

This module is dependency-injected and intentionally absent from the default
runtime configuration.  It owns the future shared
``ip_evidence/inspect_reference_videos`` paid route so ASR, Remux and Video
Understanding cannot erase one another's grants in stacked interceptors.

The R1/R2 callbacks are a local, zero-provider integration seam only.  Real
provider wiring remains blocked until one request-hash authority exists for
each stage and the R2 predecessor/submission journal is durable.  The local
seam does hold a verified source descriptor through the complete journal and
executor consumption window.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from mcp.types import CallToolResult

from app.gateway.evidence_paid_call_admission import (
    EVIDENCE_INSPECT_TOOL_NAME,
    EVIDENCE_MCP_CLIENT_NAME,
    MEDIAKIT_ASR_CAPABILITY,
    MEDIAKIT_COMPOSITE_STAGE_CAPABILITIES,
    MEDIAKIT_DERIVED_STAGE_CAPABILITIES,
    MEDIAKIT_PROVIDER,
    EvidenceCompositeRouteGroupGrantResolver,
    _RouteGroupAdmissionRepository,
)
from deerflow.ip_agent.evidence_contracts import (
    ReferenceVideoDerivedArtifacts,
    ReferenceVideoEvidence,
    ReferenceVideoProviderInferences,
    RemuxArtifactCandidate,
    VideoUnderstandingProviderInference,
)
from deerflow.ip_agent.evidence_mcp import build_reference_video_call_result
from deerflow.ip_agent.reference_evidence import (
    SEALED_SOURCE_HANDOFF_CONTRACT_VERSION,
    SEALED_SOURCE_HANDOFF_META_KEY,
    OpenVerifiedSealedSource,
    SealedSourceHandoff,
    open_verified_sealed_source_handoff,
)
from deerflow.mcp.paid_admission import (
    PAID_CALL_GRANT_HEADER,
    PAID_CALL_SELECTED_CAPABILITY_HEADER,
    PaidCallAdmissionClaim,
    PaidCallAdmissionRejected,
    PaidCallRouteGroupInvocation,
    PaidMCPToolRouteGroup,
    SignedPreAdmittedGrantVerifier,
    build_paid_call_grant_interceptor,
    canonical_tool_args_sha256,
)
from deerflow.mcp.result_metadata import OPERATOR_PRIVATE_MCP_META_PREFIX
from deerflow.persistence.personal_ip_paid_calls import (
    OperatorCappedEvidenceStagePolicy,
)
from deerflow.runtime.user_context import resolve_runtime_user_id

_REMUX_CAPABILITY = MEDIAKIT_DERIVED_STAGE_CAPABILITIES[0]
_VIDEO_UNDERSTANDING_CAPABILITY = MEDIAKIT_DERIVED_STAGE_CAPABILITIES[1]
_SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")
_DOUYIN_WORK_ID = re.compile(r"^[0-9]{8,40}$")
_SEALED_SOURCE_RELATIVE_ROOT = "reference-video-sealed-sources"

# These are executable blockers, not TODO-shaped product claims.  The module
# stays uninstalled while either request binding or durable recovery is split.
DERIVED_PROVIDER_EXECUTION_BLOCKERS = (
    "R1_PROVIDER_REQUEST_SHA256_AUTHORITY_SPLIT",
    "R1_SHARED_ROUTE_POLICY_NOT_IMPLEMENTED",
    "R2_PROVIDER_REQUEST_SHA256_AUTHORITY_SPLIT",
    "R2_DURABLE_PREDECESSOR_AND_ONCE_ONLY_JOURNAL_MISSING",
)


@dataclass(frozen=True, slots=True)
class CompositePaidStageAdmission:
    """Verified app-private admission passed only to a capability executor."""

    selected_capability: str
    claim: PaidCallAdmissionClaim = field(repr=False)
    opaque_grant: str = field(repr=False)
    _consume_once: Callable[[PaidCallAdmissionClaim], Awaitable[None]] = field(
        repr=False,
        compare=False,
    )

    async def consume_once_before_provider_submission(self) -> None:
        """Consume the verified transport grant at the provider commit point."""

        await self._consume_once(self.claim)


@dataclass(frozen=True, slots=True)
class VerifiedPersistedRemux:
    """Durably recovered R1 predecessor for an R2 execution.

    ``runtime_url`` is private operational state.  Only its SHA-256 may enter
    public evidence.  Production construction belongs to an encrypted durable
    journal; this module deliberately provides no in-memory implementation.
    """

    artifact: RemuxArtifactCandidate
    runtime_url: str = field(repr=False)
    journal_record_sha256: str

    def __post_init__(self) -> None:
        artifact = RemuxArtifactCandidate.model_validate(
            self.artifact.model_dump(mode="json", exclude_none=True),
        )
        parsed = urlsplit(self.runtime_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or hashlib.sha256(self.runtime_url.encode("utf-8")).hexdigest() != artifact.runtime_url_sha256:
            raise ValueError("persisted remux runtime binding is invalid")
        if _SHA256_TEXT.fullmatch(self.journal_record_sha256) is None:
            raise ValueError("persisted remux journal binding is invalid")
        object.__setattr__(self, "artifact", artifact)


class EvidenceDerivedStageJournal(Protocol):
    """Durable, encrypted R1 predecessor lookup; no memory fallback allowed."""

    async def load_verified_remux(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
        original_source_sha256: str,
        candidate_artifact_sha256: str,
    ) -> VerifiedPersistedRemux | None: ...


class RemuxEvidenceExecutor(Protocol):
    """Capability-specific R1 seam; no generic ``**kwargs`` dispatcher."""

    async def __call__(
        self,
        *,
        admission: CompositePaidStageAdmission,
        source: OpenVerifiedSealedSource,
        free_evidence: ReferenceVideoEvidence,
    ) -> RemuxArtifactCandidate: ...


class VideoUnderstandingEvidenceExecutor(Protocol):
    """Capability-specific R2 seam over one durable R1 predecessor."""

    async def __call__(
        self,
        *,
        admission: CompositePaidStageAdmission,
        source: OpenVerifiedSealedSource,
        persisted_remux: VerifiedPersistedRemux,
        free_evidence: ReferenceVideoEvidence,
    ) -> VideoUnderstandingProviderInference: ...


def _without_paid_headers(headers: Any) -> dict[str, Any]:
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise PaidCallAdmissionRejected("INVALID_MCP_HEADERS")
    reserved = {
        PAID_CALL_GRANT_HEADER.casefold(),
        PAID_CALL_SELECTED_CAPABILITY_HEADER.casefold(),
    }
    return {str(key): value for key, value in headers.items() if str(key).casefold() not in reserved}


def _header(headers: Any, name: str) -> str | None:
    if not isinstance(headers, Mapping):
        return None
    values = [value for key, value in headers.items() if str(key).casefold() == name.casefold()]
    if not values:
        return None
    if len(values) != 1 or not isinstance(values[0], str):
        raise PaidCallAdmissionRejected("PAID_CALL_COMPOSITE_HEADERS_INVALID")
    return values[0]


def _runtime_scope(request: Any) -> tuple[str, str, str]:
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        raise PaidCallAdmissionRejected("PAID_CALL_RUNTIME_SCOPE_INVALID")
    thread_id = context.get("thread_id")
    run_id = context.get("run_id")
    if not all(isinstance(value, str) and value for value in (thread_id, run_id)):
        raise PaidCallAdmissionRejected("PAID_CALL_RUNTIME_SCOPE_INVALID")
    try:
        owner_user_id = resolve_runtime_user_id(runtime)
    except RuntimeError as exc:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_RUNTIME_SCOPE_INVALID",
        ) from exc
    return owner_user_id, thread_id, run_id


def _observed_now(clock: Callable[[], datetime] | None) -> datetime:
    observed = clock() if clock is not None else datetime.now(UTC)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise PaidCallAdmissionRejected("PAID_CALL_CLOCK_INVALID")
    return observed.astimezone(UTC)


async def _verified_derived_admission(
    request: Any,
    *,
    selected_capability: str,
    verifier: SignedPreAdmittedGrantVerifier,
    clock: Callable[[], datetime] | None,
) -> CompositePaidStageAdmission:
    headers = getattr(request, "headers", None)
    opaque_grant = _header(headers, PAID_CALL_GRANT_HEADER)
    if opaque_grant is None:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_MISSING")
    arguments = getattr(request, "args", None)
    if not isinstance(arguments, Mapping):
        raise PaidCallAdmissionRejected("TOOL_ARGUMENTS_MISSING")
    owner_user_id, thread_id, run_id = _runtime_scope(request)
    invocation = PaidCallRouteGroupInvocation(
        server_name=EVIDENCE_MCP_CLIENT_NAME,
        tool_name=EVIDENCE_INSPECT_TOOL_NAME,
        tool_args_sha256=canonical_tool_args_sha256(arguments),
        provider=MEDIAKIT_PROVIDER,
        allowed_capabilities=MEDIAKIT_COMPOSITE_STAGE_CAPABILITIES,
        selected_capability=selected_capability,
    )
    try:
        claim = PaidCallAdmissionClaim.model_validate(
            await verifier.verify(opaque_grant, invocation),
        )
    except PaidCallAdmissionRejected:
        raise
    except Exception as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_REJECTED") from exc
    if claim.owner_user_id != owner_user_id or claim.thread_id != thread_id or claim.run_id != run_id or claim.capability != selected_capability or claim.expires_at <= _observed_now(clock):
        raise PaidCallAdmissionRejected("PAID_CALL_GRANT_SCOPE_MISMATCH")
    return CompositePaidStageAdmission(
        selected_capability=selected_capability,
        claim=claim,
        opaque_grant=opaque_grant,
        _consume_once=verifier.consume_once,
    )


def _consume_operator_private_meta(
    result: Any,
) -> tuple[CallToolResult, Any | None]:
    try:
        validated = CallToolResult.model_validate(result)
    except (TypeError, ValueError) as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_MCP_RESULT_INVALID") from exc
    meta = validated.meta
    if meta is None:
        return validated, None
    if not isinstance(meta, Mapping):
        raise PaidCallAdmissionRejected("PAID_CALL_MCP_RESULT_META_INVALID")
    handoffs: list[Any] = []
    public_meta: dict[str, Any] = {}
    target = SEALED_SOURCE_HANDOFF_META_KEY.casefold()
    private_prefix = OPERATOR_PRIVATE_MCP_META_PREFIX.casefold()
    for raw_key, value in meta.items():
        normalized = str(raw_key).replace("\x00", " ").strip()
        normalized_folded = normalized.casefold()
        if normalized_folded.startswith(private_prefix):
            if normalized_folded == target:
                handoffs.append(value)
            continue
        public_meta[str(raw_key)] = value
    if len(handoffs) > 1:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_SEALED_HANDOFF_DUPLICATED",
        )
    return (
        validated.model_copy(update={"meta": public_meta or None}),
        handoffs[0] if handoffs else None,
    )


def _reference_evidence_from_result(result: CallToolResult) -> ReferenceVideoEvidence:
    if not isinstance(result.structuredContent, Mapping):
        raise PaidCallAdmissionRejected("PAID_CALL_FREE_EVIDENCE_MISSING")
    try:
        return ReferenceVideoEvidence.model_validate(
            dict(result.structuredContent),
        )
    except (TypeError, ValueError) as exc:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_FREE_EVIDENCE_INVALID",
        ) from exc


def _validate_exact_handoff(
    handoff: Any,
    *,
    evidence: ReferenceVideoEvidence,
) -> SealedSourceHandoff:
    if not isinstance(handoff, Mapping) or set(handoff) != {"contract_version", "items"} or handoff.get("contract_version") != SEALED_SOURCE_HANDOFF_CONTRACT_VERSION:
        raise PaidCallAdmissionRejected("PAID_CALL_SEALED_HANDOFF_INVALID")
    raw_items = handoff.get("items")
    if not isinstance(raw_items, list) or len(raw_items) != 1:
        raise PaidCallAdmissionRejected("PAID_CALL_SEALED_HANDOFF_NOT_EXACT")
    if evidence.requested_count != 1 or len(evidence.items) != 1:
        raise PaidCallAdmissionRejected("PAID_CALL_FREE_EVIDENCE_NOT_EXACT")
    evidence_item = evidence.items[0]
    source = evidence_item.source
    work_ids = (
        source.requested_work_id,
        source.resolved_work_id,
        source.observed_work_id,
    )
    if source.identity_verification not in {"api_work_id_match", "api_work_and_author_match"} or source.content_sha256 is None or any(value is None for value in work_ids) or len(set(work_ids)) != 1 or evidence_item.media_metadata is None:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_FREE_EVIDENCE_IDENTITY_UNVERIFIED",
        )
    raw = raw_items[0]
    if not isinstance(raw, Mapping) or set(raw) != {
        "relative_ref",
        "source_sha256",
        "size_bytes",
        "work_id",
    }:
        raise PaidCallAdmissionRejected("PAID_CALL_SEALED_HANDOFF_INVALID")
    relative_ref = raw.get("relative_ref")
    source_sha256 = raw.get("source_sha256")
    size_bytes = raw.get("size_bytes")
    work_id = raw.get("work_id")
    if (
        not isinstance(relative_ref, str)
        or not isinstance(source_sha256, str)
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or not isinstance(work_id, str)
        or _SHA256_TEXT.fullmatch(source_sha256) is None
        or _DOUYIN_WORK_ID.fullmatch(work_id) is None
        or not 0 < size_bytes <= 200 * 1024 * 1024
        or not hmac.compare_digest(source_sha256, source.content_sha256)
        or work_id != work_ids[0]
        or size_bytes != evidence_item.media_metadata.size_bytes
    ):
        raise PaidCallAdmissionRejected(
            "PAID_CALL_SEALED_HANDOFF_BINDING_MISMATCH",
        )
    relative = Path(relative_ref)
    parts = relative.parts
    if (
        relative.is_absolute()
        or "\\" in relative_ref
        or len(parts) != 5
        or parts[0] != "outputs"
        or parts[1] != _SEALED_SOURCE_RELATIVE_ROOT
        or parts[2] != source_sha256
        or _SHA256_TEXT.fullmatch(parts[3]) is None
        or parts[4] != "source.mp4"
    ):
        raise PaidCallAdmissionRejected("PAID_CALL_SEALED_HANDOFF_PATH_INVALID")
    return SealedSourceHandoff(
        relative_ref=relative_ref,
        source_sha256=source_sha256,
        size_bytes=size_bytes,
        work_id=work_id,
    )


def _merge_remux_result(
    free_evidence: ReferenceVideoEvidence,
    artifact: RemuxArtifactCandidate,
) -> ReferenceVideoEvidence:
    item = free_evidence.items[0]
    if item.status == "failed" or item.derived_artifacts is not None or item.provider_inferences is not None or item.source.content_sha256 != artifact.derived_from_source_sha256:
        raise PaidCallAdmissionRejected("PAID_CALL_REMUX_RESULT_BINDING_MISMATCH")
    updated_item = item.model_copy(
        update={
            "derived_artifacts": ReferenceVideoDerivedArtifacts(
                remux=artifact,
            ),
        },
    )
    payload = free_evidence.model_dump(mode="json", exclude_none=True)
    payload["items"] = [updated_item.model_dump(mode="json", exclude_none=True)]
    try:
        return ReferenceVideoEvidence.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise PaidCallAdmissionRejected("PAID_CALL_REMUX_RESULT_INVALID") from exc


def _merge_video_understanding_result(
    free_evidence: ReferenceVideoEvidence,
    *,
    persisted_remux: VerifiedPersistedRemux,
    inference: VideoUnderstandingProviderInference,
) -> ReferenceVideoEvidence:
    item = free_evidence.items[0]
    artifact = persisted_remux.artifact
    existing_remux = item.derived_artifacts.remux if item.derived_artifacts is not None else None
    if (
        item.status == "failed"
        or item.provider_inferences is not None
        or item.source.content_sha256 != artifact.derived_from_source_sha256
        or (existing_remux is not None and existing_remux.model_dump(mode="json", exclude_none=True) != artifact.model_dump(mode="json", exclude_none=True))
        or inference.original_source_sha256 != item.source.content_sha256
        or inference.candidate_artifact_sha256 != artifact.artifact_sha256
        or inference.remux_transform_receipt_sha256 != artifact.transform_receipt_sha256
        or inference.provider_input_ref_sha256 != artifact.runtime_url_sha256
    ):
        raise PaidCallAdmissionRejected(
            "PAID_CALL_VIDEO_UNDERSTANDING_RESULT_BINDING_MISMATCH",
        )
    updated_item = item.model_copy(
        update={
            "status": "partial",
            "derived_artifacts": ReferenceVideoDerivedArtifacts(
                remux=artifact,
            ),
            "provider_inferences": ReferenceVideoProviderInferences(
                video_understanding=inference,
            ),
        },
    )
    payload = free_evidence.model_dump(mode="json", exclude_none=True)
    payload["items"] = [updated_item.model_dump(mode="json", exclude_none=True)]
    payload["completed_count"] = 0
    payload["operation_status"] = "partial_or_failed"
    limitations = list(free_evidence.limitations)
    limitation = "provider visual inference remains partial"
    if limitation not in limitations:
        limitations.append(limitation)
    payload["limitations"] = limitations
    try:
        return ReferenceVideoEvidence.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_VIDEO_UNDERSTANDING_RESULT_INVALID",
        ) from exc


async def _load_persisted_remux(
    journal: EvidenceDerivedStageJournal,
    *,
    admission: CompositePaidStageAdmission,
    free_evidence: ReferenceVideoEvidence,
) -> VerifiedPersistedRemux:
    source_sha256 = free_evidence.items[0].source.content_sha256
    if source_sha256 is None:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_FREE_EVIDENCE_IDENTITY_UNVERIFIED",
        )
    try:
        persisted = await journal.load_verified_remux(
            owner_user_id=admission.claim.owner_user_id,
            thread_id=admission.claim.thread_id,
            original_source_sha256=source_sha256,
            candidate_artifact_sha256=admission.claim.source_sha256,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_R2_PREDECESSOR_LOOKUP_FAILED",
        ) from None
    if not isinstance(persisted, VerifiedPersistedRemux):
        raise PaidCallAdmissionRejected("PAID_CALL_R2_PREDECESSOR_MISSING")
    if persisted.artifact.derived_from_source_sha256 != source_sha256 or persisted.artifact.artifact_sha256 != admission.claim.source_sha256:
        raise PaidCallAdmissionRejected(
            "PAID_CALL_R2_PREDECESSOR_BINDING_MISMATCH",
        )
    return persisted


def build_evidence_paid_call_composite_interceptor(
    *,
    repository: _RouteGroupAdmissionRepository,
    trusted_stage_policies: Iterable[OperatorCappedEvidenceStagePolicy],
    signing_secret: str | bytes,
    capability_configured: Callable[[str], bool],
    user_data_root_resolver: Callable[[Any], Path],
    remux_executor: RemuxEvidenceExecutor | None,
    video_understanding_executor: VideoUnderstandingEvidenceExecutor | None,
    derived_stage_journal: EvidenceDerivedStageJournal | None,
    clock: Callable[[], datetime] | None = None,
) -> Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]:
    """Build the uninstalled ASR/R1/R2 route owner.

    ASR is the only capability whose hidden grant crosses into Evidence MCP.
    R1/R2 first call the free MCP with both reserved headers removed, then
    require an exact sealed handoff before invoking their own typed local
    callback.  The source descriptor remains context-owned and open across the
    complete journal/executor await window.
    """

    if not callable(user_data_root_resolver):
        raise ValueError("composite user-data-root resolver is required")
    if remux_executor is not None and not callable(remux_executor):
        raise ValueError("composite remux executor must be callable")
    if video_understanding_executor is not None and not callable(
        video_understanding_executor,
    ):
        raise ValueError("composite video-understanding executor must be callable")
    if derived_stage_journal is not None and not callable(
        getattr(derived_stage_journal, "load_verified_remux", None),
    ):
        raise ValueError("composite derived-stage journal is invalid")
    resolver = EvidenceCompositeRouteGroupGrantResolver(
        repository=repository,
        trusted_stage_policies=trusted_stage_policies,
        signing_secret=signing_secret,
        capability_configured=capability_configured,
        clock=clock,
    )
    grant_verifier = SignedPreAdmittedGrantVerifier(
        signing_secret=signing_secret,
    )
    route = PaidMCPToolRouteGroup(
        EVIDENCE_MCP_CLIENT_NAME,
        EVIDENCE_INSPECT_TOOL_NAME,
        MEDIAKIT_PROVIDER,
        MEDIAKIT_COMPOSITE_STAGE_CAPABILITIES,
    )
    grant_interceptor = build_paid_call_grant_interceptor(
        routes=[route],
        resolver=resolver,
    )

    async def interceptor(
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        async def dispatch(admitted_request: Any) -> Any:
            selected = _header(
                getattr(admitted_request, "headers", None),
                PAID_CALL_SELECTED_CAPABILITY_HEADER,
            )
            if selected is None or selected == MEDIAKIT_ASR_CAPABILITY:
                raw_result = await handler(admitted_request)
                safe_result, _ = _consume_operator_private_meta(raw_result)
                return safe_result
            if selected not in MEDIAKIT_DERIVED_STAGE_CAPABILITIES:
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_CAPABILITY_NOT_ALLOWED",
                )
            admission = await _verified_derived_admission(
                admitted_request,
                selected_capability=selected,
                verifier=grant_verifier,
                clock=clock,
            )
            free_request = admitted_request.override(
                headers=(
                    _without_paid_headers(
                        getattr(admitted_request, "headers", None),
                    )
                    or None
                ),
            )
            raw_free_result = await handler(free_request)
            free_result, handoff = _consume_operator_private_meta(
                raw_free_result,
            )
            if free_result.isError is True:
                return free_result
            free_evidence = _reference_evidence_from_result(free_result)
            try:
                user_data_root = Path(
                    user_data_root_resolver(admitted_request),
                )
            except Exception:
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_USER_DATA_ROOT_INVALID",
                ) from None
            sealed_source_handoff = _validate_exact_handoff(
                handoff,
                evidence=free_evidence,
            )

            if selected == _REMUX_CAPABILITY:
                if remux_executor is None:
                    raise PaidCallAdmissionRejected(
                        "PAID_CALL_REMUX_EXECUTOR_NOT_CONFIGURED",
                    )
                if not hmac.compare_digest(
                    admission.claim.source_sha256,
                    sealed_source_handoff.source_sha256,
                ):
                    raise PaidCallAdmissionRejected(
                        "PAID_CALL_REMUX_SOURCE_BINDING_MISMATCH",
                    )
            else:
                if video_understanding_executor is None:
                    raise PaidCallAdmissionRejected(
                        "PAID_CALL_VIDEO_UNDERSTANDING_EXECUTOR_NOT_CONFIGURED",
                    )
                if derived_stage_journal is None:
                    raise PaidCallAdmissionRejected(
                        "PAID_CALL_R2_DURABLE_JOURNAL_NOT_CONFIGURED",
                    )
            try:
                with open_verified_sealed_source_handoff(
                    user_data_root=user_data_root,
                    handoff=sealed_source_handoff,
                ) as source:
                    if selected == _REMUX_CAPABILITY:
                        try:
                            raw_artifact = await remux_executor(
                                admission=admission,
                                source=source,
                                free_evidence=free_evidence,
                            )
                            artifact = RemuxArtifactCandidate.model_validate(
                                raw_artifact.model_dump(
                                    mode="json",
                                    exclude_none=True,
                                ),
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            raise PaidCallAdmissionRejected(
                                "PAID_CALL_REMUX_EXECUTION_FAILED",
                            ) from None
                    else:
                        persisted_remux = await _load_persisted_remux(
                            derived_stage_journal,
                            admission=admission,
                            free_evidence=free_evidence,
                        )
                        try:
                            raw_inference = await video_understanding_executor(
                                admission=admission,
                                source=source,
                                persisted_remux=persisted_remux,
                                free_evidence=free_evidence,
                            )
                            inference = VideoUnderstandingProviderInference.model_validate(
                                raw_inference.model_dump(
                                    mode="json",
                                    exclude_none=True,
                                ),
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            raise PaidCallAdmissionRejected(
                                "PAID_CALL_VIDEO_UNDERSTANDING_EXECUTION_FAILED",
                            ) from None
            except asyncio.CancelledError:
                raise
            except PaidCallAdmissionRejected:
                raise
            except (OSError, RuntimeError, ValueError) as exc:
                raise PaidCallAdmissionRejected(
                    "PAID_CALL_SEALED_HANDOFF_FILE_INVALID",
                ) from exc

            if selected == _REMUX_CAPABILITY:
                merged = _merge_remux_result(free_evidence, artifact)
            else:
                merged = _merge_video_understanding_result(
                    free_evidence,
                    persisted_remux=persisted_remux,
                    inference=inference,
                )
            return build_reference_video_call_result(merged)

        return await grant_interceptor(request, dispatch)

    setattr(
        interceptor,
        "__deerflow_paid_mcp_route_keys__",
        getattr(grant_interceptor, "__deerflow_paid_mcp_route_keys__"),
    )
    return interceptor


__all__ = [
    "CompositePaidStageAdmission",
    "DERIVED_PROVIDER_EXECUTION_BLOCKERS",
    "EvidenceDerivedStageJournal",
    "RemuxEvidenceExecutor",
    "VerifiedPersistedRemux",
    "VideoUnderstandingEvidenceExecutor",
    "build_evidence_paid_call_composite_interceptor",
]
