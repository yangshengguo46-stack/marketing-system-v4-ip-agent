"""Native tools for the subject-level Personal-IP operating strategy."""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool

from deerflow.personal_ip.runtime import get_personal_ip_runtime
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


async def _personal_ip_record_strategy(
    runtime: Runtime,
    operation_key: str,
    stage: str,
    display_name: str = "",
    subject_id: str = "",
    person_model: dict | None = None,
    business_model: dict | None = None,
    benchmark_research: dict | None = None,
    positioning_candidates: list[dict] | None = None,
    launch_package: dict | None = None,
    validation: dict | None = None,
    evidence_refs: list[dict] | None = None,
    differentiation_version_id: str = "",
    subject_type: str = "creator",
) -> str:
    """Append one private IP influence-asset operating-strategy snapshot.

    Use this throughout natural conversation for a person, brand, product or
    organization. Every business model declares influence, behavioral and
    economic goals independently. Never expose stage names, private fields or
    the underlying method to the customer. Omitted documents inherit from the
    latest immutable snapshot. The removed binary mode remains only inside
    historical storage and is not an Agent input.

    Args:
        operation_key: Stable idempotency key for this exact strategy write.
        stage: Internal strategy stage from evidence_collecting through scaling.
        display_name: Natural person or brand name; required only when creating the first subject.
        subject_id: Existing owner-scoped subject id, or empty when zero or one subject exists.
        person_model: Operated-entity evidence. For a creator use facts, history,
            expertise, boundaries, media presence and capacity. For a brand,
            product or organization use entity_type, category/lifecycle/
            operating facts, history, capability evidence, public interfaces,
            stakeholders, boundaries and capacity.
        business_model: Influence, behavioral and economic objectives plus
            buyer, paid problem, offer, proof, economics and monetization paths.
        benchmark_research: Evidence-backed real account research with source URLs.
        positioning_candidates: Two or three differentiated business-position alternatives.
        launch_package: Name, handle, avatar, bio, pinned content, pilot and conversion package.
        validation: Pilot, commercial-signal and validation evidence.
        evidence_refs: Credential-free references to interviews, media, pages, metrics or receipts.
        differentiation_version_id: Pilot or adopted thesis version required before positioning.
        subject_type: creator, brand, product or organization when creating the first subject.

    Returns:
        JSON subject id, immutable version and current stage.
    """
    try:
        services = get_personal_ip_runtime()
        if services.subjects is None or services.brand is None:
            raise RuntimeError("Personal-IP strategy persistence is not available")
        owner_user_id = resolve_runtime_user_id(runtime)
        subjects = await services.subjects.list(owner_user_id)
        subject: dict[str, Any] | None = None
        if subject_id:
            subject = await services.subjects.get(subject_id, owner_user_id=owner_user_id)
            if subject is None or subject.get("status") != "active":
                raise ValueError("Personal-IP subject not found")
        elif len(subjects) == 1:
            subject = subjects[0]
        elif len(subjects) > 1:
            raise ValueError("subject_id is required when multiple Personal-IP subjects exist")
        else:
            cleaned_name = " ".join(str(display_name or "").split())
            if not cleaned_name:
                raise ValueError("display_name is required for the first Personal-IP subject")
            subject_type_key = str(subject_type or "").strip()
            if subject_type_key not in {"creator", "brand", "product", "organization"}:
                raise ValueError("subject_type must be creator, brand, product or organization")
            subject = await services.subjects.create(
                owner_user_id=owner_user_id,
                display_name=cleaned_name,
                subject_type=subject_type_key,
                relationship="self",
                metadata={"asset_mechanism": "influence"},
            )

        strategy = await services.brand.create_strategy_version(
            owner_user_id=owner_user_id,
            operation_key=operation_key,
            subject_id=subject["id"],
            stage=stage,
            mode="monetization_first",
            person_model=person_model,
            business_model=business_model,
            benchmark_research=benchmark_research,
            positioning_candidates=positioning_candidates,
            launch_package=launch_package,
            validation=validation,
            evidence_refs=evidence_refs,
            differentiation_version_id=str(differentiation_version_id or "").strip() or None,
        )
        assigned_account_count = 0
        if services.accounts is not None and len(await services.subjects.list(owner_user_id)) == 1:
            for account in await services.accounts.list(owner_user_id):
                if account.get("subject_id") is None:
                    updated = await services.accounts.update(
                        account["id"],
                        owner_user_id=owner_user_id,
                        updates={"subject_id": subject["id"]},
                    )
                    assigned_account_count += int(updated is not None)
        return _json(
            {
                "operation_status": "ok",
                "subject_id": subject["id"],
                "strategy_version_id": strategy["id"],
                "strategy_version": strategy["version"],
                "stage": strategy["stage"],
                "assigned_account_count": assigned_account_count,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Operating strategy could not be written"})


async def _personal_ip_read_strategy_context(runtime: Runtime, subject_id: str) -> str:
    """Read the latest private operating strategy for one subject.

    Args:
        subject_id: Owner-scoped person or brand.

    Returns:
        JSON latest immutable strategy snapshot, or null when not started.
    """
    try:
        services = get_personal_ip_runtime()
        if services.brand is None:
            raise RuntimeError("Personal-IP strategy persistence is not available")
        strategy = await services.brand.get_latest_strategy(
            subject_id,
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        if strategy is not None:
            strategy = dict(strategy)
            strategy.pop("mode", None)
        return _json(
            {
                "operation_status": "ok",
                "subject_id": subject_id,
                "strategy": strategy,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Strategy context is unavailable"})


personal_ip_record_strategy_tool = tool(
    "personal_ip_record_strategy",
    parse_docstring=True,
)(_personal_ip_record_strategy)
personal_ip_read_strategy_context_tool = tool(
    "personal_ip_read_strategy_context",
    parse_docstring=True,
)(_personal_ip_read_strategy_context)
