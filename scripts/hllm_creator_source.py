#!/usr/bin/env python3
"""Verify the quarantined, pinned ByteDance HLLM research source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    source_root = (
        Path(__file__).resolve().parents[1] / "third_party" / "bytedance" / "HLLM"
    )
    manifest = json.loads(
        (source_root / "VENDORED_VERSION.json").read_text(encoding="utf-8")
    )
    required = (
        "LICENSE",
        "HLLM_CREATOR_README.md",
        "requirements.txt",
        "code/HLLM_Creator/HLLM_Creator.yaml",
        "code/REC/model/HLLM/hllm_creator.py",
        "code/REC/data/dataset/trainset.py",
        "reproduce/HLLM_Creator/HLLM_Creator.sh",
        "reproduce/HLLM_Creator/HLLM_Creator_eval.sh",
    )
    missing = [
        relative for relative in required if not (source_root / relative).is_file()
    ]
    if missing:
        raise RuntimeError(f"vendored HLLM source is incomplete: {', '.join(missing)}")
    if (
        manifest.get("source_mode") != "full-upstream-source"
        or manifest.get("license") != "Apache-2.0"
    ):
        raise RuntimeError("vendored HLLM manifest is not the approved research source")
    expected_hashes = {
        "license_sha256": source_root / "LICENSE",
        "creator_model_sha256": source_root / "code/REC/model/HLLM/hllm_creator.py",
    }
    for key, path in expected_hashes.items():
        if manifest.get(key) != _sha256(path):
            raise RuntimeError(f"vendored HLLM checksum mismatch: {path.name}")
    print("HLLM-Creator research source: verified")
    print(f"  upstream: {manifest['upstream']}")
    print(f"  commit: {manifest['commit']}")
    print("  runtime status: quarantined and disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
