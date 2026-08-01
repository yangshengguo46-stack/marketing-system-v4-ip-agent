"""Native DeerFlow tools for whole-portfolio Personal-IP performance work."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from langchain.tools import tool

from deerflow.config.paths import get_paths
from deerflow.personal_ip.account_diagnosis import PersonalIPAccountDiagnosticContextService
from deerflow.personal_ip.browser_collection import (
    BrowserPlatformCollectionError,
    BrowserPlatformCollectionService,
    BrowserPortfolioMetricCollectionService,
    DouyinBrowserCollectionError,
    DouyinBrowserCollectionService,
    acquire_account_browser_session,
)
from deerflow.personal_ip.browser_profiles import select_browser_account_target
from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient, DouyinOAuthError
from deerflow.personal_ip.final_timeline_renderer import render_locked_timeline_delivery
from deerflow.personal_ip.frame_interpolation import interpolate_video_candidate
from deerflow.personal_ip.generated_shot_qa import run_generated_shot_qa
from deerflow.personal_ip.material_inspection import inspect_local_video_material
from deerflow.personal_ip.media_execution import normalize_media_execution_receipt
from deerflow.personal_ip.operating_cockpit import (
    PersonalIPOperatingCockpitService,
    PersonalIPStartupContextService,
)
from deerflow.personal_ip.platform_metrics import (
    DouyinAuthorizedMetricCollectionService,
    PlatformMetricCollectionError,
)
from deerflow.personal_ip.remotion_renderer import render_remotion_scene
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, get_personal_ip_runtime
from deerflow.personal_ip.video_contracts import (
    compile_approved_assembly,
    compile_asset_manifest,
    compile_continuity_ledger,
    compile_final_edit_lock,
    compile_generated_shot_qa,
    compile_material_inspection,
    compile_material_selection,
    compile_narration_contract,
    compile_narration_timing,
    compile_storyboard,
    compile_timeline_revision,
    compile_video_plan,
    resolve_video_production_mode,
)
from deerflow.personal_ip.video_method_distillation import (
    compile_video_method_distillation,
    compile_video_method_skill_candidate,
)
from deerflow.personal_ip.video_skill_compiler import (
    compile_video_pattern,
    compile_video_skill_candidate,
)
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_PLATFORM_OBSERVATION_DATASETS = {
    "account_profile",
    "audience_analytics",
    "comments",
    "content_inventory",
    "content_metrics",
    "conversions",
    "dashboard",
    "platform_receipts",
    "traffic_sources",
}


def _parse_datetime(value: str, *, field: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _parse_datetime_with_timezone(value: str, *, field: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime with timezone") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _authorized_douyin_service(services: PersonalIPRuntimeServices) -> DouyinAuthorizedMetricCollectionService:
    app_id = os.environ.get("DOUYIN_MINI_APP_ID", "").strip()
    app_secret = os.environ.get("DOUYIN_MINI_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise ValueError("Douyin mini-app authorization is not configured")
    return DouyinAuthorizedMetricCollectionService(
        connections=services.connections,
        metrics=services.metrics,
        publish_receipts=services.publish_receipts,
        oauth_client=DouyinMiniAppOAuthClient(app_id=app_id, app_secret=app_secret),
    )


def _douyin_browser_collection_service(services: PersonalIPRuntimeServices) -> DouyinBrowserCollectionService:
    if services.accounts is None or services.platform_observations is None:
        raise ValueError("Personal-IP browser collection is not available")
    return DouyinBrowserCollectionService(
        accounts=services.accounts,
        observations=services.platform_observations,
    )


def _browser_platform_collection_service(services: PersonalIPRuntimeServices) -> BrowserPlatformCollectionService:
    if services.accounts is None or services.platform_observations is None:
        raise ValueError("Personal-IP browser collection is not available")
    return BrowserPlatformCollectionService(
        accounts=services.accounts,
        observations=services.platform_observations,
    )


def _browser_portfolio_metric_service(services: PersonalIPRuntimeServices) -> BrowserPortfolioMetricCollectionService:
    if services.accounts is None or services.platform_observations is None:
        raise ValueError("Personal-IP browser portfolio collection is not available")
    return BrowserPortfolioMetricCollectionService(
        accounts=services.accounts,
        observations=services.platform_observations,
        metrics=services.metrics,
    )


def _operating_cockpit_service(services: PersonalIPRuntimeServices) -> PersonalIPOperatingCockpitService:
    required = {
        "subjects": services.subjects,
        "accounts": services.accounts,
        "brand": services.brand,
        "differentiation": services.differentiation,
        "preflights": services.preflights,
        "publish_receipts": services.publish_receipts,
        "metrics": services.metrics,
        "platform_observations": services.platform_observations,
        "retrospectives": services.retrospectives,
        "video_productions": services.video_productions,
    }
    missing = sorted(name for name, repository in required.items() if repository is None)
    if missing:
        raise RuntimeError(f"Personal-IP operating cockpit is incomplete: {', '.join(missing)}")
    return PersonalIPOperatingCockpitService(**required)


def _startup_context_service(services: PersonalIPRuntimeServices) -> PersonalIPStartupContextService:
    if services.subjects is None or services.accounts is None:
        raise RuntimeError("Personal-IP startup context is unavailable")
    return PersonalIPStartupContextService(
        subjects=services.subjects,
        accounts=services.accounts,
    )


def _account_diagnostic_service(
    services: PersonalIPRuntimeServices,
) -> PersonalIPAccountDiagnosticContextService:
    required = {
        "accounts": services.accounts,
        "platform_observations": services.platform_observations,
        "retrospectives": services.retrospectives,
    }
    missing = sorted(name for name, repository in required.items() if repository is None)
    if missing:
        raise RuntimeError("Personal-IP account diagnosis is incomplete: " + ", ".join(missing))
    return PersonalIPAccountDiagnosticContextService(
        accounts=services.accounts,
        brand=services.brand,
        differentiation=services.differentiation,
        metrics=services.metrics,
        platform_observations=services.platform_observations,
        publish_receipts=services.publish_receipts,
        retrospectives=services.retrospectives,
    )


async def _personal_ip_startup_context(runtime: Runtime) -> str:
    """Check whether this is a true Personal-IP cold start.

    Call this before deciding whether a new conversation needs the full
    operating cockpit. It reads only active subject and account existence. If
    experience is new_owner, respond to the user's current request and do not
    scan strategy, publishing, metric, retrospective or video ledgers. If it
    is returning_owner, use the whole-portfolio cockpit when durable operating
    state is relevant.

    Returns:
        JSON cold-start classification, minimal counts and whether the complete
        operating cockpit is needed.
    """
    try:
        result = await _startup_context_service(get_personal_ip_runtime()).build(owner_user_id=resolve_runtime_user_id(runtime))
        return _json(result)
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Personal-IP startup context is unavailable"})


async def _personal_ip_operating_cockpit(runtime: Runtime) -> str:
    """Read the user's whole Personal-IP business and video operating state.

    Use this for a returning owner, a resume request or a portfolio-wide
    operating question after startup context says the complete read is needed.
    Do not use it for a confirmed new_owner cold start. It joins every subject
    and platform account with modeling, preflight, publishing, performance,
    retrospective and video production queues. It
    intentionally has no account filter because one conversation coordinates
    the user's entire portfolio.

    Returns:
        JSON containing the six-stage operating loop, nine-stage video line,
        explicit work queues, recent receipts and bounded history coverage.
    """
    try:
        services = get_personal_ip_runtime()
        owner_user_id = resolve_runtime_user_id(runtime)
        startup = await _startup_context_service(services).build(owner_user_id=owner_user_id)
        if not startup["should_read_operating_cockpit"]:
            return _json(
                {
                    **startup,
                    "cockpit_skipped": True,
                    "message": "A new owner has no operating ledger to resume; continue from the current request.",
                }
            )
        result = await _operating_cockpit_service(services).build(owner_user_id=owner_user_id)
        return _json(result)
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Personal-IP cockpit is unavailable"})


async def _personal_ip_account_diagnostic_context(
    runtime: Runtime,
    account_id: str,
) -> str:
    """Read owner-scoped evidence for one platform account.

    The account id selects only the concrete target. The tool returns available
    strategy notes, content, performance, platform and outcome observations.
    It never decides whether the account should continue, adjust or be
    replaced; the agent makes that judgment with the relevant methods.

    Args:
        account_id: Exact Personal-IP platform account to diagnose.

    Returns:
        Credential-free observations, provenance references and inventory
        counts. Missing data remains missing and does not block analysis.
    """
    try:
        context = await _account_diagnostic_service(get_personal_ip_runtime()).build(
            owner_user_id=resolve_runtime_user_id(runtime),
            account_id=account_id,
        )
        return _json(context)
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json(
            {
                "status": "error",
                "category": "invalid_request",
                "message": str(exc),
            }
        )
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Personal-IP account diagnostic context is unavailable",
            }
        )


async def _personal_ip_begin_video_production(
    runtime: Runtime,
    operation_key: str,
    title: str,
    subject_id: str,
    target_account_ids: list[str],
    source_kind: str,
    source: dict,
    delivery_spec: dict,
    provider_policy: dict,
    budget: dict,
    production_mode: str,
) -> str:
    """Create one immutable Personal-IP video production request.

    Call this once an idea or script and delivery intent are known. The request
    is provider-independent: Seedance, Seedream, speech, MediaKit, FFmpeg or a
    future provider are execution choices recorded later as append-only events.
    Reusing operation_key with the exact same request is idempotent.

    Args:
        operation_key: Stable idempotency key for this production request.
        title: Customer-facing production title.
        subject_id: Optional Personal-IP subject id; pass an empty string when absent.
        target_account_ids: Platform account ids targeted by the final delivery.
        source_kind: Either idea or script.
        source: Immutable source snapshot, such as an idea, brief or full script.
        delivery_spec: Aspect ratios, durations, languages and target deliverables.
        provider_policy: Preferred models/providers and allowed fallbacks.
        budget: Immutable currency, hard_limit and paid-call approval policy.
            It may be empty only for a free-only production; paid provider
            submission requires an enforceable hard_limit.
        production_mode: faceless_material for Personal-IP material videos, or generative_cinematic for films and ads.

    Returns:
        JSON production id, immutable request, current stage and ordered events.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.begin(
            owner_user_id=resolve_runtime_user_id(runtime),
            thread_id=str((runtime.context or {}).get("thread_id") or "").strip() or None,
            operation_key=operation_key,
            title=title,
            subject_id=str(subject_id or "").strip() or None,
            target_account_ids=target_account_ids,
            source_kind=source_kind,
            source=source,
            delivery_spec=delivery_spec,
            provider_policy=provider_policy,
            budget=budget,
            production_mode=production_mode,
        )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video production could not be created"})


