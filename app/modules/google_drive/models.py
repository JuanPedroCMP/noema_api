from typing import Optional
from datetime import datetime
from uuid import UUID
from ...core.db_models.google_drive_models import SyncDirection, SyncResult, ConflictStrategy
from pydantic import BaseModel, EmailStr, ConfigDict, Json
from ...core.db_models.ai_models import TaskType, AgentModelQuality

################
### BackupFile
################
class BackupFileOut(BaseModel):
    id: UUID
    id_google_account: UUID
    drive_file_id: str
    local_ref: str
    drive_version: str
    content_hash: str
    created_at: datetime | None

class BackupFileFiltes(BaseModel):
    id: Optional[UUID | None] = None
    id_google_account: Optional[UUID | None] = None
    drive_file_id: Optional[str | None] = None
    local_ref: Optional[str | None] = None
    drive_version: Optional[str | None] = None
    content_hash: Optional[str | None] = None
    created_at: Optional[datetime | None] = None
    
class BackupFileUpdate(BaseModel):
    id_google_account: Optional[UUID | None] = None
    drive_file_id: Optional[str | None] = None
    local_ref: Optional[str | None] = None
    drive_version: Optional[str | None] = None
    content_hash: Optional[str | None] = None

class BackupFileCreate(BaseModel):
    id_google_account: UUID
    drive_file_id: str
    local_ref: str
    drive_version: str
    content_hash: str

################
### SyncLog
################
class SyncLogOut(BaseModel):
    id: UUID
    id_device: UUID
    id_backup_file: UUID
    event: str
    derection: SyncDirection
    result: SyncResult
    conflict_strategy: ConflictStrategy
    error_details: str
    metadata: dict
    created_at: datetime | None

class SyncLogFilters(BaseModel):
    id: Optional[UUID | None] = None
    id_device: Optional[UUID | None] = None
    id_backup_file: Optional[UUID | None] = None
    event: Optional[str | None] = None
    derection: Optional[SyncDirection | None] = None
    result: Optional[SyncResult | None] = None
    conflict_strategy: Optional[ConflictStrategy | None] = None
    error_details: Optional[str | None] = None
    metadata: Optional[Json | None] = None
    created_at: Optional[datetime | None] = None

class SyncLogCreate(BaseModel):
    id_device: UUID
    id_backup_file: UUID
    event: str
    derection: SyncDirection
    result: SyncResult
    conflict_strategy: ConflictStrategy
    error_details: str
    metadata: Json
    
class SyncLogUpdate(BaseModel):
    id_device: Optional[UUID | None] = None
    id_backup_file: Optional[UUID | None] = None
    event: Optional[str | None] = None
    derection: Optional[SyncDirection | None] = None
    result: Optional[SyncResult | None] = None
    conflict_strategy: Optional[ConflictStrategy | None]
    error_details: Optional[str | None] = None
    metadata: Optional[Json | None] = None
