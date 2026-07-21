from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Json

class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
   
    id: UUID
    id_user: UUID
    device_name: str
    device_fingerprint: str
    platform: str
    last_seen_at: datetime | None
    created_at: datetime | None
    updated_at: datetime| None
    
class DeviceFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_user: Optional[UUID | None] = None
    device_name: Optional[str | None] = None
    device_fingerprint: Optional[str | None] = None
    platform: Optional[str | None] = None
    last_seen_at: Optional[datetime | None] = None
    created_at: Optional[datetime | None] = None
    updated_at: Optional[datetime| None] = None
    
class DeviceCreate(BaseModel):
    id_user: UUID
    device_name: str
    device_fingerprint: str
    platform: str

class DeviceUpdate(BaseModel):
    id_user: Optional[UUID | None] = None
    device_name: Optional[str | None] = None
    device_fingerprint: Optional[str | None] = None
    platform: Optional[str | None] = None
    last_seen_at: Optional[datetime | None] = None
