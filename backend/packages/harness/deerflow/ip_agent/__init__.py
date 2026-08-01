"""Evidence capabilities for the product IP Agent's isolated test profile."""

from .evidence_contracts import (
    BENCHMARK_ACCOUNT_CONTRACT_VERSION,
    REFERENCE_VIDEO_CONTRACT_VERSION,
)
from .reference_evidence import (
    collect_douyin_benchmark_account,
    inspect_reference_videos,
)

__all__ = [
    "BENCHMARK_ACCOUNT_CONTRACT_VERSION",
    "REFERENCE_VIDEO_CONTRACT_VERSION",
    "collect_douyin_benchmark_account",
    "inspect_reference_videos",
]
