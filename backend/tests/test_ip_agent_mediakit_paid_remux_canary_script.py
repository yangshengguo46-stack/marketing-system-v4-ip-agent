from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sqlite3
import stat
import sys
from pathlib import Path
from typing import Any

import pytest


def _load_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "ip_agent_mediakit_paid_remux_canary.py"
    spec = importlib.util.spec_from_file_location(
        "ip_agent_mediakit_paid_remux_canary",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


canary = _load_module()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def test_runtime_advertises_the_exact_operator_capped_remux_policy() -> None:
    assert canary._operator_capped_runtime_available() is True
    assert canary.paid_operator.MEDIAKIT_REMUX_OPERATOR_CAPPED_POLICY_VERSION == canary.OPERATOR_CAPPED_POLICY_VERSION == "evidence-managed-remux-operator-cap-v1"


def _fixture_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    execute_paid: bool,
    resume: bool = False,
) -> Any:
    acceptance = tmp_path / "acceptance"
    acceptance.mkdir(mode=0o700)
    source = tmp_path / "q157.mp4"
    source_bytes = b"sealed-q157-source"
    source.write_bytes(source_bytes)
    key = tmp_path / "mediakit-key"
    key.write_text("private-mediakit-key", encoding="utf-8")
    key.chmod(0o600)
    monkeypatch.setattr(canary, "ACCEPTANCE_ROOT", acceptance)
    monkeypatch.setattr(canary, "Q157_SOURCE", source)
    monkeypatch.setattr(canary, "Q157_SOURCE_SHA256", hashlib.sha256(source_bytes).hexdigest())
    monkeypatch.setattr(canary, "Q157_SOURCE_SIZE_BYTES", len(source_bytes))
    return canary.PaidRemuxCanaryOptions(
        execute_paid=execute_paid,
        resume=resume,
        attempt_id="q157-paid-remux-001",
        state_dir=acceptance / "q157-paid-remux-001",
        mediakit_key_file=key,
    )


def test_default_dry_run_is_zero_write_and_zero_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    options = _fixture_options(tmp_path, monkeypatch, execute_paid=False)
    monkeypatch.setattr(canary, "_parse_args", lambda _argv: options)

    def forbidden_read(_path: Path, *, read_value: bool):
        assert read_value is False
        return None

    monkeypatch.setattr(canary, "_validate_key_file", forbidden_read)
    assert canary.main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["provider_calls"] == 0
    assert output["database_writes"] == 0
    assert not options.state_dir.exists()


def test_paid_mode_fails_closed_before_state_or_credential_when_runtime_lacks_operator_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _fixture_options(tmp_path, monkeypatch, execute_paid=True)
    monkeypatch.setattr(canary, "_operator_capped_runtime_available", lambda: False)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("credential/state/provider boundary must not be crossed")

    monkeypatch.setattr(canary, "_validate_key_file", forbidden)
    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(canary.run_paid_canary(options, operator_runner=forbidden))
    assert error.value.code == "OPERATOR_CAPPED_REMUX_RUNTIME_NOT_SUPPORTED"
    assert not options.state_dir.exists()


def test_resume_never_creates_a_missing_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _fixture_options(
        tmp_path,
        monkeypatch,
        execute_paid=True,
        resume=True,
    )
    monkeypatch.setattr(canary, "_operator_capped_runtime_available", lambda: True)
    options.state_dir.mkdir(mode=0o700)
    (options.state_dir / "paid-recovery.key").write_text("x" * 64, encoding="utf-8")
    (options.state_dir / "paid-recovery.key").chmod(0o600)
    staged = options.state_dir / "q157-source.mp4"
    staged.write_bytes(canary.Q157_SOURCE.read_bytes())
    staged.chmod(0o600)
    canary._replace_private_json(
        options.state_dir / "state.json",
        canary._manifest_base(options),
    )
    database = options.state_dir / "db"
    database.mkdir(mode=0o700)

    provider_calls = 0

    async def forbidden(**_kwargs: Any) -> Any:
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider must not run")

    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(canary.run_paid_canary(options, operator_runner=forbidden))
    assert error.value.code == "RESUME_SCOPE_NOT_FOUND"
    assert provider_calls == 0
    db_path = database / "deerflow.db"
    with sqlite3.connect(db_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        count = connection.execute("SELECT COUNT(*) FROM personal_ip_paid_call_scopes").fetchone()[0]
    assert revision == "0029_personal_ip_final_artifacts"
    assert count == 0
    assert _mode(db_path) == 0o600


def test_private_state_contract_is_operator_capped_and_contains_no_raw_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _fixture_options(tmp_path, monkeypatch, execute_paid=True)
    options.state_dir.mkdir(mode=0o700)
    cipher_key = canary._new_cipher_key(options.state_dir / "paid-recovery.key")
    canary._stage_source(canary.Q157_SOURCE, options.state_dir / "q157-source.mp4")
    manifest = canary._manifest_base(options)
    canary._replace_private_json(options.state_dir / "state.json", manifest)

    assert manifest["price_status"] == "operator_capped"
    assert manifest["maximum_amount_micros"] == 20_000
    assert manifest["published_tariff_estimate_micros"] == 8_268
    assert manifest["published_price_formula_version"] == "mediakit-remux-output-milliseconds-tariff-v1"
    assert manifest["client_token_sha256"] == hashlib.sha256(canary._client_token(options).encode()).hexdigest()
    serialized = (options.state_dir / "state.json").read_text(encoding="utf-8")
    assert canary._client_token(options) not in serialized
    assert cipher_key not in serialized
    assert _mode(options.state_dir) == 0o700
    assert _mode(options.state_dir / "paid-recovery.key") == 0o600
    assert _mode(options.state_dir / "q157-source.mp4") == 0o600
    assert _mode(options.state_dir / "state.json") == 0o600


def test_existing_attempt_requires_explicit_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _fixture_options(tmp_path, monkeypatch, execute_paid=True)
    monkeypatch.setattr(canary, "_operator_capped_runtime_available", lambda: True)
    options.state_dir.mkdir(mode=0o700)

    with pytest.raises(canary.CanaryError) as error:
        asyncio.run(canary.run_paid_canary(options, operator_runner=lambda **_: None))
    assert error.value.code == "STATE_DIR_EXISTS_OR_UNWRITABLE"


def test_report_rejects_raw_runtime_url_even_from_a_receipt() -> None:
    with pytest.raises(canary.CanaryError) as error:
        canary._assert_secret_free(
            {"receipt": {"provider_value": "https://example.invalid/private"}},
            forbidden=(),
        )
    assert error.value.code == "REPORT_REDACTION_FAILED"


def test_public_tariff_estimate_is_ceil_of_millisecond_output_duration() -> None:
    assert canary._published_tariff_estimate_micros(60_000) == 7_000
    assert canary._published_tariff_estimate_micros(70_867) == 8_268
    with pytest.raises(canary.CanaryError, match="INVALID_SOURCE_DURATION"):
        canary._published_tariff_estimate_micros(0)
