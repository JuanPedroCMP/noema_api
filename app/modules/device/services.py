from ...core.db_models.device_models import Device
from ...core.security import get_current_user
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from .models import DeviceCreate, DeviceUpdate, DeviceUpdate, DeviceCreate
from datetime import datetime

def get_device(token: str, identificator : str, db: Session):
    device = Device()
    try:  
        device = db.scalar(select(Device).where(
                Device.id == UUID(identificator),
        ))
    except:
        device = db.scalar(select(Device).where(
                Device.device_fingerprint == identificator
        ))
        
    user = get_current_user(token, db)

    if device.id_user != user.id:
        raise HTTPException(401, "Não autorizado")   
        
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    return device

def list_devices(token: str, db: Session, filters: dict | None) -> list[Device]:
    stmt = select(Device)
    user = get_current_user(token, db)

    stmt = stmt.where(Device.id_user == user.id)
    
    for k, v in filters.items():
        collum_attr = getattr(Device, k)
        stmt = stmt.where(collum_attr == v)
    
    devices = db.scalars(stmt).all()
    
    if devices is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    return devices

def create_device(token: str, device_data: DeviceCreate, db: Session) -> Device:
    user = get_current_user(token, db)
    
    if device_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    new_device = Device(
        id=uuid4(),
        id_user=device_data.id_user,
        device_name=device_data.device_name,
        device_fingerprint=device_data.device_fingerprint,
        platform=device_data.platform,
        created_at=datetime.now()
    )
    
    db.add(new_device)
    db.commit()
    db.refresh(new_device)
    return new_device

def update_device(token: str, identificator : str, device_data: DeviceUpdate, db: Session) -> Device:
    device = get_device(token, identificator, db)
    
    for k, v in device_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        setattr(device, k, v)
    device.updated_at = datetime.now()
    db.commit()
    db.refresh(device)
    return device

def delete_device(token: str, identificator : str, db: Session) -> bool:
    device = get_device(token, identificator, db)
    user = get_current_user(token, db)

    if device.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    db.delete(device)
    db.commit()
    return True
