from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.install_dev_hooks import install_development_hooks


def test_source_archive_skips_repository_only_hooks(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    assert not install_development_hooks(tmp_path, run_command=fake_run)
    assert calls == []


def test_git_checkout_installs_pre_commit_hooks(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    calls: list[tuple[list[str], Path]] = []

    def fake_run(
        command: list[str],
        *,
        cwd: Path,
        **_kwargs,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd))
        return subprocess.CompletedProcess(command, 0)

    assert install_development_hooks(tmp_path, run_command=fake_run)
    assert calls == [
        (["uv", "tool", "install", "pre-commit"], tmp_path),
        (["pre-commit", "install", "--overwrite"], tmp_path),
    ]
