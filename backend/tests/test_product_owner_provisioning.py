from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from deerflow.config.paths import Paths


def _write_source(root: Path, *, tools: list[str] | None = None) -> Path:
    source = root / "product" / "defaults" / "agents" / "ip-agent"
    source.mkdir(parents=True)
    (source / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "ip-agent",
                "description": "Product Agent",
                "skills": [],
                "tool_allowlist": tools or ["web_search", "read_file"],
                "memory_enabled": False,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (source / "SOUL.md").write_text("# Product soul\n", encoding="utf-8")
    return source


def _ensure(root: Path, state: Path, owner: str = "owner-1"):
    from app.gateway.product_owner_provisioning import ensure_product_owner_agent
    from deerflow.config.agents_config import agent_artifact_sha256

    source = root / "product" / "defaults" / "agents" / "ip-agent"

    return ensure_product_owner_agent(
        owner_user_id=owner,
        assistant_id="ip-agent",
        declared_capability={
            "tool_allowlist": ["web_search", "read_file"],
            "skills": [],
            "memory_enabled": False,
        },
        declared_artifact_sha256=agent_artifact_sha256(source),
        paths=Paths(state),
        project_root=root,
    )


def test_agent_artifact_digest_covers_config_and_soul(tmp_path):
    from deerflow.config.agents_config import agent_artifact_sha256

    source = _write_source(tmp_path / "repo")
    first = agent_artifact_sha256(source)

    (source / "SOUL.md").write_text("# Changed soul\n", encoding="utf-8")
    second = agent_artifact_sha256(source)

    assert len(first) == 64
    assert first != second


def test_missing_owner_agent_is_installed_atomically_from_product_defaults(
    tmp_path,
):
    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root)

    config = _ensure(root, state, owner="user-uuid-1")

    target = state / "users" / "user-uuid-1" / "agents" / "ip-agent"
    assert config.name == "ip-agent"
    assert (target / "config.yaml").is_file()
    assert (target / "SOUL.md").read_text(encoding="utf-8") == "# Product soul\n"
    assert not list(target.parent.glob(".ip-agent.install-*"))


def test_existing_owner_agent_is_never_repaired_or_overwritten(tmp_path):
    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root)
    target = state / "users" / "owner-1" / "agents" / "ip-agent"
    target.mkdir(parents=True)
    existing = "name: ip-agent\ntool_allowlist: []\nskills: []\nmemory_enabled: false\n"
    (target / "config.yaml").write_text(existing, encoding="utf-8")

    with pytest.raises(RuntimeError, match="incomplete|drift"):
        _ensure(root, state)

    assert (target / "config.yaml").read_text(encoding="utf-8") == existing
    assert not (target / "SOUL.md").exists()


def test_legacy_shared_agent_cannot_satisfy_owner_product_binding(tmp_path):
    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root)
    legacy = state / "agents" / "ip-agent"
    legacy.mkdir(parents=True)
    (legacy / "config.yaml").write_text("name: legacy\n", encoding="utf-8")
    (legacy / "SOUL.md").write_text("legacy", encoding="utf-8")

    config = _ensure(root, state, owner="new-owner")

    owner_target = state / "users" / "new-owner" / "agents" / "ip-agent"
    assert config.name == "ip-agent"
    assert (owner_target / "SOUL.md").read_text(encoding="utf-8") == "# Product soul\n"
    assert (legacy / "SOUL.md").read_text(encoding="utf-8") == "legacy"


def test_source_capability_drift_fails_before_owner_directory_is_created(
    tmp_path,
):
    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root, tools=["web_search", "read_file", "bash"])

    with pytest.raises(RuntimeError, match="source capability drift"):
        _ensure(root, state)

    assert not (state / "users" / "owner-1" / "agents" / "ip-agent").exists()


def test_existing_owner_agent_is_validated_against_active_profile_not_default(
    tmp_path,
):
    """An isolated experiment profile may declare a separately installed Agent."""
    from app.gateway.product_owner_provisioning import ensure_product_owner_agent
    from deerflow.config.agents_config import agent_artifact_sha256

    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root)
    target = state / "users" / "owner-1" / "agents" / "ip-agent"
    target.mkdir(parents=True)
    (target / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "ip-agent",
                "description": "Evidence Agent",
                "skills": [],
                "tool_allowlist": ["web_search", "read_file", "evidence_tool"],
                "memory_enabled": False,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (target / "SOUL.md").write_text("# Evidence soul\n", encoding="utf-8")

    config = ensure_product_owner_agent(
        owner_user_id="owner-1",
        assistant_id="ip-agent",
        declared_capability={
            "tool_allowlist": ["web_search", "read_file", "evidence_tool"],
            "skills": [],
            "memory_enabled": False,
        },
        declared_artifact_sha256=agent_artifact_sha256(target),
        paths=Paths(state),
        project_root=root,
    )

    assert config.tool_allowlist == ["web_search", "read_file", "evidence_tool"]
    assert (target / "SOUL.md").read_text(encoding="utf-8") == "# Evidence soul\n"


def test_existing_owner_soul_drift_fails_closed_without_repair(tmp_path):
    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root)
    _ensure(root, state)
    target = state / "users" / "owner-1" / "agents" / "ip-agent"
    (target / "SOUL.md").write_text("tampered soul", encoding="utf-8")

    with pytest.raises(RuntimeError, match="artifact drift"):
        _ensure(root, state)

    assert (target / "SOUL.md").read_text(encoding="utf-8") == "tampered soul"


def test_concurrent_first_requests_leave_one_complete_owner_agent(tmp_path):
    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root)

    with ThreadPoolExecutor(max_workers=8) as executor:
        configs = list(executor.map(lambda _: _ensure(root, state), range(16)))

    target = state / "users" / "owner-1" / "agents" / "ip-agent"
    assert all(config.name == "ip-agent" for config in configs)
    assert {path.name for path in target.iterdir()} == {"config.yaml", "SOUL.md"}
    assert not list(target.parent.glob(".ip-agent.install-*"))


def test_symlink_owner_agent_fails_closed(tmp_path):
    root = tmp_path / "repo"
    state = tmp_path / "state"
    _write_source(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = state / "users" / "owner-1" / "agents" / "ip-agent"
    target.parent.mkdir(parents=True)
    target.symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symbolic link"):
        _ensure(root, state)

    assert not list(outside.iterdir())
