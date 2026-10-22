import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID, uuid4

from dotenv import load_dotenv
import httpx
from authlib.jose import JoseError, jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.db_models.app_auth_models import GoogleAccount
from ...core.security import encrypt, get_current_user

router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
DEFAULT_SCOPES = "openid email profile"
STATE_TTL_SECONDS = 600

load_dotenv(dotenv_path='app/config/.env.security')

def _google_config() -> tuple[str, str, str, str]:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    scopes = os.getenv("GOOGLE_SCOPES", DEFAULT_SCOPES)

    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Google OAuth is not configured. Set GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
            ),
        )
    return client_id, client_secret, redirect_uri, scopes


def _create_state(user_id: UUID) -> str:
    secret = os.getenv("secret_key")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state signing is not configured.",
        )

    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"alg": "HS256"},
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(seconds=STATE_TTL_SECONDS),
            "nonce": secrets.token_urlsafe(32),
        },
        secret,
    ).decode()


def _read_state(state: str) -> UUID:
    secret = os.getenv("secret_key")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OAuth state signing is not configured.",
        )

    try:
        claims = jwt.decode(state, secret)
        claims.validate()
        return UUID(str(claims["sub"]))
    except (JoseError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        ) from None


@router.get("/link")
def link_google_account(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user = get_current_user(token, db)
    client_id, _, redirect_uri, scopes = _google_config()
    state = _create_state(user.id)
    authorization_url = f"{GOOGLE_AUTHORIZE_URL}?{urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': scopes,
        'access_type': 'offline',
        'prompt': 'consent',
        'state': state,
    })}"
    return RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback", name="google_oauth_callback")
async def google_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    error = request.query_params.get("error")
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authorization failed: {error}",
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google callback must include code and state.",
        )

    user_id = _read_state(state)
    client_id, client_secret, redirect_uri, _ = _google_config()

    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_response.is_error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google token exchange failed.",
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google did not return an access token.",
            )

        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_response.is_error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google user information request failed.",
            )
        userinfo = userinfo_response.json()

    google_user_id = userinfo.get("sub")
    email = userinfo.get("email")
    if not google_user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Google user information is missing sub or email.",
        )

    google_account = db.scalar(
        select(GoogleAccount).where(GoogleAccount.id_user == user_id)
    )
    expires_in = token_data.get("expires_in")
    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if expires_in
        else None
    )
    values = {
        "google_user_id": google_user_id,
        "email_google": email,
        "access_token_enc": encrypt(access_token),
        "refresh_token_enc": (
            encrypt(token_data["refresh_token"])
            if token_data.get("refresh_token")
            else None
        ),
        "granted_scopes": token_data.get("scope"),
        "is_active": True,
        "expires_at": expires_at,
        "updated_at": datetime.now(timezone.utc),
    }

    if google_account is None:
        google_account = GoogleAccount(id=uuid4(), id_user=user_id, **values)
        db.add(google_account)
    else:
        for field, value in values.items():
            if value is not None:
                setattr(google_account, field, value)

    db.commit()
    db.refresh(google_account)
    return {
        "message": "Google account linked successfully.",
        "google_account_id": str(google_account.id),
        "email_google": google_account.email_google,
    }
