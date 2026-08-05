from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.config.minecontext_config import MineContextConfig


def test_minecontext_defaults_require_explicit_owner_enablement() -> None:
    config = MineContextConfig()
    assert config.enabled is True
    assert config.auto_enable_new_owners is False
    assert config.host == "127.0.0.1"
    assert config.default_retention_days == 30
    assert config.min_screen_interval_seconds == 60
    assert config.start_timeout_seconds == 120
    assert config.fallback_api_key_env == "VOLCENGINE_API_KEY"


def test_minecontext_rejects_retired_automatic_owner_enablement() -> None:
    with pytest.raises(ValidationError, match="auto_enable_new_owners is retired"):
        MineContextConfig(auto_enable_new_owners=True)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.8"])
def test_minecontext_rejects_non_loopback_bind(host: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        MineContextConfig(host=host)
