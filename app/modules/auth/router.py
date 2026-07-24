from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from .models import LoginData, GoogleAccountCreate, GoogleAccountOut, GoogleAccountUpdate
from sqlalchemy.orm import Session
from .service import login, get_google_account as gga, create_google_account as cga, update_google_account as uga, delete_google_account as dga
from ...core.database import get_db
from ...core.security import oauth2_scheme

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/login")
def authenticate(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    token = login(LoginData(login_identificator=form_data.username, password=form_data.password), db)

    if not token:
        raise HTTPException(401, detail="Credenciais invalidas")
    return token

################
### google_account
################
@router.get("/google/get/{identificator}", response_model=GoogleAccountOut)
def get_google_account(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    return gga(identificator, db)

@router.post("/google/create", response_model=GoogleAccountOut)
def create_google_account(new_google_account: GoogleAccountCreate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    google_account = cga(new_google_account, db)
    return google_account

@router.put("/google/update/{identificator}", response_model=GoogleAccountOut)
def update_google_account(identificator: str, google_account_data: GoogleAccountUpdate, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    upd_data = uga(identificator, google_account_data, db)
    return upd_data

@router.delete("/google/delete/{identificator}")
def delete_google_account(identificator: str, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    sucess = dga(token, identificator, db)
    return sucess
