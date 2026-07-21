from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Json

################
### UserColorTheme
################
class UserColorThemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_user: UUID
    name: str
    seed_color: int
    override_json: dict
    created_at: datetime | None
    updated_at: datetime| None
    
class UserColorThemeFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    name: Optional[str | None] = None
    seed_color: Optional[int | None] = None
    override_json: Optional[Json | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class UserColorThemeCreate(BaseModel):
    id_user: UUID
    name: str
    seed_color: int
    override_json: Json

class UserColorThemeUpdate(BaseModel):
    id_user: Optional[UUID | None] = None
    name: Optional[str | None] = None
    seed_color: Optional[int | None] = None
    override_json: Optional[Json | None] = None
    
################
### UserTypographyTheme
################
class UserTypographyThemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_user: UUID
    name: str
    display_font: str
    body_font: str
    mono_font: str
    override_json: dict
    created_at: datetime | None
    updated_at: datetime| None
    
class UserTypographyThemeFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    name: Optional[str | None] = None
    display_font: Optional[str | None] = None
    body_font:Optional[str | None] = None
    mono_font: Optional[str | None] = None
    override_json: Optional[Json | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class UserTypographyThemeCreate(BaseModel):
    id_user: UUID
    name: str
    display_font: str
    body_font: str
    mono_font: str
    override_json: Json | None

class UserTypographyThemeUpdate(BaseModel):
    id_user: Optional[UUID | None] = None
    name: Optional[str | None] = None
    display_font: Optional[str | None] = None
    body_font: Optional[str | None] = None
    mono_font: Optional[str | None] = None
    override_json: Optional[Json | None] = None