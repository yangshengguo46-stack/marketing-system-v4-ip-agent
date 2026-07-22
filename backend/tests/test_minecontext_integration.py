from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from deerflow.config.minecontext_config import MineContextConfig
from deerflow.personal_ip.minecontext import (
    MINECONTEXT_EVIDENCE_SCHEMA_VERSION,
    MINECONTEXT_UPSTREAM_COMMIT,
    MineContextConsent,
    MineContextService,
    seal_minecontext_results,
    verify_vendored_minecontext,
)


class _FakeProcess:
    pid = 1234

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.returncode = -9


def _service(tmp_path: Path, *, enabled: bool, launched: list[dict]) -> MineContextService:
    runtime = tmp_path / "runtime-python"
    runtime.write_text("fixture", encoding="utf-8")

    def launch(**kwargs):
        launched.append(kwargs)
        return _FakeProcess()

    return MineContextService(
        config=MineContextConfig(enabled=enabled, runtime_python=str(runtime)),
        paths=SimpleNamespace(user_dir=lambda owner: tmp_path / "users" / owner),
        project_root=tmp_path,
        source_verifier=lambda _root: {"commit": MINECONTEXT_UPSTREAM_COMMIT},
        process_factory=launch,
        health_probe=lambda *_args, **_kwargs: True,
    )


def _manual_consent(**updates) -> MineContextConsent:
    values = {
        "scopes": ["projects", "work_activity"],
        "purposes": ["persona_modeling", "hllm_user_profile", "preflight"],
        "retention_days": 30,
        "collection_mode": "manual",
    }
    values.update(updates)
    return MineContextConsent(**values)


def test_default_disabled_requires_operator_and_owner_authorization(tmp_path: Path) -> None:
    launched: list[dict] = []
    service = _service(tmp_path, enabled=False, launched=launched)

    status = service.status("owner-a")
    assert status["operator_enabled"] is False
    assert status["authorized"] is False

    service.authorize("owner-a", _manual_consent())
    with pytest.raises(RuntimeError, match="disabled by the operator"):
        service.start("owner-a")
    assert launched == []


def test_manual_mode_never_enables_screenshot_or_file_capture(tmp_path: Path) -> None:
    launched: list[dict] = []
    service = _service(tmp_path, enabled=True, launched=launched)
    service.authorize("owner-a", _manual_consent())

    status = service.start("owner-a")

    assert status["running"] is True
    config_path = Path(launched[0]["command"][5])
    generated = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert generated["capture"]["screenshot"]["enabled"] is False
    assert generated["capture"]["folder_monitor"]["enabled"] is False
    assert generated["capture"]["file_monitor"]["enabled"] is False
    assert generated["consumption"]["enabled"] is False
    assert generated["content_generation"]["activity"]["enabled"] is False
    assert generated["completion"]["enabled"] is False
    assert generated["api_auth"]["enabled"] is True
    assert generated["web"]["host"] == "127.0.0.1"


def test_continuous_capture_requires_specific_scope_and_confirmation(tmp_path: Path) -> None:
    watched = tmp_path / "fixture-documents"
    watched.mkdir()
    launched: list[dict] = []
    service = _service(tmp_path, enabled=True, launched=launched)

    with pytest.raises(ValueError, match="continuous screen capture confirmation"):
        service.authorize(
            "owner-a",
            _manual_consent(
                scopes=["screen"],
                collection_mode="bounded_continuous",
                screen_targets=["all_displays"],
            ),
        )

    service.authorize(
        "owner-a",
        _manual_consent(
            scopes=["screen", "files"],
            collection_mode="bounded_continuous",
            continuous_screen_capture_confirmed=True,
            screen_targets=["all_displays"],
            watched_paths=[str(watched)],
            screen_capture_interval_seconds=120,
        ),
    )
    service.start("owner-a")

    generated = yaml.safe_load(Path(launched[0]["command"][5]).read_text(encoding="utf-8"))
    assert generated["capture"]["screenshot"] == {
        "enabled": True,
        "capture_interval": 120,
        "storage_path": str(tmp_path / "users" / "owner-a" / "minecontext" / "runtime" / "screenshots"),
    }
    folder = generated["capture"]["folder_monitor"]
    assert folder["enabled"] is True
    assert folder["watch_folder_paths"] == [str(watched.resolve())]
    assert folder["recursive"] is False
    assert folder["initial_scan"] is False


