"""Native DeerFlow tools for whole-portfolio Personal-IP performance work."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256

from langchain.tools import tool

from deerflow.config.paths import get_paths
from deerflow.personal_ip.browser_collection import (
    BrowserPlatformCollectionError,
    BrowserPlatformCollectionService,
    DouyinBrowserCollectionError,
    DouyinBrowserCollectionService,
    acquire_account_browser_session,
)
from deerflow.personal_ip.browser_profiles import select_browser_account_target
from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient, DouyinOAuthError
from deerflow.personal_ip.media_execution import normalize_media_execution_receipt
from deerflow.personal_ip.operating_cockpit import PersonalIPOperatingCockpitService
from deerflow.personal_ip.platform_metrics import (
    DouyinAuthorizedMetricCollectionService,
    PlatformMetricCollectionError,
)
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, get_personal_ip_runtime
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


def _operating_cockpit_service(services: PersonalIPRuntimeServices) -> PersonalIPOperatingCockpitService:
    required = {
        "subjects": services.subjects,
        "accounts": services.accounts,
        "preflights": services.preflights,
        "publish_receipts": services.publish_receipts,
        "metrics": services.metrics,
        "platform_observations": services.platform_observations,
        "retrospectives": services.retrospectives,
        "evidence_promotions": services.evidence_promotions,
        "video_productions": services.video_productions,
    }
    missing = sorted(name for name, repository in required.items() if repository is None)
    if missing:
        raise RuntimeError(f"Personal-IP operating cockpit is incomplete: {', '.join(missing)}")
    return PersonalIPOperatingCockpitService(**required)


async def _personal_ip_operating_cockpit(runtime: Runtime) -> str:
    """Read the user's whole Personal-IP business and video operating state.

    Use this as the default orientation tool before planning or executing work.
    It joins every subject and platform account with modeling, preflight,
    publishing, performance, retrospective, evidence-promotion and video
    production queues. It intentionally has no account filter because one
    conversation coordinates the user's entire portfolio.

    Returns:
        JSON containing the six-stage operating loop, nine-stage video line,
        explicit work queues, recent receipts and bounded history coverage.
    """
    try:
        result = await _operating_cockpit_service(get_personal_ip_runtime()).build(owner_user_id=resolve_runtime_user_id(runtime))
        return _json(result)
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Personal-IP cockpit is unavailable"})


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
        budget: Currency, limits and approval thresholds; may be empty.

    Returns:
        JSON production id, immutable request, current stage and ordered events.
    """
    try:
        services = get_personal_ip_runtime()
        if services.video_productions is None:
            raise RuntimeError("Personal-IP video production is not available")
        result = await services.video_productions.begin(
            owner_user_id=resolve_runtime_user_id(runtime),
            operation_key=operation_key,
            title=title,
            subject_id=str(subject_id or "").strip() or None,
            target_account_ids=target_account_ids,
            source_kind=source_kind,
            source=source,
            delivery_spec=delivery_spec,
            provider_policy=provider_policy,
            budget=budget,
        )
        return _json({"operation_status": "ok", **result})
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Video production could not be created"})


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
        payload: Detailed contract, result, QA finding or human decision snapshot.
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
        receipt: Complete personal-ip-media-execution-v1 executor receipt.

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
        paths = get_paths()
        safe_user_id = paths.prepare_user_dir_for_raw_id(owner_user_id)
        profile_dir = paths.ensure_browser_profile_dir(account["id"], user_id=safe_user_id)
        target = select_browser_account_target(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
            account_id=account["id"],
            platform=account["platform"],
            display_name=account["display_name"],
            user_data_dir=profile_dir,
        )
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

personal_ip_operating_cockpit_tool = tool(
    "personal_ip_operating_cockpit",
    parse_docstring=True,
)(_personal_ip_operating_cockpit)

personal_ip_begin_video_production_tool = tool(
    "personal_ip_begin_video_production",
    parse_docstring=True,
)(_personal_ip_begin_video_production)

personal_ip_record_video_production_event_tool = tool(
    "personal_ip_record_video_production_event",
    parse_docstring=True,
)(_personal_ip_record_video_production_event)

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
