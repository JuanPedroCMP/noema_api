import logging
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...core.database import session
from ...core.db_models.log_models import ErrorLog, GenericLog
from ...core.security import get_current_user
from fastapi import HTTPException, status
from .models import GenericLogCreate

logger = logging.getLogger(__name__)


def _request_context(request: Request) -> dict[str, Any]:
    route = request.scope.get("route")
    client = request.client
    return {
        "request_id": getattr(request.state, "request_id", None),
        "method": request.method,
        "endpoint": getattr(route, "path", request.url.path),
        "path": request.url.path,
        "client_ip": client.host if client else None,
        "user_agent": request.headers.get("user-agent"),
    }


def record_request_metrics(
    request: Request,
    status_code: int,
    duration_ms: float,
) -> None:
    details = {
        **_request_context(request),
        "status_code": status_code,
        "duration_ms": round(duration_ms, 3),
        "content_length": request.headers.get("content-length"),
    }
    db = session()
    try:
        db.add(
            GenericLog(
                id=uuid4(),
                type="http_request",
                id_user=None,
                details=details,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not persist HTTP request metrics")
    finally:
        db.close()


def record_error(
    request: Request,
    status_code: int,
    error_type: str,
    message: str,
    traceback_text: str | None = None,
) -> None:
    details = {
        **_request_context(request),
        "status_code": status_code,
        "error_type": error_type,
        "message": message,
        "traceback": traceback_text,
    }
    request.state.error_logged = True
    db = session()
    try:
        db.add(
            ErrorLog(
                id=uuid4(),
                id_user=None,
                error_details=details,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not persist API error report")
    finally:
        db.close()


def record_exception(
    request: Request,
    status_code: int,
    exc: Exception,
) -> None:
    record_error(
        request,
        status_code,
        type(exc).__name__,
        str(exc),
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )

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
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_generic_log)
    db.commit()
    db.refresh(new_generic_log)
    return new_generic_log

def delete_generic_log(token: str, identificator : str, db: Session) -> bool:
    generic_log = get_generic_log(token, identificator, db)
    db.delete(generic_log)
    db.commit()
    return True
