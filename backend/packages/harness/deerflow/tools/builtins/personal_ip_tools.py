"""Native DeerFlow tools for whole-portfolio Personal-IP performance work."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256

from langchain.tools import tool

from deerflow.config.paths import get_paths
from deerflow.personal_ip.browser_profiles import select_browser_account_target
from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient, DouyinOAuthError
from deerflow.personal_ip.platform_metrics import (
    DouyinAuthorizedMetricCollectionService,
    PlatformMetricCollectionError,
)
from deerflow.personal_ip.runtime import PersonalIPRuntimeServices, get_personal_ip_runtime
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

personal_ip_sync_douyin_portfolio_tool = tool(
    "personal_ip_sync_douyin_portfolio",
    parse_docstring=True,
)(_personal_ip_sync_douyin_portfolio)
