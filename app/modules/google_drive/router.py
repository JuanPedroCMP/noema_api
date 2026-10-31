from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.security import get_current_user, oauth2_scheme
from .models import (
    BackupFileCreate,
    BackupFileFilters,
    BackupFileOut,
    BackupMetadataCreate,
    BackupMetadataUpdate,
    GoogleAccountLinkRequest,
    GoogleAccountStatusOut,
    SyncLogCreate,
    SyncLogFilters,
    SyncLogOut,
)
from .services import (
    create_backup_metadata,
    create_legacy_backup_file,
    create_sync_log,
    delete_backup_metadata,
    get_google_account_status,
    link_google_account,
    list_backup_files,
    list_sync_logs,
    refresh_google_account_status,
    update_backup_metadata,
)
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


@oauth2_account_router.post(
    "/link",
    response_model=GoogleAccountStatusOut,
    status_code=status.HTTP_200_OK,
    summary="Link a native Google authorization without storing its tokens",
    dependencies=[Depends(google_oauth_rate_limit)],
)
async def google_account_link(
    link_request: GoogleAccountLinkRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> GoogleAccountStatusOut:
    return await link_google_account(token, link_request, db)


@oauth2_account_router.post(
    "/status/refresh",
    response_model=GoogleAccountStatusOut,
    summary="Re-check the currently linked Google authorization",
    dependencies=[Depends(google_oauth_rate_limit)],
)
async def refresh_google_status(
    link_request: GoogleAccountLinkRequest,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> GoogleAccountStatusOut:
    return await refresh_google_account_status(token, link_request, db)


@router.get(
    "/backups",
    response_model=list[BackupFileOut],
    summary="List backup metadata owned by the authenticated user",
)
def list_backups(
    filters: Annotated[BackupFileFilters, Query()],
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
    summary="Record metadata after the app completes a direct Drive upload",
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
    summary="Update metadata with optimistic Drive-version and hash preconditions",
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
    summary="Delete metadata only; the app must delete the Drive file separately",
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
    filters: Annotated[BackupFileFilters, Query()],
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
    filters: Annotated[SyncLogFilters, Query()],
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> list[SyncLogOut]:
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
