from typing import Optional
import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    user_name: str = ""
    primary_email:EmailStr
    user_display_name: str | None = None
    password: str = ""
    user_display_name: str = ""

class UserUpdate(BaseModel):
    user_name: Optional[str]  = None
    primary_email: Optional[EmailStr] = None
    user_display_name: Optional[str] = None
    password: Optional[str] = None
    user_display_name: Optional[str] = None
