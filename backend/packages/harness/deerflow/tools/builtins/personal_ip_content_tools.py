"""Native tools for the bounded Personal-IP writer brain and content ledger."""

from __future__ import annotations

import json

from langchain.tools import tool

from deerflow.config.app_config import AppConfig
from deerflow.personal_ip.content_contracts import (
    BreakdownSaveRequest,
    ContentWorkAppend,
    ContentWorkCreate,
    WriterBrainRequest,
)
from deerflow.personal_ip.evidence_binding import bind_breakdown_to_reference_evidence
from deerflow.personal_ip.runtime import get_personal_ip_runtime
from deerflow.personal_ip.writer_brain import WriterBrainService
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bind_external_breakdown(
    runtime: Runtime,
    request: BreakdownSaveRequest | WriterBrainRequest,
) -> tuple[
    BreakdownSaveRequest | WriterBrainRequest,
    dict[str, dict],
]:
    breakdown = request.breakdown
    if breakdown is None or breakdown.source_kind == "owner_material":
        return request, {}
    messages = runtime.state.get("messages") if runtime.state is not None else None
    if not isinstance(messages, list):
        raise ValueError("typed Evidence MCP history is not available in this task")
    bound = bind_breakdown_to_reference_evidence(breakdown, messages=messages)
    return request.model_copy(update={"breakdown": bound.breakdown}), {str(bound.breakdown.evidence_request_id): bound.evidence_snapshot}


async def _ip_content_write(runtime: Runtime, request: WriterBrainRequest) -> str:
    """Generate and save one complete, versioned content script.

    Use this after the Owner and you have chosen a total-editor decision and a
    work direction. For a new program, provide editorial_program with an
    ordered conversion/recognition/trust mission, time horizon, explicit
    person/product/brand/organization attribution, one still-hypothesized
    difference and an optional continuing editorial spine. To continue an
    existing program across another work, provide its exact immutable
    editorial_program_version_id. Mission and attribution are independent.

    Choose route_kind separately. offer, proof, demonstration and explanation
    are factual and skip the semantic engine. semantic_story uses fictional
    truth; hybrid uses hybrid truth; both require semantic_route and a Chinese-only
    story_engine_seed whose causal_pattern exactly matches that route. The seed
    contains only an industry-neutral human conflict: no Owner identity,
    profession, shop type, product, marketing, platform or production facts.
    The server binds program, route, direction and script digests, locks fiction
    before production translation, and stores the complete lineage together.

    For a new work, also provide entry_route and objective. A benchmark entry
    requires a source-bound breakdown. Factual and hybrid directions require
    explicit claim_basis entries.

    For an external breakdown, copy metadata.request_id from the exact Evidence
    MCP result and use item index 0 for its first item. Every observation ref
    must use evidence://{request_id}/items/{item_index}/{token}. Typical tokens
    are source, media-metadata, analysis-receipt, coverage/asr, coverage/ocr,
    provider/asr, provider/ocr, provider/scene_segmentation and
    provider/storyline. Never invent JSON field-path refs or request_id#field.
    A ref only supports its typed scope: ASR supports spoken words and coverage,
    not the absence of music or sound effects; OCR supports recognized visible
    text; media-metadata supports mechanical properties only.

    If a standalone breakdown was already saved, pass its content_work_id and
    exact breakdown_version_id in direction.breakdown_version_ids, and omit
    request.breakdown. Include breakdown again only to create an intentionally
    revised immutable BreakdownVersion.

    Args:
        request: Typed writer-brain handoff. Use content_work_id to derive a new version.

    Returns:
        JSON ids, locked-story digest and complete saved script.
    """
    try:
        services = get_personal_ip_runtime()
        if services.content is None:
            raise RuntimeError("Personal-IP content persistence is not available")
        context = runtime.context if isinstance(runtime.context, dict) else {}
        app_config = context.get("app_config")
        if not isinstance(app_config, AppConfig):
            raise RuntimeError("Writer model configuration is not available")
        run_id = str(context.get("run_id") or "").strip()
        tool_call_id = str(runtime.tool_call_id or "").strip()
        if not run_id or not tool_call_id:
            raise RuntimeError("Writer run identity is not available")
        request, evidence_snapshots = _bind_external_breakdown(runtime, request)
        result = await WriterBrainService(
            services.content,
            subjects=services.subjects,
        ).generate_and_save(
            owner_user_id=resolve_runtime_user_id(runtime),
            request=request,
            idempotency_key=f"{run_id}:{tool_call_id}",
            created_by_run_id=run_id,
            app_config=app_config,
            thread_id=str(context.get("thread_id") or "") or None,
            verified_evidence_snapshots=evidence_snapshots,
        )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Content could not be generated and saved",
            }
        )


