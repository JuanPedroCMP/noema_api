from __future__ import annotations

from collections import defaultdict, deque
import re
from threading import Lock
from time import monotonic
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.db_models.google_drive_models import SyncDirection
from ...core.security import get_current_user, oauth2_scheme
from .models import (
    BackupFileCreate,
    BackupFileFilters,
    BackupFileOut,
    BackupMetadataCreate,
    BackupMetadataUpdate,
    GoogleAccountStatusOut,
    SyncLogCreate,
    SyncLogFilters,
    SyncLogOut,
    OAuthCompleteRequest,
    OAuthStartRequest,
    SyncOperationCreate,
    SyncOperationOut,
    AccountRefreshOut,
    SnapshotManifest,
)
from .services import (
    create_backup_metadata,
    create_legacy_backup_file,
    create_sync_log,
    delete_backup_metadata,
    get_google_account_status,
    list_backup_files,
    list_sync_logs,
    update_backup_metadata,
)
from .worker import (
    create_or_get_operation,
    lock_sync_target,
    mark_failed,
    process_operation,
    unlock_sync_target,
)
from .server_oauth import (
    oauth_cancel,
    oauth_callback,
    oauth_start,
    refresh_access_token,
    unlink_google_account,
)
from .transfer import (
    delete_drive_file,
    list_drive_files,
    upload_snapshot,
    stream_snapshot,
)
from ...core.db_models.google_drive_models import BackupFile, Device, GoogleAccount, OAuthState, SyncOperation
from sqlalchemy import select
from datetime import datetime, timezone
from .services import (
    get_backup_file as service_get_backup_file,
)
from .services import (
    get_sync_log as service_get_sync_log,
)

oauth2_account_router = APIRouter(prefix="/account", tags=["Google Drive OAuth"])
backup_file_router = APIRouter(prefix="/backup_file", tags=["backup_file"])
sync_log_router = APIRouter(prefix="/sync_log", tags=["sync_log"])

_RATE_LIMIT_WINDOW_SECONDS = 60
_GOOGLE_OAUTH_RATE_LIMIT = 10
_API_RATE_LIMIT = 120
_rate_limit_requests: dict[str, deque[float]] = defaultdict(deque)
_rate_limit_lock = Lock()


def _consume_rate_limit(user_id: str, limit: int, code: str, message: str) -> None:
    now = monotonic()
    with _rate_limit_lock:
        for key in tuple(_rate_limit_requests):
            hits = _rate_limit_requests[key]
            while hits and now - hits[0] >= _RATE_LIMIT_WINDOW_SECONDS:
                hits.popleft()
            if not hits:
                del _rate_limit_requests[key]
        requests = _rate_limit_requests[user_id]
        if len(requests) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": code, "message": message},
                headers={"Retry-After": str(_RATE_LIMIT_WINDOW_SECONDS)},
            )
        requests.append(now)


