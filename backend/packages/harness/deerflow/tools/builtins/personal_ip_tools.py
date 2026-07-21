"""Native DeerFlow tools for whole-portfolio Personal-IP performance work."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from langchain.tools import tool

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


personal_ip_metrics_aggregate_tool = tool(
    "personal_ip_metrics_aggregate",
    parse_docstring=True,
)(_personal_ip_metrics_aggregate)

personal_ip_sync_douyin_post_tool = tool(
    "personal_ip_sync_douyin_post",
    parse_docstring=True,
)(_personal_ip_sync_douyin_post)
