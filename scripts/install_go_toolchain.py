#!/usr/bin/env python3
"""Install the pinned official Go toolchain into the local product state."""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

GO_VERSION = "go1.26.5"
GO_FILES = {
    ("darwin", "amd64"): (
        "go1.26.5.darwin-amd64.tar.gz",
        "6231d8d3b8f5552ec6cbf6d685bdd5482e1e703214b120e89b3bf0d7bf1ef725",
    ),
    ("darwin", "arm64"): (
        "go1.26.5.darwin-arm64.tar.gz",
        "efb87ff28af9a188d0536ef5d42e63dd52ba8263cd7344a993cc48dd11dedb6a",
    ),
    ("linux", "amd64"): (
        "go1.26.5.linux-amd64.tar.gz",
        "5c2c3b16caefa1d968a94c1daca04a7ca301a496d9b086e17ad77bb81393f053",
    ),
    ("linux", "arm64"): (
        "go1.26.5.linux-arm64.tar.gz",
        "fe4789e92b1f33358680864bbe8704289e7bb5fc207d80623c308935bd696d49",
    ),
    ("windows", "amd64"): (
        "go1.26.5.windows-amd64.zip",
        "97e6b2a833b6d89f9ff17d25419ac0a7e3b482a044e9ab18cdef834bd834fd38",
    ),
    ("windows", "arm64"): (
        "go1.26.5.windows-arm64.zip",
        "f96ee46396d69f1e231c8d981ec6a70216238a646a1f2cd74aea0d0016bbc017",
    ),
}


@dataclass(frozen=True)
class GoArchive:
    os_name: str
    arch: str
    filename: str
    sha256: str

    @property
    def url(self) -> str:
        return f"https://go.dev/dl/{self.filename}"


def normalize_platform(
    *, platform_name: str | None = None, machine: str | None = None
) -> tuple[str, str]:
    platform_name = (platform_name or sys.platform).lower()
    machine = (machine or platform.machine()).lower()
    if platform_name.startswith("darwin"):
        os_name = "darwin"
    elif platform_name.startswith("linux"):
        os_name = "linux"
    elif platform_name.startswith(("win", "cygwin", "msys")):
        os_name = "windows"
    else:
        raise RuntimeError(f"unsupported operating system: {platform_name}")
    if machine in {"x86_64", "amd64"}:
        arch = "amd64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        raise RuntimeError(f"unsupported CPU architecture: {machine}")
    return os_name, arch


def resolve_archive(
    *, platform_name: str | None = None, machine: str | None = None
) -> GoArchive:
    os_name, arch = normalize_platform(platform_name=platform_name, machine=machine)
    filename, sha256 = GO_FILES[(os_name, arch)]
    return GoArchive(os_name, arch, filename, sha256)


def go_binary(root: Path, *, os_name: str | None = None) -> Path:
    os_name = os_name or normalize_platform()[0]
    suffix = ".exe" if os_name == "windows" else ""
    return root / ".deer-flow" / "toolchains" / "go" / "bin" / f"go{suffix}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(archive_path: Path, destination: Path) -> None:
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
    else:
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(destination, filter="data")


def install(root: Path) -> Path:
    archive = resolve_archive()
    binary = go_binary(root, os_name=archive.os_name)
    if binary.is_file():
        print(f"using existing local Go toolchain: {binary}")
        return binary

    toolchains = root / ".deer-flow" / "toolchains"
    downloads = toolchains / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive_path = downloads / archive.filename
    if not archive_path.is_file() or file_sha256(archive_path) != archive.sha256:
        partial = archive_path.with_suffix(archive_path.suffix + ".part")
        print(f"downloading {archive.url}")
        urllib.request.urlretrieve(archive.url, partial)
        actual = file_sha256(partial)
        if actual != archive.sha256:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"Go archive checksum mismatch: expected {archive.sha256}, got {actual}"
            )
        partial.replace(archive_path)

    target = toolchains / "go"
    if target.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target.rename(toolchains / f"go.backup-{stamp}")
    with tempfile.TemporaryDirectory(prefix="go-extract-", dir=toolchains) as temp:
        temp_path = Path(temp)
        _extract(archive_path, temp_path)
        extracted = temp_path / "go"
        if not (extracted / "bin").is_dir():
            raise RuntimeError("official Go archive did not contain go/bin")
        shutil.move(str(extracted), str(target))
    print(f"installed {GO_VERSION} at {target}")
    return binary


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-path", action="store_true")
    args = parser.parse_args()
    try:
        binary = install(root)
    except RuntimeError as exc:
        print(f"Go toolchain installation failed: {exc}", file=sys.stderr)
        return 1
    if args.print_path:
        print(binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
