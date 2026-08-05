"""Short-lived, server-verifiable account-to-work evidence bindings."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

_RECEIPT_PREFIX = "dfab1"
_SIGNING_DOMAIN = b"deerflow.ip-account-work-binding.v1\0"
_ISSUER = "ip-agent-evidence"
_AUDIENCE = "inspect_reference_videos"
_SCHEMA = "ip-account-work-binding-v1"
_MAX_RECEIPT_CHARS = 8_192
_MAX_TTL_SECONDS = 3_600
_DEFAULT_TTL_SECONDS = 1_800
_CLOCK_SKEW_SECONDS = 30
_KID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")
_WORK_ID = re.compile(r"^[0-9]{8,40}$")


class _BindingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BoundWork(_BindingModel):
    work_id: str = Field(pattern=r"^[0-9]{8,40}$")
    collection_evidence: Literal["api_author_match", "profile_dom_scope"]


class AccountBindingClaims(_BindingModel):
    schema_name: Literal["ip-account-work-binding-v1"] = Field(alias="schema")
    issuer: Literal["ip-agent-evidence"] = Field(alias="iss")
    audience: Literal["inspect_reference_videos"] = Field(alias="aud")
    platform: Literal["douyin"]
    issued_at: int = Field(alias="iat", ge=0)
    expires_at: int = Field(alias="exp", ge=0)
    binding_id: str = Field(alias="jti", pattern=r"^[0-9a-f]{32}$")
    account_request_id: str = Field(min_length=12, max_length=80)
    account_sec_uid: str = Field(min_length=16, max_length=200)
    canonical_profile_ref: str = Field(min_length=20, max_length=2_000)
    account_observed_at: str = Field(min_length=10, max_length=80)
    works: tuple[BoundWork, ...] = Field(min_length=1, max_length=12)
    identity_claims_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity_projection(self) -> AccountBindingClaims:
        if self.expires_at <= self.issued_at:
            raise ValueError("account binding expiration must follow issuance")
        if self.expires_at - self.issued_at > _MAX_TTL_SECONDS:
            raise ValueError("account binding TTL exceeds the maximum")
        work_ids = [work.work_id for work in self.works]
        if work_ids != sorted(set(work_ids)):
            raise ValueError("account binding works must be unique and sorted")
        _validate_profile_identity(self.canonical_profile_ref, self.account_sec_uid)
        expected = _identity_projection_sha256(
            account_request_id=self.account_request_id,
            account_sec_uid=self.account_sec_uid,
            canonical_profile_ref=self.canonical_profile_ref,
            account_observed_at=self.account_observed_at,
            works=self.works,
        )
        if not hmac.compare_digest(self.identity_claims_sha256, expected):
            raise ValueError("account binding identity projection digest is invalid")
        return self


class AccountBindingEnvelope(_BindingModel):
    scheme: Literal["hmac-sha256-v1"] = "hmac-sha256-v1"
    receipt: str = Field(min_length=32, max_length=_MAX_RECEIPT_CHARS)
    key_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    expires_at: str = Field(min_length=10, max_length=80)
    identity_claims_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class BindingKeyring:
    active_kid: str
    keys: Mapping[str, bytes]

    def __post_init__(self) -> None:
        if _KID.fullmatch(self.active_kid) is None:
            raise ValueError("account binding active key id is invalid")
        normalized: dict[str, bytes] = {}
        for kid, key in self.keys.items():
            if _KID.fullmatch(str(kid)) is None:
                raise ValueError("account binding key id is invalid")
            if not isinstance(key, bytes) or len(key) < 32:
                raise ValueError("account binding keys must contain at least 32 random bytes")
            normalized[str(kid)] = bytes(key)
        if self.active_kid not in normalized:
            raise ValueError("account binding active key is missing")
        object.__setattr__(self, "keys", MappingProxyType(normalized))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    if not value or _SEGMENT.fullmatch(value) is None:
        raise ValueError("account binding contains an invalid encoded segment")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeError) as exc:
        raise ValueError("account binding contains an invalid encoded segment") from exc
    if not hmac.compare_digest(_b64url_encode(decoded), value):
        raise ValueError("account binding contains an invalid encoded segment")
    return decoded


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_profile_identity(profile_ref: str, account_sec_uid: str) -> None:
    parsed = urlsplit(profile_ref)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in {"douyin.com", "www.douyin.com"}
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != f"/user/{account_sec_uid}"
    ):
        raise ValueError("account binding profile identity is invalid")


def _identity_projection_sha256(
    *,
    account_request_id: str,
    account_sec_uid: str,
    canonical_profile_ref: str,
    account_observed_at: str,
    works: tuple[BoundWork, ...] | list[BoundWork],
) -> str:
    projection = {
        "account_request_id": account_request_id,
        "account_sec_uid": account_sec_uid,
        "canonical_profile_ref": canonical_profile_ref,
        "account_observed_at": account_observed_at,
        "works": [work.model_dump(mode="json") for work in works],
    }
    return hashlib.sha256(_canonical_json(projection)).hexdigest()


def keyring_from_environment() -> BindingKeyring:
    active_kid = os.getenv("IP_AGENT_EVIDENCE_BINDING_ACTIVE_KID", "").strip()
    raw_keys = os.getenv("IP_AGENT_EVIDENCE_BINDING_KEYS_JSON", "").strip()
    if not active_kid or not raw_keys:
        raise ValueError("account binding keyring is not configured")
    try:
        parsed = json.loads(raw_keys)
    except json.JSONDecodeError as exc:
        raise ValueError("account binding keyring is invalid") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("account binding keyring is invalid")
    keys: dict[str, bytes] = {}
    for kid, encoded in parsed.items():
        if not isinstance(kid, str) or not isinstance(encoded, str):
            raise ValueError("account binding keyring is invalid")
        keys[kid] = _b64url_decode(encoded)
    return BindingKeyring(active_kid=active_kid, keys=keys)


def _binding_projection(evidence: Mapping[str, Any]) -> dict[str, Any]:
    if evidence.get("operation_status") != "ok":
        raise ValueError("account binding requires successful account evidence")
    source = evidence.get("source")
    metadata = evidence.get("metadata")
    raw_works = evidence.get("works")
    if not isinstance(source, Mapping) or not isinstance(metadata, Mapping) or not isinstance(raw_works, list):
        raise ValueError("account binding requires complete account identity evidence")
    account_sec_uid = str(source.get("account_sec_uid") or "").strip()
    canonical_profile_ref = str(source.get("canonical_profile_ref") or "").strip()
    account_observed_at = str(source.get("observed_at") or "").strip()
    account_request_id = str(metadata.get("request_id") or "").strip()
    if len(account_sec_uid) < 16 or len(account_request_id) < 12 or not account_observed_at:
        raise ValueError("account binding requires complete account identity evidence")
    _validate_profile_identity(canonical_profile_ref, account_sec_uid)
    works_by_id: dict[str, BoundWork] = {}
    for raw_work in raw_works[:12]:
        if not isinstance(raw_work, Mapping):
            raise ValueError("account binding inventory contains an invalid work")
        work = BoundWork.model_validate(
            {
                "work_id": raw_work.get("work_id"),
                "collection_evidence": raw_work.get("ownership_evidence"),
            }
        )
        if work.work_id in works_by_id:
            raise ValueError("account binding inventory contains a duplicate work")
        works_by_id[work.work_id] = work
    works = tuple(works_by_id[work_id] for work_id in sorted(works_by_id))
    if not works:
        raise ValueError("account binding requires at least one observed work")
    identity_claims_sha256 = _identity_projection_sha256(
        account_request_id=account_request_id,
        account_sec_uid=account_sec_uid,
        canonical_profile_ref=canonical_profile_ref,
        account_observed_at=account_observed_at,
        works=works,
    )
    return {
        "account_request_id": account_request_id,
        "account_sec_uid": account_sec_uid,
        "canonical_profile_ref": canonical_profile_ref,
        "account_observed_at": account_observed_at,
        "works": works,
        "identity_claims_sha256": identity_claims_sha256,
    }


def issue_account_binding(
    evidence: Mapping[str, Any],
    *,
    keyring: BindingKeyring,
    now: int | None = None,
    ttl_seconds: int | None = None,
) -> AccountBindingEnvelope:
    projection = _binding_projection(evidence)
    issued_at = int(time.time()) if now is None else int(now)
    if ttl_seconds is None:
        raw_ttl = os.getenv("IP_AGENT_EVIDENCE_BINDING_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS))
        try:
            ttl_seconds = int(raw_ttl)
        except ValueError as exc:
            raise ValueError("account binding TTL is invalid") from exc
    if ttl_seconds < 60 or ttl_seconds > _MAX_TTL_SECONDS:
        raise ValueError("account binding TTL must be between 60 and 3600 seconds")
    claims = AccountBindingClaims.model_validate(
        {
            "schema": _SCHEMA,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
            "platform": "douyin",
            "iat": issued_at,
            "exp": issued_at + ttl_seconds,
            "jti": secrets.token_hex(16),
            **projection,
        }
    )
    payload_segment = _b64url_encode(_canonical_json(claims.model_dump(mode="json", by_alias=True)))
    signing_input = _SIGNING_DOMAIN + keyring.active_kid.encode("ascii") + b"." + payload_segment.encode("ascii")
    signature = hmac.new(
        keyring.keys[keyring.active_kid],
        signing_input,
        hashlib.sha256,
    ).digest()
    receipt = ".".join(
        (
            _RECEIPT_PREFIX,
            keyring.active_kid,
            payload_segment,
            _b64url_encode(signature),
        )
    )
    return AccountBindingEnvelope(
        receipt=receipt,
        key_id=keyring.active_kid,
        expires_at=datetime_from_epoch(claims.expires_at),
        identity_claims_sha256=claims.identity_claims_sha256,
    )


def datetime_from_epoch(value: int) -> str:
    from datetime import UTC, datetime  # noqa: PLC0415

    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def verify_account_binding(
    receipt: str,
    *,
    keyring: BindingKeyring,
    now: int | None = None,
) -> AccountBindingClaims:
    if not isinstance(receipt, str) or len(receipt) > _MAX_RECEIPT_CHARS:
        raise ValueError("account binding receipt is invalid")
    parts = receipt.split(".")
    if len(parts) != 4 or parts[0] != _RECEIPT_PREFIX:
        raise ValueError("account binding receipt is invalid")
    _, kid, payload_segment, signature_segment = parts
    if _KID.fullmatch(kid) is None or kid not in keyring.keys:
        raise ValueError("account binding key id is unknown")
    signature = _b64url_decode(signature_segment)
    signing_input = _SIGNING_DOMAIN + kid.encode("ascii") + b"." + payload_segment.encode("ascii")
    expected = hmac.new(keyring.keys[kid], signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("account binding signature is invalid")
    try:
        decoded = json.loads(_b64url_decode(payload_segment))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("account binding payload is invalid") from exc
    claims = AccountBindingClaims.model_validate(decoded)
    observed_now = int(time.time()) if now is None else int(now)
    if claims.issued_at > observed_now + _CLOCK_SKEW_SECONDS:
        raise ValueError("account binding was issued in the future")
    if observed_now > claims.expires_at + _CLOCK_SKEW_SECONDS:
        raise ValueError("account binding has expired")
    return claims


def verify_video_against_binding(
    binding: AccountBindingClaims,
    *,
    requested_work_id: str,
    resolved_work_id: str,
    observed_work_id: str,
    observed_author_sec_uid: str,
    canonical_work_ref: str,
) -> BoundWork:
    if not all(_WORK_ID.fullmatch(value or "") for value in (requested_work_id, resolved_work_id, observed_work_id)):
        raise ValueError("account binding video identity is invalid")
    if len({requested_work_id, resolved_work_id, observed_work_id}) != 1:
        raise ValueError("account binding video work identity does not match")
    work = next((item for item in binding.works if item.work_id == observed_work_id), None)
    if work is None:
        raise ValueError("account binding work is outside the collected inventory")
    if canonical_work_ref != f"https://www.douyin.com/video/{observed_work_id}":
        raise ValueError("account binding canonical work reference does not match")
    if observed_author_sec_uid != binding.account_sec_uid:
        raise ValueError("account binding observed author does not match")
    return work
