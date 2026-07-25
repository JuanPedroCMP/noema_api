from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ...core.security import oauth2_scheme
from ...core.database import get_db
from ...core.db_models.ai_models import TaskType
from .services import create_generic_log as cgl, get_generic_log as ggl, list_generic_logs as lgl
from .models import GenericLogOut, GenericLogFilters, GenericLogCreate
from typing import Annotated

router = APIRouter(
    prefix="/generic_log",
    tags=["generic_log"]
)

@router.get("/get/{identificator}", response_model=GenericLogOut)
def get_generic_log(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return ggl(token, identificator, db)

@router.get("/list", response_model=list[GenericLogOut])
def list_generic_log(filters: Annotated[GenericLogFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return lgl(token, db, _filters)

@router.post("/create", response_model=GenericLogOut)
def create_generic_log(new_generic_log: GenericLogCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    generic_log = cgl(token, new_generic_log, db)
    return generic_log


