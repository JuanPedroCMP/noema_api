from authlib.jose import jwt
from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
from .db_models.app_auth_models import User
import os
import base64
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from authlib.jose import JoseError
from fastapi import HTTPException, status

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / "config" / ".env.security")


### Crypt api key
def load_key(env_var: str = "secret_key_api_key_ai") -> bytes:
    key_b64 = os.getenv(env_var)
    if not key_b64:
        raise RuntimeError(f"Required security setting '{env_var}' is not configured.")
    try:
        key = base64.b64decode(key_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise RuntimeError(f"Security setting '{env_var}' is not valid base64.") from exc
    if len(key) not in (16, 24, 32):
        raise RuntimeError(f"Security setting '{env_var}' must decode to an AES key.")
    return key


def encrypt(secret: str) -> str:
    aesgcm = AESGCM(load_key())
    nonce = os.urandom(12)  # nonce de 12 bytes, único por criptografia
    ciphertext = aesgcm.encrypt(nonce, secret.encode(), associated_data=None)
    # concatena nonce + ciphertext pra guardar tudo junto no banco
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(encrypted_b64: str) -> str:
    raw = base64.b64decode(encrypted_b64)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(load_key())
    plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    return plaintext.decode()

### Hash
pwd = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return pwd.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd.verify(password, hashed)


### JWT
SECRET_KEY = os.getenv("secret_key")

HEADER = {
    "alg": "HS256"
}


def create_access_token(user_id: UUID):
    if not SECRET_KEY:
        raise RuntimeError("Required security setting 'secret_key' is not configured.")

    payload = {
        "sub": str(user_id),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=30)
    }

    return jwt.encode(
        HEADER,
        payload,
        SECRET_KEY
    )

def decode_token(token: str):
    if not SECRET_KEY:
        raise RuntimeError("Required security setting 'secret_key' is not configured.")
    try:
        claims = jwt.decode(token, SECRET_KEY)
        claims.validate()
        return claims
    except (JoseError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

### Protected Route
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_current_user(token: str, db: Session) -> User:
    claims = decode_token(token)
    try:
        user_id = UUID(str(claims["sub"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is not available.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user