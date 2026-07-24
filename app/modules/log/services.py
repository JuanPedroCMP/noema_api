from ...core.db_models.log_models import GenericLog
from ...core.security import get_current_user, encrypt, decrypt
from sqlalchemy.orm import Session
from sqlalchemy import select, or_, and_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from ..auth.service import get_google_account
from .models import BackupFileCreate, GenericLogCreate
from datetime import datetime

################   
### Generic Log
################
def get_Genericlog(token: str, identificator : str, db: Session):
    Genericlog = GenericLog()
    user = get_current_user(token, db)    

    Genericlog = db.scalar(select(GenericLog).where(
        and_(
            GenericLog.id == UUID(identificator),
            GenericLog.id_user == user.id
        )
     ))

        
    if Genericlog is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Genericlog não encontrado")
            
    return Genericlog

def list_Genericlogs(token: str, db: Session, filters: dict | None) -> list[GenericLog]:
    user = get_current_user(token, db)
    stmt = select(GenericLog).where(
            GenericLog.id == user.id
        )
 
    for k, v in filters.items():
        collum_attr = getattr(GenericLog, k)
        stmt = stmt.where(collum_attr == v)
    
    Genericlogs = db.scalars(stmt).all()
    
    if Genericlogs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Genericlog não encontrado")
        
    return Genericlogs

def create_Genericlog(token: str, Genericlog_data: GenericLogCreate, db: Session) -> GenericLog:
    new_Genericlog = GenericLog(
        id=uuid4(),
        type=Genericlog_data.type,
        id_user=Genericlog_data.id_user,
        details=Genericlog_data.details,
        created_at=datetime.now()
    )
    new_Genericlog.created_at = datetime.now()      
    db.add(new_Genericlog)
    db.commit()
    db.refresh(new_Genericlog)
    return new_Genericlog

def delete_Genericlog(token: str, identificator : str, db: Session) -> bool:
    Genericlog = get_Genericlog(token, identificator, db)
    db.delete(Genericlog)
    db.commit()
    return True
