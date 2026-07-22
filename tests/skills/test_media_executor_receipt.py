import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    REPO_ROOT
    / "skills"
    / "public"
    / "volcengine-stack"
    / "scripts"
    / "run_media_executor.py"
)
SPEC = importlib.util.spec_from_file_location("run_media_executor", SCRIPT)
media = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(media)


def test_media_executor_wraps_local_finishing_with_verified_receipt(tmp_path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"SOURCE")
    output = tmp_path / "delivery.mp4"
    receipt_file = tmp_path / "delivery.receipt.json"
    command = [
        sys.executable,
        "-c",
        "import json,sys; from pathlib import Path; Path(sys.argv[1]).write_bytes(b'FINISHED'); print(json.dumps({'request_id':'ffmpeg-local-1'}))",
        str(output),
    ]

    receipt = media.run_media_executor(
        command=command,
        input_files=[str(source)],
        output_files=[str(output)],
        receipt_file=str(receipt_file),
        provider="local",
        executor="ffmpeg",
        model="ffmpeg-project-toolchain",
        job_kind="final_mux",
    )

    stored = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert stored == receipt
    assert stored["status"] == "succeeded"
    assert stored["request_id"] == "ffmpeg-local-1"
    assert stored["outputs"][0]["size_bytes"] == len(b"FINISHED")
    assert len(stored["outputs"][0]["sha256"]) == 64
    assert stored["parameters"]["command"].startswith("python")
    assert "Path(sys.argv" not in receipt_file.read_text(encoding="utf-8")
    from deerflow.personal_ip.media_execution import normalize_media_execution_receipt

    normalized = normalize_media_execution_receipt(stored, entity_type="delivery")
    assert normalized["event_type"] == "media_processing_completed"


def test_media_executor_preserves_async_mediakit_task_id(tmp_path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"SOURCE")
    receipt_file = tmp_path / "mediakit.receipt.json"
    command = [
        sys.executable,
        "-c",
        "import json; print(json.dumps({'data':{'task_id':'mk-task-1'}}))",
    ]

    receipt = media.run_media_executor(
        command=command,
        input_files=[str(source)],
        output_files=[],
        receipt_file=str(receipt_file),
        provider="volcengine",
        executor="mediakit-cli",
        status_mode="running",
    )

    assert receipt["status"] == "running"
    assert receipt["task_id"] == "mk-task-1"
    assert receipt["completed_at"] is None
    assert receipt["outputs"] == []


def test_media_executor_fails_if_declared_output_is_missing(tmp_path) -> None:
    receipt_file = tmp_path / "failed.receipt.json"
    with pytest.raises(RuntimeError, match="did not create"):
        media.run_media_executor(
            command=[sys.executable, "-c", "print('{}')"],
            input_files=[],
            output_files=[str(tmp_path / "missing.mp4")],
            receipt_file=str(receipt_file),
            provider="local",
            executor="ffmpeg",
        )
    stored = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert stored["status"] == "failed"
    assert stored["failure"]["category"] == "missing_output"
