from __future__ import annotations

import pytest

from deerflow.ip_agent.mediakit_video_understanding_pricing import (
    estimate_video_understanding_public_tariff,
)


def test_q157_public_tariff_estimate_uses_second_input_tier() -> None:
    estimate = estimate_video_understanding_public_tariff(
        prompt_tokens=37_501,
        completion_tokens=3_812,
    )

    assert estimate.input_tier_lower_exclusive_tokens == 32_768
    assert estimate.input_tier_upper_inclusive_tokens == 131_072
    assert estimate.input_rate_cny_per_million_tokens == "4.8"
    assert estimate.output_rate_cny_per_million_tokens == "24.0"
    assert estimate.amount_micros == 271_493
    assert estimate.reasoning_accounting == "included_once_in_provider_completion_tokens"


@pytest.mark.parametrize(
    ("prompt_tokens", "expected_upper", "expected_amount_micros"),
    [
        (32_768, 32_768, 104_858),
        (32_769, 131_072, 157_292),
        (131_072, 131_072, 629_146),
        (131_073, 262_144, 1_258_301),
        (262_144, 262_144, 2_516_583),
    ],
)
def test_public_tariff_tier_boundaries(
    prompt_tokens: int,
    expected_upper: int,
    expected_amount_micros: int,
) -> None:
    estimate = estimate_video_understanding_public_tariff(
        prompt_tokens=prompt_tokens,
        completion_tokens=0,
    )

    assert estimate.input_tier_upper_inclusive_tokens == expected_upper
    assert estimate.amount_micros == expected_amount_micros


@pytest.mark.parametrize(
    ("prompt_tokens", "completion_tokens"),
    [
        (-1, 0),
        (0, -1),
        (True, 0),
        (0, False),
        (262_145, 0),
    ],
)
def test_public_tariff_rejects_invalid_or_unpublished_usage(
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    with pytest.raises(ValueError):
        estimate_video_understanding_public_tariff(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
