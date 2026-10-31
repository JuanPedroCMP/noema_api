from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from ...core.db_models.google_drive_models import (
    BackupFile,
    BackupOperationIdempotency,
    Device,
    GoogleAccount,
    SyncLog,
    User,
)
from ...core.security import get_current_user
from .models import (
    GOOGLE_DRIVE_APPDATA_SCOPE,
    BackupFileCreate,
    BackupMetadataCreate,
    BackupMetadataUpdate,
    GoogleAccountLinkRequest,
    GoogleAccountStatusOut,
    SyncLogCreate,
)
from .oauth import (
    verify_google_access_token,
    verify_google_identity,
    verify_google_tokens,
)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "resource_not_found"})


def _conflict(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": code, "message": message, **extra},
    )


def _serialize_scopes(scopes: list[str] | None) -> str:
    return " ".join(scopes or [])


def _account_status(account: GoogleAccount | None) -> GoogleAccountStatusOut:
    if account is None:
        return GoogleAccountStatusOut(
            account_id=None,
            google_email=None,
            state="not_linked",
            drive_appdata_granted=False,
            sync_available=False,
            granted_scopes=[],
            checked_at=None,
            error="google_account_not_linked",
        )
    scopes = sorted(set((account.granted_scopes or "").split()))
    state = account.drive_appdata_status or "unknown"
    if not account.is_active:
        state = "revoked"
    if state == "granted" and GOOGLE_DRIVE_APPDATA_SCOPE not in scopes:
        state = "missing"
    has_scope = GOOGLE_DRIVE_APPDATA_SCOPE in scopes and state == "granted"
    if state not in {"granted", "missing", "revoked", "unknown"}:
        state = "unknown"
    errors = {
        "missing": "drive_appdata_scope_missing",
        "revoked": "google_authorization_revoked",
        "unknown": "google_authorization_unverified",
    }
    return GoogleAccountStatusOut(
        account_id=account.id,
        google_email=account.email_google,
        state=state,
        drive_appdata_granted=has_scope,
        sync_available=has_scope,
        granted_scopes=scopes,
        checked_at=account.scope_checked_at,
        error=errors.get(state),
    )


def get_google_account_status(token: str, db: Session) -> GoogleAccountStatusOut:
    user = get_current_user(token, db)
    account = db.scalar(select(GoogleAccount).where(GoogleAccount.id_user == user.id))
    return _account_status(account)


