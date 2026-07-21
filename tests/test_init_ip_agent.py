import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.init_ip_agent import install  # noqa: E402


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
