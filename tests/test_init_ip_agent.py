import base64
import json
import sys
from pathlib import Path

import yaml

from deerflow.config.agents_config import agent_artifact_sha256

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.init_ip_agent import (  # noqa: E402
    default_state_dir,
    ensure_account_binding_environment,
    install,
)


def _env_value(path: Path, name: str) -> str:
    prefix = f"{name}="
    line = next(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    )
    value = line[len(prefix) :]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def test_default_state_dir_matches_local_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEER_FLOW_HOME", raising=False)

    assert default_state_dir(tmp_path) == tmp_path / "backend" / ".deer-flow"

    configured = tmp_path / "custom-state"
    monkeypatch.setenv("DEER_FLOW_HOME", str(configured))
    assert default_state_dir(tmp_path) == configured.resolve()


def test_install_writes_a_complete_default_agent(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"

    install(root, state_dir, "user-1", force=False)

    agent_dir = state_dir / "users" / "user-1" / "agents" / "ip-agent"
    assert (state_dir / "USER.md").is_file()
    assert (state_dir / "product-runtime-profile.yaml").is_file()
    assert (agent_dir / "config.yaml").is_file()
    assert (agent_dir / "SOUL.md").is_file()
    config = yaml.safe_load((agent_dir / "config.yaml").read_text())
    assert config["skills"] == []
    assert config["memory_enabled"] is False
    assert set(config["tool_allowlist"]) == {
        "web_search",
        "image_search",
        "ls",
        "read_file",
        "glob",
        "grep",
        "view_image",
        "ask_clarification",
        "ip_evidence_collect_douyin_benchmark_account",
        "ip_evidence_inspect_reference_videos",
    }
    runtime_profile = yaml.safe_load(
        (state_dir / "product-runtime-profile.yaml").read_text()
    )
    assert runtime_profile["enabled"] is True
    assert runtime_profile["assistant_id"] == "ip-agent"
    assert runtime_profile["agent_artifact_sha256"] == agent_artifact_sha256(agent_dir)
    assert runtime_profile["capability_contract"] == {
        "tool_allowlist": config["tool_allowlist"],
        "skills": config["skills"],
        "memory_enabled": config["memory_enabled"],
    }


def test_install_keeps_existing_user_profile_without_force(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    user_profile = state_dir / "USER.md"
    user_profile.write_text("customer-owned profile")

    messages = install(root, state_dir, "user-1", force=False)

    assert user_profile.read_text() == "customer-owned profile"
    assert any(message.startswith("kept existing") for message in messages)


def test_refresh_product_agent_preserves_user_profile(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    state_dir = tmp_path / "state"
    install(root, state_dir, "user-1", force=False)
    user_profile = state_dir / "USER.md"
    agent_dir = state_dir / "users" / "user-1" / "agents" / "ip-agent"
    user_profile.write_text("customer-owned profile")
    (agent_dir / "SOUL.md").write_text("stale product default")
    (agent_dir / "config.yaml").write_text("name: stale")
    (state_dir / "product-runtime-profile.yaml").write_text("enabled: false")

    install(
        root,
        state_dir,
        "user-1",
        force=False,
        refresh_product_agent=True,
    )

    assert user_profile.read_text() == "customer-owned profile"
    assert (agent_dir / "SOUL.md").read_text() == (
        root / "product" / "defaults" / "agents" / "ip-agent" / "SOUL.md"
    ).read_text()
    assert (agent_dir / "config.yaml").read_text() == (
        root / "product" / "defaults" / "agents" / "ip-agent" / "config.yaml"
    ).read_text()
    assert (state_dir / "product-runtime-profile.yaml").read_text() == (
        root / "product" / "defaults" / "product-runtime-profile.yaml"
    ).read_text()


def test_account_binding_environment_is_generated_once_and_kept_private(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"

    first_message = ensure_account_binding_environment(env_path)
    first_text = env_path.read_text(encoding="utf-8")
    second_message = ensure_account_binding_environment(env_path)

    assert first_message.startswith("installed account binding environment")
    assert second_message.startswith("kept existing account binding environment")
    assert env_path.read_text(encoding="utf-8") == first_text
    assert env_path.stat().st_mode & 0o777 == 0o600
    active_kid = _env_value(env_path, "IP_AGENT_EVIDENCE_BINDING_ACTIVE_KID")
    keys = json.loads(_env_value(env_path, "IP_AGENT_EVIDENCE_BINDING_KEYS_JSON"))
    encoded = keys[active_kid]
    assert len(encoded) == 43
    assert "=" not in encoded
    assert len(base64.urlsafe_b64decode(encoded + "=")) == 32


def test_account_binding_environment_preserves_unrelated_values_and_comments(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# keep this comment\nMEDIAKIT_API_KEY=existing-key\n", encoding="utf-8"
    )

    ensure_account_binding_environment(env_path)

    text = env_path.read_text(encoding="utf-8")
    assert "# keep this comment" in text
    assert "MEDIAKIT_API_KEY=existing-key" in text


def test_account_binding_environment_normalizes_padding_without_rotating_key(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    raw_key = bytes(range(32))
    padded = base64.urlsafe_b64encode(raw_key).decode("ascii")
    env_path.write_text(
        f'IP_AGENT_EVIDENCE_BINDING_ACTIVE_KID=local-v1\nIP_AGENT_EVIDENCE_BINDING_KEYS_JSON=\'{{"local-v1":"{padded}"}}\'\n',
        encoding="utf-8",
    )

    message = ensure_account_binding_environment(env_path)

    keys = json.loads(_env_value(env_path, "IP_AGENT_EVIDENCE_BINDING_KEYS_JSON"))
    normalized = keys["local-v1"]
    assert message.startswith("normalized account binding environment")
    assert "=" not in normalized
    assert base64.urlsafe_b64decode(normalized + "=") == raw_key
