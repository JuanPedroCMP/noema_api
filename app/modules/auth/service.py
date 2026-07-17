from ...core.security import create_access_token, verify_password
from ...core.database import get_db
from sqlalchemy.orm import Session
from ...core.db_models.app_auth_models import User
from .models import LoginData
from sqlalchemy import select, or_
from fastapi import HTTPException, status

def login(login_data: LoginData, db: Session) -> dict:
  credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciais inválidas",
  )
    
  login_user = db.scalar(select(User).where(
    or_(
    User.primary_email == login_data.login_identificator,
    User.user_name == login_data.login_identificator
    )))
  
  if login_user is None: 
    raise credentials_exception
  
  if not login_user.is_active:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Conta desativada")

  if not verify_password(login_data.password, login_user.password_hash): 
    raise credentials_exception

  token = create_access_token(login_user.id)

  return {
    "access_token": token,
    "token_type": "bearer"
    }