from fastapi import APIRouter, HTTPException, Depends
from .service import cr_user, up_user, del_user
from ...core.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid
from ...core.db_models.app_auth_models import User
from ...core.security import get_current_user, oauth2_scheme, hash_password
from .models import UserCreate, UserUpdate
from datetime import datetime

router = APIRouter(
    prefix="/user",
    tags=["User"]
)

@router.get("/get")
def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    return user

@router.post("/create")
def new_user(user_data: UserCreate, db: Session = Depends(get_db)):   
    try:
        user = cr_user(user_data=user_data, db=db)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {"success": "Usuario criado com sucesso!",
            "user": user}

@router.put("/update")
def update_user(user_data: UserUpdate, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)): 
    try:
     upd_user = up_user(user_data, token, db)
    except ValueError as e:
     raise HTTPException(400, detail=str(e))
    except Exception as e:
     raise HTTPException(400, detail=str(e))

    return {"message": "Sucesso!",
          "upd data": upd_user }

@router.delete("/delete")
def delete_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        del_user(token, db) #TODO Revogar token no momento de deletar e de fazer logout, também implementar refresh token
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {"message": "Sucesso!"}
