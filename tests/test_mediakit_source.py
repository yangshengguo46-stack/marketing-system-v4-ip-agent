import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.mediakit_source import (  # noqa: E402
    MEDIAKIT_COMMIT,
    binary_path,
    media_environment,
    validate_source,
)


def test_vendored_mediakit_source_is_complete_and_has_no_prebuilt_binary() -> None:
    root = Path(__file__).resolve().parents[1]

    source = validate_source(root)

    assert MEDIAKIT_COMMIT == "279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0"
    assert (source / "go.mod").is_file()
    assert not (source / "mediakit").exists()


def test_binary_path_is_project_local_and_platform_specific(tmp_path: Path) -> None:
    assert binary_path(tmp_path, platform_name="darwin") == (
        tmp_path / ".deer-flow" / "bin" / "mediakit-cli"
    )
    assert binary_path(tmp_path, platform_name="win32") == (
        tmp_path / ".deer-flow" / "bin" / "mediakit-cli.exe"
    )


def test_media_environment_prefers_project_local_binaries(tmp_path: Path) -> None:
    path = media_environment(tmp_path)["PATH"].split(os.pathsep)

    assert path[:2] == [
        str(tmp_path / ".deer-flow" / "toolchains" / "ffmpeg" / "bin"),
        str(tmp_path / ".deer-flow" / "bin"),
    ]
