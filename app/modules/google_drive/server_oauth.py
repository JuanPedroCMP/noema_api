"""Backend-owned Google OAuth and Drive transport.

The module deliberately keeps credentials below the service boundary.  Public
functions return account status or Drive data, never OAuth tokens.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from collections.abc import AsyncIterator
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ...core.db_models.google_drive_models import (
    BackupFile,
    GoogleAccount,
    OAuthState,
    SyncOperation,
)
from ...core.security import get_current_user
from .models import GOOGLE_DRIVE_APPDATA_SCOPE

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_DRIVE_URL = "https://www.googleapis.com/drive/v3"
TOKEN_MARGIN = timedelta(minutes=2)
_access_tokens: dict[UUID, tuple[str, datetime]] = {}


def _config(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(
            status_code=503,
            detail={"code": "google_oauth_not_configured", "message": f"{name} is not configured."},
        )
    return value


def _key_version() -> str:
    return os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY_VERSION", "current")


def _allowed_redirect_uris() -> set[str]:
    configured = {
        value.strip()
        for value in os.getenv("GOOGLE_OAUTH_REDIRECT_URIS", "").split(",")
        if value.strip()
    }
    if not configured:
        raise HTTPException(
            status_code=503,
            detail={"code": "google_oauth_not_configured", "message": "Google OAuth redirect URIs are not configured."},
        )
    return configured


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def oauth_cancel(state: str, db: Session, error: str | None = None) -> None:
    row = db.scalar(
        select(OAuthState).where(
            OAuthState.state_hash == _hash(state),
            OAuthState.consumed_at.is_(None),
            OAuthState.expires_at > datetime.now(timezone.utc),
        ).with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=400, detail={"code": "invalid_oauth_state"})
    row.consumed_at = datetime.now(timezone.utc)
    row.error_code = (
        "oauth_authorization_cancelled"
        if error == "access_denied"
        else "google_oauth_provider_error"
    )
    db.commit()


def _key(version: str) -> bytes:
    raw = os.getenv(f"GOOGLE_TOKEN_ENCRYPTION_KEY_{version}") or os.getenv(
        "GOOGLE_TOKEN_ENCRYPTION_KEY"
    )
    if not raw:
        raise RuntimeError("Google token encryption key is not configured.")
    try:
        value = base64.b64decode(raw, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError("Google token encryption key must be base64.") from exc
    if len(value) not in (16, 24, 32):
        raise RuntimeError("Google token encryption key must be 128, 192, or 256 bits.")
    return value


def _seal(value: str, *, version: str, associated_data: str) -> str:
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_key(version)).encrypt(
        nonce, value.encode("utf-8"), associated_data.encode("utf-8")
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def _open(value: str, *, version: str, associated_data: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    plaintext = AESGCM(_key(version)).decrypt(
        raw[:12], raw[12:], associated_data.encode("utf-8")
    )
    return plaintext.decode("utf-8")


def oauth_start(token: str, redirect_uri: str, db: Session) -> dict[str, str]:
    user = get_current_user(token, db)
    client_id = _config("GOOGLE_OAUTH_CLIENT_ID")
    if redirect_uri not in _allowed_redirect_uris():
        raise HTTPException(status_code=400, detail={"code": "invalid_redirect_uri"})
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    now = datetime.now(timezone.utc)
    row = OAuthState(
        id=uuid4(),
        id_user=user.id,
        state_hash=_hash(state),
        nonce_hash=_hash(nonce),
        nonce_enc=_seal(nonce, version=_key_version(), associated_data=_hash(state)),
        code_verifier_enc=_seal(verifier, version=_key_version(), associated_data=_hash(state)),
        redirect_uri=redirect_uri,
        expires_at=now + timedelta(minutes=10),
        created_at=now,
    )
    db.add(row)
    db.commit()
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": f"openid email {GOOGLE_DRIVE_APPDATA_SCOPE}",
            "state": state,
            "nonce": nonce,
            "code_challenge": base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            ).rstrip(b"=").decode("ascii"),
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{query}", "state": state}


async def oauth_callback(code: str, state: str, db: Session) -> dict[str, str]:
    row = db.scalar(
        select(OAuthState).where(
            OAuthState.state_hash == _hash(state),
            OAuthState.consumed_at.is_(None),
            OAuthState.expires_at > datetime.now(timezone.utc),
        ).with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=400, detail={"code": "invalid_oauth_state"})
    verifier = _open(
        row.code_verifier_enc, version=_key_version(), associated_data=_hash(state)
    )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": _config("GOOGLE_OAUTH_CLIENT_ID"),
                "client_secret": _config("GOOGLE_OAUTH_CLIENT_SECRET"),
                "redirect_uri": row.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"code": "google_token_exchange_failed"})
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail={"code": "google_token_exchange_failed"}) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail={"code": "google_token_exchange_failed"})
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    if not isinstance(access_token, str):
        raise HTTPException(status_code=502, detail={"code": "google_access_token_missing"})
    id_token = payload.get("id_token")
    if not isinstance(id_token, str):
        raise HTTPException(status_code=502, detail={"code": "google_identity_missing"})
    async with httpx.AsyncClient(timeout=8) as client:
        identity_response = await client.get(
            "https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token}
        )
    try:
        identity = identity_response.json() if identity_response.is_success else {}
    except ValueError:
        identity = {}
    try:
        identity_expired = (
            not isinstance(identity, dict)
            or int(identity.get("exp", 0))
            <= int(datetime.now(timezone.utc).timestamp())
        )
    except (TypeError, ValueError):
        identity_expired = True
    audience = identity.get("aud") if isinstance(identity, dict) else None
    audience_valid = (
        _config("GOOGLE_OAUTH_CLIENT_ID") in audience
        if isinstance(audience, list)
        else audience == _config("GOOGLE_OAUTH_CLIENT_ID")
    )
    azp = identity.get("azp") if isinstance(identity, dict) else None
    if (
        not isinstance(identity, dict)
        or not isinstance(identity.get("nonce"), str)
        or _hash(identity["nonce"]) != row.nonce_hash
        or identity.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}
        or not audience_valid
        or (azp is not None and azp != _config("GOOGLE_OAUTH_CLIENT_ID"))
        or not isinstance(identity.get("sub"), str)
        or not identity.get("sub")
        or identity.get("email_verified") not in {True, "true", "1"}
        or identity_expired
        or GOOGLE_DRIVE_APPDATA_SCOPE not in str(payload.get("scope", "")).split()
    ):
        raise HTTPException(status_code=401, detail={"code": "invalid_google_identity"})
    account = db.scalar(select(GoogleAccount).where(GoogleAccount.id_user == row.id_user).with_for_update())
    conflicting = db.scalar(
        select(GoogleAccount).where(
            GoogleAccount.google_user_id == str(identity.get("sub")),
            GoogleAccount.id_user != row.id_user,
        )
    )
    if conflicting is not None:
        raise HTTPException(status_code=409, detail={"code": "google_account_unavailable"})
    if account is not None and account.google_user_id not in {
        None,
        str(identity["sub"]),
    }:
        retained_backups = db.scalar(
            select(BackupFile.id)
            .where(BackupFile.id_google_account == account.id)
            .limit(1)
        )
        if retained_backups is not None:
            raise HTTPException(
                status_code=409,
                detail={"code": "google_account_already_linked"},
            )
    now = datetime.now(timezone.utc)
    if refresh_token is None and account is None:
        raise HTTPException(status_code=502, detail={"code": "google_refresh_token_missing"})
    if refresh_token is not None and not isinstance(refresh_token, str):
        raise HTTPException(status_code=502, detail={"code": "google_refresh_token_invalid"})
    if account is None:
        account = GoogleAccount(id=uuid4(), id_user=row.id_user, created_at=now)
        db.add(account)
    if refresh_token is not None:
        account.refresh_token_enc = _seal(
            refresh_token, version=_key_version(), associated_data=str(account.id)
        )
        account.refresh_token_key_version = _key_version()
    account.google_user_id = str(identity["sub"])
    account.email_google = str(identity.get("email", ""))
    account.expires_at = now + timedelta(seconds=int(payload.get("expires_in", 3600)))
    account.is_active = True
    account.drive_appdata_status = "granted"
    account.granted_scopes = f"openid email {GOOGLE_DRIVE_APPDATA_SCOPE}"
    account.updated_at = now
    row.consumed_at = now
    db.commit()
    _access_tokens[account.id] = (
        access_token,
        now + timedelta(seconds=int(payload.get("expires_in", 3600))),
    )
    return {
        "account_id": str(account.id),
        "state": "completed",
        "redirect_uri": row.redirect_uri,
    }


async def refresh_access_token(account: GoogleAccount, db: Session) -> str:
    if not account.refresh_token_enc or not account.refresh_token_key_version:
        raise HTTPException(status_code=409, detail={"code": "google_authorization_revoked"})
    if db.bind is None or db.bind.dialect.name != "postgresql":
        raise HTTPException(
            status_code=503,
            detail={"code": "distributed_lock_unavailable"},
        )
    lock_key = int.from_bytes(
        hashlib.sha256(str(account.id).encode("ascii")).digest()[:8],
        byteorder="big",
        signed=True,
    )
    db.execute(
        text("SELECT pg_advisory_xact_lock(CAST(:lock_key AS BIGINT))"),
        {"lock_key": lock_key},
    )
    locked = db.scalar(
        select(GoogleAccount).where(GoogleAccount.id == account.id).with_for_update()
    )
    if locked is None:
        raise HTTPException(status_code=404, detail={"code": "google_account_not_linked"})
    account = locked
    now = datetime.now(timezone.utc)
    cached = _access_tokens.get(account.id)
    if cached and cached[1] - TOKEN_MARGIN > now:
        return cached[0]
    return await _exchange_refresh(account, db)


async def _exchange_refresh(account: GoogleAccount, db: Session) -> str:
    version = account.refresh_token_key_version or "current"
    refresh_token = _open(account.refresh_token_enc or "", version=version, associated_data=str(account.id))
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": _config("GOOGLE_OAUTH_CLIENT_ID"),
                "client_secret": _config("GOOGLE_OAUTH_CLIENT_SECRET"),
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    if response.status_code >= 400:
        try:
            error_payload = response.json()
        except ValueError:
            error_payload = {}
        if response.status_code == 400 and isinstance(error_payload, dict) and error_payload.get("error") == "invalid_grant":
            account.is_active = False
            account.drive_appdata_status = "revoked"
            account.updated_at = datetime.now(timezone.utc)
            db.commit()
            raise HTTPException(status_code=401, detail={"code": "google_authorization_revoked"})
        raise HTTPException(status_code=502, detail={"code": "google_refresh_failed"})
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail={"code": "google_refresh_failed"}) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail={"code": "google_refresh_failed"})
    access_token = payload.get("access_token")
    if not isinstance(access_token, str):
        raise HTTPException(status_code=502, detail={"code": "google_refresh_failed"})
    rotated = payload.get("refresh_token")
    if isinstance(rotated, str) and rotated:
        account.refresh_token_enc = _seal(
            rotated,
            version=_key_version(),
            associated_data=str(account.id),
        )
        account.refresh_token_key_version = _key_version()
    account.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expires_in", 3600)))
    account.last_refresh_at = datetime.now(timezone.utc)
    account.updated_at = account.last_refresh_at
    db.commit()
    _access_tokens[account.id] = (
        access_token,
        account.expires_at or datetime.now(timezone.utc),
    )
    return access_token


async def drive_request(
    account: GoogleAccount, db: Session, method: str, path: str, **kwargs: Any
) -> httpx.Response:
    access_token = await refresh_access_token(account, db)
    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = "Bearer " + access_token
    headers["Accept"] = "application/json"
    async with httpx.AsyncClient(timeout=60) as client:
        url = path if path.startswith("http") else f"{GOOGLE_DRIVE_URL}{path}"
        response = await client.request(method, url, headers=headers, **kwargs)
    if response.status_code == 401:
        account.expires_at = datetime.now(timezone.utc)
        db.commit()
        access_token = await refresh_access_token(account, db)
        headers["Authorization"] = "Bearer " + access_token
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
    return response


async def drive_stream(
    account: GoogleAccount,
    db: Session,
    method: str,
    path: str,
    **kwargs: Any,
) -> AsyncIterator[bytes]:
    """Stream a Drive response without buffering the snapshot in memory."""
    access_token = await refresh_access_token(account, db)
    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = "Bearer " + access_token
    headers["Accept"] = "application/octet-stream"
    url = path if path.startswith("http") else f"{GOOGLE_DRIVE_URL}{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(method, url, headers=headers, **kwargs) as response:
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=404 if response.status_code == 404 else 502,
                    detail={"code": "drive_file_missing" if response.status_code == 404 else "drive_download_failed"},
                )
            async for chunk in response.aiter_bytes(8 * 1024 * 1024):
                yield chunk


async def unlink_google_account(account: GoogleAccount, db: Session) -> None:
    pending = db.scalar(
        select(SyncOperation.id).where(
            SyncOperation.id_google_account == account.id,
            SyncOperation.state.in_(("pending", "uploading")),
        ).limit(1)
    )
    if pending is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "google_account_operations_pending"},
        )
    if account.refresh_token_enc and account.refresh_token_key_version:
        refresh_token = _open(
            account.refresh_token_enc,
            version=account.refresh_token_key_version,
            associated_data=str(account.id),
        )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": refresh_token},
                )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail={"code": "google_revoke_failed"}
            ) from exc
        if response.status_code >= 500:
            raise HTTPException(status_code=502, detail={"code": "google_revoke_failed"})
    _access_tokens.pop(account.id, None)
    account.refresh_token_enc = None
    account.refresh_token_key_version = None
    account.is_active = False
    account.drive_appdata_status = "revoked"
    account.updated_at = datetime.now(timezone.utc)
    db.commit()
