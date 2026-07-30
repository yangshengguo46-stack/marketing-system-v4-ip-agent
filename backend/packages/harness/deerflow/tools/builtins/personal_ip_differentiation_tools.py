"""Native tools for differentiation theses and observed IP-asset effects."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from langchain.tools import tool

from deerflow.personal_ip.runtime import get_personal_ip_runtime
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime

_SUBJECT_TYPES = {"creator", "brand", "product", "organization"}
_SUBJECT_RELATIONSHIPS = {"self", "client", "partner"}


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_datetime(value: str, *, field: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


async def _resolve_subject(
    runtime: Runtime,
    *,
    subject_id: str,
    display_name: str,
    subject_type: str,
    relationship: str,
) -> tuple[str, str]:
    services = get_personal_ip_runtime()
    if services.subjects is None:
        raise RuntimeError("Personal-IP subject persistence is not available")
    owner_user_id = resolve_runtime_user_id(runtime)
    subjects = await services.subjects.list(owner_user_id)
    if subject_id:
        subject = await services.subjects.get(subject_id, owner_user_id=owner_user_id)
        if subject is None or subject.get("status") != "active":
            raise ValueError("Personal-IP subject not found")
        return owner_user_id, str(subject["id"])
    if len(subjects) == 1:
        return owner_user_id, str(subjects[0]["id"])
    if len(subjects) > 1:
        raise ValueError("subject_id is required when multiple Personal-IP subjects exist")
    cleaned_name = " ".join(str(display_name or "").split())
    if not cleaned_name:
        raise ValueError("display_name is required for the first Personal-IP subject")
    subject_type_key = str(subject_type or "").strip()
    if subject_type_key not in _SUBJECT_TYPES:
        raise ValueError("subject_type must be creator, brand, product or organization")
    relationship_key = str(relationship or "").strip()
    if relationship_key not in _SUBJECT_RELATIONSHIPS:
        raise ValueError("relationship must be self, client or partner")
    subject = await services.subjects.create(
        owner_user_id=owner_user_id,
        display_name=cleaned_name,
        subject_type=subject_type_key,
        relationship=relationship_key,
        metadata={"source": "differentiation_incubation"},
    )
    return owner_user_id, str(subject["id"])


async def _personal_ip_record_differentiation(
    runtime: Runtime,
    operation_key: str,
    thesis_key: str,
    status: str,
    display_name: str = "",
    subject_id: str = "",
    subject_type: str = "creator",
    relationship: str = "self",
    primary_entity: dict | None = None,
    supporting_entities: list[dict] | None = None,
    decision_context: dict | None = None,
    contrast_field: dict | None = None,
    proprietary_truth: dict | None = None,
    strategic_difference: dict | None = None,
    dramatic_engine: dict | None = None,
    distinctive_encoding: dict | None = None,
    operating_fit: dict | None = None,
    validation: dict | None = None,
    evidence_refs: list[dict] | None = None,
) -> str:
    """Append one private differentiation-thesis version.

    Use this before final positioning, a series bible or a stable expression
    system. A candidate records a real strategic choice. Pilot and later
    statuses require a repeatable dramatic engine, distinctive encoding and
    evidence gates enforced by the repository. Omitted documents inherit only
    within the same thesis_key. Keep internal documents out of customer copy.

    Args:
        operation_key: Stable idempotency key for this exact immutable write.
        thesis_key: Stable lineage key while testing one strategic direction.
        status: candidate, pilot, provisionally_adopted, validated or retired.
        display_name: First operated entity name when no subject exists.
        subject_id: Existing owner-scoped subject, or empty with zero or one subject.
        subject_type: creator, brand, product or organization for a new subject.
        relationship: self, client or partner for a new subject.
        primary_entity: Entity type, name and public role being differentiated.
        supporting_entities: People, brands, products or organizations supporting the thesis.
        decision_context: Publics, jobs, alternatives, parity, desired influence and outcomes.
        contrast_field: Competitor territories, clichés, anti-benchmarks and cultural tension.
        proprietary_truth: Evidence, rare capability, mechanism, history, access and rights.
        strategic_difference: Value, meaning, choice and belief reasons, sacrifice and relevance.
        dramatic_engine: Repeatable protagonist, desire, counterforce, choice, world and events.
        distinctive_encoding: Verbal, visual, sonic, behavioral and ritual recognition system.
        operating_fit: Capacity, evidence supply, channel constraints, risk and extension rules.
        validation: Observations, hypotheses, falsifiable tests, failure and retirement conditions.
        evidence_refs: Credential-free immutable evidence references.

    Returns:
        JSON with subject, immutable version, status and observed validation summary.
    """
    try:
        services = get_personal_ip_runtime()
        if services.differentiation is None:
            raise RuntimeError("Personal-IP differentiation persistence is not available")
        owner_user_id, resolved_subject_id = await _resolve_subject(
            runtime,
            subject_id=subject_id,
            display_name=display_name,
            subject_type=subject_type,
            relationship=relationship,
        )
        version = await services.differentiation.create_version(
            owner_user_id=owner_user_id,
            operation_key=operation_key,
            subject_id=resolved_subject_id,
            thesis_key=thesis_key,
            status=status,
            primary_entity=primary_entity,
            supporting_entities=supporting_entities,
            decision_context=decision_context,
            contrast_field=contrast_field,
            proprietary_truth=proprietary_truth,
            strategic_difference=strategic_difference,
            dramatic_engine=dramatic_engine,
            distinctive_encoding=distinctive_encoding,
            operating_fit=operating_fit,
            validation=validation,
            evidence_refs=evidence_refs,
        )
        return _json(
            {
                "operation_status": "ok",
                "subject_id": resolved_subject_id,
                "differentiation_version_id": version["id"],
                "differentiation_version": version["version"],
                "thesis_key": version["thesis_key"],
                "status": version["status"],
                "validation_summary": version["validation_summary"],
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Differentiation thesis could not be written"})


async def _personal_ip_read_differentiation(runtime: Runtime, subject_id: str) -> str:
    """Read the latest private differentiation thesis for one subject.

    Args:
        subject_id: Owner-scoped person, brand, product or organization.

    Returns:
        JSON latest immutable differentiation thesis, or null.
    """
    try:
        services = get_personal_ip_runtime()
        if services.differentiation is None:
            raise RuntimeError("Personal-IP differentiation persistence is not available")
        result = await services.differentiation.get_latest(
            subject_id,
            owner_user_id=resolve_runtime_user_id(runtime),
        )
        return _json(
            {
                "operation_status": "ok",
                "subject_id": subject_id,
                "differentiation": result,
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "Differentiation context is unavailable"})


async def _personal_ip_record_asset_observation(
    runtime: Runtime,
    operation_key: str,
    subject_id: str,
    differentiation_version_id: str,
    observation_type: str,
    source: str,
    observed_at: str,
    coverage_status: str,
    measures: dict,
    evidence_refs: list[dict],
) -> str:
    """Seal one observed recognition, trust, intent, adoption or economic effect.

    This records observations rather than scores or causal claims. Missing or
    partial coverage stays explicit. At least three complete supportive
    observations across two effect types, including a downstream action, are
    required before a differentiation thesis can become validated.

    Args:
        operation_key: Stable idempotency key for this exact observation.
        subject_id: Owner-scoped operated entity.
        differentiation_version_id: Exact thesis version being observed.
        observation_type: recognition, trust, intent, adoption, conversion, economic or extension.
        source: Sealed evidence source category.
        observed_at: Timezone-aware ISO-8601 observation time.
        coverage_status: complete, partial or unavailable.
        measures: Credential-free observed measures without invented zeros.
            Must include result as supports, contradicts, mixed or inconclusive.
        evidence_refs: Immutable evidence references supporting the observation.

    Returns:
        JSON with the immutable observation id and coverage.
    """
    try:
        services = get_personal_ip_runtime()
        if services.differentiation is None:
            raise RuntimeError("Personal-IP differentiation persistence is not available")
        observation = await services.differentiation.record_observation(
            owner_user_id=resolve_runtime_user_id(runtime),
            operation_key=operation_key,
            subject_id=subject_id,
            differentiation_version_id=differentiation_version_id,
            observation_type=observation_type,
            source=source,
            observed_at=_parse_datetime(observed_at, field="observed_at"),
            coverage_status=coverage_status,
            measures=measures,
            evidence_refs=evidence_refs,
        )
        return _json(
            {
                "operation_status": "ok",
                "observation_id": observation["id"],
                "subject_id": observation["subject_id"],
                "differentiation_version_id": observation["differentiation_version_id"],
                "observation_type": observation["observation_type"],
                "coverage_status": observation["coverage_status"],
                "observed_at": observation["observed_at"],
            }
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        return _json({"status": "error", "category": "invalid_request", "message": str(exc)})
    except Exception:
        return _json({"status": "error", "category": "internal", "message": "IP-asset observation could not be written"})


personal_ip_record_differentiation_tool = tool(
    "personal_ip_record_differentiation",
    parse_docstring=True,
)(_personal_ip_record_differentiation)
personal_ip_read_differentiation_tool = tool(
    "personal_ip_read_differentiation",
    parse_docstring=True,
)(_personal_ip_read_differentiation)
personal_ip_record_asset_observation_tool = tool(
    "personal_ip_record_asset_observation",
    parse_docstring=True,
)(_personal_ip_record_asset_observation)
