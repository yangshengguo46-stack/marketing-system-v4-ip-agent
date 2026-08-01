from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.personal_ip.account_diagnosis import (
    ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION,
    PersonalIPAccountDiagnosticContextService,
)
from deerflow.skills.parser import parse_skill_file
from deerflow.skills.types import SkillCategory

REPO_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_DIAGNOSIS_SKILLS = {
    "diagnose-douyin-account",
    "diagnose-wechat-channels-account",
    "diagnose-wechat-official-account",
    "diagnose-xiaohongshu-account",
    "diagnose-x-account",
    "diagnose-instagram-account",
    "diagnose-youtube-account",
    "diagnose-tiktok-account",
}


def _service(
    *, account: dict | None = None
) -> tuple[
    PersonalIPAccountDiagnosticContextService,
    SimpleNamespace,
]:
    repos = SimpleNamespace(
        accounts=SimpleNamespace(
            get=AsyncMock(
                return_value=(
                    account
                    if account is not None
                    else {
                        "id": "acct-1",
                        "subject_id": "subject-1",
                        "platform": "douyin",
                        "display_name": "测试账号",
                        "status": "active",
                    }
                )
            )
        ),
        metrics=SimpleNamespace(list=AsyncMock(return_value=[])),
        platform_observations=SimpleNamespace(list=AsyncMock(return_value=[])),
        publish_receipts=SimpleNamespace(list=AsyncMock(return_value=[])),
        retrospectives=SimpleNamespace(list=AsyncMock(return_value=[])),
        brand=SimpleNamespace(get_latest_strategy=AsyncMock(return_value=None)),
        differentiation=SimpleNamespace(
            get_latest=AsyncMock(return_value=None),
            get_version=AsyncMock(return_value=None),
            list_observations=AsyncMock(return_value=[]),
        ),
    )
    return (
        PersonalIPAccountDiagnosticContextService(
            accounts=repos.accounts,
            metrics=repos.metrics,
            platform_observations=repos.platform_observations,
            publish_receipts=repos.publish_receipts,
            retrospectives=repos.retrospectives,
            brand=repos.brand,
            differentiation=repos.differentiation,
        ),
        repos,
    )


@pytest.mark.asyncio
async def test_context_is_owner_scoped_and_missing_data_does_not_block() -> None:
    service, repos = _service()

    result = await service.build(owner_user_id="owner-1", account_id="acct-1")

    assert result["contract_version"] == ACCOUNT_DIAGNOSTIC_CONTEXT_VERSION
    assert result["account"]["id"] == "acct-1"
    assert result["inventory"] == {
        "metric_observation_count": 0,
        "platform_observation_count": 0,
        "publish_receipt_count": 0,
        "retrospective_count": 0,
        "asset_observation_count": 0,
    }
    assert "sample" not in result
    assert "decision" not in result
    assert "guardrails" not in result
    repos.accounts.get.assert_awaited_once_with(
        "acct-1",
        owner_user_id="owner-1",
    )


@pytest.mark.asyncio
async def test_context_returns_observations_without_turning_them_into_a_verdict() -> None:
    service, repos = _service()
    repos.metrics.list.return_value = [
        {
            "id": "metric-1",
            "scope": "post",
            "metric_mode": "snapshot",
            "status": "partial",
            "observed_at": "2026-07-01T00:00:00Z",
            "metrics": {"views": 12},
            "coverage": {"scope_limit": "tracked_post_only"},
        }
    ]
    repos.platform_observations.list.return_value = [
        {
            "id": "observation-1",
            "dataset": "content_inventory",
            "status": "partial",
            "observed_at": "2026-06-01T00:00:00Z",
            "records": [{"post_id": "post-1", "title": "第一条"}],
            "summary": {},
            "coverage": {"complete": False},
        }
    ]

    result = await service.build(owner_user_id="owner-1", account_id="acct-1")

    assert result["metric_observations"][0]["metrics"] == {"views": 12}
    assert result["platform_observations"][0]["records"][0]["title"] == "第一条"
    assert result["inventory"]["metric_observation_count"] == 1
    assert result["inventory"]["platform_observation_count"] == 1
    assert "classification" not in result


def test_platform_diagnosis_skills_use_evidence_reader_without_server_verdict() -> None:
    for skill_name in PLATFORM_DIAGNOSIS_SKILLS:
        skill = parse_skill_file(
            REPO_ROOT / "skills" / "public" / skill_name / "SKILL.md",
            category=SkillCategory.PUBLIC,
        )
        assert skill is not None
        instructions = skill.skill_file.read_text(encoding="utf-8")
        assert "personal_ip_account_diagnostic_context" in instructions
        assert "personal_ip_compile_account_diagnosis" not in instructions
        assert "decision_ready" not in instructions
        assert "minimum_post_count" not in instructions
