from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ...core.security import oauth2_scheme
from ...core.database import get_db
from ...core.db_models.ai_models import TaskType
from .services import create_backup_file as cbf, get_backup_file as gbf, list_backup_files as lbf, delete_backup_file as dbf, get_sync_log as gsl, list_sync_logs as lsl, create_sync_log as csl
from .models import BackupFileCreate, BackupFileFiltes, BackupFileOut, SyncLogCreate, SyncLogFilters, SyncLogOut
from typing import Annotated

router = APIRouter(
    prefix="/google_drive",
)

################
### Backup File
################
backup_file_router = APIRouter(
    prefix="/backup_file",
    tags=["backup_file"]
)

@backup_file_router.get("/get/{identificator}", response_model=BackupFileOut)
def get_backup_file(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gbf(token, identificator, db)

@backup_file_router.get("/list", response_model=list[BackupFileOut])
def list_backup_file(filters: Annotated[BackupFileFiltes, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return lbf(token, db, _filters)

@backup_file_router.post("/create", response_model=BackupFileOut)
def create_backup_file(new_backup_file: BackupFileCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    backup_file = cbf(token, new_backup_file, db)
    return backup_file

@backup_file_router.delete("/delete/{identificator}")
def delete_backup_file(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sucess = dbf(token, identificator, db)
    return sucess

################
### Sync Log
################
sync_log_router = APIRouter(
    prefix="/sync_log",
    tags=["sync_log"]
)

@sync_log_router.get("/get/{identificator}", response_model=SyncLogOut)
def get_sync_log(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gsl(token, identificator, db)

@sync_log_router.get("/list", response_model=list[SyncLogOut])
def list_sync_log(filters: Annotated[SyncLogFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return lsl(token, db, _filters)

@sync_log_router.post("/create", response_model=SyncLogOut)
def create_sync_log(new_sync_log: SyncLogCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sync_log = csl(token, new_sync_log, db)
    return sync_log


router.include_router(backup_file_router)
router.include_router(sync_log_router)

