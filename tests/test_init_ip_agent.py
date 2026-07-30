import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.init_ip_agent import default_state_dir, install  # noqa: E402


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
    assert (agent_dir / "config.yaml").is_file()
    assert (agent_dir / "SOUL.md").is_file()
    assert "personal-ip-operator" in (agent_dir / "config.yaml").read_text()


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

    install(
        root,
        state_dir,
        "user-1",
        force=False,
        refresh_product_agent=True,
    )

    assert user_profile.read_text() == "customer-owned profile"
    assert (agent_dir / "SOUL.md").read_text() == (root / "product" / "defaults" / "agents" / "ip-agent" / "SOUL.md").read_text()
    assert (agent_dir / "config.yaml").read_text() == (root / "product" / "defaults" / "agents" / "ip-agent" / "config.yaml").read_text()
