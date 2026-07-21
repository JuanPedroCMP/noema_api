from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Json

################
### Language
################
class LanguageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    name: str
    percentage_translated: int
    verified_translation: bool
    automatic_translation:bool
    created_at: datetime | None
    updated_at: datetime| None
    
class LanguageFilters(BaseModel):
    id: Optional[UUID | None] = None
    name: Optional[str | None] = None
    percentage_translated: Optional[int | None] = None
    verified_translation: Optional[bool | None] = None
    automatic_translation:Optional[bool | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class LanguageCreate(BaseModel):
    name: str
    percentage_translated: int
    verified_translation: bool
    automatic_translation:bool

class LanguageUpdate(BaseModel):
    name: Optional[str | None] = None
    percentage_translated: Optional[int | None] = None
    verified_translation: Optional[bool | None] = None
    automatic_translation:Optional[bool | None] = None

################
### UserGlobalConfig
################
class UserGlobalConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    id_user: UUID
    id_language: UUID
    id_user_color_theme: UUID
    id_user_typography_theme: UUID
    preferences: dict
    created_at: datetime | None
    updated_at: datetime| None
    
class UserGlobalConfigFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    id_language: Optional[UUID | None] = None
    id_user_color_theme: Optional[UUID | None] = None
    id_user_typography_theme: Optional[UUID | None] = None
    preferences: Json
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class UserGlobalConfigCreate(BaseModel):
    id_user: UUID
    id_language: UUID
    id_user_color_theme: UUID
    id_user_typography_theme: UUID
    preferences: Json

class UserGlobalConfigUpdate(BaseModel):
    id_user: Optional[UUID | None] = None
    id_language: Optional[UUID | None] = None
    id_user_color_theme: Optional[UUID | None] = None
    id_user_typography_theme: Optional[UUID | None] = None
    preferences: Optional[Json | None] = None
    
################
### UserLocalConfig
################
class UserLocalConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    id_user: UUID
    id_device: UUID
    id_language: UUID
    id_user_color_theme: UUID
    id_user_typography_theme: UUID
    preferences: dict
    created_at: datetime | None
    updated_at: datetime| None
    
class UserLocalConfigFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    id_device: Optional[UUID | None] = None
    id_language: Optional[UUID | None] = None
    id_user_color_theme: Optional[UUID | None] = None
    id_user_typography_theme: Optional[UUID | None] = None
    preferences: Json
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class UserLocalConfigCreate(BaseModel):
    id_user: UUID
    id_device: Optional[UUID | None] = None
    id_language: UUID
    id_user_color_theme: UUID
    id_user_typography_theme: UUID
    preferences: Json

class UserLocalConfigUpdate(BaseModel):
    id_user: Optional[UUID | None] = None
    id_device: Optional[UUID | None] = None
    id_language: Optional[UUID | None] = None
    id_user_color_theme: Optional[UUID | None] = None
    id_user_typography_theme: Optional[UUID | None] = None
    preferences: Optional[Json | None] = None
    
################
### Response Language Preference Order
################
class ResponseLanguagePreferenceOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    preference_order: int
    id_user: UUID
    id_language: UUID

class ResponseLanguagePreferenceOrderFilters(BaseModel):
    id: Optional[UUID | None] = None
    preference_order: Optional[int | None] =None 
    id_user: Optional[UUID | None] = None
    id_language: Optional[UUID | None] = None
    
class ResponseLanguagePreferenceOrderCreate(BaseModel):
    preference_order: int
    id_user: UUID
    id_language: UUID

class ResponseLanguagePreferenceOrderUpdate(BaseModel):
    id: Optional[UUID | None] = None
    preference_order: Optional[int | None] =None 
    id_user: Optional[UUID | None] = None
    id_language: Optional[UUID | None] = None

