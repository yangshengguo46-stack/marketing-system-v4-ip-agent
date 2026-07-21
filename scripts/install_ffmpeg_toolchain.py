#!/usr/bin/env python3
"""Build a pinned, subtitle-capable FFmpeg in the project-local toolchain."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

FFMPEG_VERSION = "8.1.2"
FFMPEG_ARCHIVE = f"FFmpeg-n{FFMPEG_VERSION}.tar.gz"
FFMPEG_SHA256 = "9fd092511605bbebafe095ea6d38d9e40f34d12f7386e1258372df8be0576eb7"
FFMPEG_URLS = (
    f"https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n{FFMPEG_VERSION}",
)
BREW_FORMULAE = ("pkgconf", "libass", "lame", "openh264", "nasm")
BREW_PKGCONFIG_FORMULAE = (
    "libass",
    "freetype",
    "fontconfig",
    "fribidi",
    "harfbuzz",
    "lame",
    "openh264",
)
REQUIRED_CONFIGURATION = (
    "--enable-libass",
    "--enable-libfreetype",
    "--enable-libfontconfig",
    "--enable-libfribidi",
    "--enable-libharfbuzz",
    "--enable-libmp3lame",
    "--enable-libopenh264",
    "--enable-videotoolbox",
    "--enable-audiotoolbox",
)


def toolchain_root(root: Path) -> Path:
    return root / ".deer-flow" / "toolchains" / "ffmpeg"


def ffmpeg_binary(root: Path) -> Path:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return toolchain_root(root) / "bin" / f"ffmpeg{suffix}"


def ffprobe_binary(root: Path) -> Path:
    suffix = ".exe" if sys.platform.startswith("win") else ""
    return toolchain_root(root) / "bin" / f"ffprobe{suffix}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_ready(root: Path) -> bool:
    ffmpeg = ffmpeg_binary(root)
    ffprobe = ffprobe_binary(root)
    if not ffmpeg.is_file() or not ffprobe.is_file():
        return False
    try:
        result = subprocess.run(
            [str(ffmpeg), "-version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    return f"ffmpeg version {FFMPEG_VERSION}" in first_line and all(
        flag in result.stdout for flag in REQUIRED_CONFIGURATION
    )


def _download_with_resume(url: str, destination: Path, *, attempts: int = 10) -> None:
    partial = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, attempts + 1):
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(
            url,
            headers={"Range": f"bytes={offset}-"} if offset else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                resumable = offset > 0 and getattr(response, "status", None) == 206
                mode = "ab" if resumable else "wb"
                with partial.open(mode) as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
            partial.replace(destination)
            return
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            if attempt == attempts:
                raise RuntimeError(
                    f"download failed after {attempts} attempts: {url}: {exc}"
                ) from exc
            print(f"download interrupted; retrying ({attempt}/{attempts})")
            time.sleep(min(attempt, 5))


def _verified_archive(root: Path) -> Path:
    downloads = root / ".deer-flow" / "toolchains" / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / FFMPEG_ARCHIVE
    if archive.is_file() and file_sha256(archive) == FFMPEG_SHA256:
        return archive
    if archive.exists():
        archive.rename(archive.with_suffix(archive.suffix + ".invalid"))
    errors: list[str] = []
    for url in FFMPEG_URLS:
        try:
            print(f"downloading official FFmpeg {FFMPEG_VERSION}: {url}")
            _download_with_resume(url, archive)
            actual = file_sha256(archive)
            if actual != FFMPEG_SHA256:
                raise RuntimeError(
                    f"checksum mismatch: expected {FFMPEG_SHA256}, got {actual}"
                )
            return archive
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def _brew_prefix(brew: str, formula: str | None = None) -> Path:
    command = [brew, "--prefix"]
    if formula:
        command.append(formula)
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return Path(result.stdout.strip())


def _prepare_macos_dependencies() -> tuple[Path, dict[str, str]]:
    brew = shutil.which("brew")
    if brew is None:
        raise RuntimeError("Homebrew is required for the macOS FFmpeg source build")
    env = dict(os.environ)
    env.setdefault("HOMEBREW_NO_AUTO_UPDATE", "1")
    env.setdefault("HOMEBREW_NO_INSTALL_CLEANUP", "1")
    subprocess.run([brew, "install", *BREW_FORMULAE], check=True, env=env)
    brew_root = _brew_prefix(brew)
    pkgconfig_paths: list[str] = []
    for formula in BREW_PKGCONFIG_FORMULAE:
        prefix = _brew_prefix(brew, formula)
        for candidate in (prefix / "lib" / "pkgconfig", prefix / "share" / "pkgconfig"):
            if candidate.is_dir():
                pkgconfig_paths.append(str(candidate))
    existing = env.get("PKG_CONFIG_PATH")
    if existing:
        pkgconfig_paths.append(existing)
    env["PKG_CONFIG_PATH"] = os.pathsep.join(pkgconfig_paths)
    return brew_root, env


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path.rename(path.with_name(f"{path.name}.backup-{stamp}"))


def install(root: Path, *, force: bool = False) -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError(
            "the source-built FFmpeg installer currently supports macOS; "
            "Linux and Windows release packages must provide their platform build"
        )
    if not force and is_ready(root):
        binary = ffmpeg_binary(root)
        print(f"using existing project-local FFmpeg: {binary}")
        return binary

    archive = _verified_archive(root)
    brew_root, env = _prepare_macos_dependencies()
    toolchains = root / ".deer-flow" / "toolchains"
    stage = toolchains / "ffmpeg.next"
    _backup(stage)
    stage.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="ffmpeg-build-", dir=toolchains) as temp:
        build_parent = Path(temp)
        with tarfile.open(archive, "r:gz") as source_archive:
            source_archive.extractall(build_parent, filter="data")
        source = build_parent / f"FFmpeg-n{FFMPEG_VERSION}"
        if not (source / "configure").is_file():
            raise RuntimeError("official FFmpeg archive did not contain configure")
        # Codeload archives contain RELEASE but no VERSION. Without this file,
        # FFmpeg can inherit the enclosing product repository's Git revision.
        (source / "VERSION").write_text(f"{FFMPEG_VERSION}\n", encoding="utf-8")
        configure = [
            str(source / "configure"),
            f"--prefix={stage}",
            "--disable-debug",
            "--disable-doc",
            "--disable-htmlpages",
            "--disable-manpages",
            "--disable-podpages",
            "--disable-txtpages",
            *REQUIRED_CONFIGURATION,
            f"--extra-cflags=-I{brew_root / 'include'}",
            f"--extra-ldflags=-L{brew_root / 'lib'}",
        ]
        subprocess.run(configure, cwd=source, env=env, check=True)
        jobs = str(max(1, min(os.cpu_count() or 2, 8)))
        subprocess.run(["make", f"-j{jobs}"], cwd=source, env=env, check=True)
        subprocess.run(["make", "install"], cwd=source, env=env, check=True)

    installed = stage / "bin" / "ffmpeg"
    if not installed.is_file():
        raise RuntimeError("FFmpeg build completed without an ffmpeg executable")
    target = toolchain_root(root)
    _backup(target)
    stage.rename(target)
    if not is_ready(root):
        raise RuntimeError(
            "installed FFmpeg did not pass the required capability check"
        )
    print(f"installed FFmpeg {FFMPEG_VERSION} at {target}")
    return ffmpeg_binary(root)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--print-path", action="store_true")
    args = parser.parse_args()
    try:
        binary = install(root, force=args.force)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"FFmpeg toolchain installation failed: {exc}", file=sys.stderr)
        return 1
    if args.print_path:
        print(binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