def test_boundary_seals_only_minimized_redacted_summary() -> None:
    observed_at = datetime(2026, 7, 22, 5, 0, tzinfo=UTC)
    records = seal_minecontext_results(
        [
            {
                "context": {
                    "id": "upstream-1",
                    "content_text": "complete private screen dump",
                    "content_path": "/Users/alice/secret.txt",
                    "embedding": [0.1, 0.2],
                    "extracted_data": {
                        "title": "Roadmap for alice@example.com",
                        "summary": "Authorization: Bearer secret-token and password=hunter2; ship milestone",
                        "context_type": "activity",
                        "keywords": ["project", "api_key=abcd", "ship"],
                    },
                    "properties": {"create_time": observed_at.isoformat()},
                },
                "score": 0.92,
            }
        ],
        source_kind="work_activity",
        observed_at=observed_at,
    )

    assert len(records) == 1
    record = records[0]
    serialized = json.dumps(record, ensure_ascii=False)
    assert record["schema_version"] == MINECONTEXT_EVIDENCE_SCHEMA_VERSION
    assert record["source"]["observed_at"] == observed_at.isoformat()
    assert record["coverage"]["completeness"] == "partial"
    assert record["privacy"]["raw_content_included"] is False
    assert "secret-token" not in serialized
    assert "hunter2" not in serialized
    assert "alice@example.com" not in serialized
    assert "/Users/alice" not in serialized
    assert "embedding" not in serialized
    assert record["privacy"]["redaction_count"] >= 3


def test_evidence_is_owner_isolated_revocable_and_deletable(tmp_path: Path) -> None:
    service = _service(tmp_path, enabled=True, launched=[])
    service.authorize("owner-a", _manual_consent())
    service.authorize("owner-b", _manual_consent())
    evidence = seal_minecontext_results(
        [{"context": {"id": "ctx", "extracted_data": {"title": "A", "summary": "B", "context_type": "activity", "keywords": []}, "properties": {}}}],
        source_kind="work_activity",
    )[0]
    service.store_evidence("owner-a", [evidence])

    assert len(service.read_evidence("owner-a", purpose="preflight")) == 1
    assert service.read_evidence("owner-b", purpose="preflight") == []
    service.revoke("owner-a")
    with pytest.raises(PermissionError, match="authorization is not active"):
        service.read_evidence("owner-a", purpose="preflight")

    deleted = service.clear("owner-a", scope="evidence")
    assert deleted["deleted_evidence_records"] == 1


def test_retention_prunes_expired_records(tmp_path: Path) -> None:
    service = _service(tmp_path, enabled=True, launched=[])
    service.authorize("owner-a", _manual_consent(retention_days=1))
    expired_at = datetime.now(UTC) - timedelta(days=2)
    evidence = seal_minecontext_results(
        [{"context": {"id": "old", "extracted_data": {"title": "old", "summary": "old", "context_type": "activity", "keywords": []}, "properties": {"create_time": expired_at.isoformat()}}}],
        source_kind="work_activity",
        observed_at=expired_at,
    )[0]
    service.store_evidence("owner-a", [evidence])

    assert service.read_evidence("owner-a", purpose="preflight") == []


def test_vendored_source_manifest_is_pinned_and_complete() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    manifest = verify_vendored_minecontext(repo_root)

    assert manifest["commit"] == MINECONTEXT_UPSTREAM_COMMIT
    assert manifest["license"] == "Apache-2.0"
    assert manifest["source_mode"] == "full-upstream-source"
