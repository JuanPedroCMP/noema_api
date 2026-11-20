from typing import Optional
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Json, field_validator

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
    is_native: bool
    created_at: datetime | None
    updated_at: datetime| None
    
class LanguageFilters(BaseModel):
    id: Optional[UUID | None] = None
    name: Optional[str | None] = None
    percentage_translated: Optional[int | None] = None
    verified_translation: Optional[bool | None] = None
    automatic_translation:Optional[bool | None] = None
    is_native: Optional[bool | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class LanguageCreate(BaseModel):
    name: str
    percentage_translated: int
    verified_translation: bool
    automatic_translation:bool
    is_native: bool = False

class LanguageUpdate(BaseModel):
    name: Optional[str | None] = None
    percentage_translated: Optional[int | None] = None
    verified_translation: Optional[bool | None] = None
    automatic_translation:Optional[bool | None] = None
    is_native: Optional[bool | None] = None

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


class UserPreferencesUpdate(BaseModel):
    preferences: dict[str, object]

    @field_validator("preferences")
    @classmethod
    def validate_preferences(cls, preferences: dict[str, object]) -> dict[str, object]:
        if "backupFrequency" in preferences:
            backup_frequency = preferences["backupFrequency"]
            if not isinstance(backup_frequency, str) or backup_frequency not in {
                "manual",
                "daily",
                "weekly",
                "monthly",
            }:
                raise ValueError(
                    "backupFrequency must be manual, daily, weekly, or monthly"
                )

        if "backupSchedule" in preferences:
            schedule = preferences["backupSchedule"]
            if not isinstance(schedule, dict):
                raise ValueError("backupSchedule must be an object")
            unit = schedule.get("unit")
            interval = schedule.get("interval")
            if not isinstance(unit, str) or unit not in {"never", "days", "hours"}:
                raise ValueError(
                    "backupSchedule.unit must be never, days, or hours"
                )
            if unit == "never":
                if interval is not None:
                    raise ValueError("a never backup schedule cannot have an interval")
            elif type(interval) is not int or interval < 1:
                raise ValueError(
                    "backupSchedule.interval must be a positive integer"
                )
            elif unit == "days" and interval > 365:
                raise ValueError(
                    "backupSchedule.interval must be between 1 and 365 days"
                )
            elif unit == "hours" and interval > 24:
                raise ValueError(
                    "backupSchedule.interval must be between 1 and 24 hours"
                )

        if (
            "backupOnExit" in preferences
            and type(preferences["backupOnExit"]) is not bool
        ):
            raise ValueError("backupOnExit must be a boolean")

        user_timezone = preferences.get("timezone")
        if user_timezone is not None:
            if not isinstance(user_timezone, str):
                raise ValueError("timezone must be an IANA timezone name")
            try:
                ZoneInfo(user_timezone)
            except (ValueError, ZoneInfoNotFoundError) as exc:
                raise ValueError("timezone must be a valid IANA timezone name") from exc
        return preferences


class UserPreferencesPatch(UserPreferencesUpdate):
    pass


class UserPreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_user: UUID
    preferences: dict
    updated_at: datetime | None
    
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
