from fastapi import APIRouter, HTTPException, Depends
from .service import *
from ...core.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid
from ...core.db_models.app_auth_models import User
from ...core.security import get_current_user, oauth2_scheme, hash_password
from .models import UserCreate, UserUpdate
from datetime import datetime


def cr_user(user_data: UserCreate, db: Session) -> User:   
    user = User(
    id=uuid.uuid4(),
    user_name=user_data.user_name,
    primary_email=user_data.primary_email,
    user_display_name=user_data.user_display_name,
    password_hash=hash_password(user_data.password),
    created_at=datetime.now()
    )
        
    db.add(user)
    db.commit()
    db.refresh(instance=user)
        
    return user

def up_user(user_data: UserUpdate, token: str, db: Session): 
  user = get_current_user(token=token, db=db)
  udp_data = dict()
  
  for k, v in user_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        if k == "password":
            user.password_hash = hash_password(v)
            udp_data[k] = "**********"
        else:
            udp_data[k] = v
            setattr(user, k, v)
  user.updated_at = datetime.now()
  db.commit()
  db.refresh(user)
  return user



def del_user(token: str, db: Session) -> bool:
   user = get_current_user(token=token, db=db)
   db.delete(user)
   db.commit()
   return True