def api_rate_limit(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> None:
    user = get_current_user(token, db)
    _consume_rate_limit(
        f"api:{user.id}",
        _API_RATE_LIMIT,
        "google_drive_rate_limited",
        "Google Drive metadata requests are temporarily rate limited.",
    )


def google_oauth_rate_limit(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> None:
    user = get_current_user(token, db)
    _consume_rate_limit(
        f"oauth:{user.id}",
        _GOOGLE_OAUTH_RATE_LIMIT,
        "google_oauth_rate_limited",
        "Google authorization checks are temporarily rate limited.",
    )


router = APIRouter(
    prefix="/google_drive",
    tags=["Google Drive sync"],
    dependencies=[Depends(api_rate_limit)],
)
public_oauth_router = APIRouter(prefix="/google_drive/oauth", tags=["Google Drive OAuth"])
transfer_router = APIRouter(
    prefix="/google_drive",
    tags=["Google Drive transfer"],
    dependencies=[Depends(api_rate_limit)],
)


@oauth2_account_router.get(
    "/status",
    response_model=GoogleAccountStatusOut,
    summary="Get Google account and Drive app-data authorization state",
)
def google_account_status(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> GoogleAccountStatusOut:
    return get_google_account_status(token, db)


@public_oauth_router.post("/start")
def oauth_start_endpoint(
    payload: OAuthStartRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> dict[str, str]:
    return oauth_start(token, payload.redirect_uri, db)


@public_oauth_router.get("/callback")
async def oauth_callback_endpoint(
    state: str,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    if error is not None:
        oauth_cancel(state, db, error)
        return HTMLResponse(
            "<!doctype html><html><meta charset='utf-8'><title>Noema</title>"
            "<p>A autorização foi cancelada. Você pode fechar esta página e "
            "voltar ao Noema.</p></html>",
            status_code=200,
        )
    if not code:
        raise HTTPException(status_code=400, detail={"code": "google_oauth_code_missing"})
    try:
        await oauth_callback(code, state, db)
    except HTTPException:
        db.rollback()
        try:
            oauth_cancel(state, db, "oauth_error")
        except HTTPException as state_error:
            detail = state_error.detail if isinstance(state_error.detail, dict) else {}
            if detail.get("code") != "invalid_oauth_state":
                raise
        return HTMLResponse(
            "<!doctype html><html><meta charset='utf-8'><title>Noema</title>"
            "<p>Não foi possível concluir a autorização. Volte ao Noema para "
            "ver os detalhes e tentar novamente.</p></html>",
            status_code=200,
        )
    return HTMLResponse(
        "<!doctype html><html><meta charset='utf-8'><title>Noema</title>"
        "<p>Google Drive conectado. Volte ao Noema para continuar.</p></html>",
        status_code=200,
    )


@oauth2_account_router.post("/refresh", response_model=AccountRefreshOut)
async def refresh_account(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> AccountRefreshOut:
    user = get_current_user(token, db)
    account = db.scalar(select(GoogleAccount).where(GoogleAccount.id_user == user.id))
    if account is None:
        raise HTTPException(status_code=404, detail={"code": "google_account_not_linked"})
    await refresh_access_token(account, db)
    return AccountRefreshOut(account_id=account.id, refreshed=True, state="granted")


@oauth2_account_router.post("/complete", response_model=GoogleAccountStatusOut)
def complete_oauth(
    payload: OAuthCompleteRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> GoogleAccountStatusOut:
    user = get_current_user(token, db)
    import hashlib

    state_row = db.scalar(
        select(OAuthState)
        .where(
            OAuthState.state_hash == hashlib.sha256(payload.state.encode()).hexdigest(),
            OAuthState.id_user == user.id,
        )
        .with_for_update()
    )
    if state_row is None or state_row.consumed_at is None:
        if state_row is not None and state_row.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail={"code": "oauth_state_expired"})
        raise HTTPException(status_code=409, detail={"code": "oauth_completion_pending"})
    if state_row.error_code:
        raise HTTPException(
            status_code=409,
            detail={"code": state_row.error_code},
        )
    if state_row.completion_consumed_at is None:
        state_row.completion_consumed_at = datetime.now(timezone.utc)
        db.commit()
    return get_google_account_status(token, db)


@oauth2_account_router.delete("/unlink")
async def unlink_account(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> dict[str, bool]:
    user = get_current_user(token, db)
    account = db.scalar(select(GoogleAccount).where(GoogleAccount.id_user == user.id).with_for_update())
    if account is None:
        return {"unlinked": True, "google_grant_revoked": True}
    google_grant_revoked = await unlink_google_account(account, db)
    return {"unlinked": True, "google_grant_revoked": google_grant_revoked}


@router.post("/sync/operations", response_model=SyncOperationOut, status_code=202)
async def create_sync_operation(
    payload: SyncOperationCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> SyncOperation:
    user = get_current_user(token, db)
    account = db.scalar(select(GoogleAccount).where(
        GoogleAccount.id == payload.id_google_account,
        GoogleAccount.id_user == user.id,
    ))
    if account is None:
        raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
    if payload.id_device is not None and db.scalar(select(Device).where(
        Device.id == payload.id_device,
        Device.id_user == user.id,
    )) is None:
        raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
    if payload.backup_id is not None and db.scalar(
        select(BackupFile).where(
            BackupFile.id == payload.backup_id,
            BackupFile.id_google_account == account.id,
        )
    ) is None:
        raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
    if payload.operation_kind == "upload":
        raise HTTPException(
            status_code=422,
            detail={"code": "use_sync_upload_for_upload_operations"},
        )
    request_payload = payload.model_dump(mode="json", exclude={"idempotency_key"})
    operation = create_or_get_operation(
        db,
        id_user=user.id,
        id_google_account=account.id,
        id_device=payload.id_device,
        local_ref=payload.local_ref,
        operation_kind=payload.operation_kind,
        idempotency_key=payload.idempotency_key,
        payload=request_payload,
        backup_id=payload.backup_id,
    )
    return await process_operation(db, operation.id) or operation


@router.get("/sync/operations/{operation_id}", response_model=SyncOperationOut)
def get_sync_operation(
    operation_id: UUID,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> SyncOperation:
    user = get_current_user(token, db)
    operation = db.scalar(select(SyncOperation).where(
        SyncOperation.id == operation_id, SyncOperation.id_user == user.id
    ))
    if operation is None:
        raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
    return operation


@router.get("/sync/operations", response_model=list[SyncOperationOut])
def list_sync_operations(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> list[SyncOperation]:
    user = get_current_user(token, db)
    return list(db.scalars(select(SyncOperation).where(
        SyncOperation.id_user == user.id
    ).order_by(SyncOperation.created_at.desc()).limit(100)).all())


@transfer_router.post("/sync/upload", response_model=BackupFileOut, status_code=201)
async def upload_backup_snapshot(
    id_google_account: UUID = Form(...),
    local_ref: str = Form(...),
    snapshot_version: str = Form(...),
    content_hash: str = Form(...),
    manifest: str = Form(...),
    idempotency_key: str = Form(...),
    backup_id: UUID | None = Form(default=None),
    expected_drive_version: str | None = Form(default=None),
    expected_content_hash: str | None = Form(default=None),
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> BackupFileOut:
    try:
        parsed_manifest = SnapshotManifest.model_validate_json(manifest)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "snapshot_validation_failed"}) from exc
    if (
        not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", local_ref)
        or not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", idempotency_key)
        or not re.fullmatch(r"(?:sha256:)?[A-Fa-f0-9]{16,128}", content_hash)
        or len(snapshot_version) > 128
    ):
        raise HTTPException(status_code=422, detail={"code": "snapshot_validation_failed"})
    user = get_current_user(token, db)
    if db.scalar(
        select(GoogleAccount).where(
            GoogleAccount.id == id_google_account,
            GoogleAccount.id_user == user.id,
        )
    ) is None:
        raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
    has_revision_fields = (
        expected_drive_version is not None,
        expected_content_hash is not None,
    )
    if (
        (backup_id is None and any(has_revision_fields))
        or (backup_id is not None and not all(has_revision_fields))
        or (
            backup_id is not None
            and (
                not expected_drive_version
                or len(expected_drive_version) > 128
                or not expected_content_hash
                or not re.fullmatch(
                    r"(?:sha256:)?[A-Fa-f0-9]{16,128}",
                    expected_content_hash,
                )
            )
        )
    ):
        raise HTTPException(
            status_code=422,
            detail={"code": "backup_revision_fields_required"},
        )
    sync_lock = lock_sync_target(db, id_google_account, local_ref)
    try:
        operation = create_or_get_operation(
            db,
            id_user=user.id,
            id_google_account=id_google_account,
            id_device=None,
            local_ref=local_ref,
            operation_kind="upload",
            idempotency_key=idempotency_key,
            payload={
                "backup_id": str(backup_id) if backup_id else None,
                "expected_drive_version": expected_drive_version,
                "expected_content_hash": expected_content_hash,
                "snapshot_version": snapshot_version,
                "content_hash": content_hash,
                "manifest": parsed_manifest.model_dump(mode="json"),
            },
            backup_id=backup_id,
        )
        if operation.state == "completed" and operation.id_backup_file:
            backup = db.get(BackupFile, operation.id_backup_file)
            if backup is not None:
                return backup
        operation.state = "uploading"
        operation.updated_at = datetime.now(timezone.utc)
        db.commit()
        try:
            return await upload_snapshot(
                token,
                id_google_account,
                local_ref,
                snapshot_version,
                content_hash,
                parsed_manifest,
                idempotency_key,
                upload,
                db,
                operation.id,
                backup_id,
                expected_drive_version,
                expected_content_hash,
            )
        except HTTPException as exc:
            mark_failed(
                db,
                operation.id,
                f"upload_http_{exc.status_code}",
                retryable=exc.status_code >= 500,
            )
            raise
    finally:
        unlock_sync_target(db, sync_lock)


@transfer_router.get("/sync/download/{backup_id}")
async def download_backup_snapshot(
    backup_id: UUID,
    id_google_account: UUID,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> StreamingResponse:
    content, etag = await stream_snapshot(token, id_google_account, backup_id, db)
    headers = {"ETag": etag} if etag else {}
    return StreamingResponse(content, media_type="application/octet-stream", headers=headers)


@transfer_router.get("/sync/files")
async def list_drive_backup_files(
    id_google_account: UUID,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> list[dict[str, Any]]:
    return await list_drive_files(token, id_google_account, db)


@transfer_router.delete("/sync/files/{backup_id}", status_code=204)
async def delete_drive_backup_file(
    backup_id: UUID,
    id_google_account: UUID,
    if_match: str | None = Query(default=None),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> None:
    await delete_drive_file(token, id_google_account, backup_id, db, if_match)


@oauth2_account_router.post(
    "/link",
    status_code=status.HTTP_410_GONE,
    summary="Retired native Google linking endpoint",
    deprecated=True,
    dependencies=[Depends(google_oauth_rate_limit)],
)
def google_account_link(
    token: str = Depends(oauth2_scheme),
) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "server_oauth_required"},
    )


@oauth2_account_router.post(
    "/status/refresh",
    status_code=status.HTTP_410_GONE,
    summary="Retired client-token refresh endpoint",
    deprecated=True,
    dependencies=[Depends(google_oauth_rate_limit)],
)
def refresh_google_status(
    token: str = Depends(oauth2_scheme),
) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail={"code": "server_oauth_required"},
    )


@router.get(
    "/backups",
    response_model=list[BackupFileOut],
    summary="List backup metadata owned by the authenticated user",
)
def list_backups(
    filters: BackupFileFilters = Depends(),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> list[BackupFileOut]:
    return list_backup_files(
        token,
        db,
        filters.model_dump(exclude_unset=True, exclude_none=True),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/backups/{backup_id}",
    response_model=BackupFileOut,
    summary="Get one owned backup metadata record",
)
def get_backup(
    backup_id: UUID,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> BackupFileOut:
    return service_get_backup_file(token, str(backup_id), db)


@router.post(
    "/backups",
    response_model=BackupFileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Legacy metadata compatibility endpoint; use /sync/upload",
    deprecated=True,
    responses={409: {"description": "Idempotency or metadata conflict"}},
)
def create_backup(
    new_backup: BackupMetadataCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> BackupFileOut:
    return create_backup_metadata(token, new_backup, db)


@router.put(
    "/backups/{backup_id}",
    response_model=BackupFileOut,
    summary="Legacy metadata compatibility endpoint; use server-side sync operations",
    deprecated=True,
    responses={409: {"description": "Current metadata differs from expected version"}},
)
def update_backup(
    backup_id: UUID,
    update: BackupMetadataUpdate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> BackupFileOut:
    return update_backup_metadata(token, backup_id, update, db)


@router.delete(
    "/backups/{backup_id}",
    status_code=status.HTTP_200_OK,
    summary="Legacy metadata compatibility endpoint; use DELETE /sync/files/{backup_id}",
    deprecated=True,
)
def delete_backup(
    backup_id: UUID,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> dict[str, bool]:
    delete_backup_metadata(token, backup_id, db)
    return {"deleted": True, "drive_file_deleted": False}


@backup_file_router.get("/get/{identificator}", response_model=BackupFileOut)
def get_backup_file(
    identificator: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> BackupFileOut:
    return service_get_backup_file(token, identificator, db)


@backup_file_router.get("/list", response_model=list[BackupFileOut])
def list_backup_file(
    filters: BackupFileFilters = Depends(),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> list[BackupFileOut]:
    return list_backup_files(
        token,
        db,
        filters.model_dump(exclude_unset=True, exclude_none=True),
        limit=limit,
        offset=offset,
    )


@backup_file_router.post("/create", response_model=BackupFileOut)
def create_backup_file(
    new_backup_file: BackupFileCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> BackupFileOut:
    return create_legacy_backup_file(token, new_backup_file, db)


@backup_file_router.delete("/delete/{identificator}")
def delete_backup_file(
    identificator: UUID,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> dict[str, bool]:
    delete_backup_metadata(token, identificator, db)
    return {"deleted": True, "drive_file_deleted": False}


@sync_log_router.get("/get/{identificator}", response_model=SyncLogOut)
def get_sync_log(
    identificator: str,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> SyncLogOut:
    return service_get_sync_log(token, identificator, db)


@sync_log_router.get("/list", response_model=list[SyncLogOut])
def list_sync_log(
    filters: SyncLogFilters = Depends(),
    direction: SyncDirection | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> list[SyncLogOut]:
    if direction is not None:
        if filters.derection is not None and filters.derection != direction:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "conflicting_direction_filters"},
            )
        filters = filters.model_copy(update={"derection": direction})
    return list_sync_logs(
        token,
        db,
        filters.model_dump(exclude_unset=True, exclude_none=True, by_alias=False),
        limit=limit,
        offset=offset,
    )


@sync_log_router.post("/create", response_model=SyncLogOut, status_code=201)
def create_sync_log_endpoint(
    new_sync_log: SyncLogCreate,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> SyncLogOut:
    return create_sync_log(token, new_sync_log, db)


router.include_router(oauth2_account_router)
router.include_router(backup_file_router)
router.include_router(sync_log_router)
