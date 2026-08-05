"""Trusted bridge from local Evidence MCP results to paid-call proposals.

The MCP evidence contract remains pure and strict.  This interceptor validates
the raw ``ReferenceVideoEvidence`` first, persists a server-owned proposal,
then places only the safe customer view in MCP result metadata.  The metadata
is converted into the LangChain ToolMessage artifact and never becomes part of
the provider-facing evidence text or the strict Evidence schema.

This slice proposes only MediaKit ASR.  It neither approves nor reserves a
call, and it never maps one approval onto the old whole-batch provider boolean.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from mcp.types import CallToolResult

from app.gateway.evidence_direct_pay import EvidenceASRDirectPayPolicy
from app.gateway.routers.evidence_paid_calls import build_evidence_paid_call_view
from deerflow.ip_agent.evidence_contracts import (
    InspectReferenceVideosInput,
    ReferenceVideoEvidence,
)
from deerflow.ip_agent.mediakit_adapter import cloud_provider_request_sha256
from deerflow.ip_agent.reference_evidence import (
    SEALED_SOURCE_HANDOFF_CONTRACT_VERSION,
    SEALED_SOURCE_HANDOFF_META_KEY,
)
from deerflow.mcp.paid_admission import canonical_tool_args_sha256
from deerflow.mcp.result_metadata import is_operator_private_mcp_meta_key
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.personal_ip_paid_calls import PersonalIPPaidCallRepository
from deerflow.runtime.user_context import resolve_runtime_user_id

logger = logging.getLogger(__name__)

PAID_CALL_REQUESTS_META_KEY = "deerflow/paid_call_requests"
_EVIDENCE_SERVER = "ip_evidence"
_INSPECT_TOOL = "inspect_reference_videos"
_PROPOSAL_TTL = timedelta(minutes=15)


class _ProposalRepository(Protocol):
    async def request_call(self, **kwargs: Any) -> Mapping[str, Any]: ...

    async def list_thread(
        self,
        *,
        owner_user_id: str,
        thread_id: str,
    ) -> list[Mapping[str, Any]]: ...

    async def mark_operator_capped_asr_reconciliation_exact(
        self,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None: ...

    async def mark_operator_capped_asr_invocation_unresolved(
        self,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None: ...


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _runtime_scope(request: Any) -> tuple[str, str, str] | None:
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        return None
    thread_id = context.get("thread_id")
    origin_run_id = context.get("run_id")
    context_owner_user_id = context.get("user_id")
    if not all(isinstance(value, str) and value for value in (context_owner_user_id, thread_id, origin_run_id)):
        return None
    owner_user_id = resolve_runtime_user_id(runtime)
    if owner_user_id != context_owner_user_id:
        return None
    return owner_user_id, thread_id, origin_run_id


def _matching_existing_request(
    rows: list[Mapping[str, Any]],
    *,
    expected: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    matches = [row for row in rows if row.get("request_key") == expected["request_key"]]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("paid-call request key is not unique")
    row = matches[0]
    for field in (
        "owner_user_id",
        "thread_id",
        "origin_run_id",
        "server_name",
        "tool_name",
        "tool_args_sha256",
        "provider",
        "capability",
        "model",
        "sku",
        "source_sha256",
        "stage_digest",
        "provider_request_sha256",
        "maximum_amount_micros",
        "currency",
        "billing_basis",
        "price_status",
        "policy_version",
        "price_version",
    ):
        if row.get(field) != expected[field]:
            raise ValueError("persisted paid-call request binding drifted")
    return row


def _consume_reserved_meta(
    result: CallToolResult,
) -> tuple[CallToolResult, Any | None]:
    """Take server-only handoff data and return a transport-safe result."""

    meta = getattr(result, "meta", None)
    if not isinstance(meta, Mapping):
        return result, None
    handoff: Any | None = None
    handoff_seen = False
    sanitized: dict[str, Any] = {}
    for raw_key, value in meta.items():
        key = str(raw_key).replace("\x00", " ").strip()
        if key == PAID_CALL_REQUESTS_META_KEY:
            continue
        if is_operator_private_mcp_meta_key(key):
            if key == SEALED_SOURCE_HANDOFF_META_KEY:
                if handoff_seen:
                    raise ValueError("operator-private sealed source metadata is duplicated")
                handoff = value
                handoff_seen = True
            continue
        sanitized[str(raw_key)] = value
    return result.model_copy(update={"meta": sanitized or None}), handoff


def _handoff_matches_evidence(
    handoff: Any,
    evidence: ReferenceVideoEvidence,
) -> bool:
    """Validate raw private identity claims before a future paid-stage consumer."""

    if not isinstance(handoff, Mapping) or handoff.get("contract_version") != SEALED_SOURCE_HANDOFF_CONTRACT_VERSION:
        return False
    items = handoff.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 3:
        return False
    evidence_bindings = {
        (
            item.source.content_sha256,
            item.source.requested_work_id,
        )
        for item in evidence.items
        if item.source.content_sha256 is not None and item.source.requested_work_id is not None and item.source.requested_work_id == item.source.resolved_work_id == item.source.observed_work_id
    }
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping) or set(item) != {
            "relative_ref",
            "source_sha256",
            "size_bytes",
            "work_id",
        }:
            return False
        relative_ref = item.get("relative_ref")
        source_sha256 = item.get("source_sha256")
        size_bytes = item.get("size_bytes")
        work_id = item.get("work_id")
        if (
            not isinstance(relative_ref, str)
            or relative_ref in seen
            or not isinstance(source_sha256, str)
            or not isinstance(work_id, str)
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or not 0 < size_bytes <= 200 * 1024 * 1024
            or (source_sha256, work_id) not in evidence_bindings
        ):
            return False
        parts = relative_ref.split("/")
        if (
            "\\" in relative_ref
            or len(parts) != 5
            or parts[0] != "outputs"
            or parts[1] != "reference-video-sealed-sources"
            or parts[2] != source_sha256
            or len(parts[3]) != 64
            or any(character not in "0123456789abcdef" for character in parts[3])
            or parts[4] != "source.mp4"
        ):
            return False
        seen.add(relative_ref)
    return True


def _default_repository() -> _ProposalRepository | None:
    session_factory = get_session_factory()
    if session_factory is None:
        return None
    return PersonalIPPaidCallRepository(session_factory)


async def _persist_asr_proposals(
    *,
    repository: _ProposalRepository,
    request: Any,
    evidence: ReferenceVideoEvidence,
    direct_pay_policy: EvidenceASRDirectPayPolicy,
    observed_at: datetime,
) -> list[dict[str, Any]]:
    scope = _runtime_scope(request)
    arguments = getattr(request, "args", None)
    if scope is None or not isinstance(arguments, Mapping):
        return []
    owner_user_id, thread_id, origin_run_id = scope
    # One opaque grant admits one exact provider input.  The current transport
    # cannot safely select among multiple videos hidden behind the same outer
    # MCP argument digest, so the first cloud slice is deliberately one-video.
    try:
        validated_arguments = InspectReferenceVideosInput.model_validate(dict(arguments))
    except (TypeError, ValueError):
        return []
    if len(validated_arguments.video_refs) != 1 or evidence.requested_count != 1 or len(evidence.items) != 1:
        return []
    if validated_arguments.analysis_depth not in {
        "speech_text",
        "full",
    }:
        return []

    tool_args_sha256 = canonical_tool_args_sha256(arguments)
    views: list[dict[str, Any]] = []
    for index, item in enumerate(evidence.items, start=1):
        receipt = item.analysis_receipt
        metadata = item.media_metadata
        source_sha256 = item.source.content_sha256
        coverage = item.coverage
        if (
            item.status == "failed"
            or receipt is None
            or metadata is None
            or metadata.has_audio is not True
            or coverage is None
            or source_sha256 is None
            or receipt.analysis_depth not in {"speech_text", "full"}
            or coverage.asr.collection_status != "unavailable"
            or coverage.asr.reason_codes != ["UNAVAILABLE_PROVIDER_EXECUTION_NOT_AUTHORIZED"]
        ):
            continue
        stage_spec_sha256 = receipt.provider_stage_spec_sha256.get("asr")
        if stage_spec_sha256 is None:
            continue
        provider_request_sha256 = cloud_provider_request_sha256(
            capability="asr",
            source_sha256=source_sha256,
            stage_spec_sha256=stage_spec_sha256,
        )
        duration_millis = max(1, round(float(metadata.duration_seconds) * 1_000))
        operator_capped = bool(os.getenv("MEDIAKIT_API_KEY", "").strip()) and direct_pay_policy.admits_source(duration_millis=duration_millis)
        local_limit = direct_pay_policy.local_admission_limit_micros if operator_capped else None
        price_status = "operator_capped" if operator_capped else "unknown"
        policy_version = direct_pay_policy.policy_version if operator_capped else "evidence-paid-call-policy-v1"
        price_version = "provider-price-unknown-local-admission-cap-v1" if operator_capped else "volc-doc-104992-reviewed-2026-08-02-unquoted"
        billing_basis = "供应商价格未知；Owner 接受本地准入风险上限，该上限不是供应商计费封顶" if operator_capped else "官方按量计费；当前未取得可核验的单次最高报价"
        request_key = "evidence-asr:" + _canonical_sha256(
            {
                "contract_version": "ip-agent-evidence-paid-call-key-v1",
                "owner_user_id": owner_user_id,
                "thread_id": thread_id,
                "origin_run_id": origin_run_id,
                "server_name": str(request.server_name),
                "tool_name": str(request.name),
                "tool_args_sha256": tool_args_sha256,
                "source_sha256": source_sha256,
                "stage_spec_sha256": stage_spec_sha256,
                "provider_request_sha256": provider_request_sha256,
                "provider": "volcengine-mediakit",
                "capability": "asr",
                "source_duration_millis": duration_millis,
                "price_status": price_status,
                "local_admission_limit_micros": local_limit,
                "policy_version": policy_version,
                "price_version": price_version,
            }
        )
        proposal = {
            "owner_user_id": owner_user_id,
            "request_key": request_key,
            "scope_kind": "run",
            "thread_id": thread_id,
            "origin_run_id": origin_run_id,
            "server_name": str(request.server_name),
            "tool_name": str(request.name),
            "tool_args_sha256": tool_args_sha256,
            "provider": "volcengine-mediakit",
            "capability": "asr",
            "model": "official-mediakit-asr-subtitles",
            "sku": "asr-subtitles",
            "provider_label": "火山引擎 AI MediaKit",
            "capability_label": "语音转写",
            "object_ref_label": (f"参考视频 {index}（SHA {source_sha256[:8]}…{source_sha256[-8:]}）"),
            "source_duration_millis": duration_millis,
            "source_sha256": source_sha256,
            "stage_digest": stage_spec_sha256,
            "provider_request_sha256": provider_request_sha256,
            "maximum_amount_micros": local_limit,
            "currency": "CNY",
            "billing_basis": billing_basis,
            "price_status": price_status,
            "policy_version": policy_version,
            "price_version": price_version,
            "provider_input_attested": False,
            "evidence_coverage": "partial",
            "warning_code": "provider_content_hash_unattested",
            "expires_at": observed_at + _PROPOSAL_TTL,
            "now": observed_at,
        }
        existing_rows = await repository.list_thread(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
        )
        raw = _matching_existing_request(existing_rows, expected=proposal)
        if raw is None:
            try:
                raw = await repository.request_call(**proposal)
            except ValueError:
                # A concurrent replay may have won the unique request-key
                # insert. Re-read and accept only an exact immutable binding.
                raw = _matching_existing_request(
                    await repository.list_thread(
                        owner_user_id=owner_user_id,
                        thread_id=thread_id,
                    ),
                    expected=proposal,
                )
                if raw is None:
                    raise
        views.append(
            build_evidence_paid_call_view(raw).model_dump(
                mode="json",
                exclude_none=False,
            )
        )
    return views


async def _mark_unknown_cost_for_admitted_asr(
    *,
    repository: _ProposalRepository,
    request: Any,
    evidence: ReferenceVideoEvidence,
    observed_at: datetime,
) -> bool:
    scope = _runtime_scope(request)
    arguments = getattr(request, "args", None)
    if scope is None or not isinstance(arguments, Mapping):
        return False
    owner_user_id, thread_id, execution_run_id = scope
    try:
        validated_arguments = InspectReferenceVideosInput.model_validate(dict(arguments))
    except (TypeError, ValueError):
        return False
    if len(validated_arguments.video_refs) != 1 or evidence.requested_count != 1 or len(evidence.items) != 1:
        return False
    item = evidence.items[0]
    receipt = item.analysis_receipt
    metadata = item.media_metadata
    coverage = item.coverage
    source_sha256 = item.source.content_sha256
    if receipt is None or metadata is None or coverage is None or source_sha256 is None or receipt.analysis_depth not in {"speech_text", "full"} or coverage.asr.reason_codes == ["UNAVAILABLE_PROVIDER_EXECUTION_NOT_AUTHORIZED"]:
        return False
    stage_spec_sha256 = receipt.provider_stage_spec_sha256.get("asr")
    if stage_spec_sha256 is None:
        return False
    provider_request_sha256 = cloud_provider_request_sha256(
        capability="asr",
        source_sha256=source_sha256,
        stage_spec_sha256=stage_spec_sha256,
    )
    duration_millis = max(1, round(float(metadata.duration_seconds) * 1_000))
    tool_args_sha256 = canonical_tool_args_sha256(arguments)
    execution_outcome_digest = _canonical_sha256(
        {
            "contract_version": "evidence-asr-provider-outcome-v1",
            "owner_user_id": owner_user_id,
            "thread_id": thread_id,
            "execution_run_id": execution_run_id,
            "server_name": str(request.server_name),
            "tool_name": str(request.name),
            "tool_args_sha256": tool_args_sha256,
            "source_duration_millis": duration_millis,
            "source_sha256": source_sha256,
            "stage_spec_sha256": stage_spec_sha256,
            "provider_request_sha256": provider_request_sha256,
            "evidence": evidence.model_dump(mode="json", exclude_none=True),
        }
    )
    result = await repository.mark_operator_capped_asr_reconciliation_exact(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        execution_run_id=execution_run_id,
        server_name=str(request.server_name),
        tool_name=str(request.name),
        tool_args_sha256=tool_args_sha256,
        source_duration_millis=duration_millis,
        source_sha256=source_sha256,
        stage_digest=stage_spec_sha256,
        provider_request_sha256=provider_request_sha256,
        event_key=(f"direct-pay-reconciliation:{execution_run_id}:{execution_outcome_digest[:24]}"),
        execution_outcome_digest=execution_outcome_digest,
        now=observed_at,
    )
    return result is not None


async def _mark_unresolved_admitted_asr(
    *,
    repository: _ProposalRepository,
    request: Any,
    observed_at: datetime,
    outcome_kind: str,
) -> None:
    scope = _runtime_scope(request)
    arguments = getattr(request, "args", None)
    if scope is None or not isinstance(arguments, Mapping):
        return
    owner_user_id, thread_id, execution_run_id = scope
    tool_args_sha256 = canonical_tool_args_sha256(arguments)
    outcome_digest = _canonical_sha256(
        {
            "contract_version": "evidence-asr-unresolved-outcome-v1",
            "owner_user_id": owner_user_id,
            "thread_id": thread_id,
            "execution_run_id": execution_run_id,
            "server_name": str(request.server_name),
            "tool_name": str(request.name),
            "tool_args_sha256": tool_args_sha256,
            "outcome_kind": " ".join(str(outcome_kind).split())[:120],
        }
    )
    await repository.mark_operator_capped_asr_invocation_unresolved(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        execution_run_id=execution_run_id,
        server_name=str(request.server_name),
        tool_name=str(request.name),
        tool_args_sha256=tool_args_sha256,
        event_key=(f"direct-pay-unresolved:{execution_run_id}:{outcome_digest[:24]}"),
        execution_outcome_digest=outcome_digest,
        now=observed_at,
    )


def build_evidence_paid_call_interceptor(
    *,
    repository: _ProposalRepository | None = None,
    direct_pay_policy: EvidenceASRDirectPayPolicy | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Callable[[Any, Callable[[Any], Awaitable[Any]]], Awaitable[Any]]:
    """Build the Evidence proposal and consumed-grant settlement interceptor."""

    observed_clock = clock or (lambda: datetime.now(UTC))
    policy = direct_pay_policy or EvidenceASRDirectPayPolicy.from_environment()

    async def interceptor(
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        active_repository = repository or _default_repository()
        target_route = str(getattr(request, "server_name", "")) == _EVIDENCE_SERVER and str(getattr(request, "name", "")) == _INSPECT_TOOL

        def observed_time(*, settlement: bool) -> datetime | None:
            observed_at = observed_clock()
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                logger.warning(
                    "Evidence paid-call clock is timezone-naive; %s",
                    "using server UTC for consumed-grant reconciliation" if settlement else "proposal skipped",
                )
                return datetime.now(UTC) if settlement else None
            return observed_at.astimezone(UTC)

        async def reconcile_unresolved(outcome_kind: str) -> None:
            if not target_route or active_repository is None:
                return
            occurred_at = observed_time(settlement=True)
            if occurred_at is None:
                return
            try:
                await _mark_unresolved_admitted_asr(
                    repository=active_repository,
                    request=request,
                    observed_at=occurred_at,
                    outcome_kind=outcome_kind,
                )
            except Exception as exc:
                logger.warning(
                    "Evidence paid-call unresolved outcome was not recorded: %s",
                    exc.__class__.__name__,
                )

        try:
            raw_result = await handler(request)
        except asyncio.CancelledError:
            # Keep the database transition alive after request cancellation;
            # the outer cancellation is still re-raised immediately.
            task = asyncio.create_task(reconcile_unresolved("mcp_call_cancelled"))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass
            raise
        except Exception as exc:
            await reconcile_unresolved(f"mcp_handler_exception:{exc.__class__.__name__}")
            raise

        if not isinstance(raw_result, CallToolResult):
            await reconcile_unresolved("non_call_tool_result")
            return raw_result
        try:
            result, sealed_source_handoff = _consume_reserved_meta(raw_result)
        except ValueError:
            await reconcile_unresolved("invalid_operator_private_metadata")
            raise
        if not target_route:
            return result
        if result.isError:
            await reconcile_unresolved("mcp_error_result")
            return result
        try:
            evidence = ReferenceVideoEvidence.model_validate(result.structuredContent)
        except (TypeError, ValueError):
            await reconcile_unresolved("invalid_reference_evidence_result")
            return result
        if sealed_source_handoff is not None and not _handoff_matches_evidence(
            sealed_source_handoff,
            evidence,
        ):
            await reconcile_unresolved("invalid_sealed_source_handoff")
            return result
        if active_repository is None:
            return result

        normalized_observed_at = observed_time(settlement=True)
        if normalized_observed_at is None:
            return result
        exact_reconciliation = False
        try:
            exact_reconciliation = await _mark_unknown_cost_for_admitted_asr(
                repository=active_repository,
                request=request,
                evidence=evidence,
                observed_at=normalized_observed_at,
            )
        except Exception as exc:
            logger.warning(
                "Evidence paid-call exact outcome was not recorded: %s",
                exc.__class__.__name__,
            )
        if not exact_reconciliation:
            await reconcile_unresolved("reference_evidence_without_exact_cost")

        proposal_time = observed_time(settlement=False)
        if proposal_time is None:
            return result
        try:
            views = await _persist_asr_proposals(
                repository=active_repository,
                request=request,
                evidence=evidence,
                direct_pay_policy=policy,
                observed_at=proposal_time,
            )
        except Exception as exc:  # local evidence must survive control-plane loss
            logger.warning(
                "Evidence paid-call proposal was not persisted: %s",
                exc.__class__.__name__,
            )
            return result
        if not views:
            return result
        # Put the trusted control-plane field first so the generic bounded MCP
        # metadata sanitizer cannot truncate it behind 64 untrusted keys.
        meta = {PAID_CALL_REQUESTS_META_KEY: views, **dict(result.meta or {})}
        return result.model_copy(update={"meta": meta})

    return interceptor


__all__ = [
    "PAID_CALL_REQUESTS_META_KEY",
    "build_evidence_paid_call_interceptor",
]
