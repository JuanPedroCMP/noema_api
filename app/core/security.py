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

load_dotenv(dotenv_path='app/config/.env.security')


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