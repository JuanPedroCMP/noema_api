from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from .models import LoginData
from sqlalchemy.orm import Session
from .service import login
from ...core.database import get_db

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
