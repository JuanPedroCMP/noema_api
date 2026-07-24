from ...core.db_models.google_drive_models import BackupFile, GoogleAccount, SyncLog, Device
from ...core.security import get_current_user, encrypt, decrypt
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from ..auth.service import get_google_account
from .models import BackupFileCreate, SyncLogCreate
from datetime import datetime

################
### Backup File
################
def get_backup_file(token: str, identificator : str, db: Session):
    backup_file = BackupFile()
 
    backup_file = db.scalar(select(BackupFile).where(
        BackupFile.id == UUID(identificator),
    ))

    if backup_file is None:
        backup_file = db.scalar(select(BackupFile).where(
            BackupFile.id_google_account == UUID(identificator)
        ))
        
    if backup_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="backup_file não encontrado")
    
    user = get_current_user(token, db)
    google_account = get_google_account(token, backup_file.id_google_account, db)
    if google_account.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
        
        
    return backup_file

def list_backup_files(token: str, db: Session, filters: dict | None) -> list[BackupFile]:
    user = get_current_user(token, db)
    stmt = select(BackupFile).join(
        BackupFile.google_account
        ).where(
        GoogleAccount.id_user == user.id
        )
 
    for k, v in filters.items():
        collum_attr = getattr(BackupFile, k)
        stmt = stmt.where(collum_attr == v)
    
    backup_files = db.scalars(stmt).all()
    
    if backup_files is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="backup_file não encontrado")
        
    return backup_files

def create_backup_file(token: str, backup_file_data: BackupFileCreate, db: Session) -> BackupFile:
    new_backup_file = BackupFile(
        id=uuid4(),
        id_google_account=backup_file_data.id_google_account,
        drive_file_id=backup_file_data.drive_file_id,
        local_ref=backup_file_data.local_ref,
        drive_version=backup_file_data.drive_version,
        content_hash=backup_file_data.content_hash,
    )
    new_backup_file.created_at = datetime.now()      
    db.add(new_backup_file)
    db.commit()
    db.refresh(new_backup_file)
    return new_backup_file

def delete_backup_file(token: str, identificator : str, db: Session) -> bool:
    backup_file = get_backup_file(token, identificator, db)
    db.delete(backup_file)
    db.commit()
    return True

################   
### Sync Log
################
def get_sync_log(token: str, identificator : str, db: Session):
    sync_log = SyncLog()
    user = get_current_user(token, db)    

    sync_log = db.scalar(select(SyncLog).join(
        Device, SyncLog.id_device == Device.id
        ).where(
        and_(
            SyncLog.id == UUID(identificator),
            Device.id_user == user.id
        )
     ))

        
    if sync_log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sync_log não encontrado")
            
    return sync_log

def list_sync_logs(token: str, db: Session, filters: dict | None) -> list[SyncLog]:
    user = get_current_user(token, db)
    stmt = select(SyncLog).join(
        Device, SyncLog.id_device == Device.id
        ).where(
        Device.id_user == user.id
        )
 
    for k, v in filters.items():
        collum_attr = getattr(SyncLog, k)
        stmt = stmt.where(collum_attr == v)
    
    sync_logs = db.scalars(stmt).all()
    
    if sync_logs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="sync_log não encontrado")
        
    return sync_logs

def create_sync_log(token: str, sync_log_data: SyncLogCreate, db: Session) -> SyncLog:
    new_sync_log = SyncLog(
        id=uuid4(),
        id_backup_file=sync_log_data.id_backup_file,
        id_device=sync_log_data.id_device,
        event=sync_log_data.event,
        derection=sync_log_data.derection,
        result=sync_log_data.result,
        conflict_strategy=sync_log_data.conflict_strategy,
        error_details=sync_log_data.error_details,
        metadata=sync_log_data.metadata,
        created_at=datetime.now()
    )
    new_sync_log.created_at = datetime.now()      
    db.add(new_sync_log)
    db.commit()
    db.refresh(new_sync_log)
    return new_sync_log

def delete_sync_log(token: str, identificator : str, db: Session) -> bool:
    sync_log = get_sync_log(token, identificator, db)
    db.delete(sync_log)
    db.commit()
    return True
