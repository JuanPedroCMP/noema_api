from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


def validate_password_strength(password: str) -> str:
    if (
        len(password) < 8
        or not any(character.isalpha() for character in password)
        or not any(character.isdigit() for character in password)
    ):
        raise ValueError(
            "password must be at least 8 characters and contain a letter and a number"
        )
    return password


class UserOut(BaseModel):
    id: UUID
    user_name: str
    primary_email: EmailStr
    user_display_name: str | None
    created_at: datetime | None
    updated_at: datetime | None
    is_active: bool | None
    is_verified: bool | None

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    user_name: str = ""
    primary_email: EmailStr
    user_display_name: str | None = None
    password: str

    _validate_password = field_validator("password")(validate_password_strength)


class UserUpdate(BaseModel):
    user_name: Optional[str] = None
    primary_email: Optional[EmailStr] = None
    user_display_name: Optional[str] = None
    password: Optional[str] = None
    current_password: Optional[str] = None

    _validate_password = field_validator("password")(validate_password_strength)
