from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import oauth2_scheme
from .models import GoogleAccountOut, LoginData
from .service import confirm_password_reset, login, start_reset_password
from .service import delete_google_account as dga
from .service import get_google_account as gga

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def authenticate(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    token = login(
        LoginData(login_identificator=form_data.username, password=form_data.password),
        db,
    )

    if not token:
        raise HTTPException(401, detail="Credenciais invalidas")
    return token


@router.post("/call_password_rest")
def send_pwd_reset(identificator: str, db: Session = Depends(get_db)):
    return start_reset_password(token=identificator, db=db)


@router.post("/confirm_password_rest")
def confirm_pwd_reset(
    identificator: str, new_password: str, code: str, db: Session = Depends(get_db)
):
    return confirm_password_reset(
        token=identificator, db=db, code=code, new_password=new_password
    )


################
### google_account
################
@router.get("/google/get/{identificator}", response_model=GoogleAccountOut)
def get_google_account(
    identificator: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    return gga(token, identificator, db)


@router.post("/google/create", deprecated=True)
def create_google_account(token: str = Depends(oauth2_scheme)):
    raise HTTPException(
        status_code=410,
        detail={
            "code": "google_account_write_flow_retired",
            "message": "Link Google accounts through /api/v1/google_drive/account/link.",
        },
    )


@router.put("/google/update/{identificator}", deprecated=True)
def update_google_account(
    identificator: str,
    token: str = Depends(oauth2_scheme),
):
    raise HTTPException(
        status_code=410,
        detail={
            "code": "google_account_write_flow_retired",
            "message": "Google credentials and scopes cannot be set through this endpoint.",
        },
    )


@router.delete("/google/delete/{identificator}")
def delete_google_account(
    identificator: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    sucess = dga(token, identificator, db)
    return sucess
