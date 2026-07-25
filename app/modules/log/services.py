from ...core.db_models.log_models import GenericLog
from ...core.security import get_current_user
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from .models import GenericLogCreate, GenericLogCreate
from datetime import datetime

################   
### Generic Log
################
def get_generic_log(token: str, identificator : str, db: Session):
    user = get_current_user(token, db)    

    generic_log = db.scalar(select(GenericLog).where(
        and_(
            GenericLog.id == UUID(identificator),
            GenericLog.id_user == user.id
        )
     ))

        
    if generic_log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generic_log não encontrado")
            
    return generic_log

def list_generic_logs(token: str, db: Session, filters: dict | None) -> list[GenericLog]:
    user = get_current_user(token, db)
    stmt = select(GenericLog).where(
            GenericLog.id_user == user.id
        )
 
    for k, v in filters.items():
        collum_attr = getattr(GenericLog, k)
        stmt = stmt.where(collum_attr == v)
    
    generic_logs = db.scalars(stmt).all()
    
    if generic_logs is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="generic_log não encontrado")
        
    return generic_logs

def create_generic_log(token: str, generic_log_data: GenericLogCreate, db: Session) -> GenericLog:
    new_generic_log = GenericLog(
        id=uuid4(),
        type=generic_log_data.type,
        id_user=generic_log_data.id_user,
        details=generic_log_data.details,
        created_at=datetime.now()
    )
    new_generic_log.created_at = datetime.now()      
    db.add(new_generic_log)
    db.commit()
    db.refresh(new_generic_log)
    return new_generic_log

def delete_generic_log(token: str, identificator : str, db: Session) -> bool:
    generic_log = get_generic_log(token, identificator, db)
    db.delete(generic_log)
    db.commit()
    return True