async def _personal_ip_reserve_video_budget(
    runtime: Runtime,
    production_id: str,
    reservation_key: str,
    capability: str,
    provider: str,
    entity_type: str,
    entity_id: str,
    maximum_amount: float,
    currency: str,
    approval_event_key: str,
    request_ref: str,
) -> str:
    """Reserve a paid media call's hard maximum before provider submission.

    Call this before any paid image, video, speech or cloud-processing request.
    The server serializes concurrent reservations against the production's
    immutable hard limit. When the production requires explicit approval,
    approval_event_key must identify the human-approved paid-provider review
    whose budget request exactly matches this reservation. Every retry needs a
    new reservation_key and reservation.

    Args:
        production_id: Server-issued video production id.
        reservation_key: Stable idempotency key for this one provider attempt.
        capability: Provider capability such as image_generation, video_generation, speech_generation or media_processing.
        provider: Exact provider that will receive the paid request.
        entity_type: Production entity targeted by the call.
        entity_id: Stable target entity id.
        maximum_amount: Hard maximum this call may consume, in the budget currency.
        currency: Currency matching the immutable production budget.
        approval_event_key: Approved paid-provider review event key, or empty only when approval is disabled.
        request_ref: Credential-free immutable request or shot reference.

    Returns:
        JSON reservation receipt and current reserved, spent and available budget.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.reserve_budget(
            production_id,
            owner_user_id=resolve_runtime_user_id(runtime),
            reservation_key=reservation_key,
            capability=capability,
            provider=provider,
            entity_type=entity_type,
            entity_id=entity_id,
            maximum_amount=maximum_amount,
            currency=currency,
            approval_event_key=str(approval_event_key or "").strip() or None,
            request_ref=request_ref,
        )
        if result is None:
            return _json(
                {
                    "status": "error",
                    "category": "not_found",
                    "message": "Video production not found",
                }
            )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json(
            {
                "status": "error",
                "category": "invalid_request",
                "message": str(exc),
            }
        )
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Video budget could not be reserved",
            }
        )


async def _personal_ip_settle_video_budget(
    runtime: Runtime,
    production_id: str,
    reservation_id: str,
    settlement_key: str,
    actual_amount: float,
    currency: str,
    provider_receipt_ref: str,
) -> str:
    """Accumulate one provider attempt's actual cost against its reservation.

    Settle every succeeded or failed paid attempt from a real provider billing
    receipt before retrying. Actual cost cannot exceed the reserved maximum.
    If billing is temporarily unknown, keep the reservation active and settle
    it only when evidence arrives; do not guess or release it.

    Args:
        production_id: Server-issued video production id.
        reservation_id: Reservation returned before this provider submission.
        settlement_key: Stable idempotency key for this billing receipt.
        actual_amount: Actual provider cost, including zero for a called but free attempt.
        currency: Currency matching the reservation.
        provider_receipt_ref: Credential-free immutable provider billing/execution receipt reference.

    Returns:
        JSON settlement receipt and current reserved, spent and available budget.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.settle_budget(
            production_id,
            owner_user_id=resolve_runtime_user_id(runtime),
            reservation_id=reservation_id,
            settlement_key=settlement_key,
            actual_amount=actual_amount,
            currency=currency,
            provider_receipt_ref=provider_receipt_ref,
        )
        if result is None:
            return _json(
                {
                    "status": "error",
                    "category": "not_found",
                    "message": "Video production not found",
                }
            )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json(
            {
                "status": "error",
                "category": "invalid_request",
                "message": str(exc),
            }
        )
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Video budget could not be settled",
            }
        )


