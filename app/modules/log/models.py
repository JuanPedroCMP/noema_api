from typing import Optional
from datetime import datetime
from uuid import UUID
from ...core.db_models.google_drive_models import SyncDirection, SyncResult, ConflictStrategy
from pydantic import BaseModel, ConfigDict, Json
from typing import Any
from ...core.db_models.ai_models import TaskType, AgentModelQuality

################
### Generic Log
################
class GenericLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    id_user: UUID | None 
    details: dict[str, Any]
    created_at: datetime | None 

class GenericLogFilters(BaseModel):
    id: Optional[UUID | None] = None
    type: Optional[str | None] = None
    id_user: Optional[UUID | None] = None
    details: Optional[Json | None] = None
    created_at: Optional[datetime | None ] = None
    
class GenericLogUpdate(BaseModel):
    type: Optional[str | None] = None
    id_user: Optional[UUID | None] = None
    details: Optional[Json | None] = None
    created_at: Optional[datetime | None ] = None

class GenericLogCreate(BaseModel):
    id_user: UUID | None 
    type: str
    details: Json
