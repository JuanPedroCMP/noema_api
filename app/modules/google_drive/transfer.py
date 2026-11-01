from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime, timezone
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.db_models.google_drive_models import BackupFile, GoogleAccount, SyncOperation
from ...core.security import get_current_user
from .models import (
    MAX_BACKUP_SIZE_BYTES,
    BackupMetadataCreate,
    BackupMetadataUpdate,
    SnapshotManifest,
)
from .server_oauth import drive_request, drive_stream

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
    operation_id: UUID | None = None,
    backup_id: UUID | None = None,
    expected_drive_version: str | None = None,
    expected_content_hash: str | None = None,
) -> BackupFile:
    account = _account(token, account_id, db)
    if manifest.snapshot_version != snapshot_version:
        raise HTTPException(
            status_code=422,
            detail={"code": "snapshot_manifest_version_mismatch"},
        )
    existing_backup = None
    expected_etag = None
    if backup_id is not None:
        if not expected_drive_version or not expected_content_hash:
            raise HTTPException(
                status_code=422,
                detail={"code": "backup_revision_required"},
            )
        existing_backup = await _owned_backup(token, account_id, backup_id, db)
        if existing_backup.local_ref != local_ref:
            raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
        if (
            existing_backup.content_hash == content_hash
            and existing_backup.snapshot_version == snapshot_version
        ):
            operation = db.get(SyncOperation, operation_id) if operation_id else None
            if operation is not None:
                operation.id_backup_file = existing_backup.id
                operation.state = "completed"
                operation.result_payload = {"backup_id": str(existing_backup.id)}
                operation.updated_at = datetime.now(timezone.utc)
                db.commit()
            return existing_backup
        if (
            existing_backup.drive_version != expected_drive_version
            or existing_backup.content_hash != expected_content_hash
        ):
            raise HTTPException(
                status_code=409,
                detail={"code": "drive_revision_conflict"},
            )
        remote_response = await drive_request(
            account,
            db,
            "GET",
            f"/files/{existing_backup.drive_file_id}",
            params={"fields": "id,parents,appProperties,version,size"},
        )
        if remote_response.status_code == 404:
            raise HTTPException(status_code=409, detail={"code": "drive_file_missing"})
        if remote_response.status_code >= 400:
            raise HTTPException(status_code=502, detail={"code": "drive_metadata_check_failed"})
        remote = remote_response.json()
        if (
            remote.get("id") != existing_backup.drive_file_id
            or "appDataFolder" not in (remote.get("parents") or [])
            or remote.get("appProperties", {}).get("noema_local_ref") != local_ref
        ):
            raise HTTPException(
                status_code=409,
                detail={"code": "drive_revision_conflict"},
            )
        operation = db.get(SyncOperation, operation_id) if operation_id else None
        app_properties = remote.get("appProperties") or {}
        if str(remote.get("version")) != expected_drive_version:
            if (
                operation is not None
                and operation.drive_file_id == existing_backup.drive_file_id
                and app_properties.get("noema_operation_id") == str(operation.id)
                and app_properties.get("noema_content_hash") == content_hash
                and app_properties.get("noema_snapshot_version") == snapshot_version
            ):
                try:
                    remote_size = int(remote["size"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise HTTPException(
                        status_code=502,
                        detail={"code": "drive_metadata_check_failed"},
                    ) from exc
                from .services import update_backup_metadata
                backup = update_backup_metadata(
                    token,
                    existing_backup.id,
                    BackupMetadataUpdate(
                        expected_drive_version=expected_drive_version,
                        expected_content_hash=expected_content_hash,
                        idempotency_key=hashlib.sha256(
                            f"{idempotency_key}:metadata".encode()
                        ).hexdigest(),
                        drive_version=str(remote.get("version", "")),
                        drive_etag=remote_response.headers.get("etag"),
                        snapshot_version=snapshot_version,
                        content_hash=content_hash,
                        size_bytes=remote_size,
                        operation_state="completed",
                        manifest=manifest,
                    ),
                    db,
                )
                operation.id_backup_file = backup.id
                operation.state = "completed"
                operation.result_payload = {"backup_id": str(backup.id)}
                operation.updated_at = datetime.now(timezone.utc)
                db.commit()
                return backup
            raise HTTPException(
                status_code=409,
                detail={"code": "drive_revision_conflict"},
            )
        expected_etag = remote_response.headers.get("etag") or existing_backup.drive_etag
        if not expected_etag:
            raise HTTPException(
                status_code=409,
                detail={"code": "drive_revision_unavailable"},
            )
    existing = db.scalar(select(BackupFile).where(
        BackupFile.id_google_account == account_id,
        BackupFile.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        if (
            existing.local_ref != local_ref
            or existing.snapshot_version != snapshot_version
            or existing.content_hash.lower() != content_hash.lower()
        ):
            raise HTTPException(
                status_code=409,
                detail={"code": "idempotency_key_reused"},
            )
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
        if operation_id is not None:
            operation = db.get(SyncOperation, operation_id)
            if operation is not None and operation.drive_file_id:
                existing_remote = await drive_request(
                    account,
                    db,
                    "GET",
                    f"/files/{operation.drive_file_id}",
                    params={"fields": "id,parents,appProperties,version,size"},
                )
                remote = existing_remote.json() if existing_remote.status_code < 400 else {}
                if (
                    existing_remote.status_code < 400
                    and "appDataFolder" in (remote.get("parents") or [])
                    and remote.get("appProperties", {}).get("noema_local_ref") == local_ref
                    and remote.get("appProperties", {}).get("noema_content_hash") == content_hash
                    and remote.get("appProperties", {}).get("noema_snapshot_version") == snapshot_version
                ):
                    if existing_backup is not None:
                        from .services import update_backup_metadata
                        backup = update_backup_metadata(
                            token,
                            existing_backup.id,
                            BackupMetadataUpdate(
                                expected_drive_version=expected_drive_version,
                                expected_content_hash=expected_content_hash,
                                idempotency_key=hashlib.sha256(
                                    f"{idempotency_key}:metadata".encode()
                                ).hexdigest(),
                                drive_version=str(remote.get("version", "")),
                                drive_etag=existing_remote.headers.get("etag"),
                                snapshot_version=snapshot_version,
                                content_hash=content_hash,
                                size_bytes=size,
                                operation_state="completed",
                                manifest=manifest,
                            ),
                            db,
                        )
                    else:
                        from .services import create_backup_metadata
                        backup = create_backup_metadata(
                            token,
                            BackupMetadataCreate(
                            id_google_account=account_id,
                            id_device=operation.id_device,
                            drive_file_id=operation.drive_file_id,
                            local_ref=local_ref,
                            drive_version=str(remote.get("version", "")),
                            drive_etag=existing_remote.headers.get("etag"),
                            snapshot_version=snapshot_version,
                            content_hash=content_hash,
                            size_bytes=size,
                            operation_state="completed",
                            manifest=manifest,
                            idempotency_key=idempotency_key,
                            ),
                            db,
                        )
                    operation.id_backup_file = backup.id
                    operation.state = "completed"
                    operation.result_payload = {"backup_id": str(backup.id)}
                    operation.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    return backup
        metadata = {
            "name": f"noema-{local_ref}",
            "appProperties": {
                "noema_local_ref": local_ref,
                "noema_snapshot_version": snapshot_version,
                "noema_content_hash": content_hash,
            },
        }
        if existing_backup is None:
            metadata["parents"] = ["appDataFolder"]
        operation = db.get(SyncOperation, operation_id) if operation_id is not None else None
        if operation is not None:
            metadata["appProperties"]["noema_operation_id"] = str(operation.id)
        upload_path = (
            f"https://www.googleapis.com/upload/drive/v3/files/{existing_backup.drive_file_id}?uploadType=resumable&fields=id,version,modifiedTime,size"
            if existing_backup is not None
            else "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,version,modifiedTime,size"
        )
        session = await drive_request(
            account,
            db,
            "PATCH" if existing_backup is not None else "POST",
            upload_path,
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/octet-stream",
                **({"If-Match": expected_etag} if expected_etag else {}),
            },
            json=metadata,
        )
        if session.status_code == 412:
            raise HTTPException(status_code=409, detail={"code": "drive_revision_conflict"})
        if session.status_code not in {200, 201} or not session.headers.get("location"):
            raise HTTPException(status_code=502, detail={"code": "drive_upload_session_failed"})
        temp.seek(0)
        offset = 0
        result: dict[str, Any] | None = None
        result_etag: str | None = None
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
                if response.status_code == 412:
                    raise HTTPException(
                        status_code=409,
                        detail={"code": "drive_revision_conflict"},
                    )
                raise HTTPException(status_code=502, detail={"code": "drive_upload_failed"})
            offset = end + 1
            if response.status_code in {200, 201}:
                result = response.json()
                result_etag = response.headers.get("etag")
        if result is None:
            raise HTTPException(status_code=502, detail={"code": "drive_upload_incomplete"})
    assert result is not None
    drive_file_id = result.get("id") or (
        existing_backup.drive_file_id if existing_backup is not None else None
    )
    drive_version = str(result.get("version", ""))
    if not isinstance(drive_file_id, str) or not drive_version:
        raise HTTPException(status_code=502, detail={"code": "drive_upload_invalid_response"})
    if operation_id is not None:
        operation = db.get(SyncOperation, operation_id)
        if operation is not None:
            operation.drive_file_id = drive_file_id
            operation.updated_at = datetime.now(timezone.utc)
            db.commit()
    if existing_backup is not None:
        from .services import update_backup_metadata
        backup = update_backup_metadata(
            token,
            existing_backup.id,
            BackupMetadataUpdate(
                expected_drive_version=expected_drive_version,
                expected_content_hash=expected_content_hash,
                idempotency_key=hashlib.sha256(
                    f"{idempotency_key}:metadata".encode()
                ).hexdigest(),
                drive_version=drive_version,
                drive_etag=result_etag,
                snapshot_version=snapshot_version,
                content_hash=content_hash,
                size_bytes=size,
                operation_state="completed",
                manifest=manifest,
            ),
            db,
        )
    else:
        from .services import create_backup_metadata
        backup = create_backup_metadata(token, BackupMetadataCreate(
            id_google_account=account_id,
            id_device=operation.id_device if operation is not None else None,
            drive_file_id=drive_file_id,
            local_ref=local_ref,
            drive_version=drive_version,
            drive_etag=result_etag,
            snapshot_version=snapshot_version,
            content_hash=content_hash,
            size_bytes=size,
            operation_state="completed",
            manifest=manifest,
            idempotency_key=idempotency_key,
        ), db)
    if operation_id is not None:
        operation = db.get(SyncOperation, operation_id)
        if operation is not None:
            operation.id_backup_file = backup.id
            operation.state = "completed"
            operation.result_payload = {"backup_id": str(backup.id)}
            operation.updated_at = datetime.now(timezone.utc)
            db.commit()
    return backup


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


async def stream_snapshot(
    token: str, account_id: UUID, backup_id: UUID, db: Session
) -> tuple[AsyncIterator[bytes], str | None]:
    account = _account(token, account_id, db)
    backup = await _owned_backup(token, account_id, backup_id, db)
    metadata = await drive_request(
        account,
        db,
        "GET",
        f"/files/{backup.drive_file_id}",
        params={"fields": "id,parents,appProperties,version,size"},
    )
    remote = metadata.json() if metadata.status_code < 400 else {}
    app_properties = remote.get("appProperties") or {}
    if (
        metadata.status_code == 404
        or remote.get("id") != backup.drive_file_id
        or "appDataFolder" not in (remote.get("parents") or [])
        or app_properties.get("noema_local_ref") != backup.local_ref
        or (
            backup.size_bytes is not None
            and remote.get("size") is not None
            and int(remote["size"]) != backup.size_bytes
        )
    ):
        raise HTTPException(status_code=409, detail={"code": "drive_metadata_conflict"})
    if (
        backup.drive_version is not None
        and str(remote.get("version")) != backup.drive_version
    ) or (
        backup.content_hash is not None
        and app_properties.get("noema_content_hash") is not None
        and app_properties.get("noema_content_hash") != backup.content_hash
    ):
        raise HTTPException(status_code=409, detail={"code": "drive_revision_conflict"})
    return (
        drive_stream(account, db, "GET", f"/files/{backup.drive_file_id}?alt=media"),
        metadata.headers.get("etag") or backup.drive_etag,
    )


async def list_drive_files(token: str, account_id: UUID, db: Session) -> list[dict[str, Any]]:
    account = _account(token, account_id, db)
    known_ids = {
        row.drive_file_id
        for row in db.scalars(
            select(BackupFile).where(
                BackupFile.id_google_account == account_id,
                BackupFile.operation_state == "completed",
            )
        )
    }
    response = await drive_request(
        account, db, "GET", "/files",
        params={"spaces": "appDataFolder", "fields": "files(id,name,version,size,md5Checksum,modifiedTime,appProperties)"},
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"code": "drive_list_failed"})
    payload = response.json()
    files = payload.get("files", []) if isinstance(payload, dict) else []
    return [
        item
        for item in files
        if item.get("id") in known_ids
        and item.get("appProperties", {}).get("noema_local_ref") is not None
    ]


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
