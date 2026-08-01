"""Native DeerFlow tools for the Personal-IP evidence and publishing loop."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime

import httpx
from langchain.tools import tool

from deerflow.config.paths import get_paths
from deerflow.personal_ip.audience_provider import AudiencePreflightRequest, HLLMCreatorHTTPProvider
from deerflow.personal_ip.browser_profiles import get_browser_account_target, select_browser_account_target
from deerflow.personal_ip.browser_publishing import normalize_publication_url, verify_browser_publication_evidence
from deerflow.personal_ip.hllm_creator import HLLMCreatorAdapter
from deerflow.personal_ip.runtime import get_personal_ip_runtime
from deerflow.personal_ip.strategy_methodology import PERSONAL_IP_STRATEGY_METHOD_VERSION
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


def _attempt_with_key(receipt: dict, attempt_key: str) -> dict | None:
    return next(
        (item for item in receipt.get("attempts") or [] if item.get("attempt_key") == attempt_key),
        None,
    )


def _browser_handoff_payload(*, account_id: str, start_url: str) -> dict:
    return {
        "handoff": "deerflow_browser",
        "selected_account_id": account_id,
        "start_url": start_url,
    }


def _browser_result_replay_matches(
    *,
    receipt: dict,
    existing_attempt: dict,
    status: str,
    evidence: dict,
    occurred_at: str,
    external_post_id: str,
    external_url: str,
) -> bool:
    if existing_attempt.get("status") != status:
        return False
    post_id = str(external_post_id or "").strip() or None
    if existing_attempt.get("external_post_id") != post_id:
        return False
    raw_url = str(external_url or "").strip()
    normalized_url = normalize_publication_url(raw_url, platform=receipt["platform"]) if raw_url else None
    if existing_attempt.get("external_url") != normalized_url:
        return False
    supplied_result = dict(evidence)
    if status == "published":
        supplied_result.pop("browser_proof", None)
        existing_result = dict(existing_attempt.get("result") or {})
        if not isinstance(existing_result.pop("browser_proof", None), dict):
            return False
    else:
        existing_result = existing_attempt.get("result")
    if existing_result != supplied_result:
        return False
    supplied_time = _optional_datetime(occurred_at, field="occurred_at")
    if supplied_time is not None and existing_attempt.get("occurred_at") != supplied_time.isoformat():
        return False
    return True


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
    target: dict,
    variant_count: int = 3,
    local_context_evidence_ids: list[str] | None = None,
) -> str:
    """Run HLLM-Lite/full HLLM preflight and seal its immutable receipt.

    Use aggregate published-content history when it exists. For a first pilot,
    history may be empty and the sealed basis remains an unmeasured cold-start
    hypothesis. The adapter rejects individual viewer identities, and local
    subject/account ids stay in DeerFlow rather than being sent to the model
    provider.

    Args:
        operation_key: Stable idempotency key for this exact preflight.
        subject_ids: Owner-scoped subjects represented by the preflight.
        target_account_ids: Accounts this prediction may later publish to.
        history: Chronological published content with aggregate metrics, or an empty list for a first pilot.
        target: Draft content id, title, description and content type to evaluate.
        variant_count: Number of creative variants, from 1 to 8.
        local_context_evidence_ids: Optional sealed MineContext evidence ids; both preflight and HLLM-profile purposes must already be authorized.

    Returns:
        JSON sealed preflight with provider/model versions and prediction variants.
    """
    try:
        services = get_personal_ip_runtime()
        if services.preflights is None:
            raise RuntimeError("Personal-IP preflight persistence is not available")
        owner_user_id = resolve_runtime_user_id(runtime)
        normalized_subject_ids = list(dict.fromkeys(subject_ids))
        if not normalized_subject_ids:
            raise ValueError("preflight requires at least one Personal-IP subject")
        if services.subjects is None:
            raise RuntimeError("Personal-IP subject persistence is not available")
        for subject_id in normalized_subject_ids:
            subject = await services.subjects.get(
                subject_id,
                owner_user_id=owner_user_id,
            )
            if subject is None or subject.get("status") != "active":
                raise ValueError("Personal-IP subject not found")
        if services.accounts is not None:
            for account_id in list(dict.fromkeys(target_account_ids)):
                account = await services.accounts.get(
                    account_id,
                    owner_user_id=owner_user_id,
                )
                if account is None or account.get("status") != "active":
                    raise ValueError("Personal-IP account not found")
        strategy_contexts: list[dict] = []
        for subject_id in normalized_subject_ids:
            strategy = (
                await services.brand.get_latest_strategy(
                    subject_id,
                    owner_user_id=owner_user_id,
                )
                if services.brand is not None
                else None
            )
            direction = None
            if services.differentiation is not None:
                direction_id = str(strategy.get("differentiation_version_id") or "").strip() if strategy else ""
                if direction_id:
                    direction = await services.differentiation.get_version(
                        direction_id,
                        owner_user_id=owner_user_id,
                    )
                if direction is None:
                    direction = await services.differentiation.get_latest(
                        subject_id,
                        owner_user_id=owner_user_id,
                    )
            strategy_contexts.append(
                {
                    "subject_id_present": True,
                    "strategy": (
                        {
                            "person_model": strategy.get("person_model", {}),
                            "business_model": strategy.get("business_model", {}),
                            "benchmark_research": strategy.get("benchmark_research", {}),
                            "positioning_candidates": strategy.get("positioning_candidates", []),
                            "launch_package": strategy.get("launch_package", {}),
                        }
                        if strategy
                        else {}
                    ),
                    "direction": (
                        {
                            "primary_entity": direction.get("primary_entity", {}),
                            "decision_context": direction.get("decision_context", {}),
                            "strategic_difference": direction.get("strategic_difference", {}),
                            "dramatic_engine": direction.get("dramatic_engine", {}),
                            "distinctive_encoding": direction.get("distinctive_encoding", {}),
                        }
                        if direction
                        else {}
                    ),
                }
            )
        creator_profile = {
            "method_version": PERSONAL_IP_STRATEGY_METHOD_VERSION,
            "operating_strategies": strategy_contexts,
        }
        audience_profile = {
            "epistemic_status": ("aggregate_history_only_revisable" if history else "cold_start_unmeasured_revisable"),
            "published_sample_count": len(history),
        }
        local_context_evidence: list[dict] = []
        requested_evidence_ids = list(dict.fromkeys(local_context_evidence_ids or []))
        if requested_evidence_ids:
            if services.minecontext is None:
                raise RuntimeError("MineContext local evidence is not available")
            local_context_evidence = await asyncio.to_thread(
                services.minecontext.read_evidence,
                owner_user_id,
                purpose="preflight",
                evidence_ids=requested_evidence_ids,
                limit=len(requested_evidence_ids),
            )
            # Require the independent HLLM-profile purpose as well. The second
            # read is intentional: the service enforces the persisted consent.
            await asyncio.to_thread(
                services.minecontext.read_evidence,
                owner_user_id,
                purpose="hllm_user_profile",
                evidence_ids=requested_evidence_ids,
                limit=len(requested_evidence_ids),
            )
            found_ids = {item.get("evidence_id") for item in local_context_evidence}
            if found_ids != set(requested_evidence_ids):
                raise ValueError("requested MineContext evidence is missing or expired")
        example = HLLMCreatorAdapter().build_example(
            history=history,
            audience_profile=audience_profile,
            creator_profile=creator_profile,
            target=target,
            local_context_evidence=local_context_evidence,
        )
        request = AudiencePreflightRequest(example=example, variant_count=int(variant_count))
        result = await _audience_preflight_provider().preflight(request)
        sealed = await services.preflights.seal(
            owner_user_id=owner_user_id,
            operation_key=operation_key,
            subject_ids=normalized_subject_ids,
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

    This tool records intent but does not publish. The request must include a
    personal-ip-publish-compliance-v1 declaration; the server validates the
    target platform's disclosure plan and seals its own policy receipt. When
    preflight_id is present, request must also contain a variant_id sealed by
    that preflight. Call it only after the user has approved the consequential
    publish operation.

    Args:
        operation_key: Stable business operation key.
        idempotency_key: Stable executor idempotency key.
        account_id: Exact owner-scoped platform account to publish through.
        preflight_id: Optional preflight id; pass an empty string when absent.
        executor: platform_api, ui_tars or manual. Browser must use prepare.
        request: Exact caption/media/options, selected variant and compliance declaration.

    Returns:
        JSON planned publication receipt and its immutable request digest.
    """
    try:
        if str(executor or "").strip() == "browser":
            raise ValueError("browser receipts must use personal_ip_prepare_browser_publish")
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