async def _personal_ip_release_video_budget(
    runtime: Runtime,
    production_id: str,
    reservation_id: str,
    release_key: str,
    reason: str,
) -> str:
    """Release a reservation only when no provider submission occurred.

    Never release an uncertain, failed or successful provider call merely to
    regain capacity. Called attempts must be settled, including a proven zero
    actual cost. Release is only for cancellation before submission.

    Args:
        production_id: Server-issued video production id.
        reservation_id: Active reservation to release.
        release_key: Stable idempotency key for this cancellation.
        reason: Evidence-grounded reason proving the provider was not called.

    Returns:
        JSON release receipt and current reserved, spent and available budget.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.release_budget(
            production_id,
            owner_user_id=resolve_runtime_user_id(runtime),
            reservation_id=reservation_id,
            release_key=release_key,
            reason=reason,
        )
        if result is None:
            return _json(
                {
                    "status": "error",
                    "category": "not_found",
                    "message": "Video production not found",
                }
            )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json(
            {
                "status": "error",
                "category": "invalid_request",
                "message": str(exc),
            }
        )
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Video budget could not be released",
            }
        )


async def _append_compiled_video_contract(
    runtime: Runtime,
    *,
    production_id: str,
    event_key: str,
    event_type: str,
    contract: dict,
    status: str = "succeeded",
    entity_type: str = "production",
    entity_id: str | None = None,
    input_refs: list[str] | None = None,
    output_refs: list[str] | None = None,
    provider: str = "deerflow_contract_compiler",
) -> str:
    services = get_personal_ip_runtime()
    if services.video_productions is None:
        raise RuntimeError("Personal-IP video production is not available")
    owner_user_id = resolve_runtime_user_id(runtime)
    result = await services.video_productions.append_event(
        production_id,
        owner_user_id=owner_user_id,
        event_key=event_key,
        event_type=event_type,
        status=status,
        entity_type=entity_type,
        entity_id=entity_id or production_id,
        payload=contract,
        input_refs=input_refs or [f"video-production://{production_id}/request"],
        output_refs=output_refs or [f"contract://{contract['contract_version']}/{contract['sha256']}"],
        provider=provider,
        model=None,
        provider_task_id=None,
        cost={"status": "known", "currency": "CNY", "amount": 0},
        occurred_at=None,
    )
    if result is None:
        return _json({"status": "error", "category": "not_found", "message": "Video production not found"})
    return _json({"operation_status": "ok", "compiled_contract": contract, **result})


async def _video_production_mode(runtime: Runtime, production_id: str) -> tuple[str, str]:
    production = await _load_video_production(runtime, production_id)
    mode = production.get("production_mode") or (production.get("source") or {}).get("production_mode")
    if not mode:
        raise ValueError("Video production has no production_mode; begin a typed production request")
    return str(production.get("id") or production_id), str(mode)


async def _load_video_production(runtime: Runtime, production_id: str) -> dict:
    services = get_personal_ip_runtime()
    if services.video_productions is None:
        raise RuntimeError("Personal-IP video production is not available")
    owner_user_id = resolve_runtime_user_id(runtime)
    production = await services.video_productions.get(production_id, owner_user_id=owner_user_id)
    if production is None:
        raise ValueError("Video production not found")
    return production


def _latest_video_contract(production: dict, event_type: str) -> dict:
    matching = [event for event in production.get("events") or [] if isinstance(event, dict) and event.get("event_type") == event_type and isinstance(event.get("payload"), dict)]
    if not matching:
        raise ValueError(f"Video production has no {event_type} contract")
    return matching[-1]["payload"]


def _assembly_event_index(production: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for event in production.get("events") or []:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or "").strip()
        event_key = str(event.get("event_key") or "").strip()
        if event_id:
            result[f"event://{event_id}"] = event
        if event_key:
            result[f"event-key://{event_key}"] = event
    return result


def _verify_assembly_receipts(production: dict, contract: dict) -> None:
    indexed = _assembly_event_index(production)
    for clip in contract.get("clips") or []:
        candidate_id = clip["candidate_id"]
        selection_ref = clip["selection_receipt_ref"]
        selection = indexed.get(selection_ref)
        if selection is None:
            raise ValueError(f"selection receipt does not exist for {candidate_id}")
        selection_payload = selection.get("payload") if isinstance(selection.get("payload"), dict) else {}
        selected = selection.get("event_type") == "candidate_selected" and selection.get("status") == "succeeded"
        selected = selected or (selection.get("event_type") == "review_recorded" and selection.get("status") == "approved" and selection_payload.get("review_kind") == "candidate_selection")
        if not selected or selection.get("entity_type") != "candidate" or selection.get("entity_id") != candidate_id:
            raise ValueError(f"selection receipt does not approve candidate {candidate_id}")
        if selection_payload.get("source_sha256") != clip["source_sha256"]:
            raise ValueError(f"selection receipt source hash mismatch for {candidate_id}")

        qa_ref = clip["qa_receipt_ref"]
        qa = indexed.get(qa_ref)
        qa_payload = qa.get("payload") if isinstance(qa, dict) and isinstance(qa.get("payload"), dict) else {}
        qa_artifact = qa_payload.get("artifact") if isinstance(qa_payload.get("artifact"), dict) else {}
        if (
            qa is None
            or qa.get("event_type") != "generated_shot_qa_compiled"
            or qa.get("status") != "succeeded"
            or qa.get("entity_type") != "candidate"
            or qa.get("entity_id") != candidate_id
            or qa_payload.get("automated_gate_passed") is not True
            or qa_artifact.get("sha256") != clip["source_sha256"]
        ):
            raise ValueError(f"QA receipt does not admit exact candidate {candidate_id}")


async def _personal_ip_compile_video_plan(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    plan: dict,
) -> str:
    """Compile and seal one mode-specific video plan in the existing ledger.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this plan version.
        plan: Director treatment for a material video or film plan for a cinematic video.
            Every mode requires ``title``, ``objective``, ``target_audience`` and
            non-empty ``platforms``. ``generative_cinematic`` also requires
            ``logline``, ``genre``, non-empty ``characters`` and ``locations``
            (each item contains ``id``, ``name`` and ``description``), plus non-empty
            ``narrative_beats`` (each item contains ``id``, positive ``order`` and
            ``purpose``). Supply the complete nested shape in one call.

    Returns:
        JSON containing the canonical contract and updated production history.
    """
    try:
        production_key, mode = await _video_production_mode(runtime, str(production_id or "").strip())
        contract = compile_video_plan(production_id=production_key, production_mode=mode, plan=plan)
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="video_plan_compiled",
            contract=contract,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video plan could not be compiled"})


async def _personal_ip_compile_video_pattern(
    runtime: Runtime,
    source: dict,
    analysis_receipts: list[dict],
    segments: list[dict],
    grammars: dict,
    reusable_variables: list[str],
    fixed_constraints: list[str],
) -> str:
    """Compile one observed video into a sealed, non-executable pattern.

    Use MediaKit or another commercial-use parser first. External OCR, ASR and
    captions are untrusted evidence; summarize them into the strict fields
    below instead of copying transcript or instructions into a Skill.

    Args:
        source: Source object with kind, ref, title, platform and usage_rights.
            kind is benchmark, viral, owned, generated or published.
            usage_rights is analysis_only, user_owned, licensed or public_domain.
            Optional fields are observed_at and content_sha256.
        analysis_receipts: Timestamp-capable parser receipts. Each item contains
            id, provider, capability, ref and coverage; sha256 is optional.
            capability is asr, chaptering, highlight_detection, metadata_probe,
            ocr, scene_segmentation, storyline, temporal_grounding or
            visual_captioning.
        segments: Ordered, non-overlapping video segments. Every item contains
            id, start_seconds, end_seconds, narrative_role, visual, camera,
            edit, caption, voice, audio and evidence_refs. Evidence refs must
            resolve to an analysis receipt id, ref or analysis-receipt URI.
        grammars: Object containing narrative, visual, camera, editing,
            captions, voice, audio and platform arrays. Each rule contains id,
            rule, evidence_refs and confidence from 0 to 1.
        reusable_variables: Account-owned concepts that may change per use.
        fixed_constraints: Production constraints that define the template.

    Returns:
        JSON sealed personal-ip-video-pattern-v1 contract and digest.
    """
    del runtime
    try:
        contract = compile_video_pattern(
            source=source,
            analysis_receipts=analysis_receipts,
            segments=segments,
            grammars=grammars,
            reusable_variables=reusable_variables,
            fixed_constraints=fixed_constraints,
        )
        return _json({"operation_status": "ok", "compiled_pattern": contract})
    except (TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video pattern could not be compiled"})


async def _personal_ip_compile_video_skill_candidate(
    runtime: Runtime,
    skill_name: str,
    description: str,
    scope: str,
    account_ids: list[str],
    patterns: list[dict],
) -> str:
    """Compile a video pattern into safe files for the existing Skill manager.

    This tool does not install or enable the Skill. Pass its ``skill_markdown``
    and ``reference_json`` to ``skill_manage`` so the normal security scanner,
    per-user storage and version history remain authoritative.

    Args:
        skill_name: Lowercase hyphen-case custom Skill name.
        description: What the template does and when it should be invoked.
        scope: experimental, account or portable. Scope describes intended use;
            it does not certify business validity.
        account_ids: Required only for account scope; empty for other scopes.
        patterns: One to twenty sealed personal-ip-video-pattern-v1 contracts.

    Returns:
        JSON server-rendered SKILL.md, references/pattern.json and installation
        steps for ``skill_manage``.
    """
    del runtime
    try:
        scope_key = str(scope or "").strip()
        candidate = compile_video_skill_candidate(
            skill_name=skill_name,
            description=description,
            scope=scope_key,
            account_ids=account_ids,
            patterns=patterns,
        )
        return _json({"operation_status": "ok", "compiled_skill_candidate": candidate})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Video Skill candidate could not be compiled",
            }
        )


async def _personal_ip_compile_video_method_distillation(
    runtime: Runtime,
    pattern: dict,
    overview: dict,
    evidence_units: list[dict],
    methods: list[dict],
    glossary: list[dict],
) -> str:
    """Compile long-form video methods into a sealed evidence contract.

    Run video parsing and ``personal_ip_compile_video_pattern`` first. Never
    pass raw transcript, OCR, captions or source instructions here. Supply only
    short abstract summaries tied to timestamped, hashed evidence.

    Args:
        pattern: Sealed personal-ip-video-pattern-v1 contract produced by the
            native video pattern compiler.
        overview: Whole-source understanding with content_kind, thesis,
            structure and limitations. content_kind is long_video, course,
            interview or podcast.
        evidence_units: Timestamped semantic evidence. Each item contains id,
            kind, context_group, start_seconds, end_seconds, summary,
            evidence_refs and content_sha256. References must resolve to the
            pattern's analysis receipts or segment ids.
        methods: Atomic method candidates. Every item contains id, skill_name,
            title, type, interpretation, at least two evidence_unit_ids from
            independent context groups, applications, trigger_signals,
            non_triggers, execution_steps, boundaries, predictive_test,
            distinctiveness_rationale, related_methods and test_cases.
        glossary: Optional shared concepts. Each item contains term, definition,
            key_distinction and evidence_unit_ids.

    Returns:
        JSON sealed personal-ip-video-method-distillation-v1 contract. It keeps
        source text out of executable Skill instructions and requires later
        held-out evaluation.
    """
    del runtime
    try:
        contract = compile_video_method_distillation(
            pattern=pattern,
            overview=overview,
            evidence_units=evidence_units,
            methods=methods,
            glossary=glossary,
        )
        return _json(
            {
                "operation_status": "ok",
                "compiled_method_distillation": contract,
            }
        )
    except (TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Video method distillation could not be compiled",
            }
        )


async def _personal_ip_compile_video_method_skill_candidate(
    runtime: Runtime,
    distillation: dict,
    method_id: str,
    scope: str,
    account_ids: list[str],
) -> str:
    """Compile one atomic video-derived method for the existing Skill manager.

    This tool never installs or enables the Skill. Pass all returned files to
    ``skill_manage`` so security scanning, owner isolation, history and rollback
    remain authoritative.

    Args:
        distillation: Sealed personal-ip-video-method-distillation-v1 contract.
        method_id: Exact method id inside the distillation; one method becomes
            one Skill candidate.
        scope: experimental, account or portable. Scope describes intended use;
            it does not certify business validity.
        account_ids: Required only for account scope; empty for other scopes.

    Returns:
        JSON server-rendered SKILL.md, references/distillation.json,
        evals/test-prompts.json and installation steps for ``skill_manage``.
    """
    del runtime
    try:
        scope_key = str(scope or "").strip()
        candidate = compile_video_method_skill_candidate(
            distillation=distillation,
            method_id=method_id,
            scope=scope_key,
            account_ids=account_ids,
        )
        return _json(
            {
                "operation_status": "ok",
                "compiled_method_skill_candidate": candidate,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Video method Skill candidate could not be compiled",
            }
        )


async def _personal_ip_compile_video_asset_manifest(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    assets: list[dict],
) -> str:
    """Compile and seal one rights-aware video asset manifest.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this asset-manifest version.
        assets: Owned, sourced or generated assets. Every item must contain
            ``id``, ``type``, ``name``, ``source_ref`` and
            ``allowed_for_use`` equal to true. When a file hash is known, put the bare
            64-character lowercase digest in ``sha256``; do not prefix it with
            a scheme label and do not substitute a descriptive ``content_hash``.
            ``faceless_material`` assets additionally require ``license``.

    Returns:
        JSON containing the canonical manifest and updated production history.
    """
    try:
        production_key, mode = await _video_production_mode(runtime, str(production_id or "").strip())
        contract = compile_asset_manifest(production_id=production_key, production_mode=mode, assets=assets)
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="asset_manifest_compiled",
            contract=contract,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video asset manifest could not be compiled"})


async def _personal_ip_compile_video_storyboard(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    shots: list[dict],
) -> str:
    """Compile and seal mode-specific shot contracts in the existing ledger.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this storyboard version.
        shots: Complete ordered shot contracts. Every item requires ``id``,
            positive integer ``order`` and positive ``duration_seconds``.
            ``generative_cinematic`` additionally requires non-empty string
            fields ``scene_id``, ``first_frame``, ``last_frame``, ``motion``,
            ``camera`` and ``action``, plus string arrays
            ``preserve_elements`` and ``change_elements``. Do not use aliases
            such as ``sequence`` or ``expected_duration_seconds``.
            ``faceless_material`` instead requires ``narration_text``,
            ``visual_subject``, ``visual_query``, ``composition_strategy``,
            ``claim_evidence_refs``, exactly matching
            ``claim_evidence_quotes``, ``negative_conditions`` and
            ``pass_criteria``. Supply the complete nested shape in one call.

    Returns:
        JSON containing the canonical storyboard and updated production history.
    """
    try:
        production_key, mode = await _video_production_mode(runtime, str(production_id or "").strip())
        contract = compile_storyboard(production_id=production_key, production_mode=mode, shots=shots)
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="storyboard_compiled",
            contract=contract,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video storyboard could not be compiled"})


async def _personal_ip_compile_video_narration(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    language: str,
    segments: list[dict],
) -> str:
    """Compile exact spoken copy against the latest material-video storyboard.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this narration version.
        language: BCP-47-style narration language such as zh-CN.
        segments: One spoken segment per storyboard shot, in the same order.

    Returns:
        JSON canonical narration contract and updated immutable production.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        storyboard = _latest_video_contract(production, "storyboard_compiled")
        contract = compile_narration_contract(
            production_id=production_key,
            storyboard=storyboard,
            language=language,
            segments=segments,
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="narration_contract_compiled",
            contract=contract,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video narration could not be compiled"})


async def _personal_ip_compile_video_material_selection(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    selections: list[dict],
) -> str:
    """Compile frame-grounded, rights-cleared material ranges for every shot.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this material-selection version.
        selections: One asset/range/evidence selection per material-video shot.

    Returns:
        JSON canonical material-selection contract and updated production.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        asset_manifest = _latest_video_contract(production, "asset_manifest_compiled")
        storyboard = _latest_video_contract(production, "storyboard_compiled")
        contract = compile_material_selection(
            production_id=production_key,
            asset_manifest=asset_manifest,
            storyboard=storyboard,
            selections=selections,
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="material_selection_compiled",
            contract=contract,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video material selection could not be compiled"})


def _local_material_inspection_paths(
    *,
    owner_user_id: str,
    thread_id: str,
    production_id: str,
    asset_id: str,
    event_key: str,
    source_path: str,
) -> tuple[Path, Path, str, str, str]:
    paths = get_paths()
    safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
    source = paths.resolve_virtual_path(
        thread_id,
        source_path,
        user_id=safe_user_id,
    )
    if not source.is_file():
        raise ValueError("material source was not found in this task")
    suffix = ".exe" if os.name == "nt" else ""
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    ffmpeg = toolchain / f"ffmpeg{suffix}"
    ffprobe = toolchain / f"ffprobe{suffix}"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise ValueError("Project-local FFmpeg is not installed; run the product toolchain installer")
    review_key = sha256(f"{production_id}\0{asset_id}\0{event_key}".encode()).hexdigest()[:20]
    review_dir = paths.sandbox_outputs_dir(thread_id, user_id=safe_user_id) / "material-inspection" / review_key
    review_ref_prefix = f"/mnt/user-data/outputs/material-inspection/{review_key}"
    return source, review_dir, review_ref_prefix, str(ffmpeg), str(ffprobe)


async def _personal_ip_inspect_local_video_material(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    shot_id: str,
    asset_id: str,
    source_path: str,
    source_in_seconds: float,
    source_out_seconds: float,
    max_frames: int = 12,
) -> str:
    """Extract local timestamped frames and seal a material-inspection receipt.

    Args:
        production_id: Server-issued material-video production id.
        event_key: Stable idempotency key for this inspection.
        shot_id: Storyboard shot that the source range is intended to support.
        asset_id: Rights-cleared asset id from the latest asset manifest.
        source_path: Local source path below /mnt/user-data for the current task.
        source_in_seconds: Exact inclusive start of the candidate source range.
        source_out_seconds: Exact exclusive end of the candidate source range.
        max_frames: Maximum timestamped review frames, from 4 through 24.

    Returns:
        JSON mechanical inspection contract and updated immutable production.
    """

    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        mode = str(production.get("production_mode") or (production.get("source") or {}).get("production_mode") or "")
        if mode != "faceless_material":
            raise ValueError("Local material inspection is only available for faceless_material")
        asset_manifest = _latest_video_contract(production, "asset_manifest_compiled")
        storyboard = _latest_video_contract(production, "storyboard_compiled")
        asset = next(
            (item for item in asset_manifest.get("assets") or [] if isinstance(item, dict) and item.get("id") == asset_id),
            None,
        )
        if asset is None:
            raise ValueError("Material inspection asset is not in the latest manifest")
        if asset.get("allowed_for_use") is not True or not asset.get("license"):
            raise ValueError("Material inspection asset is not rights-authorized")
        if not any(isinstance(item, dict) and item.get("id") == shot_id for item in storyboard.get("shots") or []):
            raise ValueError("Material inspection shot is not in the latest storyboard")
        context = getattr(runtime, "context", None)
        if not isinstance(context, dict):
            raise ValueError("Local material inspection requires a task context")
        thread_id = str(context.get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("Local material inspection requires a thread_id")
        owner_user_id = resolve_runtime_user_id(runtime)
        (
            source,
            review_dir,
            review_ref_prefix,
            ffmpeg_path,
            ffprobe_path,
        ) = await asyncio.to_thread(
            _local_material_inspection_paths,
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            production_id=production_key,
            asset_id=str(asset_id or "").strip(),
            event_key=str(event_key or "").strip(),
            source_path=str(source_path or "").strip(),
        )
        evidence = await asyncio.to_thread(
            inspect_local_video_material,
            source,
            review_dir,
            source_in_seconds=source_in_seconds,
            source_out_seconds=source_out_seconds,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            source_ref=source_path,
            review_ref_prefix=review_ref_prefix,
            max_frames=max_frames,
        )
        evidence["source"]["ref"] = source_path
        manifest_digest = str(asset.get("sha256") or "").strip()
        if manifest_digest and evidence["source"]["sha256"] != manifest_digest:
            raise ValueError("Local material source hash does not match the asset manifest")
        contract = compile_material_inspection(
            production_id=production_key,
            shot_id=shot_id,
            asset_id=asset_id,
            evidence=evidence,
        )
        output_refs = [item["artifact"]["ref"] for item in evidence["frames"]] + [
            evidence["contact_sheet"]["ref"],
            evidence["report"]["ref"],
            f"contract://{contract['contract_version']}/{contract['sha256']}",
        ]
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="material_inspection_compiled",
            contract=contract,
            entity_type="asset",
            entity_id=asset_id,
            input_refs=[source_path],
            output_refs=output_refs,
            provider="ffmpeg_ffprobe",
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Local material inspection could not be completed",
            }
        )


async def _personal_ip_compile_video_narration_timing(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    segments: list[dict],
) -> str:
    """Reconcile exact narration text with measured TTS receipts.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this narration-timing version.
        segments: Measured audio, provider task, text hash and cost for every segment.

    Returns:
        JSON canonical narration-timing contract and updated production.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        narration = _latest_video_contract(production, "narration_contract_compiled")
        contract = compile_narration_timing(
            production_id=production_key,
            narration=narration,
            segments=segments,
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="narration_timing_compiled",
            contract=contract,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video narration timing could not be compiled"})


async def _personal_ip_compile_video_continuity(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    initial_facts: list[dict],
    shot_states: list[dict],
) -> str:
    """Compile a hash-chained continuity ledger for a cinematic storyboard.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this continuity version.
        initial_facts: Non-empty or empty initial state facts. Every fact is
            ``domain``, ``subject_id``, ``attribute`` and ``value``.
        shot_states: One item for every storyboard shot in exact order. Every
            item is ``shot_id``, positive integer ``order``, ``preserve`` and
            ``changes``. ``preserve`` items contain ``domain``, ``subject_id``,
            ``attribute`` and ``value``. ``changes`` items contain ``domain``,
            ``subject_id``, ``attribute``, ``before`` and nullable ``after``.

    Returns:
        JSON canonical continuity ledger and updated immutable production.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        storyboard = _latest_video_contract(production, "storyboard_compiled")
        contract = compile_continuity_ledger(
            production_id=production_key,
            storyboard=storyboard,
            initial_facts=initial_facts,
            shot_states=shot_states,
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="continuity_compiled",
            contract=contract,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video continuity could not be compiled"})


async def _personal_ip_compile_generated_shot_qa(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    shot_id: str,
    candidate_id: str,
    artifact: dict,
    anchor: dict,
    policy: dict,
    evidence: dict,
) -> str:
    """Compute one candidate's technical and temporal QA gates.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this QA execution.
        shot_id: Storyboard shot id.
        candidate_id: Candidate entity id produced for the shot.
        artifact: Candidate media reference and exact sha256.
        anchor: First-frame anchor reference and exact sha256.
        policy: Complete QA policy object with positive ``expected_width``,
            ``expected_height``, ``expected_fps`` and
            ``expected_duration_seconds``. Optional threshold fields are
            ``duration_tolerance_seconds`` (default 0.2),
            ``minimum_first_frame_ssim`` (default 0.85),
            ``maximum_internal_cut_count`` (default 0),
            ``expected_audio_stream_count`` (default 0) and
            ``expected_decode_error_count`` (default 0).
        evidence: Executor-derived probe, SSIM, cut and review-artifact evidence.

    Returns:
        JSON computed QA contract and updated immutable production.
    """
    try:
        production_key, mode = await _video_production_mode(runtime, str(production_id or "").strip())
        contract = compile_generated_shot_qa(
            production_id=production_key,
            production_mode=mode,
            shot_id=shot_id,
            candidate_id=candidate_id,
            artifact=artifact,
            anchor=anchor,
            policy=policy,
            evidence=evidence,
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="generated_shot_qa_compiled",
            contract=contract,
            status="succeeded" if contract["automated_gate_passed"] else "failed",
            entity_type="candidate",
            entity_id=candidate_id,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Generated-shot QA could not be compiled"})


def _local_generated_shot_qa_paths(
    *,
    owner_user_id: str,
    thread_id: str,
    production_id: str,
    candidate_id: str,
    event_key: str,
    artifact_path: str,
    anchor_path: str,
) -> tuple[Path, Path, Path, str, str, str]:
    paths = get_paths()
    safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
    artifact = paths.resolve_virtual_path(
        thread_id,
        artifact_path,
        user_id=safe_user_id,
    )
    anchor = paths.resolve_virtual_path(
        thread_id,
        anchor_path,
        user_id=safe_user_id,
    )
    if not artifact.is_file():
        raise ValueError("generated-shot artifact was not found in this task")
    if not anchor.is_file():
        raise ValueError("generated-shot anchor was not found in this task")
    suffix = ".exe" if os.name == "nt" else ""
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    ffmpeg = toolchain / f"ffmpeg{suffix}"
    ffprobe = toolchain / f"ffprobe{suffix}"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise ValueError("Project-local FFmpeg is not installed; run the product toolchain installer")
    review_key = sha256(f"{production_id}\0{candidate_id}\0{event_key}".encode()).hexdigest()[:20]
    review_dir = paths.sandbox_outputs_dir(thread_id, user_id=safe_user_id) / "video-qa" / review_key
    review_ref_prefix = f"/mnt/user-data/outputs/video-qa/{review_key}"
    return (
        artifact,
        anchor,
        review_dir,
        review_ref_prefix,
        str(ffmpeg),
        str(ffprobe),
    )


async def _personal_ip_run_local_generated_shot_qa(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    shot_id: str,
    candidate_id: str,
    artifact_path: str,
    anchor_path: str,
    policy: dict,
) -> str:
    """Measure a local generated shot and seal its QA evidence in the video ledger.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this local QA execution.
        shot_id: Storyboard shot id.
        candidate_id: Candidate entity id produced for the shot.
        artifact_path: Candidate path below /mnt/user-data for the current task.
        anchor_path: First-frame anchor path below /mnt/user-data for the current task.
        policy: Complete QA policy object with positive ``expected_width``,
            ``expected_height``, ``expected_fps`` and
            ``expected_duration_seconds``. Optional threshold fields are
            ``duration_tolerance_seconds``, ``minimum_first_frame_ssim``,
            ``maximum_internal_cut_count``, ``expected_audio_stream_count`` and
            ``expected_decode_error_count``. Motion analysis accepts
            ``motion_expectation`` (static, natural or continuous),
            ``target_playback_fps``, ``enforce_motion_cadence``,
            ``maximum_near_duplicate_ratio``,
            ``maximum_near_duplicate_run_seconds``,
            ``minimum_motion_fps`` and ``maximum_motion_delta_cv``.

    Returns:
        JSON compiled QA contract and updated immutable production.
    """

    try:
        production_key, mode = await _video_production_mode(runtime, str(production_id or "").strip())
        context = getattr(runtime, "context", None)
        if not isinstance(context, dict):
            raise ValueError("Local generated-shot QA requires a task context")
        thread_id = str(context.get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("Local generated-shot QA requires a thread_id")
        owner_user_id = resolve_runtime_user_id(runtime)
        (
            artifact,
            anchor,
            review_dir,
            review_ref_prefix,
            ffmpeg_path,
            ffprobe_path,
        ) = await asyncio.to_thread(
            _local_generated_shot_qa_paths,
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            production_id=production_key,
            candidate_id=str(candidate_id or "").strip(),
            event_key=str(event_key or "").strip(),
            artifact_path=str(artifact_path or "").strip(),
            anchor_path=str(anchor_path or "").strip(),
        )
        measured = await asyncio.to_thread(
            run_generated_shot_qa,
            artifact,
            anchor,
            review_dir,
            policy=policy,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            review_ref_prefix=review_ref_prefix,
            artifact_ref=artifact_path,
            anchor_ref=anchor_path,
        )
        measured["artifact"]["ref"] = artifact_path
        measured["anchor"]["ref"] = anchor_path
        contract = compile_generated_shot_qa(
            production_id=production_key,
            production_mode=mode,
            shot_id=shot_id,
            candidate_id=candidate_id,
            artifact=measured["artifact"],
            anchor=measured["anchor"],
            policy=policy,
            evidence=measured["evidence"],
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="generated_shot_qa_compiled",
            contract=contract,
            status="succeeded" if contract["automated_gate_passed"] else "failed",
            entity_type="candidate",
            entity_id=candidate_id,
            input_refs=[artifact_path, anchor_path],
            output_refs=[item["ref"] for item in measured["evidence"]["review_artifacts"]] + [f"contract://{contract['contract_version']}/{contract['sha256']}"],
            provider="ffmpeg_ffprobe",
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Local generated-shot QA could not be completed",
            }
        )


def _successful_candidate_source(
    production: dict,
    *,
    candidate_id: str,
    artifact_ref: str,
) -> dict:
    for event in reversed(production.get("events") or []):
        if not isinstance(event, dict) or event.get("entity_type") != "candidate" or event.get("entity_id") != candidate_id or event.get("status") != "succeeded" or event.get("event_type") != "shot_generation_completed":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        for artifact in reversed(payload.get("outputs") or []):
            if isinstance(artifact, dict) and artifact.get("ref") == artifact_ref and isinstance(artifact.get("sha256"), str) and len(artifact["sha256"]) == 64:
                return artifact
    raise ValueError("source candidate artifact has no successful immutable generation receipt")


def _local_frame_interpolation_paths(
    *,
    owner_user_id: str,
    thread_id: str,
    production_id: str,
    output_candidate_id: str,
    event_key: str,
    artifact_path: str,
) -> tuple[Path, Path, str, str, str, str]:
    paths = get_paths()
    safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
    source = paths.resolve_virtual_path(
        thread_id,
        artifact_path,
        user_id=safe_user_id,
    )
    if not source.is_file():
        raise ValueError("source candidate artifact was not found in this task")
    suffix = ".exe" if os.name == "nt" else ""
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    ffmpeg = toolchain / f"ffmpeg{suffix}"
    ffprobe = toolchain / f"ffprobe{suffix}"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise ValueError("Project-local FFmpeg is not installed; run the product toolchain installer")
    interpolation_key = sha256(f"{production_id}\0{output_candidate_id}\0{event_key}".encode()).hexdigest()[:20]
    output_dir = paths.sandbox_outputs_dir(thread_id, user_id=safe_user_id) / "video-interpolations" / interpolation_key
    output = output_dir / "candidate.mp4"
    output_ref = f"/mnt/user-data/outputs/video-interpolations/{interpolation_key}/candidate.mp4"
    task_id = f"local-frame-interpolation-{interpolation_key}"
    return source, output, output_ref, task_id, str(ffmpeg), str(ffprobe)


async def _personal_ip_interpolate_video_candidate(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    shot_id: str,
    source_candidate_id: str,
    output_candidate_id: str,
    artifact_path: str,
    target_fps: int,
) -> str:
    """Create a separate smooth-motion candidate with project-local FFmpeg.

    This uses FFmpeg ``minterpolate`` motion compensation rather than duplicate
    frames. The source remains immutable, the enhanced MP4 is recorded as a new
    candidate, and the new candidate still requires generated-shot QA and
    human selection before assembly.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this interpolation attempt.
        shot_id: Storyboard shot id shared by source and output candidates.
        source_candidate_id: Existing successful candidate id.
        output_candidate_id: New candidate id; it must not equal the source id.
        artifact_path: Recorded source MP4 below /mnt/user-data in this task.
        target_fps: Higher output frame rate from 1 through 120, normally 48 or 60.

    Returns:
        JSON updated production with an immutable checksummed candidate receipt.
    """

    try:
        production = await _load_video_production(
            runtime,
            str(production_id or "").strip(),
        )
        production_key = str(production.get("id") or production_id)
        mode = resolve_video_production_mode(production)
        source_id = str(source_candidate_id or "").strip()
        output_id = str(output_candidate_id or "").strip()
        shot_key = str(shot_id or "").strip()
        source_ref = str(artifact_path or "").strip()
        if not source_id or not output_id or not shot_key:
            raise ValueError("shot_id, source_candidate_id and output_candidate_id are required")
        if source_id == output_id:
            raise ValueError("output_candidate_id must create a new candidate")
        recorded_source = _successful_candidate_source(
            production,
            candidate_id=source_id,
            artifact_ref=source_ref,
        )
        context = getattr(runtime, "context", None)
        if not isinstance(context, dict):
            raise ValueError("Local frame interpolation requires a task context")
        thread_id = str(context.get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("Local frame interpolation requires a thread_id")
        owner_user_id = resolve_runtime_user_id(runtime)
        source, output, output_ref, task_id, ffmpeg_path, ffprobe_path = await asyncio.to_thread(
            _local_frame_interpolation_paths,
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            production_id=production_key,
            output_candidate_id=output_id,
            event_key=str(event_key or "").strip(),
            artifact_path=source_ref,
        )
        receipt = await asyncio.to_thread(
            interpolate_video_candidate,
            source,
            output,
            source_ref=source_ref,
            output_ref=output_ref,
            target_fps=target_fps,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            task_id=task_id,
            expected_source_sha256=recorded_source["sha256"],
        )
        receipt["parameters"].update(
            {
                "production_mode": mode,
                "shot_id": shot_key,
                "source_candidate_id": source_id,
                "output_candidate_id": output_id,
                "requires_fresh_qa": True,
                "requires_human_selection": True,
            }
        )
        normalized = normalize_media_execution_receipt(
            receipt,
            entity_type="candidate",
        )
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.append_event(
            production_key,
            owner_user_id=owner_user_id,
            event_key=event_key,
            event_type=normalized["event_type"],
            status=normalized["event_status"],
            entity_type="candidate",
            entity_id=output_id,
            payload=normalized["payload"],
            input_refs=normalized["input_refs"],
            output_refs=normalized["output_refs"],
            provider=normalized["provider"],
            model=normalized["model"],
            provider_task_id=normalized["provider_task_id"],
            cost=normalized["cost"],
            occurred_at=normalized["occurred_at"],
        )
        if result is None:
            return _json(
                {
                    "status": "error",
                    "category": "not_found",
                    "message": "Video production not found",
                }
            )
        return _json(
            {
                "operation_status": "ok",
                "output_candidate_id": output_id,
                "output_ref": output_ref,
                "next_required_actions": ["generated_shot_qa", "human_selection"],
                **result,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json(
            {
                "status": "error",
                "category": "invalid_request",
                "message": str(exc),
            }
        )
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Local frame interpolation could not be completed",
            }
        )


def _local_remotion_render_paths(
    *,
    owner_user_id: str,
    thread_id: str,
    production_id: str,
    candidate_id: str,
    event_key: str,
    scene_spec_path: str,
) -> tuple[Path, Path, str, str, str, str, str]:
    paths = get_paths()
    safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
    scene_spec = paths.resolve_virtual_path(
        thread_id,
        scene_spec_path,
        user_id=safe_user_id,
    )
    if not scene_spec.is_file():
        raise ValueError("Remotion scene spec was not found in this task")
    suffix = ".exe" if os.name == "nt" else ""
    toolchain = paths.base_dir / "toolchains" / "ffmpeg" / "bin"
    ffmpeg = toolchain / f"ffmpeg{suffix}"
    ffprobe = toolchain / f"ffprobe{suffix}"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise ValueError("Project-local FFmpeg is not installed; run the product toolchain installer")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValueError("Playwright browser runtime is not installed") from exc
    with sync_playwright() as playwright:
        browser = Path(playwright.chromium.executable_path)
    if not browser.is_file():
        raise ValueError("Playwright Chromium is not installed")
    render_key = sha256(f"{production_id}\0{candidate_id}\0{event_key}".encode()).hexdigest()[:20]
    output_dir = paths.sandbox_outputs_dir(thread_id, user_id=safe_user_id) / "video-renders" / render_key
    output = output_dir / "candidate.mp4"
    output_ref = f"/mnt/user-data/outputs/video-renders/{render_key}/candidate.mp4"
    task_id = f"local-remotion-{render_key}"
    return scene_spec, output, output_ref, task_id, str(ffmpeg), str(ffprobe), str(browser)


async def _personal_ip_render_local_remotion_scene(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    shot_id: str,
    candidate_id: str,
    scene_spec_path: str,
) -> str:
    """Render a deterministic local video candidate with pinned Remotion.

    The scene spec and every referenced media file must live below
    ``/mnt/user-data`` for the current task. The source-owned executor renders
    deterministic PNG frames with software Chromium, finishes them through the
    project-local FFmpeg build, verifies the MP4 and appends an immutable
    ``video_generation`` receipt. Remotion is currently enabled for MVP
    validation; customer distribution still requires license confirmation.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this render attempt.
        shot_id: Storyboard shot id represented by the scene spec.
        candidate_id: Stable candidate id created by this render.
        scene_spec_path: personal-ip-render-scene-v1 JSON below /mnt/user-data.

    Returns:
        JSON updated production projection and ordered immutable event history.
    """

    try:
        production_key, mode = await _video_production_mode(runtime, str(production_id or "").strip())
        context = getattr(runtime, "context", None)
        if not isinstance(context, dict):
            raise ValueError("Local Remotion rendering requires a task context")
        thread_id = str(context.get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("Local Remotion rendering requires a thread_id")
        owner_user_id = resolve_runtime_user_id(runtime)
        (
            scene_spec,
            output,
            output_ref,
            task_id,
            ffmpeg_path,
            ffprobe_path,
            browser_path,
        ) = await asyncio.to_thread(
            _local_remotion_render_paths,
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            production_id=production_key,
            candidate_id=str(candidate_id or "").strip(),
            event_key=str(event_key or "").strip(),
            scene_spec_path=str(scene_spec_path or "").strip(),
        )
        receipt = await asyncio.to_thread(
            render_remotion_scene,
            scene_spec,
            output,
            scene_spec_ref=scene_spec_path,
            output_ref=output_ref,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            browser_path=browser_path,
            task_id=task_id,
        )
        receipt["parameters"]["production_mode"] = mode
        receipt["parameters"]["shot_id"] = str(shot_id or "").strip()
        normalized = normalize_media_execution_receipt(receipt, entity_type="candidate")
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.append_event(
            production_key,
            owner_user_id=owner_user_id,
            event_key=event_key,
            event_type=normalized["event_type"],
            status=normalized["event_status"],
            entity_type="candidate",
            entity_id=candidate_id,
            payload=normalized["payload"],
            input_refs=normalized["input_refs"],
            output_refs=normalized["output_refs"],
            provider=normalized["provider"],
            model=normalized["model"],
            provider_task_id=normalized["provider_task_id"],
            cost=normalized["cost"],
            occurred_at=normalized["occurred_at"],
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Video production not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Local Remotion scene could not be rendered",
            }
        )


async def _personal_ip_compile_approved_video_assembly(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    timeline_id: str,
    resolution: str,
    fps: int,
    clips: list[dict],
) -> str:
    """Admit exact selected, QA-passing candidate hashes to a timeline.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this assembly version.
        timeline_id: Stable timeline entity id.
        resolution: Output resolution in WIDTHxHEIGHT form.
        fps: Output frames per second, between 1 and 120.
        clips: Ordered clips with exact source, selection and QA receipt hashes.

    Returns:
        JSON canonical assembly contract and updated immutable production.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        mode = resolve_video_production_mode(production)
        contract = compile_approved_assembly(
            production_id=production_key,
            production_mode=str(mode or ""),
            resolution=resolution,
            fps=fps,
            clips=clips,
        )
        _verify_assembly_receipts(production, contract)
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="assembly_admitted",
            contract=contract,
            entity_type="timeline",
            entity_id=str(timeline_id or "").strip(),
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Approved video assembly could not be compiled"})


async def _personal_ip_compile_video_timeline_revision(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    revision_id: str,
    base_revision_id: str,
    author_kind: str,
    intent: str,
    fps: int,
    tracks: list[dict],
    operations: list[dict],
    strategy_confirmed: bool,
) -> str:
    """Compile a human or agent edit into the shared append-only timeline.

    Use this for conversational editing after reading the current production.
    The complete resulting tracks are sealed alongside typed edit operations;
    never overwrite an earlier revision or use a shot id as conversation scope.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this edit decision.
        revision_id: New immutable timeline revision id.
        base_revision_id: Previous revision id, or an empty string for the admitted assembly.
        author_kind: human or agent.
        intent: The requested editorial change in plain language.
        fps: Output frames per second, between 1 and 120.
        tracks: Complete resulting video, dialogue, music and subtitle track snapshot.
        operations: Typed move, trim, split, delete, duplicate, replace_candidate, change_volume, edit_caption, add_transition or restore_revision decisions.
        strategy_confirmed: True after the edit strategy has been accepted for execution.

    Returns:
        JSON canonical timeline revision and updated immutable production.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        mode = resolve_video_production_mode(production)
        base_revision = str(base_revision_id or "").strip() or None
        contract = compile_timeline_revision(
            production_id=production_key,
            production_mode=str(mode or ""),
            revision_id=revision_id,
            base_revision_id=base_revision,
            author_kind=author_kind,
            intent=intent,
            fps=fps,
            tracks=tracks,
            operations=operations,
            strategy_confirmed=strategy_confirmed,
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="timeline_revision_compiled",
            contract=contract,
            entity_type="timeline",
            entity_id=contract["revision_id"],
            input_refs=([f"timeline-revision://{base_revision}"] if base_revision else [f"video-production://{production_key}/assembly"]),
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video timeline revision could not be compiled"})


async def _personal_ip_lock_video_final_edit(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    lock_id: str,
    locked_by: str,
    note: str,
) -> str:
    """Lock the latest timeline revision as the only delivery-QA input.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this final-edit lock.
        lock_id: New immutable lock entity id.
        locked_by: human or agent.
        note: Why this exact revision is ready for final rendering and QA.

    Returns:
        JSON final-edit lock contract and updated immutable production.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        timeline_revision = _latest_video_contract(production, "timeline_revision_compiled")
        mode = resolve_video_production_mode(production, contract=timeline_revision)
        contract = compile_final_edit_lock(
            production_id=production_key,
            production_mode=str(mode or ""),
            lock_id=lock_id,
            timeline_revision=timeline_revision,
            locked_by=locked_by,
            note=note,
        )
        return await _append_compiled_video_contract(
            runtime,
            production_id=production_key,
            event_key=event_key,
            event_type="final_edit_locked",
            contract=contract,
            entity_type="timeline",
            entity_id=contract["lock_id"],
            input_refs=[f"timeline-revision://{contract['source_revision_id']}"],
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Final video edit could not be locked"})


async def _personal_ip_render_locked_video_delivery(
    runtime: Runtime,
    production_id: str,
) -> str:
    """Render, verify and deliver the latest locked timeline with local tools.

    Call this only after ``personal_ip_lock_video_final_edit``. It resolves
    timeline candidates and voice solely from verified artifacts already
    recorded in the same production, renders with the project-pinned FFmpeg,
    fully decodes and probes the result, then appends media, QA and delivery
    receipts to the immutable ledger. It never calls a cloud model, publishes
    externally or overwrites an earlier delivery artifact.

    Args:
        production_id: Server-issued video production id whose latest edit is locked.

    Returns:
        JSON current production status, exact delivered artifact and QA checks.
    """
    try:
        production = await _load_video_production(runtime, str(production_id or "").strip())
        production_key = str(production.get("id") or production_id)
        timeline = _latest_video_contract(production, "timeline_revision_compiled")
        lock = _latest_video_contract(production, "final_edit_locked")
        revision_id = str(timeline.get("revision_id") or "").strip()
        revision_sha = str(timeline.get("sha256") or "").strip().lower()
        if lock.get("source_revision_id") != revision_id or lock.get("source_timeline_sha256") != revision_sha:
            raise ValueError("Latest final-edit lock does not freeze the latest timeline revision")
        key_suffix = sha256(f"{production_key}\0{revision_id}\0{revision_sha}".encode()).hexdigest()[:20]
        render_event_key = f"locked-timeline-render:{key_suffix}"
        qa_event_key = f"locked-timeline-qa:{key_suffix}"
        delivery_event_key = f"locked-timeline-delivery:{key_suffix}"
        existing_delivery = next(
            (event for event in production.get("events") or [] if isinstance(event, dict) and event.get("event_key") == delivery_event_key and event.get("status") == "succeeded"),
            None,
        )
        if existing_delivery is not None:
            return _json(
                {
                    "operation_status": "ok",
                    "idempotent_replay": True,
                    "production_id": production_key,
                    "status": production.get("status"),
                    "current_stage": production.get("current_stage"),
                    "event_count": production.get("event_count"),
                    "artifact": (existing_delivery.get("payload") or {}).get("artifact"),
                    "delivery_event_key": delivery_event_key,
                }
            )

        paths = get_paths()
        owner_user_id = resolve_runtime_user_id(runtime)
        safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
        suffix = ".exe" if os.name == "nt" else ""
        toolchain_candidates = [
            paths.base_dir / "toolchains" / "ffmpeg" / "bin",
            paths.base_dir.parent.parent / ".deer-flow" / "toolchains" / "ffmpeg" / "bin",
        ]
        toolchain = next(
            (candidate for candidate in toolchain_candidates if (candidate / f"ffmpeg{suffix}").is_file() and (candidate / f"ffprobe{suffix}").is_file()),
            toolchain_candidates[0],
        )
        ffmpeg_path = toolchain / f"ffmpeg{suffix}"
        ffprobe_path = toolchain / f"ffprobe{suffix}"
        if not ffmpeg_path.is_file() or not ffprobe_path.is_file():
            raise ValueError("Project-local FFmpeg is not installed; run the product toolchain installer")
        output_root = paths.user_dir(safe_user_id) / "video-deliveries" / sha256(production_key.encode()).hexdigest()[:24]
        render = await asyncio.to_thread(
            render_locked_timeline_delivery,
            production,
            output_root=output_root,
            ffmpeg_path=str(ffmpeg_path),
            ffprobe_path=str(ffprobe_path),
        )
        receipt = render["receipt"]
        normalized = normalize_media_execution_receipt(receipt, entity_type="delivery")
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        rendered = await services.video_productions.append_event(
            production_key,
            owner_user_id=owner_user_id,
            event_key=render_event_key,
            event_type=normalized["event_type"],
            status=normalized["event_status"],
            entity_type="delivery",
            entity_id=str(lock.get("lock_id") or revision_id),
            payload=normalized["payload"],
            input_refs=normalized["input_refs"],
            output_refs=normalized["output_refs"],
            provider=normalized["provider"],
            model=normalized["model"],
            provider_task_id=normalized["provider_task_id"],
            cost=normalized["cost"],
            occurred_at=normalized["occurred_at"],
        )
        if rendered is None:
            raise ValueError("Video production not found")

        qa = render["qa"]
        artifact_ref = str(qa["artifact"]["ref"])
        qa_result = await services.video_productions.append_event(
            production_key,
            owner_user_id=owner_user_id,
            event_key=qa_event_key,
            event_type="delivery_qa_completed",
            status="succeeded" if qa["passed"] else "failed",
            entity_type="delivery",
            entity_id=str(lock.get("lock_id") or revision_id),
            payload=qa,
            input_refs=[artifact_ref],
            output_refs=[artifact_ref],
            provider="project-ffmpeg-ffprobe",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0.0, "currency": "CNY", "basis": "local delivery QA"},
            occurred_at=None,
        )
        if qa_result is None:
            raise ValueError("Video production not found")
        if qa.get("passed") is not True:
            return _json(
                {
                    "operation_status": "blocked",
                    "production_id": production_key,
                    "status": qa_result.get("status"),
                    "current_stage": qa_result.get("current_stage"),
                    "event_count": qa_result.get("event_count"),
                    "artifact": qa["artifact"],
                    "qa": qa,
                    "message": "Locked timeline rendered, but current delivery QA failed",
                }
            )

        completed = await services.video_productions.append_event(
            production_key,
            owner_user_id=owner_user_id,
            event_key=delivery_event_key,
            event_type="delivery_completed",
            status="succeeded",
            entity_type="delivery",
            entity_id=str(lock.get("lock_id") or revision_id),
            payload={
                "accepted": True,
                "qa_event_key": qa_event_key,
                "artifact": qa["artifact"],
                "source_revision_id": revision_id,
                "source_timeline_sha256": revision_sha,
                "lock_id": lock.get("lock_id"),
            },
            input_refs=[artifact_ref],
            output_refs=[artifact_ref],
            provider="project-ffmpeg",
            model=None,
            provider_task_id=None,
            cost={"status": "known", "amount": 0.0, "currency": "CNY", "basis": "local locked-timeline delivery"},
            occurred_at=None,
        )
        if completed is None:
            raise ValueError("Video production not found")
        return _json(
            {
                "operation_status": "ok",
                "idempotent_replay": False,
                "production_id": production_key,
                "revision_id": revision_id,
                "lock_id": lock.get("lock_id"),
                "status": completed.get("status"),
                "current_stage": completed.get("current_stage"),
                "event_count": completed.get("event_count"),
                "artifact": qa["artifact"],
                "qa": qa,
                "render_event_key": render_event_key,
                "qa_event_key": qa_event_key,
                "delivery_event_key": delivery_event_key,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json(
            {
                "status": "error",
                "category": "internal",
                "message": "Locked video delivery could not be rendered",
            }
        )


async def _personal_ip_record_video_production_event(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    event_type: str,
    status: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
    input_refs: list[str],
    output_refs: list[str],
    provider: str,
    model: str,
    provider_task_id: str,
    cost: dict,
    occurred_at: str,
) -> str:
    """Append one immutable stage, provider, review or delivery receipt.

    This is the shared evidence spine for blueprint, assets, storyboard, shot
    generation, consistency, candidate selection, finishing and delivery.
    Store detailed business artifacts by reference or in payload, but never put
    cookies, tokens, passwords or authorization headers into any field.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this event or provider callback.
        event_type: Registered video event such as storyboard_sealed or edit_completed.
        status: planned, running, succeeded, failed, awaiting_review, approved or rejected.
        entity_type: production, character, scene, prop, shot, candidate, audio, timeline or delivery.
        entity_id: Stable id of the entity affected by this event.
        payload: Detailed contract, result, QA finding or human decision
            snapshot. For ``event_type`` equal to ``review_requested`` use
            ``review_kind`` equal to ``candidate_selection`` and include ``shot_id``,
            ``candidate_id``, ``artifact_ref``, ``artifact_sha256`` and the
            linked ``qa_event_ref`` so the workbench can render the exact
            candidate confirmation card. A provider-request event must declare
            ``billing_mode``. Paid requests include the active
            ``budget_reservation_id`` and an estimated cost no greater than
            that reservation; free requests carry known zero cost.
        input_refs: Immutable artifact or upstream event references.
        output_refs: Generated artifact, media or delivery references.
        provider: Provider or executor name, including deerflow or manual.
        model: Optional exact model/version; pass an empty string when absent.
        provider_task_id: Optional provider task id; pass an empty string when absent.
        cost: Actual or estimated cost snapshot; may be empty.
        occurred_at: ISO-8601 event time with timezone.

    Returns:
        JSON with the updated production projection and full ordered event history.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.append_event(
            production_id,
            owner_user_id=resolve_runtime_user_id(runtime),
            event_key=event_key,
            event_type=event_type,
            status=status,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
            input_refs=input_refs,
            output_refs=output_refs,
            provider=provider,
            model=str(model or "").strip() or None,
            provider_task_id=str(provider_task_id or "").strip() or None,
            cost=cost,
            occurred_at=_parse_datetime(occurred_at, field="occurred_at"),
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Video production not found"})
        return _json(
            {
                "operation_status": "ok",
                **result,
                "event_count": result.get("event_count", len(result.get("events") or [])),
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video production event could not be recorded"})


async def _personal_ip_read_video_production(runtime: Runtime, production_id: str) -> str:
    """Read one full owner-scoped video production and its immutable history.

    Args:
        production_id: Server-issued video production id from the cockpit.

    Returns:
        JSON immutable request, current projection and every ordered stage receipt.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.get(
            str(production_id or "").strip(),
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Video production not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video production is unavailable"})


async def _personal_ip_ingest_media_execution(
    runtime: Runtime,
    production_id: str,
    event_key: str,
    entity_type: str,
    entity_id: str,
    receipt: dict,
) -> str:
    """Validate and append one real media executor receipt to a production.

    Use this after Seedance, Seedream, Doubao Speech, MediaKit or FFmpeg emits a
    ``personal-ip-media-execution-v1`` receipt. The receipt is credential-free
    and preserves provider task/request ids, exact executor/model, checksummed
    outputs, failure state and known/estimated/unknown cost. Event type and
    status are derived by the server so an agent cannot mislabel execution.

    Args:
        production_id: Server-issued video production id.
        event_key: Stable idempotency key for this executor attempt.
        entity_type: Receipt target such as shot, candidate, audio, timeline or delivery.
        entity_id: Stable id of the target entity.
        receipt: Complete credential-free receipt with ``contract_version``
            equal to ``personal-ip-media-execution-v1``,
            ``capability`` (video_generation, image_generation,
            speech_generation or media_processing), ``provider``, ``executor``,
            optional ``model``, ``status`` (running, succeeded or failed),
            optional ``task_id`` and ``request_id``, timezone-aware
            ``started_at`` and ``completed_at``, object ``parameters``, arrays
            ``inputs`` and ``outputs``, and object ``cost``. A succeeded video
            generation requires ``task_id`` and at least one output containing
            ``ref``, bare lowercase 64-character ``sha256`` and non-negative
            ``size_bytes``. Cost must use known or estimated status with amount
            and currency, or unknown status with a reason. Before a running
            paid receipt is submitted, its parameters include
            ``billing_mode`` set to ``paid`` and the server-issued
            ``budget_reservation_id``; a free/local request uses
            ``billing_mode`` set to ``free`` and known zero cost.

    Returns:
        JSON updated production projection and ordered immutable event history.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        normalized = normalize_media_execution_receipt(receipt, entity_type=entity_type)
        result = await services.video_productions.append_event(
            production_id,
            owner_user_id=resolve_runtime_user_id(runtime),
            event_key=event_key,
            event_type=normalized["event_type"],
            status=normalized["event_status"],
            entity_type=entity_type,
            entity_id=entity_id,
            payload=normalized["payload"],
            input_refs=normalized["input_refs"],
            output_refs=normalized["output_refs"],
            provider=normalized["provider"],
            model=normalized["model"],
            provider_task_id=normalized["provider_task_id"],
            cost=normalized["cost"],
            occurred_at=normalized["occurred_at"],
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Video production not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Media execution receipt could not be recorded"})


async def _personal_ip_metrics_aggregate(
    runtime: Runtime,
    window_started_at: str,
    window_ended_at: str,
) -> str:
    """Aggregate additive performance across every active account owned by the user.

    Use this for portfolio-wide questions such as total views across all
    platforms. The result explicitly reports missing, partial and unavailable
    accounts; never present missing coverage as zero.

    Args:
        window_started_at: Inclusive ISO-8601 start time with timezone.
        window_ended_at: Exclusive ISO-8601 end time with timezone.

    Returns:
        JSON containing whole-portfolio totals, per-platform/account breakdowns
        and coverage. This tool intentionally has no account filter.
    """
    try:
        result = await get_personal_ip_runtime().metrics.aggregate(
            owner_user_id=resolve_runtime_user_id(runtime),
            window_started_at=_parse_datetime(window_started_at, field="window_started_at"),
            window_ended_at=_parse_datetime(window_ended_at, field="window_ended_at"),
        )
        return _json({"status": "ok", **result})
    except (RuntimeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Portfolio metrics are unavailable"})


async def _personal_ip_collect_browser_portfolio_today(
    runtime: Runtime,
    collection_key: str,
    window_started_at: str,
    window_ended_at: str,
) -> str:
    """Collect and aggregate today's views across the user's whole browser portfolio.

    This scans every active account for Douyin, WeChat Channels, WeChat Official
    Accounts, Xiaohongshu, X, Instagram, YouTube and TikTok. It reuses each
    isolated login profile, seals detailed rendered-page evidence, and writes a
    window metric only when the page explicitly labels the displayed data as
    today. Missing, partial and unavailable accounts remain explicit, and the
    output omits a views total when no supported account supplied one. This tool
    intentionally has no account filter and never reads cookies or tokens.

    Args:
        collection_key: Stable idempotency key for this portfolio collection instant.
        window_started_at: Inclusive ISO-8601 start of today with timezone.
        window_ended_at: Exclusive ISO-8601 collection cutoff with timezone.

    Returns:
        JSON per-account collection receipts, eight-platform coverage and the
        resulting whole-portfolio aggregate.
    """
    try:
        result = await _browser_portfolio_metric_service(get_personal_ip_runtime()).collect_today(
            owner_user_id=resolve_runtime_user_id(runtime),
            collection_key=collection_key,
            window_started_at=_parse_datetime_with_timezone(window_started_at, field="window_started_at"),
            window_ended_at=_parse_datetime(window_ended_at, field="window_ended_at"),
        )
        return _json(result)
    except (BrowserPlatformCollectionError, RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Browser portfolio collection is unavailable"})


async def _personal_ip_sync_douyin_post(
    runtime: Runtime,
    connection_id: str,
    publish_receipt_id: str,
    observation_key: str,
) -> str:
    """Sync one published Douyin post through its encrypted account connection.

    Use this before a retrospective or when fresh post counters are needed.
    Pass only server-issued identifiers; credentials remain inside the Gateway.

    Args:
        connection_id: Server-issued Douyin platform connection id.
        publish_receipt_id: Confirmed Personal-IP publish receipt id.
        observation_key: Stable idempotency key for this collection instant.

    Returns:
        JSON metric observation or a sanitized remediation error. No access or
        refresh token can appear in the result.
    """
    try:
        result = await _authorized_douyin_service(get_personal_ip_runtime()).collect_published_post(
            owner_user_id=resolve_runtime_user_id(runtime),
            connection_id=connection_id,
            publish_receipt_id=publish_receipt_id,
            observation_key=observation_key,
        )
        return _json({"status": "ok", **result})
    except DouyinOAuthError as exc:
        category = "reauthorization_required" if exc.category == "reauthorization_required" else "provider_unavailable"
        return _json({"status": "error", "category": category, "message": "Douyin authorization must be renewed"})
    except PlatformMetricCollectionError as exc:
        return _json(
            {
                "status": "error",
                "category": exc.category,
                "retryable": exc.retryable,
                "message": "Douyin metric collection failed",
            }
        )
    except (RuntimeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Douyin metric collection is unavailable"})


async def _personal_ip_collect_douyin_browser_page(
    runtime: Runtime,
    account_id: str,
    observation_key: str,
    dataset: str,
    target_url: str = "",
) -> str:
    """Capture one authenticated Douyin creator page as detailed business evidence.

    This uses the account's persistent local Chromium profile and reads only
    rendered DOM content plus a screenshot digest. It never reads cookies,
    browser storage, request headers or network token values. The result is
    normally partial because one loaded page does not prove complete pagination;
    a declared content listing is complete only when every item is parsed and
    the platform explicitly reports that there are no more works.

    Args:
        account_id: Server-issued Douyin account id to inspect.
        observation_key: Stable idempotency key for this capture.
        dataset: Business family such as dashboard, content_inventory or audience_analytics.
        target_url: Optional query-free creator.douyin.com page to navigate before capture.

    Returns:
        JSON evidence reference, direct summary and explicit collection coverage.
    """
    try:
        services = get_personal_ip_runtime()
        if services.accounts is None:
            raise ValueError("Personal-IP accounts are not available")
        owner_user_id = resolve_runtime_user_id(runtime)
        account = await services.accounts.get(account_id, owner_user_id=owner_user_id)
        if account is None or account.get("status") != "active" or account.get("platform") != "douyin":
            raise ValueError("Active Douyin account not found")
        _bind_runtime_browser_account(runtime, owner_user_id=owner_user_id, account=account)
        with acquire_account_browser_session(owner_user_id=owner_user_id, account=account) as session:
            result = await _douyin_browser_collection_service(services).collect_creator_page(
                owner_user_id=owner_user_id,
                account_id=account_id,
                observation_key=observation_key,
                dataset=dataset,
                target_url=str(target_url or "").strip() or None,
                session=session,
            )
        return _json(
            {
                "status": result.get("status"),
                "id": result.get("id"),
                "account_id": result.get("account_id"),
                "platform": result.get("platform"),
                "dataset": result.get("dataset"),
                "source_url": result.get("source_url"),
                "observed_at": result.get("observed_at"),
                "record_count": len(result.get("records") or []),
                "summary": result.get("summary") or {},
                "coverage": result.get("coverage") or {},
                "evidence_digest": result.get("evidence_digest"),
            }
        )
    except DouyinBrowserCollectionError as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Douyin browser collection is unavailable"})


async def _personal_ip_collect_browser_page(
    runtime: Runtime,
    account_id: str,
    observation_key: str,
    dataset: str,
    target_url: str = "",
) -> str:
    """Capture one authenticated creator page as detailed business evidence.

    This is the shared browser-first collector for Douyin, WeChat Channels,
    WeChat Official Accounts, Xiaohongshu, X, Instagram, YouTube and TikTok.
    It reuses the exact account's isolated Chromium profile and reads rendered
    DOM content plus a screenshot digest. It never reads cookies, browser
    storage, request headers or network token values. Account ids select only
    this operation target and never narrow conversation authority.

    Args:
        account_id: Server-issued Personal-IP account id to inspect.
        observation_key: Stable idempotency key for this capture.
        dataset: Business family such as dashboard, content_inventory or audience_analytics.
        target_url: Optional query-free page on this platform's registered creator host.

    Returns:
        JSON detailed records, evidence reference, direct summary and collection coverage.
    """
    try:
        services = get_personal_ip_runtime()
        if services.accounts is None:
            raise ValueError("Personal-IP accounts are not available")
        owner_user_id = resolve_runtime_user_id(runtime)
        account = await services.accounts.get(account_id, owner_user_id=owner_user_id)
        if account is None or account.get("status") != "active":
            raise ValueError("Active Personal-IP account not found")
        _bind_runtime_browser_account(runtime, owner_user_id=owner_user_id, account=account)
        with acquire_account_browser_session(owner_user_id=owner_user_id, account=account) as session:
            result = await _browser_platform_collection_service(services).collect_creator_page(
                owner_user_id=owner_user_id,
                account_id=account_id,
                observation_key=observation_key,
                dataset=dataset,
                target_url=str(target_url or "").strip() or None,
                session=session,
            )
        return _json(
            {
                "status": result.get("status"),
                "id": result.get("id"),
                "account_id": result.get("account_id"),
                "platform": result.get("platform"),
                "dataset": result.get("dataset"),
                "source_url": result.get("source_url"),
                "observed_at": result.get("observed_at"),
                "record_count": len(result.get("records") or []),
                "records": result.get("records") or [],
                "summary": result.get("summary") or {},
                "coverage": result.get("coverage") or {},
                "evidence_digest": result.get("evidence_digest"),
            }
        )
    except BrowserPlatformCollectionError as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Browser collection is unavailable"})


async def _personal_ip_platform_observation_inventory(
    runtime: Runtime,
    dataset: str = "",
    limit: int = 100,
) -> str:
    """List recent detailed evidence across the authenticated user's portfolio.

    This inventory intentionally has no account filter. It returns observation
    ids, direct summaries and coverage for every account so the agent can find
    the right evidence without narrowing conversation authority. Call
    personal_ip_read_platform_observation for the full records of one item.

    Args:
        dataset: Optional business-data family; empty means every dataset.
        limit: Maximum recent observations to return, from 1 to 500.

    Returns:
        JSON portfolio inventory without bulky detailed records.
    """
    try:
        services = get_personal_ip_runtime()
        if services.platform_observations is None:
            raise RuntimeError("Personal-IP platform observations are not available")
        dataset_key = str(dataset or "").strip()
        if dataset_key and dataset_key not in _PLATFORM_OBSERVATION_DATASETS:
            raise ValueError("Unsupported platform observation dataset")
        result_limit = int(limit)
        if result_limit < 1 or result_limit > 500:
            raise ValueError("limit must be between 1 and 500")
        observations = await services.platform_observations.list(
            resolve_runtime_user_id(runtime),
            dataset=dataset_key or None,
            limit=result_limit,
        )
        fields = (
            "id",
            "account_id",
            "subject_id",
            "platform",
            "dataset",
            "source",
            "status",
            "source_url",
            "observed_at",
            "summary",
            "coverage",
            "evidence_digest",
        )
        return _json(
            {
                "status": "ok",
                "observation_count": len(observations),
                "observations": [{field: observation.get(field) for field in fields if field in observation} for observation in observations],
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Evidence inventory is unavailable"})


async def _personal_ip_read_platform_observation(
    runtime: Runtime,
    observation_id: str,
) -> str:
    """Read the full detailed business records of one immutable observation.

    Credential material cannot be present because the evidence repository
    rejects it recursively before persistence. The owner-scoped lookup prevents
    one user from reading another user's creator data.

    Args:
        observation_id: Server-issued platform observation id from the portfolio inventory.

    Returns:
        JSON containing full records, summary, coverage and evidence provenance.
    """
    try:
        services = get_personal_ip_runtime()
        if services.platform_observations is None:
            raise RuntimeError("Personal-IP platform observations are not available")
        observation_key = str(observation_id or "").strip()
        if not observation_key:
            raise ValueError("observation_id is required")
        result = await services.platform_observations.get(
            observation_key,
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Platform observation not found"})
        return _json({"status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Platform observation is unavailable"})


async def _personal_ip_performance_inventory(
    runtime: Runtime,
    published_limit: int = 100,
) -> str:
    """List performance connections and recent published receipts across the portfolio.

    Call this before syncing platform metrics to discover the server-issued
    connection and publish-receipt ids. It returns sanitized metadata only and
    never credential, request-body or executor-result material.

    Args:
        published_limit: Maximum recent published receipts to inspect, 1-500.

    Returns:
        JSON with every active platform connection and recent confirmed
        publications across all accounts owned by the authenticated user.
    """
    try:
        limit = int(published_limit)
        if limit < 1 or limit > 500:
            raise ValueError("published_limit must be between 1 and 500")
        services = get_personal_ip_runtime()
        owner_user_id = resolve_runtime_user_id(runtime)
        connections = await services.connections.list(owner_user_id, include_revoked=False)
        receipts = await services.publish_receipts.list(owner_user_id, limit=limit)
        connection_fields = (
            "id",
            "account_id",
            "platform",
            "status",
            "scopes",
            "access_expires_at",
            "refresh_expires_at",
            "last_refreshed_at",
            "last_error_code",
            "updated_at",
        )
        receipt_fields = (
            "id",
            "account_id",
            "platform",
            "status",
            "external_post_id",
            "published_at",
        )
        return _json(
            {
                "status": "ok",
                "connections": [{field: connection.get(field) for field in connection_fields if field in connection} for connection in connections],
                "published_receipts": [{field: receipt.get(field) for field in receipt_fields if field in receipt} for receipt in receipts if receipt.get("status") == "published"],
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Performance inventory is unavailable"})


async def _personal_ip_select_browser_account(
    runtime: Runtime,
    account_id: str,
) -> str:
    """Select one account's persistent local browser profile for the next operation.

    Selection changes only the concrete browser target for this thread. It does
    not restrict the conversation, tools, data access, or portfolio aggregation
    to this account. Login cookies stay in a user/account-isolated local browser
    directory; passwords are never accepted by this tool.

    Args:
        account_id: Server-issued Personal-IP account id to operate now.

    Returns:
        Sanitized account, platform and creator-center start URL metadata.
    """
    try:
        services = get_personal_ip_runtime()
        if services.accounts is None:
            raise RuntimeError("Personal-IP account persistence is not available")
        owner_user_id = resolve_runtime_user_id(runtime)
        thread_id = str((runtime.context or {}).get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("browser account selection requires a thread")
        account = await services.accounts.get(account_id, owner_user_id=owner_user_id)
        if account is None or account.get("status") != "active":
            raise ValueError("Personal-IP account not found")
        target = _bind_runtime_browser_account(
            runtime,
            owner_user_id=owner_user_id,
            account=account,
        )
        if target is None:
            raise ValueError("browser account selection requires a thread")
        return _json(
            {
                "status": "ok",
                "connection_mode": "browser_profile",
                "account_id": target.account_id,
                "platform": target.platform,
                "display_name": target.display_name,
                "start_url": target.start_url,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Browser account selection is unavailable"})


def _bind_runtime_browser_account(
    runtime: Runtime,
    *,
    owner_user_id: str,
    account: dict[str, Any],
):
    """Bind later Browser Control calls to the profile used for collection."""
    thread_id = str((runtime.context or {}).get("thread_id") or "").strip()
    if not thread_id:
        return None
    paths = get_paths()
    safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
    profile_dir = paths.ensure_browser_profile_dir(account["id"], user_id=safe_user_id)
    return select_browser_account_target(
        owner_user_id=owner_user_id,
        thread_id=thread_id,
        account_id=account["id"],
        platform=account["platform"],
        display_name=account.get("display_name") or account["id"],
        user_data_dir=profile_dir,
    )


async def _personal_ip_record_browser_observation(
    runtime: Runtime,
    observation_key: str,
    account_id: str,
    dataset: str,
    status: str,
    source_url: str,
    observed_at: str,
    records: list[dict],
    summary: dict,
    coverage: dict,
    evidence: dict,
) -> str:
    """Seal detailed business data observed in an authenticated creator backend.

    Call this after Browser Control has inspected an authorized platform page.
    Preserve account/content data, metrics, audience analytics, traffic sources,
    comments, conversions and platform receipts as fully as the page permits.
    Never pass cookies, tokens, passwords, authorization headers, local profile
    paths or other credential material; the evidence contract rejects them.

    Args:
        observation_key: Stable idempotency key for this capture.
        account_id: Server-issued account id that was inspected.
        dataset: One supported business-data family such as content_inventory.
        status: observed, partial or unavailable.
        source_url: Creator-backend page URL; query and fragment are stripped.
        observed_at: ISO-8601 capture time with timezone.
        records: Detailed structured business records visible to the user.
        summary: Page or dataset totals derived directly from the source.
        coverage: Pagination, sections read, missing fields and completeness.
        evidence: Screenshot/artifact references and field-source descriptions.

    Returns:
        JSON observation reference, summary and coverage. Detailed records stay
        in the immutable evidence row and credential values can never be stored.
    """
    try:
        services = get_personal_ip_runtime()
        if services.platform_observations is None:
            raise RuntimeError("Personal-IP platform observations are not available")
        result = await services.platform_observations.record(
            owner_user_id=resolve_runtime_user_id(runtime),
            observation_key=observation_key,
            account_id=account_id,
            dataset=dataset,
            source="browser",
            status=status,
            source_url=source_url,
            observed_at=_parse_datetime(observed_at, field="observed_at"),
            records=records,
            summary=summary,
            coverage=coverage,
            evidence=evidence,
        )
        return _json(
            {
                "status": result.get("status"),
                "id": result.get("id"),
                "account_id": result.get("account_id"),
                "platform": result.get("platform"),
                "dataset": result.get("dataset"),
                "source_url": result.get("source_url"),
                "record_count": len(result.get("records") or []),
                "summary": result.get("summary") or {},
                "coverage": result.get("coverage") or {},
                "evidence_digest": result.get("evidence_digest"),
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Browser observation could not be sealed"})


def _portfolio_observation_key(
    *,
    collection_key: str,
    connection_id: str,
    publish_receipt_id: str,
) -> str:
    collection = str(collection_key or "").strip()
    if not collection or len(collection) > 128:
        raise ValueError("collection_key must contain 1 to 128 characters")
    digest = sha256(f"{collection}|{connection_id}|{publish_receipt_id}".encode()).hexdigest()
    return f"portfolio-douyin:{digest}"


async def _personal_ip_sync_douyin_portfolio(
    runtime: Runtime,
    collection_key: str,
    published_limit: int = 500,
) -> str:
    """Sync every discoverable published Douyin post in the user's portfolio.

    This is the scheduled-task entry point for portfolio performance baselines
    and interval deltas. It resolves accounts, encrypted connections and
    confirmed publish receipts server-side, isolates individual post failures,
    and never sends credentials into model context.

    Args:
        collection_key: Stable idempotency key for this portfolio collection run.
        published_limit: Maximum recent publish receipts to inspect, 1-500.

    Returns:
        Sanitized per-post observation references, counts, failures and explicit
        scan coverage. A partial result never claims complete portfolio data.
    """
    try:
        limit = int(published_limit)
        if limit < 1 or limit > 500:
            raise ValueError("published_limit must be between 1 and 500")
        normalized_collection_key = str(collection_key or "").strip()
        if not normalized_collection_key or len(normalized_collection_key) > 128:
            raise ValueError("collection_key must contain 1 to 128 characters")
        services = get_personal_ip_runtime()
        owner_user_id = resolve_runtime_user_id(runtime)
        observation_service = _authorized_douyin_service(services)
        connections = await services.connections.list(owner_user_id, include_revoked=False)
        receipts = await services.publish_receipts.list(owner_user_id, limit=limit)
        connection_by_account: dict[str, dict] = {}
        for connection in connections:
            if connection.get("platform") == "douyin" and connection.get("status") == "connected":
                connection_by_account.setdefault(str(connection.get("account_id") or ""), connection)

        published = [receipt for receipt in receipts if receipt.get("platform") == "douyin" and receipt.get("status") == "published"]
        results: list[dict] = []
        failures: list[dict] = []
        missing_connection_accounts: set[str] = set()
        baseline_count = 0
        delta_count = 0
        for receipt in published:
            account_id = str(receipt.get("account_id") or "")
            publish_receipt_id = str(receipt.get("id") or "")
            connection = connection_by_account.get(account_id)
            if connection is None:
                missing_connection_accounts.add(account_id)
                continue
            connection_id = str(connection.get("id") or "")
            observation_key = _portfolio_observation_key(
                collection_key=normalized_collection_key,
                connection_id=connection_id,
                publish_receipt_id=publish_receipt_id,
            )
            try:
                observation = await observation_service.collect_published_post(
                    owner_user_id=owner_user_id,
                    connection_id=connection_id,
                    publish_receipt_id=publish_receipt_id,
                    observation_key=observation_key,
                )
            except DouyinOAuthError as exc:
                failures.append(
                    {
                        "account_id": account_id,
                        "connection_id": connection_id,
                        "publish_receipt_id": publish_receipt_id,
                        "category": "reauthorization_required" if exc.category == "reauthorization_required" else "provider_unavailable",
                        "retryable": False,
                    }
                )
                continue
            except PlatformMetricCollectionError as exc:
                failures.append(
                    {
                        "account_id": account_id,
                        "connection_id": connection_id,
                        "publish_receipt_id": publish_receipt_id,
                        "category": exc.category,
                        "retryable": exc.retryable,
                    }
                )
                continue
            except (RuntimeError, ValueError):
                failures.append(
                    {
                        "account_id": account_id,
                        "connection_id": connection_id,
                        "publish_receipt_id": publish_receipt_id,
                        "category": "invalid_request",
                        "retryable": False,
                    }
                )
                continue
            except Exception:
                failures.append(
                    {
                        "account_id": account_id,
                        "connection_id": connection_id,
                        "publish_receipt_id": publish_receipt_id,
                        "category": "internal",
                        "retryable": False,
                    }
                )
                continue

            delta = observation.get("derived_delta")
            if delta is not None:
                delta_count += 1
            elif observation.get("status") != "unavailable":
                baseline_count += 1
            results.append(
                {
                    "account_id": account_id,
                    "connection_id": connection_id,
                    "publish_receipt_id": publish_receipt_id,
                    "metric_id": observation.get("id"),
                    "status": observation.get("status"),
                    "delta_id": delta.get("id") if isinstance(delta, dict) else None,
                }
            )

        possibly_truncated = len(receipts) >= limit
        incomplete = bool(failures or missing_connection_accounts or possibly_truncated)
        status = "partial" if incomplete else "complete"
        if not published and not incomplete:
            status = "unavailable"
        return _json(
            {
                "status": status,
                "platform": "douyin",
                "published_receipt_count": len(published),
                "synced_count": len(results),
                "baseline_count": baseline_count,
                "delta_count": delta_count,
                "failed_count": len(failures),
                "results": results,
                "failures": failures,
                "coverage": {
                    "receipt_scan_limit": limit,
                    "possibly_truncated": possibly_truncated,
                    "missing_connection_account_ids": sorted(missing_connection_accounts),
                },
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Portfolio sync is unavailable"})


personal_ip_metrics_aggregate_tool = tool(
    "personal_ip_metrics_aggregate",
    parse_docstring=True,
)(_personal_ip_metrics_aggregate)

personal_ip_collect_browser_portfolio_today_tool = tool(
    "personal_ip_collect_browser_portfolio_today",
    parse_docstring=True,
)(_personal_ip_collect_browser_portfolio_today)

personal_ip_operating_cockpit_tool = tool(
    "personal_ip_operating_cockpit",
    parse_docstring=True,
)(_personal_ip_operating_cockpit)

personal_ip_startup_context_tool = tool(
    "personal_ip_startup_context",
    parse_docstring=True,
)(_personal_ip_startup_context)

personal_ip_account_diagnostic_context_tool = tool(
    "personal_ip_account_diagnostic_context",
    parse_docstring=True,
)(_personal_ip_account_diagnostic_context)

personal_ip_begin_video_production_tool = tool(
    "personal_ip_begin_video_production",
    parse_docstring=True,
)(_personal_ip_begin_video_production)

personal_ip_compile_video_plan_tool = tool(
    "personal_ip_compile_video_plan",
    parse_docstring=True,
)(_personal_ip_compile_video_plan)

personal_ip_compile_video_pattern_tool = tool(
    "personal_ip_compile_video_pattern",
    parse_docstring=True,
)(_personal_ip_compile_video_pattern)

personal_ip_compile_video_skill_candidate_tool = tool(
    "personal_ip_compile_video_skill_candidate",
    parse_docstring=True,
)(_personal_ip_compile_video_skill_candidate)

personal_ip_compile_video_method_distillation_tool = tool(
    "personal_ip_compile_video_method_distillation",
    parse_docstring=True,
)(_personal_ip_compile_video_method_distillation)

personal_ip_compile_video_method_skill_candidate_tool = tool(
    "personal_ip_compile_video_method_skill_candidate",
    parse_docstring=True,
)(_personal_ip_compile_video_method_skill_candidate)

personal_ip_compile_video_asset_manifest_tool = tool(
    "personal_ip_compile_video_asset_manifest",
    parse_docstring=True,
)(_personal_ip_compile_video_asset_manifest)

personal_ip_compile_video_storyboard_tool = tool(
    "personal_ip_compile_video_storyboard",
    parse_docstring=True,
)(_personal_ip_compile_video_storyboard)

personal_ip_compile_video_narration_tool = tool(
    "personal_ip_compile_video_narration",
    parse_docstring=True,
)(_personal_ip_compile_video_narration)

personal_ip_compile_video_material_selection_tool = tool(
    "personal_ip_compile_video_material_selection",
    parse_docstring=True,
)(_personal_ip_compile_video_material_selection)

personal_ip_inspect_local_video_material_tool = tool(
    "personal_ip_inspect_local_video_material",
    parse_docstring=True,
)(_personal_ip_inspect_local_video_material)

personal_ip_compile_video_narration_timing_tool = tool(
    "personal_ip_compile_video_narration_timing",
    parse_docstring=True,
)(_personal_ip_compile_video_narration_timing)

personal_ip_compile_video_continuity_tool = tool(
    "personal_ip_compile_video_continuity",
    parse_docstring=True,
)(_personal_ip_compile_video_continuity)

personal_ip_compile_generated_shot_qa_tool = tool(
    "personal_ip_compile_generated_shot_qa",
    parse_docstring=True,
)(_personal_ip_compile_generated_shot_qa)

personal_ip_run_local_generated_shot_qa_tool = tool(
    "personal_ip_run_local_generated_shot_qa",
    parse_docstring=True,
)(_personal_ip_run_local_generated_shot_qa)

personal_ip_interpolate_video_candidate_tool = tool(
    "personal_ip_interpolate_video_candidate",
    parse_docstring=True,
)(_personal_ip_interpolate_video_candidate)

personal_ip_render_local_remotion_scene_tool = tool(
    "personal_ip_render_local_remotion_scene",
    parse_docstring=True,
)(_personal_ip_render_local_remotion_scene)

personal_ip_compile_approved_video_assembly_tool = tool(
    "personal_ip_compile_approved_video_assembly",
    parse_docstring=True,
)(_personal_ip_compile_approved_video_assembly)

personal_ip_compile_video_timeline_revision_tool = tool(
    "personal_ip_compile_video_timeline_revision",
    parse_docstring=True,
)(_personal_ip_compile_video_timeline_revision)

personal_ip_lock_video_final_edit_tool = tool(
    "personal_ip_lock_video_final_edit",
    parse_docstring=True,
)(_personal_ip_lock_video_final_edit)

personal_ip_render_locked_video_delivery_tool = tool(
    "personal_ip_render_locked_video_delivery",
    parse_docstring=True,
)(_personal_ip_render_locked_video_delivery)

personal_ip_record_video_production_event_tool = tool(
    "personal_ip_record_video_production_event",
    parse_docstring=True,
)(_personal_ip_record_video_production_event)

personal_ip_reserve_video_budget_tool = tool(
    "personal_ip_reserve_video_budget",
    parse_docstring=True,
)(_personal_ip_reserve_video_budget)

personal_ip_settle_video_budget_tool = tool(
    "personal_ip_settle_video_budget",
    parse_docstring=True,
)(_personal_ip_settle_video_budget)

personal_ip_release_video_budget_tool = tool(
    "personal_ip_release_video_budget",
    parse_docstring=True,
)(_personal_ip_release_video_budget)

personal_ip_ingest_media_execution_tool = tool(
    "personal_ip_ingest_media_execution",
    parse_docstring=True,
)(_personal_ip_ingest_media_execution)

personal_ip_read_video_production_tool = tool(
    "personal_ip_read_video_production",
    parse_docstring=True,
)(_personal_ip_read_video_production)

personal_ip_collect_douyin_browser_page_tool = tool(
    "personal_ip_collect_douyin_browser_page",
    parse_docstring=True,
)(_personal_ip_collect_douyin_browser_page)

personal_ip_collect_browser_page_tool = tool(
    "personal_ip_collect_browser_page",
    parse_docstring=True,
)(_personal_ip_collect_browser_page)

personal_ip_platform_observation_inventory_tool = tool(
    "personal_ip_platform_observation_inventory",
    parse_docstring=True,
)(_personal_ip_platform_observation_inventory)

personal_ip_read_platform_observation_tool = tool(
    "personal_ip_read_platform_observation",
    parse_docstring=True,
)(_personal_ip_read_platform_observation)

personal_ip_sync_douyin_post_tool = tool(
    "personal_ip_sync_douyin_post",
    parse_docstring=True,
)(_personal_ip_sync_douyin_post)

personal_ip_performance_inventory_tool = tool(
    "personal_ip_performance_inventory",
    parse_docstring=True,
)(_personal_ip_performance_inventory)

personal_ip_select_browser_account_tool = tool(
    "personal_ip_select_browser_account",
    parse_docstring=True,
)(_personal_ip_select_browser_account)

personal_ip_record_browser_observation_tool = tool(
    "personal_ip_record_browser_observation",
    parse_docstring=True,
)(_personal_ip_record_browser_observation)

personal_ip_sync_douyin_portfolio_tool = tool(
    "personal_ip_sync_douyin_portfolio",
    parse_docstring=True,
)(_personal_ip_sync_douyin_portfolio)
