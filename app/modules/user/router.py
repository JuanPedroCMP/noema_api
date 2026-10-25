from fastapi import APIRouter, Depends
from .service import cr_user, up_user, del_user
from ...core.database import get_db
from sqlalchemy.orm import Session
from ...core.security import get_current_user, oauth2_scheme
from .models import UserCreate, UserOut, UserUpdate

router = APIRouter(
    prefix="/user",
    tags=["User"]
)

@router.get("/get", response_model=UserOut)
def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_current_user(token, db)
    return user

@router.post("/create", response_model=UserOut)
def new_user(user_data: UserCreate, db: Session = Depends(get_db)):   
    return cr_user(user_data=user_data, db=db)

@router.put("/update", response_model=UserOut)
def update_user(user_data: UserUpdate, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)): 
    return up_user(user_data, token, db)

@router.delete("/delete")
def delete_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    del_user(token, db)
    return {"message": "Sucesso!"}
