#!/usr/bin/env python3
"""Verify, install and diagnose MineContext from the pinned vendored source."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

MINECONTEXT_COMMIT = "171c7a9ea8091e326ddcf0f10718aa1b58c83c65"
SOURCE_RELATIVE_PATH = Path("third_party/volcengine/MineContext")
CHECKSUMS = {
    "license_sha256": "LICENSE",
    "pyproject_sha256": "pyproject.toml",
    "cli_sha256": "opencontext/cli.py",
    "context_operations_sha256": "opencontext/server/context_operations.py",
}
REQUIRED = (
    "LICENSE",
    "NOTICE",
    "README.md",
    "UPSTREAM_FILES.sha256",
    "VENDORED_VERSION.json",
    "pyproject.toml",
    "opencontext/cli.py",
    "opencontext/server/context_operations.py",
)


def source_dir(root: Path) -> Path:
    return root.resolve() / SOURCE_RELATIVE_PATH


def runtime_python(root: Path) -> Path:
    suffix = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return root.resolve() / ".deer-flow" / "toolchains" / "minecontext" / suffix


def runtime_python_request(root: Path) -> str:
    version_file = root.resolve() / "backend" / ".python-version"
    requested = (
        version_file.read_text(encoding="utf-8").strip()
        if version_file.is_file()
        else "3.12"
    )
    if requested not in {"3.12", "3.13"}:
        raise RuntimeError(
            "MineContext runtime requires the repository's supported Python 3.12 or 3.13"
        )
    return requested


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source(root: Path) -> dict[str, Any]:
    source = source_dir(root)
    missing = [relative for relative in REQUIRED if not (source / relative).is_file()]
    if missing:
        raise RuntimeError(
            f"vendored MineContext source is incomplete: {', '.join(missing)}"
        )
    manifest = json.loads(
        (source / "VENDORED_VERSION.json").read_text(encoding="utf-8")
    )
    expected = {
        "commit": MINECONTEXT_COMMIT,
        "license": "Apache-2.0",
        "source_mode": "full-upstream-source",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RuntimeError(
                f"vendored MineContext {key} does not match the pinned source"
            )
    for key, relative in CHECKSUMS.items():
        if manifest.get(key) != _sha256(source / relative):
            raise RuntimeError(f"vendored MineContext checksum mismatch: {relative}")
    file_manifest_path = source / "UPSTREAM_FILES.sha256"
    if manifest.get("upstream_file_manifest_sha256") != _sha256(file_manifest_path):
        raise RuntimeError(
            "vendored MineContext full-source manifest checksum mismatch"
        )
    entries = file_manifest_path.read_text(encoding="utf-8").splitlines()
    if len(entries) != manifest.get("upstream_tracked_file_count"):
        raise RuntimeError("vendored MineContext full-source file count mismatch")
    for entry in entries:
        try:
            expected_digest, relative = entry.split("  ", 1)
        except ValueError as exc:
            raise RuntimeError(
                "vendored MineContext full-source manifest is invalid"
            ) from exc
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError(
                "vendored MineContext full-source manifest contains an unsafe path"
            )
        source_path = source / relative_path
        if not source_path.is_file() or _sha256(source_path) != expected_digest:
            raise RuntimeError(
                f"vendored MineContext upstream file mismatch: {relative}"
            )
    binary_magics = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf")
    for path in source.rglob("*"):
        if path.is_file() and path.suffix.lower() in {
            "",
            ".exe",
            ".dll",
            ".dylib",
            ".so",
        }:
            with path.open("rb") as candidate:
                if candidate.read(4).startswith(binary_magics):
                    raise RuntimeError(
                        "vendored MineContext contains an unexpected executable binary"
                    )
    return manifest


def install(root: Path) -> Path:
    validate_source(root)
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError(
            "uv is required; install it before running `make minecontext-install`"
        )
    environment = dict(os.environ)
    environment.setdefault("UV_LINK_MODE", "copy")
    venv = runtime_python(root).parent.parent
    venv.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [uv, "venv", "--clear", "--python", runtime_python_request(root), str(venv)],
        check=True,
        env=environment,
    )
    # Editable installation keeps the executable runtime tied to the exact
    # source tree whose checksums and license ship in the package.
    subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(runtime_python(root)),
            "--editable",
            str(source_dir(root)),
        ],
        check=True,
        env=environment,
    )
    return runtime_python(root)


def doctor(root: Path) -> None:
    manifest = validate_source(root)
    python = runtime_python(root)
    if not python.is_file():
        raise RuntimeError(
            "MineContext runtime is not installed; run `make minecontext-install`"
        )
    probe = "import pathlib, opencontext; print(pathlib.Path(opencontext.__file__).resolve())"
    completed = subprocess.run(
        [str(python), "-B", "-c", probe], check=True, capture_output=True, text=True
    )
    module_path = Path(completed.stdout.strip()).resolve()
    if source_dir(root) not in module_path.parents:
        raise RuntimeError(
            "MineContext runtime is not linked to the pinned vendored source"
        )
    print("MineContext source and runtime: verified")
    print(f"  commit: {manifest['commit']}")
    print("  license: Apache-2.0")
    print("  capture: default-off; each owner must explicitly enable it in Settings")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "install", "doctor", "path"))
    args = parser.parse_args()
    try:
        if args.command == "verify":
            manifest = validate_source(root)
            print("MineContext source: verified")
            print(f"  commit: {manifest['commit']}")
        elif args.command == "install":
            print(f"MineContext runtime installed: {install(root)}")
        elif args.command == "doctor":
            doctor(root)
        else:
            validate_source(root)
            print(runtime_python(root))
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        print(f"MineContext source command failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
