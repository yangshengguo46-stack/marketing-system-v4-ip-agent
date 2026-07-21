#!/usr/bin/env python3
"""Install the distribution's default profile and local IP Agent safely."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def copy_file(source: Path, target: Path, *, force: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        return f"kept existing {target}"
    shutil.copy2(source, target)
    return f"installed {target}"


def install(root: Path, state_dir: Path, user_id: str, *, force: bool) -> list[str]:
    defaults = root / "product" / "defaults"
    messages = [
        copy_file(defaults / "USER.md", state_dir / "USER.md", force=force),
    ]
    source_agent = defaults / "agents" / "ip-agent"
    target_agent = state_dir / "users" / user_id / "agents" / "ip-agent"
    for filename in ("config.yaml", "SOUL.md"):
        messages.append(
            copy_file(source_agent / filename, target_agent / filename, force=force)
        )
    return messages


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=root / ".deer-flow",
        help="DeerFlow state directory (default: <repo>/.deer-flow)",
    )
    parser.add_argument("--user-id", default="default")
    parser.add_argument("--force", action="store_true", help="replace existing defaults")
    args = parser.parse_args()
    for message in install(root, args.state_dir.resolve(), args.user_id, force=args.force):
        print(message)


if __name__ == "__main__":
    main()
