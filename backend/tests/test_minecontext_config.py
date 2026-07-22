from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.config.minecontext_config import MineContextConfig


def test_minecontext_defaults_fail_closed() -> None:
    config = MineContextConfig()
    assert config.enabled is False
    assert config.host == "127.0.0.1"
    assert config.default_retention_days == 30
    assert config.min_screen_interval_seconds == 60


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.8"])
def test_minecontext_rejects_non_loopback_bind(host: str) -> None:
    with pytest.raises(ValidationError, match="loopback"):
        MineContextConfig(host=host)
