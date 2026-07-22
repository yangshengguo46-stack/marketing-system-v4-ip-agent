"""Optional source-auditable UI-TARS desktop operator integration."""

from .client import UITarsOperatorClient, UITarsOperatorError
from .permissions import diagnose_desktop_permissions
from .source import verify_vendored_ui_tars

__all__ = [
    "UITarsOperatorClient",
    "UITarsOperatorError",
    "diagnose_desktop_permissions",
    "verify_vendored_ui_tars",
]
