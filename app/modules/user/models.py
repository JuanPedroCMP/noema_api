from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict

class UserOut(BaseModel):
    id: UUID
    user_name: str
    primary_email:EmailStr
    user_display_name: str | None
    created_at: datetime | None
    updated_at: datetime| None
    is_active: bool | None
    is_verified: bool | None
    
    model_config = ConfigDict(from_attributes=True)

class UserCreate(BaseModel):
    user_name: str = ""
    primary_email:EmailStr
    user_display_name: str | None = None
    password: str = ""

class UserUpdate(BaseModel):
    user_name: Optional[str]  = None
    primary_email: Optional[EmailStr] = None
    user_display_name: Optional[str] = None
    password: Optional[str] = None

