import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.install_go_toolchain import (  # noqa: E402
    GO_VERSION,
    go_binary,
    normalize_platform,
    resolve_archive,
)


def test_platform_normalization_covers_customer_architectures() -> None:
    assert normalize_platform(platform_name="darwin", machine="x86_64") == (
        "darwin",
        "amd64",
    )
    assert normalize_platform(platform_name="linux", machine="aarch64") == (
        "linux",
        "arm64",
    )
    assert normalize_platform(platform_name="win32", machine="AMD64") == (
        "windows",
        "amd64",
    )


def test_archive_and_binary_are_pinned_per_platform(tmp_path: Path) -> None:
    archive = resolve_archive(platform_name="darwin", machine="x86_64")

    assert GO_VERSION == "go1.26.5"
    assert archive.filename == "go1.26.5.darwin-amd64.tar.gz"
    assert len(archive.sha256) == 64
    assert go_binary(tmp_path, os_name="darwin") == (
        tmp_path / ".deer-flow" / "toolchains" / "go" / "bin" / "go"
    )
    assert go_binary(tmp_path, os_name="windows").name == "go.exe"
