#!/usr/bin/env python3
"""Verify the complete pinned ByteDance HLLM source in this distribution."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    harness_root = repo_root / "backend" / "packages" / "harness"
    sys.path.insert(0, str(harness_root))

    from deerflow.personal_ip.hllm_creator import verify_vendored_hllm

    manifest = verify_vendored_hllm(repo_root)
    print("HLLM-Creator source: verified")
    print(f"  upstream: {manifest['upstream']}")
    print(f"  commit: {manifest['commit']}")
    print(f"  license: {manifest['license']}")
    print("  model weights: optional external asset (not silently downloaded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