async def link_google_account(
    token: str,
    link_request: GoogleAccountLinkRequest,
    db: Session,
) -> GoogleAccountStatusOut:
    user = get_current_user(token, db)
    google_user_id, email, scopes = await verify_google_tokens(
        link_request.google_id_token.get_secret_value(),
        link_request.google_access_token.get_secret_value(),
    )
    now = datetime.now(timezone.utc)
    accounts = db.scalars(
        select(GoogleAccount)
        .where(
            or_(
                GoogleAccount.id_user == user.id,
                GoogleAccount.google_user_id == google_user_id,
            )
        )
        .with_for_update()
    ).all()
    account_for_user = next(
        (account for account in accounts if account.id_user == user.id), None
    )
    account_for_google_user = next(
        (account for account in accounts if account.google_user_id == google_user_id),
        None,
    )
    if (
        account_for_google_user is not None
        and account_for_google_user.id_user != user.id
    ):
        raise _conflict(
            "google_account_unavailable",
            "This Google account cannot be linked to the authenticated user.",
        )
    if account_for_user is not None and account_for_user.google_user_id not in {
        None,
        google_user_id,
    }:
        raise _conflict(
            "google_account_already_linked",
            "Remove existing backup metadata before linking a different Google account.",
        )

    account = account_for_user or account_for_google_user
    drive_scope_granted = GOOGLE_DRIVE_APPDATA_SCOPE in scopes
    values = {
        "google_user_id": google_user_id,
        "email_google": email,
        "access_token_enc": None,
        "refresh_token_enc": None,
        "granted_scopes": _serialize_scopes(scopes),
        "drive_appdata_status": "granted" if drive_scope_granted else "missing",
        "scope_checked_at": now,
        "is_active": True,
        "updated_at": now,
    }
    if account is None:
        account = GoogleAccount(id=uuid4(), id_user=user.id, created_at=now, **values)
        db.add(account)
    else:
        for field, value in values.items():
            setattr(account, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        account = db.scalar(
            select(GoogleAccount).where(
                GoogleAccount.id_user == user.id,
                GoogleAccount.google_user_id == google_user_id,
            )
        )
        if account is not None and account.email_google == email:
            return _account_status(account)
        raise _conflict(
            "google_account_unavailable",
            "This Google account cannot be linked to the authenticated user.",
        ) from None
    db.refresh(account)
    return _account_status(account)


async def refresh_google_account_status(
    token: str,
    link_request: GoogleAccountLinkRequest,
    db: Session,
) -> GoogleAccountStatusOut:
    user = get_current_user(token, db)
    google_user_id, email = await verify_google_identity(
        link_request.google_id_token.get_secret_value()
    )
    account = db.scalar(
        select(GoogleAccount).where(GoogleAccount.id_user == user.id).with_for_update()
    )
    if account is None or account.google_user_id != google_user_id:
        raise _not_found()

    try:
        scopes = await verify_google_access_token(
            link_request.google_access_token.get_secret_value(),
            google_user_id,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if (
            exc.status_code != status.HTTP_401_UNAUTHORIZED
            or detail.get("code") != "invalid_google_authorization"
        ):
            raise
        account.drive_appdata_status = "revoked"
        account.granted_scopes = None
        account.scope_checked_at = datetime.now(timezone.utc)
        account.is_active = False
        account.updated_at = account.scope_checked_at
        db.commit()
        db.refresh(account)
        return _account_status(account)

    account.email_google = email
    account.granted_scopes = _serialize_scopes(scopes)
    account.drive_appdata_status = (
        "granted" if GOOGLE_DRIVE_APPDATA_SCOPE in scopes else "missing"
    )
    account.scope_checked_at = datetime.now(timezone.utc)
    account.is_active = True
    account.updated_at = account.scope_checked_at
    db.commit()
    db.refresh(account)
    return _account_status(account)


def _get_owned_account(
    token: str,
    account_id: UUID,
    db: Session,
    *,
    require_scope: bool = False,
) -> tuple[User, GoogleAccount]:
    user = get_current_user(token, db)
    account = db.scalar(
        select(GoogleAccount).where(
            GoogleAccount.id == account_id,
            GoogleAccount.id_user == user.id,
        )
    )
    if account is None:
        raise _not_found()
    if require_scope and _account_status(account).state != "granted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "drive_appdata_unavailable",
                "message": "Google Drive app-data authorization is not available.",
                "state": _account_status(account).state,
            },
        )
    return user, account


def _validate_owned_device(
    user: User,
    device_id: UUID | None,
    db: Session,
) -> None:
    if device_id is None:
        return
    device = db.scalar(
        select(Device).where(Device.id == device_id, Device.id_user == user.id)
    )
    if device is None:
        raise _not_found()


def get_backup_file(token: str, identificator: str, db: Session) -> BackupFile:
    user = get_current_user(token, db)
    try:
        backup_id = UUID(identificator)
    except ValueError:
        raise _not_found() from None
    backup = db.scalar(
        select(BackupFile)
        .join(GoogleAccount, BackupFile.id_google_account == GoogleAccount.id)
        .outerjoin(Device, BackupFile.id_device == Device.id)
        .where(
            BackupFile.id == backup_id,
            GoogleAccount.id_user == user.id,
            or_(BackupFile.id_device.is_(None), Device.id_user == user.id),
        )
    )
    if backup is None:
        raise _not_found()
    return backup


