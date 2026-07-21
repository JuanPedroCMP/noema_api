from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ...core.security import oauth2_scheme
from ...core.database import get_db
from ...core.db_models.ai_models import TaskType
from .services import get_device as gd, list_devices as ld, create_device as cd, update_device as ud, delete_device as dd
from .models import DeviceOut, DeviceCreate, DeviceFilters, DeviceUpdate
from typing import Annotated

router = APIRouter(
    prefix="/device",
    tags=["Device"]
)


@router.get("/get/{identificator}", response_model=DeviceOut)
def get_device(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gd(token, identificator, db)

@router.get("/list", response_model=list[DeviceOut])
def list_device(filters: Annotated[DeviceFilters, Query()], db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):  
    _filters = filters.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True)
    
    return ld(token, db, _filters)

@router.post("/create", response_model=DeviceOut)
def create_device(new_user_device: DeviceCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    user_device = cd(token, new_user_device, db)
    return user_device

@router.put("/update/{identificator}", response_model=DeviceOut)
def update_device(identificator: str, user_device_data: DeviceUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = ud(token, identificator, user_device_data, db)
    return upd_data

@router.delete("/delete/{identificator}")
def delete_device(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sucess = dd(token, identificator, db)
    return sucess
