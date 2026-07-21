"""Gateway-only Douyin mini-app credential configuration."""

from __future__ import annotations

import os

from fastapi import HTTPException

from deerflow.personal_ip.douyin_oauth import DouyinMiniAppOAuthClient


def get_douyin_mini_app_oauth_client() -> DouyinMiniAppOAuthClient:
    """Build a server-side client without exposing the mini-app secret."""
    app_id = os.environ.get("DOUYIN_MINI_APP_ID", "").strip()
    app_secret = os.environ.get("DOUYIN_MINI_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise HTTPException(
            status_code=503,
            detail="Douyin mini-app authorization is not configured",
        )
    return DouyinMiniAppOAuthClient(app_id=app_id, app_secret=app_secret)
