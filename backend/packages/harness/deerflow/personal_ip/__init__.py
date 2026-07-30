"""Thin Personal-IP adapters over DeerFlow and vendored model foundations."""

from deerflow.personal_ip.audience_provider import (
    AUDIENCE_PREFLIGHT_CONTRACT_VERSION,
    AudienceCreativeVariant,
    AudienceMechanismHypothesis,
    AudiencePreflightRequest,
    AudiencePreflightResult,
    HLLMCreatorHTTPProvider,
)
from deerflow.personal_ip.differentiation import (
    DIFFERENTIATION_STATUSES,
    PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION,
)
from deerflow.personal_ip.hllm_creator import (
    HLLM_CREATOR_FIELDS,
    HLLM_UPSTREAM_COMMIT,
    HLLMCreatorAdapter,
    verify_vendored_hllm,
)

__all__ = [
    "AUDIENCE_PREFLIGHT_CONTRACT_VERSION",
    "DIFFERENTIATION_STATUSES",
    "HLLM_CREATOR_FIELDS",
    "HLLM_UPSTREAM_COMMIT",
    "PERSONAL_IP_DIFFERENTIATION_METHOD_VERSION",
    "AudienceCreativeVariant",
    "AudienceMechanismHypothesis",
    "AudiencePreflightRequest",
    "AudiencePreflightResult",
    "HLLMCreatorAdapter",
    "HLLMCreatorHTTPProvider",
    "verify_vendored_hllm",
]
