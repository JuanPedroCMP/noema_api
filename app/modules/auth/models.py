from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    id_user: UUID
    google_user_id: str | None
    email_google: str | None
    granted_scopes: str | None
    drive_appdata_status: str = "unknown"
    scope_checked_at: datetime | None = None
    is_active: bool
    expires_at: datetime | None
    last_refresh_at: datetime | None
    updated_at: datetime | None
    created_at: datetime | None
