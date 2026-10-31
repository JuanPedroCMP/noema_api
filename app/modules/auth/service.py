import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.modules.user.models import UserUpdate, validate_password_strength
from app.modules.user.service import get_user_by_identificator

from ...core.db_models.app_auth_models import GoogleAccount, PasswordResetToken, User
from ...core.db_models.google_drive_models import BackupFile
from ...core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from .models import GoogleAccountOut, LoginData


def login(login_data: LoginData, db: Session) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
    )

    login_user = db.scalar(
        select(User).where(
            or_(
                User.primary_email == login_data.login_identificator,
                User.user_name == login_data.login_identificator,
            )
        )
    )

    if login_user is None:
        raise credentials_exception

    if not login_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Conta desativada"
        )

    if not verify_password(login_data.password, login_user.password_hash):
        raise credentials_exception

    token = create_access_token(login_user.id)

    return {"access_token": token, "token_type": "bearer"}


def start_reset_password(token: str, db: Session):
    code: str = f"{secrets.randbelow(1_000_000):06d}"
    created_at = datetime.now()
    expires_at = datetime.now() + timedelta(minutes=10)

    user = get_user_by_identificator(db=db, identificator=token)

    pwd_reset = PasswordResetToken(
        id=uuid4(),
        user_id=user.id,
        token_hash=code,
        created_at=created_at,
        expires_at=expires_at,
    )

    # Configurações de e-mail
    load_dotenv(dotenv_path="app/config/.env.security")
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
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as servidor:
            servidor.starttls()
            servidor.login(remetente, senha)
            servidor.sendmail(remetente, destinatario, msg.as_string())
    except smtplib.SMTPException as exc:
        db.rollback()
        raise RuntimeError("Não foi possível enviar o e-mail de redefinição.") from exc

    return {"message": "If the account exists, reset instructions were sent."}


def confirm_password_reset(code: str, token: str, db: Session, new_password):
    validate_password_strength(new_password)
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

        user_data = UserUpdate(password=new_password)
        udp_data = dict()
        for k, v in user_data.model_dump(
            exclude_unset=True, exclude_none=True, exclude_defaults=True
        ).items():
            if k == "password":
                user.password_hash = hash_password(v)
                udp_data[k] = "**********"
            else:
                udp_data[k] = v
                setattr(user, k, v)
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
        return "Sucesso"  ## TODO concertar
    return "Falha"


################
### Google Account
################
def _google_account_filters(identificator: str) -> list[ColumnElement[bool]]:
    account_identifiers = [GoogleAccount.google_user_id == identificator]
    try:
        account_uuid = UUID(identificator)
    except ValueError:
        account_uuid = None
    if account_uuid is not None:
        account_identifiers.extend(
            [
                GoogleAccount.id == account_uuid,
                GoogleAccount.id_user == account_uuid,
            ]
        )
    return account_identifiers


def get_google_account_out(
    token: str, identificator: str, db: Session
) -> GoogleAccountOut:
    user = get_current_user(token, db)
    row = (
        db.execute(
            select(
                GoogleAccount.id,
                GoogleAccount.id_user,
                GoogleAccount.google_user_id,
                GoogleAccount.email_google,
                GoogleAccount.granted_scopes,
                GoogleAccount.is_active,
                GoogleAccount.expires_at,
                GoogleAccount.last_refresh_at,
                GoogleAccount.updated_at,
                GoogleAccount.created_at,
                text(
                    "COALESCE("
                    "to_jsonb(google_account)->>'drive_appdata_status', "
                    "'unknown'"
                    ") AS drive_appdata_status"
                ),
                text(
                    "NULLIF("
                    "to_jsonb(google_account)->>'scope_checked_at', "
                    "''"
                    ")::timestamptz AS scope_checked_at"
                ),
            ).where(
                GoogleAccount.id_user == user.id,
                or_(*_google_account_filters(identificator)),
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google account not found",
        )

    return GoogleAccountOut.model_validate(row)


def get_google_account(token: str, identificator: str, db: Session) -> GoogleAccountOut:
    return get_google_account_out(token, identificator, db)


def delete_google_account(token: str, identificator: str, db: Session) -> bool:
    user = get_current_user(token, db)
    account = db.scalar(
        select(GoogleAccount)
        .where(
            GoogleAccount.id_user == user.id,
            or_(*_google_account_filters(identificator)),
        )
        .with_for_update()
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google account not found",
        )
    backup_id = db.scalar(
        select(BackupFile.id)
        .where(BackupFile.id_google_account == account.id)
        .limit(1)
    )
    if backup_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "google_account_has_backups",
                "message": (
                    "Delete this account's backup metadata before unlinking it."
                ),
            },
        )
    db.delete(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "google_account_has_backups",
                "message": (
                    "Delete this account's backup metadata before unlinking it."
                ),
            },
        ) from None
    return True
