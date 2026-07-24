from ...core.security import create_access_token, verify_password, get_current_user, decrypt, encrypt
from ...core.database import get_db
from sqlalchemy.orm import Session
from ...core.db_models.app_auth_models import User, GoogleAccount
from authlib.integrations.starlette_client import OAuth
from .models import LoginData, GoogleAccountCreate, GoogleAccountUpdate
from sqlalchemy import select, or_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from datetime import datetime


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
  
################
### Google Account
################
def get_google_account(token: str, identificator : str, db: Session):    
    google_account = db.scalar(select(GoogleAccount).where(
      GoogleAccount.id == UUID(identificator),
    ))

    if google_account is None:
      google_account = db.scalar(select(GoogleAccount).where(
        GoogleAccount.id_user == UUID(identificator)
      ))
      
    if google_account is None:
      google_account = db.scalar(select(GoogleAccount).where(
        GoogleAccount.google_user_id == identificator
      ))
        
    user = get_current_user(token, db)

    if google_account.id_user != user.id:
        raise HTTPException(401, "Não autorizado")   
        
    if google_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="color theme não encontrado")
        
    return google_account

def create_google_account(token: str, google_account_data: GoogleAccountCreate, db: Session) -> GoogleAccount:
    user = get_current_user(token, db)
    
    if google_account_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    new_google_account = GoogleAccount(
        id=uuid4(),
        id_user=google_account_data.id_user,
        google_user_id=google_account_data.google_user_id,
        email_google=google_account_data.email_google,
        access_token_enc=google_account_data.access_token_enc,
        refresh_token_enc=google_account_data.refresh_token_enc,
        granted_scopes=google_account_data.granted_scopes,
        is_active=google_account_data.is_active,
        expires_at=google_account_data.expires_at,
        created_at=datetime.now()
    )
    
    db.add(new_google_account)
    db.commit()
    db.refresh(new_google_account)
    return new_google_account

def update_google_account(token: str, identificator : str, google_account_data: GoogleAccountUpdate, db: Session) -> GoogleAccount:
    google_account = get_google_account(token, identificator, db)
    
    user = get_current_user(token, db)
    
    if google_account_data.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
    
    for k, v in google_account_data.model_dump(exclude_unset=True, exclude_none=True, exclude_defaults=True).items():  
        if k == "access_token_enc" or k == "refresh_token_enc":
          setattr(google_account, k, encrypt(v))
        else:
          setattr(google_account, k, v)
    google_account.updated_at = datetime.now()
    db.commit()
    db.refresh(google_account)
    return google_account

def delete_google_account(token: str, identificator : str, db: Session) -> bool:
    google_account = get_google_account(token, identificator, db)

    db.delete(google_account)
    db.commit()
    return True