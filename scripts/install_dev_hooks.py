#!/usr/bin/env python3
"""Install repository-only developer hooks without breaking source archives."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

RunCommand = Callable[..., subprocess.CompletedProcess[str]]


def install_development_hooks(
    project_root: Path,
    *,
    run_command: RunCommand = subprocess.run,
) -> bool:
    project_root = project_root.resolve()
    if not (project_root / ".git").exists():
        print("Skipping pre-commit hooks: this source archive has no Git metadata")
        return False

    run_command(
        ["uv", "tool", "install", "pre-commit"],
        cwd=project_root,
        check=True,
        text=True,
    )
    run_command(
        ["pre-commit", "install", "--overwrite"],
        cwd=project_root,
        check=True,
        text=True,
    )
    return True


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    try:
        install_development_hooks(project_root)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Developer hook installation failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
