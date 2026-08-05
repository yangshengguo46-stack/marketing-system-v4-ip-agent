from __future__ import annotations

import asyncio

import pytest
import sqlalchemy as sa
from alembic import command as alembic_command
from sqlalchemy.ext.asyncio import create_async_engine

import deerflow.persistence.models  # noqa: F401
from deerflow.persistence.bootstrap import _get_alembic_config, _upgrade

PAID_CALL_FINAL_REVISION = "0026_personal_ip_paid_call_submission_recovery"
OPERATOR_CAP_REVISION = "0024_personal_ip_paid_call_operator_cap"


async def _tables(engine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: set(sa.inspect(sync).get_table_names()))


async def _columns(engine, table: str) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: {column["name"] for column in sa.inspect(sync).get_columns(table)})


async def _checks(engine, table: str) -> list[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda sync: [str(check.get("sqltext") or "") for check in sa.inspect(sync).get_check_constraints(table)])


async def _version(engine) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(sa.text("SELECT version_num FROM alembic_version"))
        return str(result.scalar_one())


async def _install_legacy_0023_scope(engine, *, with_row: bool = False) -> None:
    """Reproduce the pre-final test-profile shape already seen in the wild."""

    async with engine.begin() as connection:
        await connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL PRIMARY KEY)"))
        await connection.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0023_personal_ip_paid_call_execution_run')"))
        await connection.execute(
            sa.text("CREATE TABLE personal_ip_paid_call_scopes (id VARCHAR(64) NOT NULL PRIMARY KEY, maximum_amount_micros BIGINT NOT NULL, CONSTRAINT ck_personal_ip_paid_call_scopes_maximum_positive CHECK (maximum_amount_micros > 0))")
        )
        if with_row:
            await connection.execute(sa.text("INSERT INTO personal_ip_paid_call_scopes (id, maximum_amount_micros) VALUES ('legacy-row', 1)"))


