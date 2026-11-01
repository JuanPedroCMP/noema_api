from __future__ import annotations

import hashlib
import tempfile
from typing import Any
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.db_models.google_drive_models import BackupFile, GoogleAccount
from ...core.security import get_current_user
from .models import (
    MAX_BACKUP_SIZE_BYTES,
    BackupMetadataCreate,
    SnapshotManifest,
)
from .server_oauth import drive_request

MAX_CHUNK = 8 * 1024 * 1024


def _account(token: str, account_id: UUID, db: Session) -> GoogleAccount:
    user = get_current_user(token, db)
    account = db.scalar(select(GoogleAccount).where(
        GoogleAccount.id == account_id, GoogleAccount.id_user == user.id
    ))
    if account is None or account.drive_appdata_status != "granted" or not account.is_active:
        raise HTTPException(status_code=409, detail={"code": "drive_appdata_unavailable"})
    return account


async def upload_snapshot(
    token: str,
    account_id: UUID,
    local_ref: str,
    snapshot_version: str,
    content_hash: str,
    manifest: SnapshotManifest,
    idempotency_key: str,
    upload: UploadFile,
    db: Session,
) -> BackupFile:
    account = _account(token, account_id, db)
    existing = db.scalar(select(BackupFile).where(
        BackupFile.id_google_account == account_id,
        BackupFile.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        return existing
    digest = hashlib.sha256()
    size = 0
    with tempfile.TemporaryFile() as temp:
        while chunk := await upload.read(MAX_CHUNK):
            size += len(chunk)
            if size > MAX_BACKUP_SIZE_BYTES:
                raise HTTPException(status_code=413, detail={"code": "snapshot_too_large"})
            digest.update(chunk)
            temp.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail={"code": "empty_snapshot"})
        actual_hash = f"sha256:{digest.hexdigest()}"
        if actual_hash.lower() != content_hash.lower():
            raise HTTPException(status_code=422, detail={"code": "snapshot_hash_mismatch"})
        metadata = {
            "name": f"noema-{local_ref}",
            "parents": ["appDataFolder"],
            "appProperties": {"noema_local_ref": local_ref, "noema_snapshot_version": snapshot_version},
        }
        session = await drive_request(
            account,
            db,
            "POST",
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
            headers={"Content-Type": "application/json; charset=UTF-8", "X-Upload-Content-Type": "application/octet-stream"},
            json=metadata,
        )
        if session.status_code not in {200, 201} or not session.headers.get("location"):
            raise HTTPException(status_code=502, detail={"code": "drive_upload_session_failed"})
        temp.seek(0)
        offset = 0
        result: dict[str, Any] | None = None
        while chunk := temp.read(MAX_CHUNK):
            end = offset + len(chunk) - 1
            response = await drive_request(
                account,
                db,
                "PUT",
                session.headers["location"],
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {offset}-{end}/{size}",
                    "Content-Type": "application/octet-stream",
                },
                content=chunk,
            )
            if response.status_code not in {200, 201, 308}:
                raise HTTPException(status_code=502, detail={"code": "drive_upload_failed"})
            offset = end + 1
            if response.status_code in {200, 201}:
                result = response.json()
        if result is None:
            raise HTTPException(status_code=502, detail={"code": "drive_upload_incomplete"})
    assert result is not None
    drive_file_id = result.get("id")
    drive_version = str(result.get("version", result.get("modifiedTime", "")))
    if not isinstance(drive_file_id, str) or not drive_version:
        raise HTTPException(status_code=502, detail={"code": "drive_upload_invalid_response"})
    from .services import create_backup_metadata
    return create_backup_metadata(token, BackupMetadataCreate(
        id_google_account=account_id,
        id_device=None,
        drive_file_id=drive_file_id,
        local_ref=local_ref,
        drive_version=drive_version,
        drive_etag=result.get("etag"),
        snapshot_version=snapshot_version,
        content_hash=content_hash,
        size_bytes=size,
        operation_state="completed",
        manifest=manifest,
        idempotency_key=idempotency_key,
    ), db)


async def _owned_backup(token: str, account_id: UUID, backup_id: UUID, db: Session) -> BackupFile:
    user = get_current_user(token, db)
    backup = db.scalar(
        select(BackupFile).join(GoogleAccount).where(
            BackupFile.id == backup_id,
            BackupFile.id_google_account == account_id,
            GoogleAccount.id_user == user.id,
        )
    )
    if backup is None:
        raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
    return backup


async def download_snapshot(token: str, account_id: UUID, backup_id: UUID, db: Session) -> tuple[bytes, str | None]:
    account = _account(token, account_id, db)
    backup = await _owned_backup(token, account_id, backup_id, db)
    metadata = await drive_request(
        account, db, "GET", f"/files/{backup.drive_file_id}",
        params={"fields": "id,parents,appProperties,version,etag,size,md5Checksum"},
    )
    if metadata.status_code == 404:
        raise HTTPException(status_code=404, detail={"code": "drive_file_missing"})
    remote = metadata.json()
    if (
        metadata.status_code >= 400
        or remote.get("id") != backup.drive_file_id
        or "appDataFolder" not in (remote.get("parents") or [])
        or remote.get("appProperties", {}).get("noema_local_ref") != backup.local_ref
    ):
        raise HTTPException(status_code=409, detail={"code": "drive_metadata_conflict"})
    response = await drive_request(account, db, "GET", f"/files/{backup.drive_file_id}?alt=media")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail={"code": "drive_file_missing"})
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"code": "drive_download_failed"})
    return response.content, response.headers.get("etag") or remote.get("etag")


async def list_drive_files(token: str, account_id: UUID, db: Session) -> list[dict[str, Any]]:
    account = _account(token, account_id, db)
    response = await drive_request(
        account, db, "GET", "/files",
        params={"spaces": "appDataFolder", "fields": "files(id,name,version,size,md5Checksum,modifiedTime,appProperties)"},
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"code": "drive_list_failed"})
    payload = response.json()
    return payload.get("files", []) if isinstance(payload, dict) else []


async def delete_drive_file(token: str, account_id: UUID, backup_id: UUID, db: Session, if_match: str | None = None) -> None:
    account = _account(token, account_id, db)
    backup = await _owned_backup(token, account_id, backup_id, db)
    expected = if_match or backup.drive_etag or backup.drive_version
    headers = {"If-Match": expected} if expected else {}
    response = await drive_request(account, db, "DELETE", f"/files/{backup.drive_file_id}", headers=headers)
    if response.status_code == 412:
        raise HTTPException(status_code=409, detail={"code": "drive_revision_conflict"})
    if response.status_code not in {200, 204, 404}:
        raise HTTPException(status_code=502, detail={"code": "drive_delete_failed"})
