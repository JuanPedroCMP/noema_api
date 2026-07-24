from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime

################
### Login
################
class LoginData(BaseModel):
    login_identificator: str
    password: str
    
################
### GoogleAcconunt
################
class GoogleAccountOut(BaseModel):
    id: UUID
    id_user: UUID
    google_user_id: str | None
    email_google: str
    access_token_enc: str | None
    refresh_token_enc: str | None
    granted_scopes: str | None
    is_active: bool 
    expires_at: datetime | None
    last_refresh_at: datetime | None
    updated_at: datetime | None
    created_at: datetime | None

class GoogleAccountCreate(BaseModel):
    id_user: UUID
    google_user_id: str | None
    email_google: str
    access_token_enc: str | None
    refresh_token_enc: str | None
    granted_scopes: str | None
    is_active: bool
    expires_at: datetime | None

class GoogleAccountUpdate(BaseModel):
    id_user: Optional[UUID | None]
    google_user_id: Optional[str | None]
    email_google: Optional[str | None]
    access_token_enc: Optional[str | None]
    refresh_token_enc: Optional[str | None]
    granted_scopes:Optional[str | None]
    is_active: Optional[bool | None]
    expires_at: Optional[datetime | None]
    last_refresh_at: Optional[datetime | None]

class GoogleAccountFilters(BaseModel):
    id: Optional[UUID | None]
    id_user: Optional[UUID | None]
    google_user_id: Optional[str | None]
    email_google: Optional[str | None]
    access_token_enc: Optional[str | None]
    refresh_token_enc: Optional[str | None]
    granted_scopes:Optional[str | None]
    is_active: Optional[bool | None]
    expires_at: Optional[datetime | None]
    last_refresh_at: Optional[datetime | None]
    updated_at: Optional[datetime | None]
    created_at: Optional[datetime | None]