@pytest.mark.asyncio
async def test_0022_through_0026_upgrade_paid_call_schema(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'paid-call.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, "0021_personal_ip_semantic_layer_retirement")
        assert {
            "personal_ip_paid_call_scopes",
            "personal_ip_paid_call_events",
        }.isdisjoint(await _tables(engine))

        await asyncio.to_thread(_upgrade, config, "0022_personal_ip_paid_call_admission")
        assert await _version(engine) == "0022_personal_ip_paid_call_admission"
        assert {
            "personal_ip_paid_call_scopes",
            "personal_ip_paid_call_events",
        } <= await _tables(engine)
        assert "run_id" in await _columns(engine, "personal_ip_paid_call_scopes")
        assert "origin_run_id" not in await _columns(engine, "personal_ip_paid_call_scopes")
        assert "execution_run_id" not in await _columns(engine, "personal_ip_paid_call_events")

        await asyncio.to_thread(_upgrade, config, PAID_CALL_FINAL_REVISION)
        assert await _version(engine) == PAID_CALL_FINAL_REVISION
        assert {
            "request_digest",
            "origin_run_id",
            "execution_run_id",
            "price_status",
            "maximum_amount_micros",
            "object_ref_label",
            "source_duration_millis",
            "expires_at",
            "admission_jti_hash",
            "server_name",
            "tool_name",
            "tool_args_sha256",
            "provider_request_sha256",
            "provider_task_status",
            "encrypted_provider_client_token",
            "provider_client_token_sha256",
            "encrypted_provider_submission_json",
            "provider_submission_sha256",
            "encrypted_provider_task_id",
            "provider_task_id_sha256",
            "provider_terminal_status",
            "encrypted_provider_terminal_json",
            "provider_terminal_sha256",
        } <= await _columns(engine, "personal_ip_paid_call_scopes")
        assert {
            "event_key",
            "event_digest",
            "request_digest",
            "event_type",
            "execution_run_id",
            "amount_micros",
            "payload_json",
        } <= await _columns(engine, "personal_ip_paid_call_events")
        assert any(
            "operator_capped" in expression
            for expression in await _checks(
                engine,
                "personal_ip_paid_call_scopes",
            )
        )
        assert any("provider_task" in expression for expression in await _checks(engine, "personal_ip_paid_call_events"))

        await asyncio.to_thread(
            alembic_command.downgrade,
            config,
            "0022_personal_ip_paid_call_admission",
        )
        assert await _version(engine) == "0022_personal_ip_paid_call_admission"
        assert "run_id" in await _columns(engine, "personal_ip_paid_call_scopes")
        assert "origin_run_id" not in await _columns(engine, "personal_ip_paid_call_scopes")
        assert "execution_run_id" not in await _columns(engine, "personal_ip_paid_call_events")

        await asyncio.to_thread(
            alembic_command.downgrade,
            config,
            "0021_personal_ip_semantic_layer_retirement",
        )
        assert await _version(engine) == "0021_personal_ip_semantic_layer_retirement"
        assert {
            "personal_ip_paid_call_scopes",
            "personal_ip_paid_call_events",
        }.isdisjoint(await _tables(engine))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0025_preserves_rows_and_0026_refuses_active_provider_tasks(
    tmp_path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'upgrade-with-row.db').as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(
            _upgrade,
            config,
            "0024_personal_ip_paid_call_operator_cap",
        )
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    INSERT INTO personal_ip_paid_call_scopes (
                        id, owner_user_id, request_key, scope_kind, thread_id,
                        origin_run_id, execution_run_id, server_name, tool_name,
                        tool_args_sha256, provider, capability, model, sku,
                        provider_label, capability_label, object_ref_label,
                        source_duration_millis, source_sha256, stage_digest,
                        provider_request_sha256, maximum_amount_micros, currency,
                        billing_basis, price_status, policy_version, price_version,
                        provider_input_attested, evidence_coverage, warning_code,
                        expires_at, request_digest, status, event_count,
                        reserved_amount_micros, settled_amount_micros,
                        admission_jti_hash, created_at, updated_at
                    ) VALUES (
                        :id, :owner, :request_key, 'run', :thread_id,
                        :origin_run_id, NULL, :server_name, :tool_name,
                        :tool_args_sha256, :provider, :capability, :model, :sku,
                        :provider_label, :capability_label, :object_ref_label,
                        8000, :source_sha256, :stage_digest,
                        :provider_request_sha256, 500000, 'CNY',
                        :billing_basis, 'quoted', :policy_version, :price_version,
                        0, 'partial', :warning_code,
                        :expires_at, :request_digest, 'requested', 1,
                        0, NULL, NULL, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": "paid-call-scope-existing",
                    "owner": "owner-existing",
                    "request_key": "request-existing",
                    "thread_id": "thread-existing",
                    "origin_run_id": "run-existing",
                    "server_name": "ip_evidence",
                    "tool_name": "inspect_reference_videos",
                    "tool_args_sha256": "a" * 64,
                    "provider": "volcengine-mediakit",
                    "capability": "asr",
                    "model": "mediakit-asr",
                    "sku": "asr-subtitles",
                    "provider_label": "MediaKit",
                    "capability_label": "ASR",
                    "object_ref_label": "reference-existing",
                    "source_sha256": "b" * 64,
                    "stage_digest": "c" * 64,
                    "provider_request_sha256": "d" * 64,
                    "billing_basis": "official quote",
                    "policy_version": "paid-call-v1",
                    "price_version": "price-v1",
                    "warning_code": "input_unattested",
                    "expires_at": "2026-08-04 00:00:00",
                    "request_digest": "e" * 64,
                    "created_at": "2026-08-03 00:00:00",
                    "updated_at": "2026-08-03 00:00:00",
                },
            )
        await asyncio.to_thread(
            _upgrade,
            config,
            "0025_personal_ip_paid_call_recovery",
        )
        async with engine.connect() as connection:
            row = (await connection.execute(sa.text("SELECT owner_user_id, provider_task_status, encrypted_provider_task_id FROM personal_ip_paid_call_scopes WHERE id = 'paid-call-scope-existing'"))).one()
        assert tuple(row) == ("owner-existing", None, None)

        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    UPDATE personal_ip_paid_call_scopes
                    SET provider_task_status = 'submitting',
                        encrypted_provider_client_token = 'encrypted-token',
                        provider_client_token_sha256 = :token_sha256
                    WHERE id = 'paid-call-scope-existing'
                    """
                ),
                {"token_sha256": "f" * 64},
            )
        with pytest.raises(RuntimeError, match="export and retire those task records"):
            await asyncio.to_thread(_upgrade, config, PAID_CALL_FINAL_REVISION)
        assert await _version(engine) == "0025_personal_ip_paid_call_recovery"

        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    UPDATE personal_ip_paid_call_scopes
                    SET provider_task_status = NULL,
                        encrypted_provider_client_token = NULL,
                        provider_client_token_sha256 = NULL
                    WHERE id = 'paid-call-scope-existing'
                    """
                )
            )
        await asyncio.to_thread(_upgrade, config, PAID_CALL_FINAL_REVISION)
        assert await _version(engine) == PAID_CALL_FINAL_REVISION
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    sa.text(
                        """
                        SELECT encrypted_provider_submission_json,
                               provider_submission_sha256
                        FROM personal_ip_paid_call_scopes
                        WHERE id = 'paid-call-scope-existing'
                        """
                    )
                )
            ).one()
        assert tuple(row) == (None, None)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0024_upgrades_empty_legacy_test_profile_without_reset(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'legacy-empty.db').as_posix()}")
    try:
        await _install_legacy_0023_scope(engine)
        config = _get_alembic_config(engine)
        await asyncio.to_thread(_upgrade, config, OPERATOR_CAP_REVISION)

        assert await _version(engine) == OPERATOR_CAP_REVISION
        assert {
            "server_name",
            "tool_name",
            "tool_args_sha256",
            "provider_request_sha256",
            "price_status",
        } <= await _columns(engine, "personal_ip_paid_call_scopes")
        assert any("operator_capped" in expression for expression in await _checks(engine, "personal_ip_paid_call_scopes"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_0024_refuses_to_guess_missing_immutable_fields_for_legacy_rows(
    tmp_path,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'legacy-nonempty.db').as_posix()}")
    try:
        await _install_legacy_0023_scope(engine, with_row=True)
        config = _get_alembic_config(engine)
        with pytest.raises(RuntimeError, match="Owner backup"):
            await asyncio.to_thread(_upgrade, config, OPERATOR_CAP_REVISION)

        assert await _version(engine) == "0023_personal_ip_paid_call_execution_run"
    finally:
        await engine.dispose()