async def _personal_ip_prepare_browser_publish(
    runtime: Runtime,
    operation_key: str,
    idempotency_key: str,
    pending_attempt_key: str,
    account_id: str,
    preflight_id: str,
    request: dict,
) -> str:
    """Bind a selected account browser to an immutable publication receipt.

    Call this after the user has requested or confirmed publication, before any
    browser click that submits content. It selects the owner/account-isolated
    profile, validates the personal-ip-publish-compliance-v1 declaration,
    seals the exact request and server policy receipt, then appends a pending
    browser handoff in one idempotent operation.

    Args:
        operation_key: Stable business operation key.
        idempotency_key: Stable key for this exact publish request.
        pending_attempt_key: Stable key for the browser handoff attempt.
        account_id: Exact owner-scoped platform account to publish through.
        preflight_id: Optional preflight id; pass an empty string when absent.
        request: Exact caption, media, options, selected variant and compliance declaration.

    Returns:
        JSON receipt plus the selected platform start URL for Browser Control.
    """
    try:
        services = get_personal_ip_runtime()
        if services.accounts is None:
            raise RuntimeError("Personal-IP account persistence is not available")
        owner_user_id = resolve_runtime_user_id(runtime)
        thread_id = str((runtime.context or {}).get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("browser publication requires a thread")
        account = await services.accounts.get(account_id, owner_user_id=owner_user_id)
        if account is None or account.get("status") != "active":
            raise ValueError("Personal-IP publish target account not found")
        receipt = await services.publish_receipts.begin(
            owner_user_id=owner_user_id,
            operation_key=operation_key,
            idempotency_key=idempotency_key,
            account_id=account["id"],
            preflight_id=str(preflight_id or "").strip() or None,
            executor="browser",
            request_payload=request,
        )
        paths = get_paths()
        safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
        target = select_browser_account_target(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            account_id=account["id"],
            platform=account["platform"],
            display_name=account["display_name"],
            user_data_dir=paths.ensure_browser_profile_dir(account["id"], user_id=safe_user_id),
        )
        handoff_payload = _browser_handoff_payload(account_id=target.account_id, start_url=target.start_url)
        existing_attempt = _attempt_with_key(receipt, pending_attempt_key)
        if existing_attempt is None:
            if receipt.get("status") not in {"planned", "failed", "unknown"}:
                raise ValueError("browser publish receipt already entered execution with a different attempt key")
            receipt = await services.publish_receipts.record_attempt(
                receipt["id"],
                owner_user_id=owner_user_id,
                attempt_key=pending_attempt_key,
                status="pending",
                result_payload=handoff_payload,
                occurred_at=(_parse_datetime(receipt["created_at"], field="created_at") if not (receipt.get("attempts") or []) else None),
            )
            if receipt is None:
                raise RuntimeError("Publish receipt disappeared during browser handoff")
        elif existing_attempt.get("status") != "pending" or existing_attempt.get("result") != handoff_payload:
            raise ValueError("pending_attempt_key already records a different browser handoff")
        return _json(
            {
                "operation_status": "ok",
                "browser_target": {
                    "account_id": target.account_id,
                    "platform": target.platform,
                    "display_name": target.display_name,
                    "start_url": target.start_url,
                },
                "receipt": receipt,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Browser publication could not be prepared"})


async def _observe_selected_browser(runtime: Runtime) -> dict:
    from deerflow.community.browser_automation import acquire_runtime_browser_session

    with acquire_runtime_browser_session(runtime) as session:
        snapshot = await session.snapshot()
        visible_text = await session.get_text(max_chars=20_000)
    return {
        "url": snapshot.url,
        "title": snapshot.title,
        "visible_text": visible_text,
    }


async def _personal_ip_finish_browser_publish(
    runtime: Runtime,
    receipt_id: str,
    attempt_key: str,
    status: str,
    evidence: dict,
    occurred_at: str,
    external_post_id: str,
    external_url: str,
) -> str:
    """Seal the outcome of the currently selected account's browser publish.

    A published outcome is accepted only when the live browser is open on the
    declared platform post, or the declared post id is visible there. The
    evidence must include personal-ip-publish-compliance-evidence-v1 bound to
    the sealed policy receipt and identify the applied disclosures. Query
    credentials and fragments are removed; only a page-title and text digest
    are persisted with caller-supplied credential-free evidence.

    Args:
        receipt_id: Browser publish receipt returned by prepare.
        attempt_key: Stable key for this terminal browser observation.
        status: published, failed or unknown.
        evidence: Credential-free confirmation/failure context and compliance evidence on success.
        occurred_at: Optional ISO-8601 time with timezone; empty uses server time.
        external_post_id: Platform post id; empty when unavailable.
        external_url: Public post URL; empty when unavailable.

    Returns:
        JSON updated immutable receipt with live-browser proof on success.
    """
    try:
        if status not in {"published", "failed", "unknown"}:
            raise ValueError("browser publish outcome must be published, failed or unknown")
        services = get_personal_ip_runtime()
        owner_user_id = resolve_runtime_user_id(runtime)
        receipt = await services.publish_receipts.get(receipt_id, owner_user_id=owner_user_id)
        if receipt is None:
            return _json({"status": "error", "category": "not_found", "message": "Publish receipt not found"})
        if receipt.get("executor") != "browser":
            raise ValueError("publish receipt is not assigned to the browser executor")
        existing_attempt = _attempt_with_key(receipt, attempt_key)
        if existing_attempt is not None:
            if not _browser_result_replay_matches(
                receipt=receipt,
                existing_attempt=existing_attempt,
                status=status,
                evidence=evidence,
                occurred_at=occurred_at,
                external_post_id=external_post_id,
                external_url=external_url,
            ):
                raise ValueError("attempt_key already records a different browser result")
            return _json({"operation_status": "ok", **receipt})
        thread_id = str((runtime.context or {}).get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("browser publication requires a thread")
        target = get_browser_account_target(owner_user_id=owner_user_id, thread_id=thread_id)
        if target is None or target.account_id != receipt.get("account_id"):
            raise ValueError("selected browser account does not match the publish receipt")
        if target.platform != receipt.get("platform"):
            raise ValueError("selected browser platform does not match the publish receipt")
        result_payload = dict(evidence)
        if status == "published":
            observed = await _observe_selected_browser(runtime)
            result_payload["browser_proof"] = verify_browser_publication_evidence(
                platform=target.platform,
                observed_url=observed["url"],
                page_title=observed["title"],
                visible_text=observed["visible_text"],
                external_url=str(external_url or "").strip() or None,
                external_post_id=str(external_post_id or "").strip() or None,
            )
        result = await services.publish_receipts.record_attempt(
            receipt_id,
            owner_user_id=owner_user_id,
            attempt_key=attempt_key,
            status=status,
            result_payload=result_payload,
            occurred_at=_optional_datetime(occurred_at, field="occurred_at"),
            external_post_id=str(external_post_id or "").strip() or None,
            external_url=str(external_url or "").strip() or None,
        )
        if result is None:
            return _json({"status": "error", "category": "not_found", "message": "Publish receipt not found"})
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Browser publication outcome could not be sealed"})


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
    """Append evidence from one real non-browser publication attempt.

    Record pending before handing control to a provider when possible, then
    append a new published, failed or unknown attempt from observed evidence.
    A published result must include personal-ip-publish-compliance-evidence-v1
    bound to the request's server receipt. Browser receipts must use the
    composite prepare/finish tools.

    Args:
        receipt_id: Planned publication receipt id.
        attempt_key: Stable id for this exact attempt or callback.
        status: pending, published, failed, unknown or deleted.
        result: Sanitized visible/API evidence and compliance evidence on success; never credentials.
        occurred_at: Optional ISO-8601 time with timezone; empty uses server time.
        external_post_id: Confirmed platform post id, or empty when unavailable.
        external_url: Confirmed public post URL, or empty when unavailable.

    Returns:
        JSON updated receipt with its complete append-only attempt history.
    """
    try:
        services = get_personal_ip_runtime()
        owner_user_id = resolve_runtime_user_id(runtime)
        existing = await services.publish_receipts.get(receipt_id, owner_user_id=owner_user_id)
        if existing is None:
            return _json({"status": "error", "category": "not_found", "message": "Publish receipt not found"})
        if existing.get("executor") == "browser":
            raise ValueError("browser receipts must use personal_ip_finish_browser_publish")
        receipt = await services.publish_receipts.record_attempt(
            receipt_id,
            owner_user_id=owner_user_id,
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


personal_ip_run_preflight_tool = tool("personal_ip_run_preflight", parse_docstring=True)(_personal_ip_run_preflight)
personal_ip_read_preflight_tool = tool("personal_ip_read_preflight", parse_docstring=True)(_personal_ip_read_preflight)
personal_ip_begin_publish_receipt_tool = tool("personal_ip_begin_publish_receipt", parse_docstring=True)(_personal_ip_begin_publish_receipt)
personal_ip_prepare_browser_publish_tool = tool("personal_ip_prepare_browser_publish", parse_docstring=True)(_personal_ip_prepare_browser_publish)
personal_ip_finish_browser_publish_tool = tool("personal_ip_finish_browser_publish", parse_docstring=True)(_personal_ip_finish_browser_publish)
personal_ip_record_publish_attempt_tool = tool("personal_ip_record_publish_attempt", parse_docstring=True)(_personal_ip_record_publish_attempt)
personal_ip_read_publish_receipt_tool = tool("personal_ip_read_publish_receipt", parse_docstring=True)(_personal_ip_read_publish_receipt)
personal_ip_seal_retrospective_tool = tool("personal_ip_seal_retrospective", parse_docstring=True)(_personal_ip_seal_retrospective)
personal_ip_read_retrospective_tool = tool("personal_ip_read_retrospective", parse_docstring=True)(_personal_ip_read_retrospective)
