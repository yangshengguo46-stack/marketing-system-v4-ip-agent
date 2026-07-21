"""Douyin mini-app authorization-code and login-code exchanges."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

_ACCESS_TOKEN_URL = "https://open.douyin.com/oauth/access_token/"
_REFRESH_TOKEN_URL = "https://open.douyin.com/oauth/refresh_token/"
_CODE2SESSION_URL = "https://developer.toutiao.com/api/apps/v2/jscode2session"


class DouyinOAuthError(RuntimeError):
    """Sanitized provider failure that never embeds code, token, or secret values."""

    def __init__(self, *, category: str, provider_code: int | None, retryable: bool) -> None:
        super().__init__(f"Douyin authorization failed ({category}, provider_code={provider_code})")
        self.category = category
        self.provider_code = provider_code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class DouyinOAuthGrant:
    access_token: str
    refresh_token: str
    oauth_open_id: str
    expires_in: int
    refresh_expires_in: int
    scopes: list[str]


@dataclass(frozen=True, slots=True)
class DouyinMiniAppIdentity:
    open_id: str
    union_id: str | None


class DouyinMiniAppOAuthClient:
    """Server-side client for permission-ticket and ``tt.login`` exchanges."""

    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._client = client

    @property
    def app_id(self) -> str:
        """Public mini-app identifier safe to send to the mini-app frontend."""
        return self._app_id

    async def _post(self, url: str, **kwargs) -> dict:
        try:
            if self._client is not None:
                response = await self._client.post(url, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(url, **kwargs)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DouyinOAuthError(category="transient", provider_code=None, retryable=True) from exc
        if not isinstance(payload, dict):
            raise DouyinOAuthError(category="invalid_response", provider_code=None, retryable=False)
        return payload

    @staticmethod
    def _grant_from_payload(payload: dict) -> DouyinOAuthGrant:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DouyinOAuthError(category="invalid_response", provider_code=None, retryable=False)
        try:
            error_code = int(data.get("error_code", 0))
        except (TypeError, ValueError):
            error_code = -1
        if error_code:
            category = "reauthorization_required" if error_code in {10007, 10008, 10010} else "provider_rejected"
            raise DouyinOAuthError(category=category, provider_code=error_code, retryable=error_code == 10001)
        try:
            access_token = str(data["access_token"])
            refresh_token = str(data["refresh_token"])
            oauth_open_id = str(data["open_id"])
            expires_in = int(data["expires_in"])
            refresh_expires_in = int(data["refresh_expires_in"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DouyinOAuthError(category="invalid_response", provider_code=None, retryable=False) from exc
        if not access_token or not refresh_token or not oauth_open_id or expires_in <= 0 or refresh_expires_in <= 0:
            raise DouyinOAuthError(category="invalid_response", provider_code=None, retryable=False)
        scope = data.get("scope")
        scopes = [item.strip() for item in str(scope or "").split(",") if item.strip()]
        return DouyinOAuthGrant(
            access_token=access_token,
            refresh_token=refresh_token,
            oauth_open_id=oauth_open_id,
            expires_in=expires_in,
            refresh_expires_in=refresh_expires_in,
            scopes=scopes,
        )

    async def exchange_permission_ticket(self, ticket: str) -> DouyinOAuthGrant:
        payload = await self._post(
            _ACCESS_TOKEN_URL,
            data={
                "client_key": self._app_id,
                "client_secret": self._app_secret,
                "code": ticket,
                "grant_type": "authorization_code",
            },
        )
        return self._grant_from_payload(payload)

    async def refresh(self, refresh_token: str) -> DouyinOAuthGrant:
        payload = await self._post(
            _REFRESH_TOKEN_URL,
            data={
                "client_key": self._app_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return self._grant_from_payload(payload)

    async def exchange_login_code(self, login_code: str) -> DouyinMiniAppIdentity:
        payload = await self._post(
            _CODE2SESSION_URL,
            json={
                "appid": self._app_id,
                "secret": self._app_secret,
                "code": login_code,
            },
        )
        try:
            error_code = int(payload.get("err_no", -1))
        except (TypeError, ValueError):
            error_code = -1
        if error_code:
            raise DouyinOAuthError(
                category="provider_rejected",
                provider_code=error_code,
                retryable=error_code == -1,
            )
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("openid"):
            raise DouyinOAuthError(category="invalid_response", provider_code=None, retryable=False)
        return DouyinMiniAppIdentity(
            open_id=str(data["openid"]),
            union_id=str(data["unionid"]) if data.get("unionid") else None,
        )
