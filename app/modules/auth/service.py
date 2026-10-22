from dotenv import load_dotenv

from app.modules.user.models import UserUpdate
from app.modules.user.service import get_user_by_identificator, up_user

from ...core.security import create_access_token, hash_password, verify_password, get_current_user, decrypt, encrypt
from ...core.database import get_db
from sqlalchemy.orm import Session
from ...core.db_models.app_auth_models import PasswordResetToken, User, GoogleAccount
from authlib.integrations.starlette_client import OAuth
from .models import LoginData, GoogleAccountCreate, GoogleAccountUpdate
from sqlalchemy import select, or_, and_
from fastapi import HTTPException, status
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
from html import escape
import random
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


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


def start_reset_password(token: str, db: Session):
  code : str = str(random.randint(100000, 999999))
  created_at = datetime.now()
  expires_at = datetime.now() + timedelta(minutes=10)
  
  user = get_user_by_identificator(db=db, identificator=token)
    
  pwd_reset = PasswordResetToken(
    id = uuid4(),
    user_id = user.id,
    token_hash = code,
    created_at = created_at,
    expires_at = expires_at
  )
  
  # Configurações de e-mail
  load_dotenv(dotenv_path='app/config/.env.security')
  remetente = os.getenv("SMTP_USERNAME", "noema.app.services@gmail.com")
  senha = os.getenv("SMTP_PASSWORD")
  if not senha:
      raise RuntimeError("SMTP_PASSWORD não está configurada.")

  destinatario = user.primary_email
  
  assunto = "Redefinição de senha | Noema"

  # Criando a estrutura da mensagem
  msg = MIMEMultipart("alternative")
  msg["From"] = remetente
  msg["To"] = destinatario
  msg["Subject"] = assunto
  
  
  created_at_text = created_at.strftime("%d/%m/%Y às %H:%M")
  expires_at_text = expires_at.strftime("%d/%m/%Y às %H:%M")
  html_content = f"""
  <!doctype html>
  <html lang="pt-BR">
    <body style="margin:0;background:#f7f9fa;font-family:Arial,Helvetica,sans-serif;color:#263238;">
      <div style="padding:40px 16px;">
        <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e5eaec;border-radius:10px;">
          <div style="padding:28px 32px 22px;border-bottom:1px solid #edf0f1;">
            <div style="font-size:12px;font-weight:bold;letter-spacing:2px;color:#2e6c80;text-transform:uppercase;">Noema</div>
            <h1 style="margin:12px 0 0;font-size:22px;font-weight:600;line-height:1.3;color:#263238;">Redefinição de senha</h1>
          </div>
          <div style="padding:28px 32px 32px;">
            <p style="margin:0 0 14px;font-size:15px;">Olá,</p>
            <p style="margin:0;font-size:15px;line-height:1.6;color:#52636a;">Recebemos uma solicitação para redefinir a senha da sua conta Noema.</p>
            <p style="margin:28px 0 10px;font-size:12px;font-weight:bold;letter-spacing:1px;color:#718187;text-transform:uppercase;">Código de verificação</p>
            <div style="padding:18px 20px;text-align:center;background:#f7fafb;border:1px solid #dbe8eb;border-radius:8px;font-size:30px;font-weight:600;letter-spacing:8px;color:#2e6c80;">{escape(code)}</div>
            <p style="margin:16px 0 0;font-size:13px;line-height:1.5;color:#718187;">Este código expira em 10 minutos. Não compartilhe com outras pessoas.</p>
            <p style="margin:24px 0 0;padding-top:20px;border-top:1px solid #edf0f1;font-size:12px;line-height:1.6;color:#718187;">Solicitado em: {created_at_text}<br>Expira em: {expires_at_text}</p>
            <p style="margin:20px 0 0;font-size:13px;line-height:1.6;color:#52636a;">Se você não solicitou essa alteração, ignore este e-mail. Sua senha permanecerá a mesma.</p>
            <p style="margin:28px 0 0;font-size:13px;line-height:1.5;">Atenciosamente,<br><strong style="color:#2e6c80;">Equipe Noema</strong></p>
          </div>
        </div>
        <p style="max-width:520px;margin:16px auto 0;text-align:center;font-size:11px;color:#8a999e;">Mensagem automática. Por favor, não responda.</p>
      </div>
    </body>
  </html>
  """
  text_content = f"""Redefinição de senha | Noema

Olá,

Recebemos uma solicitação para redefinir a senha da sua conta Noema.

Seu código de verificação é: {code}

Solicitado em: {created_at_text}
Expira em: {expires_at_text}

Se você não solicitou essa alteração, ignore este e-mail.

Atenciosamente,
Equipe Noema
"""
  
  db.add(pwd_reset)
  db.commit()
  db.refresh(instance=pwd_reset)

  msg.attach(MIMEText(text_content, "plain", "utf-8"))
  msg.attach(MIMEText(html_content, "html", "utf-8"))
  
  # Conexão com o servidor SMTP do Gmail
  try:
      # Usando a porta 587 com TLS
      servidor = smtplib.SMTP("smtp.gmail.com", 587)
      servidor.starttls()
      servidor.login(remetente, senha)
      servidor.sendmail(remetente, destinatario, msg.as_string())
      servidor.quit()
  except smtplib.SMTPException as exc:
      raise RuntimeError("Não foi possível enviar o e-mail de redefinição.") from exc
            
  print(code)
  return

def confirm_password_reset(code: str, token: str, db: Session, new_password):
  user = get_user_by_identificator(db=db, identificator=token)

  
  reset_call = db.scalar(
    select(PasswordResetToken).where(
      and_(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.now(),
        PasswordResetToken.token_hash == code,
      )
    )
  )
  if reset_call:
    reset_call.used_at = datetime.now()
    db.commit()
    db.refresh(reset_call)
    
    user_data = UserUpdate(password=new_password)
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
    return 'Sucesso' ## TODO concertar
  return 'Falha'

  
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

    if google_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google account not found",
        )

    if google_account.id_user != user.id:
        raise HTTPException(401, "Não autorizado")
        
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