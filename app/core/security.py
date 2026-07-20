from authlib.jose import jwt
from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
from .database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
from .db_models.app_auth_models import User
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

load_dotenv(dotenv_path='app/config/.env.security')


### Crypt api key
def load_key(env_var: str = "secret_key_api_key_ai") -> bytes:
    key_b64 = os.environ[env_var]
    return base64.b64decode(key_b64)


def encrypt_api_key(api_key: str) -> str:
    aesgcm = AESGCM(load_key())
    nonce = os.urandom(12)  # nonce de 12 bytes, único por criptografia
    ciphertext = aesgcm.encrypt(nonce, api_key.encode(), associated_data=None)
    # concatena nonce + ciphertext pra guardar tudo junto no banco
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_api_key(encrypted_b64: str) -> str:
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

    claims = jwt.decode(
        token,
        SECRET_KEY
    )

    claims.validate()

    return claims

### Protected Route
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_current_user(token: str, db: Session) -> User:
    claims = decode_token(token)
    user = db.scalar(select(User).where(User.id == UUID(claims["sub"])))
    return user