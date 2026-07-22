"""Native DeerFlow tools for the Personal-IP evidence and publishing loop."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import httpx
from langchain.tools import tool

from deerflow.personal_ip.audience_provider import AudiencePreflightRequest, HLLMCreatorHTTPProvider
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter
from deerflow.personal_ip.runtime import get_personal_ip_runtime
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


def _optional_datetime(value: str, *, field: str) -> datetime | None:
    return _parse_datetime(value, field=field) if str(value or "").strip() else None


def _audience_preflight_provider() -> HLLMCreatorHTTPProvider:
    return HLLMCreatorHTTPProvider(
        base_url=os.environ.get("PERSONAL_IP_AUDIENCE_BASE_URL", "http://127.0.0.1:9128"),
        token=os.environ.get("PERSONAL_IP_AUDIENCE_TOKEN"),
    )


async def _personal_ip_run_preflight(
    runtime: Runtime,
    operation_key: str,
    subject_ids: list[str],
    target_account_ids: list[str],
    history: list[dict],
    audience_profile: dict,
    creator_profile: dict,
    target: dict,
    variant_count: int = 3,
) -> str:
    """Run HLLM-Lite/full HLLM preflight and seal its immutable receipt.

    Use aggregate published-content history and audience evidence only. The
    adapter rejects individual viewer identities, and local subject/account ids
    stay in DeerFlow rather than being sent to the model provider.

    Args:
        operation_key: Stable idempotency key for this exact preflight.
        subject_ids: Owner-scoped subjects represented by the preflight.
        target_account_ids: Accounts this prediction may later publish to.
        history: Chronological published content with aggregate metrics.
        audience_profile: Aggregate cohort traits and revisable audience hypotheses.
        creator_profile: Creator voice, boundaries, positioning and business intent.
        target: Draft content id, title, description and content type to evaluate.
        variant_count: Number of creative variants, from 1 to 8.

    Returns:
        JSON sealed preflight with provider/model versions and prediction variants.
    """
    try:
        services = get_personal_ip_runtime()
        if services.preflights is None:
            raise RuntimeError("Personal-IP preflight persistence is not available")
        example = HLLMCreatorAdapter().build_example(
            history=history,
            audience_profile=audience_profile,
            creator_profile=creator_profile,
            target=target,
        )
        request = AudiencePreflightRequest(example=example, variant_count=int(variant_count))
        result = await _audience_preflight_provider().preflight(request)
        sealed = await services.preflights.seal(
            owner_user_id=resolve_runtime_user_id(runtime),
            operation_key=operation_key,
            subject_ids=subject_ids,
            target_account_ids=target_account_ids,
            request=request,
            result=result,
        )
        return _json({"operation_status": "ok", **sealed})
    except httpx.HTTPError:
        return _json(
            {
                "status": "error",
                "category": "provider_unavailable",
                "message": "Audience preflight provider is unavailable",
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Audience preflight could not be sealed"})


async def _personal_ip_read_preflight(runtime: Runtime, preflight_id: str) -> str:
    """Read one full owner-scoped immutable audience preflight.

    Args:
        preflight_id: Server-issued preflight id from the operating cockpit.

    Returns:
        JSON model request and exact provider receipt used before publication.
    """
    try:
        services = get_personal_ip_runtime()
        if services.preflights is None:
            raise RuntimeError("Personal-IP preflight persistence is not available")
        result = await services.preflights.get(
            str(preflight_id or "").strip(),
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Personal-IP preflight not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Personal-IP preflight is unavailable"})


async def _personal_ip_begin_publish_receipt(
    runtime: Runtime,
    operation_key: str,
    idempotency_key: str,
    account_id: str,
    preflight_id: str,
    executor: str,
    request: dict,
) -> str:
    """Seal the exact request before a browser, UI-TARS, API or manual publish.

    This tool records intent but does not publish. When preflight_id is present,
    request must contain a variant_id sealed by that preflight. Call it only
    after the user has approved the consequential publish operation.

    Args:
        operation_key: Stable business operation key.
        idempotency_key: Stable executor idempotency key.
        account_id: Exact owner-scoped platform account to publish through.
        preflight_id: Optional preflight id; pass an empty string when absent.
        executor: platform_api, ui_tars, browser or manual.
        request: Exact caption/media/options and selected variant snapshot.

    Returns:
        JSON planned publication receipt and its immutable request digest.
    """
    try:
        services = get_personal_ip_runtime()
        result = await services.publish_receipts.begin(
            owner_user_id=resolve_runtime_user_id(runtime),
            operation_key=operation_key,
            idempotency_key=idempotency_key,
            account_id=account_id,
            preflight_id=str(preflight_id or "").strip() or None,
            executor=executor,
            request_payload=request,
        )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Publish receipt could not be created"})


async def _personal_ip_record_publish_attempt(
    runtime: Runtime,
    receipt_id: str,
    attempt_key: str,
    status: str,
    result: dict,
    occurred_at: str,
    external_post_id: str,
    external_url: str,
) -> str:
    """Append the evidence from one real publication execution attempt.

    Record pending before handing control to a provider when possible, then
    append a new published, failed or unknown attempt from observed evidence.
    Never call a browser action successful merely because a click returned.

    Args:
        receipt_id: Planned publication receipt id.
        attempt_key: Stable id for this exact attempt or callback.
        status: pending, published, failed, unknown or deleted.
        result: Sanitized visible/API evidence; never credentials.
        occurred_at: Optional ISO-8601 time with timezone; empty uses server time.
        external_post_id: Confirmed platform post id, or empty when unavailable.
        external_url: Confirmed public post URL, or empty when unavailable.

    Returns:
        JSON updated receipt with its complete append-only attempt history.
    """
    try:
        services = get_personal_ip_runtime()
        receipt = await services.publish_receipts.record_attempt(
            receipt_id,
            owner_user_id=resolve_runtime_user_id(runtime),
            attempt_key=attempt_key,
            status=status,
            result_payload=result,
            occurred_at=_optional_datetime(occurred_at, field="occurred_at"),
            external_post_id=str(external_post_id or "").strip() or None,
            external_url=str(external_url or "").strip() or None,
        )
        if receipt is None:
            return _json({"status": "error", "category": "not_found", "message": "Publish receipt not found"})
        return _json({"operation_status": "ok", **receipt})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Publish attempt could not be recorded"})


async def _personal_ip_read_publish_receipt(runtime: Runtime, receipt_id: str) -> str:
    """Read one publication request and all executor attempts.

    Args:
        receipt_id: Server-issued publish receipt id from the operating cockpit.

    Returns:
        JSON immutable request, current status and append-only attempts.
    """
    try:
        result = await get_personal_ip_runtime().publish_receipts.get(
            str(receipt_id or "").strip(),
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Publish receipt not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Publish receipt is unavailable"})


async def _personal_ip_seal_retrospective(
    runtime: Runtime,
    review_key: str,
    publish_receipt_id: str,
    horizon: str,
    metric_observation_ids: list[str],
) -> str:
    """Seal prediction-versus-outcome evidence for one published post.

    Args:
        review_key: Stable idempotency key for this post and horizon.
        publish_receipt_id: Confirmed publication receipt tied to a preflight.
        horizon: Observation horizon such as T+3d, T+7d or T+30d.
        metric_observation_ids: Post-level metric observation ids for the receipt.

    Returns:
        JSON immutable prediction/outcome comparison and policy eligibility.
    """
    try:
        services = get_personal_ip_runtime()
        if services.retrospectives is None:
            raise RuntimeError("Personal-IP retrospective persistence is not available")
        result = await services.retrospectives.seal(
            owner_user_id=resolve_runtime_user_id(runtime),
            review_key=review_key,
            publish_receipt_id=publish_receipt_id,
            horizon=horizon,
            metric_observation_ids=metric_observation_ids,
        )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Retrospective could not be sealed"})


async def _personal_ip_read_retrospective(runtime: Runtime, retrospective_id: str) -> str:
    """Read one full prediction-versus-outcome retrospective.

    Args:
        retrospective_id: Server-issued retrospective id from the cockpit.

    Returns:
        JSON prediction, observed outcome, coverage and training eligibility.
    """
    try:
        services = get_personal_ip_runtime()
        if services.retrospectives is None:
            raise RuntimeError("Personal-IP retrospective persistence is not available")
        result = await services.retrospectives.get(
            str(retrospective_id or "").strip(),
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Personal-IP retrospective not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Personal-IP retrospective is unavailable"})


async def _personal_ip_promote_evidence(
    runtime: Runtime,
    proposal_key: str,
    evidence_type: str,
    claim: str,
    retrospective_ids: list[str],
    minimum_support: int = 3,
) -> str:
    """Promote a cross-sample pattern when the evidence policy is satisfied.

    At least three independent, completely measured published posts must support
    the claim. Passing the rule automatically creates an approved policy receipt;
    this internal learning action does not require user confirmation.

    Args:
        proposal_key: Stable idempotency key for this exact claim and evidence set.
        evidence_type: audience_pattern, content_pattern, platform_pattern or training_cohort.
        claim: Falsifiable pattern supported by the selected retrospectives.
        retrospective_ids: Complete retrospective ids from distinct publications.
        minimum_support: Required independent measured posts, at least 3.

    Returns:
        JSON automatically approved promotion and its policy decision receipt.
    """
    try:
        services = get_personal_ip_runtime()
        if services.evidence_promotions is None:
            raise RuntimeError("Personal-IP evidence promotion is not available")
        result = await services.evidence_promotions.propose(
            owner_user_id=resolve_runtime_user_id(runtime),
            proposal_key=proposal_key,
            evidence_type=evidence_type,
            claim=claim,
            retrospective_ids=retrospective_ids,
            minimum_support=int(minimum_support),
        )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Evidence could not be promoted"})


async def _personal_ip_read_evidence_promotion(runtime: Runtime, promotion_id: str) -> str:
    """Read one evidence promotion and its automatic policy decision receipt.

    Args:
        promotion_id: Server-issued evidence promotion id from the cockpit.

    Returns:
        JSON claim, support summary, evidence ids and decision history.
    """
    try:
        services = get_personal_ip_runtime()
        if services.evidence_promotions is None:
            raise RuntimeError("Personal-IP evidence promotion is not available")
        result = await services.evidence_promotions.get(
            str(promotion_id or "").strip(),
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Evidence promotion not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Evidence promotion is unavailable"})


personal_ip_run_preflight_tool = tool("personal_ip_run_preflight", parse_docstring=True)(_personal_ip_run_preflight)
personal_ip_read_preflight_tool = tool("personal_ip_read_preflight", parse_docstring=True)(_personal_ip_read_preflight)
personal_ip_begin_publish_receipt_tool = tool("personal_ip_begin_publish_receipt", parse_docstring=True)(_personal_ip_begin_publish_receipt)
personal_ip_record_publish_attempt_tool = tool("personal_ip_record_publish_attempt", parse_docstring=True)(_personal_ip_record_publish_attempt)
personal_ip_read_publish_receipt_tool = tool("personal_ip_read_publish_receipt", parse_docstring=True)(_personal_ip_read_publish_receipt)
personal_ip_seal_retrospective_tool = tool("personal_ip_seal_retrospective", parse_docstring=True)(_personal_ip_seal_retrospective)
personal_ip_read_retrospective_tool = tool("personal_ip_read_retrospective", parse_docstring=True)(_personal_ip_read_retrospective)
personal_ip_promote_evidence_tool = tool("personal_ip_promote_evidence", parse_docstring=True)(_personal_ip_promote_evidence)
personal_ip_read_evidence_promotion_tool = tool("personal_ip_read_evidence_promotion", parse_docstring=True)(_personal_ip_read_evidence_promotion)
