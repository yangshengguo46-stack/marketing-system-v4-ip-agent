from __future__ import annotations

import doctor


def test_null_models_is_reported_once_as_unconfigured(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("config_version: 5\nmodels:\n", encoding="utf-8")

    assert doctor.check_models_configured(config_path).status == "fail"
    assert doctor.check_llm_api_key(config_path) == []
    assert doctor.check_llm_auth(config_path) == []
    assert doctor.check_llm_package(config_path) == []
