import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.install_ffmpeg_toolchain import (  # noqa: E402
    FFMPEG_SHA256,
    FFMPEG_URLS,
    FFMPEG_VERSION,
    REQUIRED_CONFIGURATION,
    ffmpeg_binary,
    ffprobe_binary,
)


def test_ffmpeg_source_is_checksum_pinned_to_the_official_repository() -> None:
    assert FFMPEG_VERSION == "8.1.2"
    assert len(FFMPEG_SHA256) == 64
    assert FFMPEG_URLS == (
        "https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/refs/tags/n8.1.2",
    )


def test_ffmpeg_binaries_are_project_local(tmp_path: Path) -> None:
    expected = tmp_path / ".deer-flow" / "toolchains" / "ffmpeg" / "bin"

    assert ffmpeg_binary(tmp_path) == expected / "ffmpeg"
    assert ffprobe_binary(tmp_path) == expected / "ffprobe"


def test_ffmpeg_build_keeps_the_media_delivery_features() -> None:
    assert "--enable-libass" in REQUIRED_CONFIGURATION
    assert "--enable-libfribidi" in REQUIRED_CONFIGURATION
    assert "--enable-libharfbuzz" in REQUIRED_CONFIGURATION
    assert "--enable-libopenh264" in REQUIRED_CONFIGURATION
    assert "--enable-videotoolbox" in REQUIRED_CONFIGURATION
    assert all(
        "gpl" not in flag and "nonfree" not in flag for flag in REQUIRED_CONFIGURATION
    )
