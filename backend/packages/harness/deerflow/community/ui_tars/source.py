"""Verification for the pinned, selected UI-TARS upstream source."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_MANIFEST_NAME = "VENDORED_VERSION.json"
_INTEGRATION_NOTE = "DEERFLOW_INTEGRATION.md"


def default_vendored_root() -> Path:
    return Path(__file__).resolve().parents[6] / "third_party" / "bytedance" / "UI-TARS-desktop"


def _source_tree_digest(root: Path) -> tuple[int, str]:
    ignored = {_MANIFEST_NAME, _INTEGRATION_NOTE}
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name not in ignored)
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        file_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\0")
    return len(files), digest.hexdigest()


def verify_vendored_ui_tars(root: Path | None = None) -> dict[str, Any]:
    source_root = (root or default_vendored_root()).resolve()
    manifest_path = source_root / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise RuntimeError("UI-TARS vendored source manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("upstream_commit") != "c2ad42e3eb9b27830db41a3e6f51ca7179d9b168":
        raise RuntimeError("UI-TARS upstream commit pin is invalid")
    if manifest.get("package_version") != "1.2.3":
        raise RuntimeError("UI-TARS package version pin is invalid")
    if manifest.get("license") != "Apache-2.0" or not (source_root / "LICENSE").is_file():
        raise RuntimeError("UI-TARS Apache-2.0 license is missing")
    count, digest = _source_tree_digest(source_root)
    if count != manifest.get("source_file_count") or digest != manifest.get("source_tree_sha256"):
        raise RuntimeError("UI-TARS vendored source does not match its pinned tree digest")
    return {**manifest, "source_root": str(source_root), "verified": True}
