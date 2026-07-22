"""Native DeerFlow read/sync tools for consented local MineContext evidence."""

from __future__ import annotations

import asyncio
import json

from langchain.tools import tool

from deerflow.personal_ip.runtime import get_personal_ip_runtime
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _service():
    service = get_personal_ip_runtime().minecontext
    if service is None:
        raise RuntimeError("MineContext local evidence is not available")
    return service


async def _personal_ip_minecontext_sync(
    runtime: Runtime,
    query: str,
    source_kind: str,
    purpose: str,
    context_types: list[str],
    limit: int = 10,
) -> str:
    """Sync minimized local context summaries through the MineContext boundary.

    This tool cannot start capture or widen consent. It only searches a running,
    explicitly authorized owner sidecar and returns sealed summaries without raw
    screenshots, document text, file paths, vectors or credentials.

    Args:
        query: Bounded semantic search query; secrets are redacted before use.
        source_kind: Authorized source scope: screen, files, people, projects or work_activity.
        purpose: Authorized use: persona_modeling, audience_modeling, hllm_user_profile, preflight or retrospective.
        context_types: Optional MineContext processed context type filters.
        limit: Maximum sealed records to return, from 1 to the operator cap.

    Returns:
        JSON containing versioned, minimized evidence records and coverage limits.
    """
    try:
        records = await asyncio.to_thread(
            _service().sync,
            resolve_runtime_user_id(runtime),
            query=query,
            source_kind=source_kind,
            purpose=purpose,
            context_types=context_types,
            limit=int(limit),
        )
        return _json({"operation_status": "ok", "records": records, "count": len(records)})
    except (PermissionError, RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "MineContext evidence sync failed"})


async def _personal_ip_minecontext_evidence(
    runtime: Runtime,
    purpose: str,
    source_kinds: list[str],
    evidence_ids: list[str],
    limit: int = 20,
) -> str:
    """Read previously sealed local evidence for an authorized Personal-IP purpose.

    Args:
        purpose: Authorized use: persona_modeling, audience_modeling, hllm_user_profile, preflight or retrospective.
        source_kinds: Optional authorized source scopes to include.
        evidence_ids: Optional exact evidence ids to include.
        limit: Maximum records to return, from 1 to 100.

    Returns:
        JSON versioned evidence records with provenance, observation time and privacy metadata.
    """
    try:
        records = await asyncio.to_thread(
            _service().read_evidence,
            resolve_runtime_user_id(runtime),
            purpose=purpose,
            source_kinds=source_kinds,
            evidence_ids=evidence_ids,
            limit=int(limit),
        )
        return _json({"operation_status": "ok", "records": records, "count": len(records)})
    except (PermissionError, RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "MineContext evidence is unavailable"})


personal_ip_minecontext_sync_tool = tool("personal_ip_minecontext_sync", parse_docstring=True)(_personal_ip_minecontext_sync)
personal_ip_minecontext_evidence_tool = tool("personal_ip_minecontext_evidence", parse_docstring=True)(_personal_ip_minecontext_evidence)
