from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.package_ip_agent import (
    REQUIRED_PACKAGE_PATHS,
    build_source_package,
    smoke_test_source_package,
    verify_source_package,
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _source_repo(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    real_root = Path(__file__).resolve().parents[1]
    shutil.copytree(
        real_root / "third_party" / "volcengine" / "MineContext",
        root / "third_party" / "volcengine" / "MineContext",
    )
    for relative in REQUIRED_PACKAGE_PATHS:
        if relative.startswith("third_party/volcengine/MineContext/"):
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative in {"scripts/init_ip_agent.py", "scripts/minecontext_source.py"}:
            path.write_bytes((real_root / relative).read_bytes())
        else:
            path.write_text("source\n", encoding="utf-8")
    extra = root / "backend" / "packages" / "harness" / "deerflow" / "personal_ip" / "module.py"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "package-test@example.invalid")
    _git(root, "config", "user.name", "Package Test")
    _git(root, "add", ".")
    _git(root, "add", "-f", "third_party/volcengine/MineContext")
    _git(root, "commit", "-m", "source")
    return root


def test_source_package_is_deterministic_verified_and_smoke_installable(tmp_path) -> None:
    root = _source_repo(tmp_path)
    (root / ".env").write_text("SECRET=must-not-ship\n", encoding="utf-8")
    output_one = tmp_path / "one.tar.gz"
    output_two = tmp_path / "two.tar.gz"

    build_source_package(root, output_one)
    build_source_package(root, output_two)
    manifest = verify_source_package(output_one)
    smoke_test_source_package(output_one)

    assert hashlib.sha256(output_one.read_bytes()).digest() == hashlib.sha256(output_two.read_bytes()).digest()
    tracked_count = len(
        subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )
    assert manifest["file_count"] == tracked_count
    assert not any(item["path"] == ".env" for item in manifest["files"])
    checksum = output_one.with_suffix(output_one.suffix + ".sha256").read_text(encoding="utf-8")
    assert hashlib.sha256(output_one.read_bytes()).hexdigest() in checksum


def test_source_package_rejects_tracked_runtime_secret(tmp_path) -> None:
    root = _source_repo(tmp_path)
    (root / ".env").write_text("SECRET=tracked\n", encoding="utf-8")
    _git(root, "add", "-f", ".env")
    _git(root, "commit", "-m", "bad secret")

    with pytest.raises(RuntimeError, match="forbidden"):
        build_source_package(root, tmp_path / "bad.tar.gz")


def test_source_package_rejects_tracked_environment_variant(tmp_path) -> None:
    root = _source_repo(tmp_path)
    (root / ".env.local").write_text("SECRET=tracked\n", encoding="utf-8")
    _git(root, "add", "-f", ".env.local")
    _git(root, "commit", "-m", "bad local environment")

    with pytest.raises(RuntimeError, match="forbidden"):
        build_source_package(root, tmp_path / "bad-env-variant.tar.gz")


def test_source_package_rejects_dirty_tracked_tree(tmp_path) -> None:
    root = _source_repo(tmp_path)
    (root / "IP_AGENT.md").write_text("changed\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="tracked worktree changes"):
        build_source_package(root, tmp_path / "dirty.tar.gz")
