from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import HTTPException, status

from .models import GOOGLE_DRIVE_APPDATA_SCOPE

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
ALLOWED_NON_DRIVE_SCOPES = {
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
}


class _TokenInfoLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple) or len(record.args) < 2:
            return True
        url = urlsplit(str(record.args[1]))
        if (
            url.scheme == "https"
            and url.netloc == "oauth2.googleapis.com"
            and url.path == "/tokeninfo"
        ):
            arguments = list(record.args)
            arguments[1] = urlunsplit((url.scheme, url.netloc, url.path, "", ""))
            record.args = tuple(arguments)
        return True


logging.getLogger("httpx").addFilter(_TokenInfoLogFilter())


class InvalidGoogleToken(Exception):
    pass


def google_client_ids() -> set[str]:
    client_ids = {
        value.strip()
        for value in os.getenv("GOOGLE_OAUTH_CLIENT_IDS", "").split(",")
        if value.strip()
    }
    if not client_ids:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "google_oauth_not_configured",
                "message": "Google OAuth client IDs are not configured.",
            },
        )
    return client_ids


async def _fetch_token_info(parameter: str, token: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(
                GOOGLE_TOKEN_INFO_URL,
                params={parameter: token},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "google_verification_unavailable",
                "message": "Google authorization could not be verified.",
            },
        ) from exc

    if response.status_code in {400, 401}:
        raise InvalidGoogleToken
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "google_verification_unavailable",
                "message": "Google authorization could not be verified.",
            },
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "invalid_google_response",
                "message": "Google returned an invalid authorization response.",
            },
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "invalid_google_response",
                "message": "Google returned an invalid authorization response.",
            },
        )
    return payload


def _audience(payload: dict[str, Any]) -> set[str]:
    audiences: set[str] = set()
    for key in ("aud", "audience", "issued_to", "client_id", "azp"):
        value = payload.get(key)
        if isinstance(value, list):
            audiences.update(str(item) for item in value if item)
        elif value:
            audiences.add(str(value))
    return audiences


async def verify_google_identity(id_token: str) -> tuple[str, str]:
    client_ids = google_client_ids()
    try:
        identity = await _fetch_token_info("id_token", id_token)
    except InvalidGoogleToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_google_identity",
                "message": "Google identity could not be verified.",
            },
        ) from exc

    issuer = identity.get("iss")
    try:
        expires_at = int(identity.get("exp", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_google_identity",
                "message": "Google identity could not be verified.",
            },
        ) from exc
    subject = identity.get("sub")
    email = identity.get("email")
    email_verified = identity.get("email_verified")
    if (
        not subject
        or not email
        or str(email_verified).lower() not in {"true", "1"}
        or issuer not in {"accounts.google.com", "https://accounts.google.com"}
        or expires_at <= int(time.time())
        or not (_audience(identity) & client_ids)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_google_identity",
                "message": "Google identity could not be verified.",
            },
        )

    return str(subject), str(email)


async def verify_google_access_token(
    access_token: str,
    expected_subject: str,
) -> list[str]:
    client_ids = google_client_ids()
    try:
        authorization = await _fetch_token_info("access_token", access_token)
    except InvalidGoogleToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_google_authorization",
                "message": "Google authorization is invalid or revoked.",
            },
        ) from exc
    if not (_audience(authorization) & client_ids):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "google_authorization_mismatch",
                "message": "Google authorization could not be verified.",
            },
        )
    access_subject = authorization.get("sub") or authorization.get("user_id")
    if not access_subject or str(access_subject) != expected_subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "google_identity_mismatch",
                "message": "Google identity and authorization do not match.",
            },
        )

    scopes = sorted(set(str(authorization.get("scope", "")).split()))
    allowed_scopes = {GOOGLE_DRIVE_APPDATA_SCOPE, *ALLOWED_NON_DRIVE_SCOPES}
    if set(scopes) - allowed_scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "google_scope_not_allowed",
                "message": "Only the private Drive app-data scope is permitted.",
            },
        )
    return scopes


async def verify_google_tokens(
    id_token: str,
    access_token: str,
) -> tuple[str, str, list[str]]:
    subject, email = await verify_google_identity(id_token)
    scopes = await verify_google_access_token(access_token, subject)
    return subject, email, scopes
