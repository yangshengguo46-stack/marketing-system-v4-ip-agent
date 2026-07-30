#!/usr/bin/env python3
"""Install and verify the exact source-owned HyperFrames renderer runtime."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _node_major(node: str) -> int:
    result = subprocess.run(
        [node, "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    value = result.stdout.strip().lstrip("v").split(".", 1)[0]
    if not value.isdigit():
        raise RuntimeError("Node.js returned an invalid version")
    return int(value)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    renderer_root = project_root / "product" / "video-renderers"
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        print("Node.js and npm are required", file=sys.stderr)
        return 1
    if _node_major(node) < 22:
        print("HyperFrames requires Node.js 22 or newer", file=sys.stderr)
        return 1
    subprocess.run(
        [npm, "ci", "--ignore-scripts"],
        cwd=renderer_root,
        check=True,
    )
    subprocess.run(
        [node, str(renderer_root / "verify-pins.mjs")],
        cwd=renderer_root,
        check=True,
    )
    print(
        "HyperFrames and Remotion source renderers installed with exact dependency pins"
    )
    print(
        "Remotion MVP use is enabled; confirm license eligibility before customer distribution"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