async def _ip_content_read(runtime: Runtime, content_work_id: str = "", limit: int = 20) -> str:
    """Read saved content works or the complete lineage of one work.

    Args:
        content_work_id: Stable content work id. Empty lists the Owner's recent works.
        limit: Maximum recent works when content_work_id is empty, from 1 to 100.

    Returns:
        JSON content summary list or complete immutable version lineage.
    """
    try:
        services = get_personal_ip_runtime()
        if services.content is None:
            raise RuntimeError("Personal-IP content persistence is not available")
        owner_user_id = resolve_runtime_user_id(runtime)
        work_id = str(content_work_id or "").strip()
        if work_id:
            result = await services.content.get_lineage(work_id, owner_user_id=owner_user_id)
            if result is None:
                return _json(
                    {
                        "status": "error",
                        "category": "not_found",
                        "message": "Personal-IP content work not found",
                    }
                )
            return _json({"operation_status": "ok", **result})
        bounded_limit = max(1, min(int(limit), 100))
        works = await services.content.list(owner_user_id, limit=bounded_limit)
        return _json({"operation_status": "ok", "content_works": works})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Content is unavailable"})


async def _ip_content_save_breakdown(runtime: Runtime, request: BreakdownSaveRequest) -> str:
    """Save a source-bound BreakdownVersion without forcing script creation.

    Call this after inspecting an exact link or uploaded file when the Owner
    asked for a breakdown, or before the Owner has chosen a writing direction.
    Observations need evidence refs; interpretations stay labelled as derived
    or hypothesized. Reuse the returned content_work_id in a later write call.

    Copy metadata.request_id from the exact Evidence MCP result and use item
    index 0 for its first item. Every observation ref must use
    evidence://{request_id}/items/{item_index}/{token}. Typical tokens are
    source, media-metadata, analysis-receipt, coverage/asr, coverage/ocr,
    provider/asr, provider/ocr, provider/scene_segmentation and
    provider/storyline. Never invent JSON field-path refs or request_id#field.
    A ref only supports its typed scope: ASR supports spoken words and coverage,
    not the absence of music or sound effects; OCR supports recognized visible
    text; media-metadata supports mechanical properties only.

    Args:
        request: Standalone breakdown plus work identity or new-work objective.

    Returns:
        JSON stable content_work_id and immutable breakdown_version_id.
    """
    try:
        services = get_personal_ip_runtime()
        if services.content is None:
            raise RuntimeError("Personal-IP content persistence is not available")
        context = runtime.context if isinstance(runtime.context, dict) else {}
        run_id = str(context.get("run_id") or "").strip()
        tool_call_id = str(runtime.tool_call_id or "").strip()
        if not run_id or not tool_call_id:
            raise RuntimeError("Breakdown run identity is not available")
        request, evidence_snapshots = _bind_external_breakdown(runtime, request)
        idempotency_key = f"{run_id}:{tool_call_id}"
        owner_user_id = resolve_runtime_user_id(runtime)
        if request.content_work_id is None:
            assert request.objective is not None
            saved = await services.content.create(
                owner_user_id=owner_user_id,
                request=ContentWorkCreate(
                    idempotency_key=idempotency_key,
                    subject_id=request.subject_id,
                    title=request.work_title,
                    entry_route="benchmark",
                    objective=request.objective,
                    breakdown=request.breakdown,
                ),
                created_by_run_id=run_id,
                thread_id=str(context.get("thread_id") or "") or None,
                verified_evidence_snapshots=evidence_snapshots,
            )
            breakdown = saved["breakdown_versions"][-1]
            work_id = saved["content_work"]["id"]
            replayed = bool(saved.get("replayed"))
        else:
            saved = await services.content.append(
                request.content_work_id,
                owner_user_id=owner_user_id,
                request=ContentWorkAppend(
                    idempotency_key=idempotency_key,
                    breakdown=request.breakdown,
                ),
                created_by_run_id=run_id,
                verified_evidence_snapshots=evidence_snapshots,
            )
            if saved is None:
                return _json(
                    {
                        "status": "error",
                        "category": "not_found",
                        "message": "Personal-IP content work not found",
                    }
                )
            breakdown = saved["breakdown_version"]
            work_id = saved["content_work_id"]
            replayed = bool(saved.get("replayed"))
        return _json(
            {
                "operation_status": "ok",
                "content_work_id": work_id,
                "breakdown_version_id": breakdown["id"],
                "version_number": breakdown["version_number"],
                "replayed": replayed,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Breakdown could not be saved"})


async def _ip_content_start_production(
    runtime: Runtime,
    content_work_id: str,
    script_version_id: str,
    title: str,
    production_mode: str,
    target_account_ids: list[str],
    delivery_spec: dict,
    provider_policy: dict,
    budget: dict,
) -> str:
    """Start one production from an immutable saved ScriptVersion.

    Use this only after the Owner chooses a saved script version for production.
    The server verifies that the work and script belong to the current Owner,
    seals the full ScriptVersion as the immutable production source and keeps
    all later production receipts in the existing video-production ledger.

    Args:
        content_work_id: Stable content work id returned by content writing.
        script_version_id: Exact immutable ScriptVersion selected for production.
        title: Customer-facing production title.
        production_mode: faceless_material or generative_cinematic.
        target_account_ids: Owner-scoped publishing account targets, or an empty list.
        delivery_spec: Aspect ratio, duration, language and deliverable constraints.
        provider_policy: Preferred providers/models and permitted fallbacks.
        budget: Currency and hard_limit, or an empty object for free-only work.

    Returns:
        JSON production id, linked content/script ids, stage and immutable source receipt.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        context = runtime.context if isinstance(runtime.context, dict) else {}
        run_id = str(context.get("run_id") or "").strip()
        tool_call_id = str(runtime.tool_call_id or "").strip()
        if not run_id or not tool_call_id:
            raise RuntimeError("Production run identity is not available")
        work_id = str(content_work_id or "").strip()
        script_id = str(script_version_id or "").strip()
        if not work_id or not script_id:
            raise ValueError("content_work_id and script_version_id are required for content production")
        result = await services.video_productions.begin(
            owner_user_id=resolve_runtime_user_id(runtime),
            operation_key=f"{run_id}:{tool_call_id}",
            title=title,
            subject_id=None,
            target_account_ids=target_account_ids,
            source_kind="script",
            source={},
            delivery_spec=delivery_spec,
            provider_policy=provider_policy,
            budget=budget,
            production_mode=production_mode,
            thread_id=str(context.get("thread_id") or "").strip() or None,
            content_work_id=work_id,
            script_version_id=script_id,
        )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Production could not be started",
            }
        )


ip_content_write_tool = tool("ip_content_write", parse_docstring=True)(_ip_content_write)
ip_content_read_tool = tool("ip_content_read", parse_docstring=True)(_ip_content_read)
ip_content_save_breakdown_tool = tool("ip_content_save_breakdown", parse_docstring=True)(_ip_content_save_breakdown)
ip_content_start_production_tool = tool("ip_content_start_production", parse_docstring=True)(_ip_content_start_production)


__all__ = [
    "ip_content_read_tool",
    "ip_content_save_breakdown_tool",
    "ip_content_start_production_tool",
    "ip_content_write_tool",
]