def list_backup_files(
    token: str,
    db: Session,
    filters: dict[str, Any] | None = None,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[BackupFile]:
    user = get_current_user(token, db)
    statement = (
        select(BackupFile)
        .join(GoogleAccount, BackupFile.id_google_account == GoogleAccount.id)
        .outerjoin(Device, BackupFile.id_device == Device.id)
        .where(GoogleAccount.id_user == user.id)
        .where(or_(BackupFile.id_device.is_(None), Device.id_user == user.id))
        .order_by(BackupFile.created_at.desc(), BackupFile.id)
        .limit(limit)
        .offset(offset)
    )
    allowed_filters = {
        "id",
        "id_google_account",
        "id_device",
        "drive_file_id",
        "local_ref",
        "snapshot_version",
        "operation_state",
    }
    for key, value in (filters or {}).items():
        if key not in allowed_filters:
            raise HTTPException(status_code=422, detail={"code": "invalid_filter"})
        statement = statement.where(getattr(BackupFile, key) == value)
    return list(db.scalars(statement).all())


def _manifest_value(manifest: Any) -> dict[str, Any] | None:
    return manifest.model_dump(mode="json") if manifest is not None else None


def _create_values(data: BackupMetadataCreate | BackupFileCreate) -> dict[str, Any]:
    return {
        "id_google_account": data.id_google_account,
        "id_device": data.id_device,
        "drive_file_id": data.drive_file_id,
        "local_ref": data.local_ref,
        "drive_version": data.drive_version,
        "snapshot_version": data.snapshot_version,
        "content_hash": data.content_hash,
        "size_bytes": data.size_bytes,
        "operation_state": data.operation_state,
        "manifest": _manifest_value(data.manifest),
        "idempotency_key": data.idempotency_key,
    }


def _operation_request_hash(operation_kind: str, data: Any) -> str:
    request_data = data.model_dump(mode="json", exclude={"idempotency_key"})
    canonical = json.dumps(
        {"operation_kind": operation_kind, "request": request_data},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _get_operation_receipt(
    db: Session, account_id: UUID, idempotency_key: str
) -> BackupOperationIdempotency | None:
    return db.scalar(
        select(BackupOperationIdempotency).where(
            BackupOperationIdempotency.id_google_account == account_id,
            BackupOperationIdempotency.idempotency_key == idempotency_key,
        )
    )


def _get_receipt_backup(db: Session, receipt: BackupOperationIdempotency) -> BackupFile:
    if receipt.id_backup_file is None:
        raise _conflict(
            "backup_metadata_deleted",
            "The metadata record for this completed operation has been deleted.",
        )
    backup = db.scalar(
        select(BackupFile).where(
            BackupFile.id == receipt.id_backup_file,
            BackupFile.id_google_account == receipt.id_google_account,
        )
    )
    if backup is None:
        raise _conflict(
            "backup_metadata_deleted",
            "The metadata record for this completed operation has been deleted.",
        )
    return backup


def create_backup_metadata(
    token: str,
    data: BackupMetadataCreate | BackupFileCreate,
    db: Session,
) -> BackupFile:
    user, _ = _get_owned_account(token, data.id_google_account, db, require_scope=True)
    _validate_owned_device(user, data.id_device, db)
    values = _create_values(data)
    request_hash = _operation_request_hash("create", data)
    receipt = _get_operation_receipt(db, data.id_google_account, data.idempotency_key)
    if receipt is not None:
        if receipt.operation_kind == "create" and receipt.request_hash == request_hash:
            return _get_receipt_backup(db, receipt)
        raise _conflict(
            "idempotency_key_reused",
            "The idempotency key was already used with different metadata.",
        )

    backup = BackupFile(id=uuid4(), created_at=datetime.now(timezone.utc), **values)
    receipt = BackupOperationIdempotency(
        id=uuid4(),
        id_google_account=data.id_google_account,
        idempotency_key=data.idempotency_key,
        operation_kind="create",
        request_hash=request_hash,
        id_backup_file=backup.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(backup)
    db.add(receipt)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        receipt = _get_operation_receipt(
            db, data.id_google_account, data.idempotency_key
        )
        if receipt is not None:
            if (
                receipt.operation_kind == "create"
                and receipt.request_hash == request_hash
            ):
                return _get_receipt_backup(db, receipt)
            raise _conflict(
                "idempotency_key_reused",
                "The idempotency key was already used with different metadata.",
            ) from None
        raise _conflict(
            "metadata_conflict",
            "Backup metadata could not be created without replacing current state.",
        ) from None
    db.refresh(backup)
    return backup


def create_legacy_backup_file(
    token: str,
    data: BackupFileCreate,
    db: Session,
) -> BackupFile:
    if data.idempotency_key is None:
        canonical = json.dumps(
            data.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        key = f"legacy-{hashlib.sha256(canonical.encode()).hexdigest()}"
        data = data.model_copy(update={"idempotency_key": key})
    return create_backup_metadata(token, data, db)


def update_backup_metadata(
    token: str,
    backup_id: UUID,
    data: BackupMetadataUpdate,
    db: Session,
) -> BackupFile:
    user = get_current_user(token, db)
    backup = db.scalar(
        select(BackupFile)
        .join(GoogleAccount, BackupFile.id_google_account == GoogleAccount.id)
        .outerjoin(Device, BackupFile.id_device == Device.id)
        .where(
            BackupFile.id == backup_id,
            GoogleAccount.id_user == user.id,
            or_(BackupFile.id_device.is_(None), Device.id_user == user.id),
        )
        .with_for_update(of=BackupFile)
    )
    if backup is None:
        raise _not_found()

    request_hash = _operation_request_hash("update", data)
    receipt = _get_operation_receipt(db, backup.id_google_account, data.idempotency_key)
    if receipt is not None:
        if (
            receipt.operation_kind == "update"
            and receipt.request_hash == request_hash
            and receipt.id_backup_file == backup.id
        ):
            return backup
        raise _conflict(
            "idempotency_key_reused",
            "The idempotency key was already used with different metadata.",
        )

    if (
        backup.drive_version != data.expected_drive_version
        or backup.content_hash != data.expected_content_hash
    ):
        from .models import BackupFileOut

        raise _conflict(
            "backup_version_conflict",
            "Backup metadata has changed since it was read.",
            current=BackupFileOut.model_validate(backup).model_dump(mode="json"),
        )

    backup.drive_version = data.drive_version
    backup.snapshot_version = data.snapshot_version
    backup.content_hash = data.content_hash
    backup.size_bytes = data.size_bytes
    backup.operation_state = data.operation_state
    backup.manifest = _manifest_value(data.manifest)
    backup.updated_at = datetime.now(timezone.utc)
    db.add(
        BackupOperationIdempotency(
            id=uuid4(),
            id_google_account=backup.id_google_account,
            idempotency_key=data.idempotency_key,
            operation_kind="update",
            request_hash=request_hash,
            id_backup_file=backup.id,
            created_at=datetime.now(timezone.utc),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        receipt = _get_operation_receipt(
            db, backup.id_google_account, data.idempotency_key
        )
        if (
            receipt is not None
            and receipt.operation_kind == "update"
            and receipt.request_hash == request_hash
            and receipt.id_backup_file == backup.id
        ):
            return _get_receipt_backup(db, receipt)
        if receipt is not None:
            raise _conflict(
                "idempotency_key_reused",
                "The idempotency key was already used with different metadata.",
            ) from None
        raise _conflict(
            "metadata_conflict",
            "Backup metadata could not be updated without replacing current state.",
        ) from None
    db.refresh(backup)
    return backup


def delete_backup_metadata(token: str, backup_id: UUID, db: Session) -> None:
    backup = get_backup_file(token, str(backup_id), db)
    db.delete(backup)
    db.commit()


def get_sync_log(token: str, identificator: str, db: Session) -> SyncLog:
    user = get_current_user(token, db)
    try:
        log_id = UUID(identificator)
    except ValueError:
        raise _not_found() from None
    backup_account = aliased(GoogleAccount)
    log = db.scalar(
        select(SyncLog)
        .outerjoin(Device, SyncLog.id_device == Device.id)
        .outerjoin(
            GoogleAccount,
            SyncLog.id_google_account == GoogleAccount.id,
        )
        .outerjoin(BackupFile, SyncLog.id_backup_file == BackupFile.id)
        .outerjoin(
            backup_account,
            BackupFile.id_google_account == backup_account.id,
        )
        .where(
            SyncLog.id == log_id,
            or_(SyncLog.id_user.is_(None), SyncLog.id_user == user.id),
            or_(SyncLog.id_device.is_(None), Device.id_user == user.id),
            or_(
                SyncLog.id_google_account.is_(None),
                GoogleAccount.id_user == user.id,
            ),
            or_(
                SyncLog.id_backup_file.is_(None),
                backup_account.id_user == user.id,
            ),
            or_(
                SyncLog.id_user == user.id,
                Device.id_user == user.id,
                GoogleAccount.id_user == user.id,
                backup_account.id_user == user.id,
            ),
        )
    )
    if log is None:
        raise _not_found()
    return log


def list_sync_logs(
    token: str,
    db: Session,
    filters: dict[str, Any] | None,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[SyncLog]:
    user = get_current_user(token, db)
    backup_account = aliased(GoogleAccount)
    statement = (
        select(SyncLog)
        .outerjoin(Device, SyncLog.id_device == Device.id)
        .outerjoin(
            GoogleAccount,
            SyncLog.id_google_account == GoogleAccount.id,
        )
        .outerjoin(BackupFile, SyncLog.id_backup_file == BackupFile.id)
        .outerjoin(
            backup_account,
            BackupFile.id_google_account == backup_account.id,
        )
        .where(
            or_(SyncLog.id_user.is_(None), SyncLog.id_user == user.id),
            or_(SyncLog.id_device.is_(None), Device.id_user == user.id),
            or_(
                SyncLog.id_google_account.is_(None),
                GoogleAccount.id_user == user.id,
            ),
            or_(
                SyncLog.id_backup_file.is_(None),
                backup_account.id_user == user.id,
            ),
            or_(
                SyncLog.id_user == user.id,
                Device.id_user == user.id,
                GoogleAccount.id_user == user.id,
                backup_account.id_user == user.id,
            ),
        )
        .order_by(SyncLog.created_at.desc(), SyncLog.id)
        .limit(limit)
        .offset(offset)
    )
    allowed_filters = {
        "id",
        "id_device",
        "id_backup_file",
        "id_google_account",
        "event",
        "direction",
        "result",
        "conflict_strategy",
    }
    for key, value in (filters or {}).items():
        if key == "derection":
            key = "direction"
        if key not in allowed_filters:
            raise HTTPException(status_code=422, detail={"code": "invalid_filter"})
        statement = statement.where(getattr(SyncLog, key) == value)
    return list(db.scalars(statement).all())


def create_sync_log(token: str, data: SyncLogCreate, db: Session) -> SyncLog:
    user = get_current_user(token, db)
    _validate_owned_device(user, data.id_device, db)
    backup = None
    if data.id_backup_file is not None:
        backup = db.scalar(
            select(BackupFile)
            .join(GoogleAccount, BackupFile.id_google_account == GoogleAccount.id)
            .where(
                BackupFile.id == data.id_backup_file,
                GoogleAccount.id_user == user.id,
            )
        )
        if backup is None:
            raise _not_found()
    account_id = data.id_google_account or (
        backup.id_google_account if backup is not None else None
    )
    if account_id is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "google_account_required"},
        )
    _get_owned_account(token, account_id, db)
    if backup is not None and backup.id_google_account != account_id:
        raise _not_found()

    if data.idempotency_key:
        existing = db.scalar(
            select(SyncLog).where(
                SyncLog.id_user == user.id,
                SyncLog.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None:
            expected = {
                "id_device": data.id_device,
                "id_backup_file": data.id_backup_file,
                "id_google_account": account_id,
                "event": data.event,
                "direction": data.derection,
                "result": data.result,
                "conflict_strategy": data.conflict_strategy,
                "error_details": data.error_details,
                "metadata_": data.metadata,
            }
            if all(getattr(existing, key) == value for key, value in expected.items()):
                return existing
            raise _conflict(
                "idempotency_key_reused",
                "The idempotency key was already used with different sync data.",
            )

    sync_log = SyncLog(
        id=uuid4(),
        id_user=user.id,
        id_google_account=account_id,
        id_backup_file=data.id_backup_file,
        id_device=data.id_device,
        idempotency_key=data.idempotency_key,
        event=data.event,
        direction=data.derection,
        result=data.result,
        conflict_strategy=data.conflict_strategy,
        error_details=data.error_details,
        metadata_=data.metadata,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sync_log)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if data.idempotency_key:
            existing = db.scalar(
                select(SyncLog).where(
                    SyncLog.id_user == user.id,
                    SyncLog.idempotency_key == data.idempotency_key,
                )
            )
            if existing is not None and all(
                getattr(existing, key) == value
                for key, value in {
                    "id_device": data.id_device,
                    "id_backup_file": data.id_backup_file,
                    "id_google_account": account_id,
                    "event": data.event,
                    "direction": data.derection,
                    "result": data.result,
                    "conflict_strategy": data.conflict_strategy,
                    "error_details": data.error_details,
                    "metadata_": data.metadata,
                }.items()
            ):
                return existing
        raise _conflict(
            "sync_log_conflict",
            "The sync event could not be recorded.",
        ) from None
    db.refresh(sync_log)
    return sync_log
