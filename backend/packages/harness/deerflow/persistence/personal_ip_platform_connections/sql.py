"""SQL repository for account-level platform authorization connections."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import InvalidToken
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.channel_connections.sql import ChannelCredentialCipher
from deerflow.persistence.personal_ip_accounts.model import PersonalIPAccountRow
from deerflow.persistence.personal_ip_platform_connections.model import (
    PersonalIPPlatformConnectionRow,
    PersonalIPPlatformCredentialRow,
    PersonalIPPlatformOAuthStateRow,
)
from deerflow.utils.time import coerce_iso


class PersonalIPPlatformConnectionRepository:
    """Owner-scoped authorization vault attached to accounts, not conversations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        cipher: ChannelCredentialCipher,
    ) -> None:
        self._sf = session_factory
        self._cipher = cipher

    @staticmethod
    def _state_hash(state: str) -> str:
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    @staticmethod
    def _to_public_dict(row: PersonalIPPlatformConnectionRow) -> dict[str, Any]:
        data = row.to_dict()
        data["scopes"] = data.pop("scopes_json") or []
        for key in (
            "access_expires_at",
            "refresh_expires_at",
            "last_refreshed_at",
            "created_at",
            "updated_at",
        ):
            value = data.get(key)
            if isinstance(value, datetime):
                data[key] = coerce_iso(value)
        return data

    @staticmethod
    async def _require_account(
        session: AsyncSession,
        *,
        owner_user_id: str,
        account_id: str,
        platform: str,
    ) -> PersonalIPAccountRow:
        account = await session.get(PersonalIPAccountRow, account_id)
        if account is None or account.owner_user_id != owner_user_id or account.status != "active":
            raise ValueError("Personal-IP account not found")
        if account.platform != platform:
            raise ValueError("Personal-IP account platform does not match authorization platform")
        return account

    async def create_oauth_state(
        self,
        *,
        owner_user_id: str,
        account_id: str,
        platform: str,
        expires_at: datetime,
        requested_scopes: list[str] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        state = secrets.token_urlsafe(32)
        async with self._sf() as session:
            await self._require_account(
                session,
                owner_user_id=owner_user_id,
                account_id=account_id,
                platform=platform,
            )
            session.add(
                PersonalIPPlatformOAuthStateRow(
                    state_hash=self._state_hash(state),
                    owner_user_id=owner_user_id,
                    account_id=account_id,
                    platform=platform,
                    requested_scopes_json=list(requested_scopes or ["ma.video.bind"]),
                    expires_at=expires_at,
                    created_at=now,
                )
            )
            await session.commit()
        return {
            "state": state,
            "expires_at": coerce_iso(expires_at),
            "requested_scopes": list(requested_scopes or ["ma.video.bind"]),
        }

    async def consume_oauth_state(
        self,
        *,
        state: str,
        owner_user_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        now = now or datetime.now(UTC)
        state_hash = self._state_hash(state)
        async with self._sf() as session:
            row = await session.get(PersonalIPPlatformOAuthStateRow, state_hash)
            if row is None or row.owner_user_id != owner_user_id or row.consumed_at is not None:
                return None
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < now:
                return None
            result = await session.execute(
                update(PersonalIPPlatformOAuthStateRow)
                .where(
                    PersonalIPPlatformOAuthStateRow.state_hash == state_hash,
                    PersonalIPPlatformOAuthStateRow.owner_user_id == owner_user_id,
                    PersonalIPPlatformOAuthStateRow.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            )
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
            return {
                "account_id": row.account_id,
                "owner_user_id": row.owner_user_id,
                "platform": row.platform,
                "requested_scopes": list(row.requested_scopes_json or []),
            }

    async def store_grant(
        self,
        *,
        owner_user_id: str,
        account_id: str,
        platform: str,
        external_user_id: str,
        oauth_open_id: str | None,
        access_token: str,
        refresh_token: str,
        scopes: list[str],
        access_expires_at: datetime,
        refresh_expires_at: datetime,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        async with self._sf() as session:
            await self._require_account(
                session,
                owner_user_id=owner_user_id,
                account_id=account_id,
                platform=platform,
            )
            conflicting = (
                await session.execute(
                    select(PersonalIPPlatformConnectionRow.id).where(
                        PersonalIPPlatformConnectionRow.platform == platform,
                        PersonalIPPlatformConnectionRow.external_user_id == external_user_id,
                        PersonalIPPlatformConnectionRow.owner_user_id != owner_user_id,
                        PersonalIPPlatformConnectionRow.status != "revoked",
                    )
                )
            ).scalar_one_or_none()
            if conflicting is not None:
                raise ValueError("Platform identity is already connected to another owner")

            row = (
                await session.execute(
                    select(PersonalIPPlatformConnectionRow).where(
                        PersonalIPPlatformConnectionRow.owner_user_id == owner_user_id,
                        PersonalIPPlatformConnectionRow.account_id == account_id,
                        PersonalIPPlatformConnectionRow.platform == platform,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = PersonalIPPlatformConnectionRow(
                    id=f"platform-conn-{uuid.uuid4().hex}",
                    owner_user_id=owner_user_id,
                    account_id=account_id,
                    platform=platform,
                    status="connected",
                    external_user_id=external_user_id,
                    oauth_open_id=oauth_open_id,
                    scopes_json=list(scopes),
                    access_expires_at=access_expires_at,
                    refresh_expires_at=refresh_expires_at,
                    token_version=1,
                    last_refreshed_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                version = 1
            else:
                row.status = "connected"
                row.external_user_id = external_user_id
                row.oauth_open_id = oauth_open_id
                row.scopes_json = list(scopes)
                row.access_expires_at = access_expires_at
                row.refresh_expires_at = refresh_expires_at
                row.token_version += 1
                row.last_refreshed_at = now
                row.last_error_code = None
                row.updated_at = now
                version = row.token_version
                await session.execute(delete(PersonalIPPlatformCredentialRow).where(PersonalIPPlatformCredentialRow.connection_id == row.id))
            credential = PersonalIPPlatformCredentialRow(
                connection_id=row.id,
                encrypted_access_token=self._cipher.encrypt_text(access_token),
                encrypted_refresh_token=self._cipher.encrypt_text(refresh_token),
                version=version,
                updated_at=now,
            )
            session.add(credential)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("Platform identity is already connected") from exc
            await session.refresh(row)
            return self._to_public_dict(row)

    async def get(self, connection_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(PersonalIPPlatformConnectionRow, connection_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._to_public_dict(row)

    async def list(self, owner_user_id: str, *, include_revoked: bool = False) -> list[dict[str, Any]]:
        stmt = select(PersonalIPPlatformConnectionRow).where(PersonalIPPlatformConnectionRow.owner_user_id == owner_user_id)
        if not include_revoked:
            stmt = stmt.where(PersonalIPPlatformConnectionRow.status != "revoked")
        stmt = stmt.order_by(
            PersonalIPPlatformConnectionRow.updated_at.desc(),
            PersonalIPPlatformConnectionRow.id.desc(),
        )
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._to_public_dict(row) for row in rows]

    async def get_credentials(self, connection_id: str, *, owner_user_id: str) -> dict[str, str] | None:
        async with self._sf() as session:
            connection = await session.get(PersonalIPPlatformConnectionRow, connection_id)
            if connection is None or connection.owner_user_id != owner_user_id or connection.status == "revoked":
                return None
            credential = await session.get(PersonalIPPlatformCredentialRow, connection_id)
            if credential is None:
                return None
            try:
                access_token = self._cipher.decrypt_text(credential.encrypted_access_token)
                refresh_token = self._cipher.decrypt_text(credential.encrypted_refresh_token)
            except InvalidToken:
                return None
            if access_token is None or refresh_token is None:
                return None
            return {"access_token": access_token, "refresh_token": refresh_token}

    async def revoke(
        self,
        connection_id: str,
        *,
        owner_user_id: str,
        now: datetime | None = None,
    ) -> bool:
        now = now or datetime.now(UTC)
        async with self._sf() as session:
            row = await session.get(PersonalIPPlatformConnectionRow, connection_id)
            if row is None or row.owner_user_id != owner_user_id:
                return False
            row.status = "revoked"
            row.updated_at = now
            await session.execute(delete(PersonalIPPlatformCredentialRow).where(PersonalIPPlatformCredentialRow.connection_id == connection_id))
            await session.commit()
            return True
