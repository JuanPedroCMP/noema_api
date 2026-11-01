"""Durable Google Drive synchronization worker.

Run this module from a scheduler or a dedicated process (for example
``python -m app.modules.google_drive.worker``) with one database session per
poll. Workers claim rows with PostgreSQL ``SKIP LOCKED`` and may safely run in
multiple processes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from ...core.db_models.google_drive_models import (
    BackupFile,
    GoogleAccount,
    SyncOperation,
)
from .server_oauth import drive_request

MAX_ATTEMPTS = 8
STUCK_OPERATION_TIMEOUT = timedelta(minutes=15)


def _sync_lock_key(account_id: UUID, local_ref: str) -> tuple[int, int]:
    digest = hashlib.sha256(
        f"noema-google-sync:{account_id}:{local_ref}".encode()
    ).digest()
    return (
        int.from_bytes(digest[:4], "big", signed=True),
        int.from_bytes(digest[4:8], "big", signed=True),
    )


def lock_sync_target(db: Session, account_id: UUID, local_ref: str) -> tuple[int, int]:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        raise HTTPException(
            status_code=503,
            detail={"code": "distributed_lock_unavailable"},
        )
    first, second = _sync_lock_key(account_id, local_ref)
    db.execute(
        text("SELECT pg_advisory_lock(:first, :second)"),
        {"first": first, "second": second},
    )
    return first, second


def unlock_sync_target(db: Session, key: tuple[int, int]) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_unlock(:first, :second)"),
            {"first": key[0], "second": key[1]},
        )


def request_hash(operation_kind: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"operation_kind": operation_kind, "request": payload},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def create_or_get_operation(
    db: Session,
    *,
    id_user: UUID,
    id_google_account: UUID,
    id_device: UUID | None,
    local_ref: str,
    operation_kind: str,
    idempotency_key: str,
    payload: dict[str, Any],
    backup_id: UUID | None = None,
) -> SyncOperation:
    fingerprint = request_hash(
        operation_kind,
        {
            "id_google_account": str(id_google_account),
            "id_device": str(id_device) if id_device else None,
            "local_ref": local_ref,
            "payload": payload,
        },
    )
    existing = db.scalar(
        select(SyncOperation).where(
            SyncOperation.id_user == id_user,
            SyncOperation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise HTTPException(
                status_code=409,
                detail={"code": "idempotency_key_reused"},
            )
        return existing
    operation = SyncOperation(
        id=uuid4(),
        id_user=id_user,
        id_google_account=id_google_account,
        id_backup_file=backup_id,
        id_device=id_device,
        local_ref=local_ref,
        operation_kind=operation_kind,
        idempotency_key=idempotency_key,
        request_hash=fingerprint,
        request_payload=payload,
        state="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(operation)
    db.commit()
    db.refresh(operation)
    return operation


def recover_stuck_operations(
    db: Session, timeout: timedelta = STUCK_OPERATION_TIMEOUT
) -> int:
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(SyncOperation)
        .where(
            SyncOperation.state == "uploading",
            SyncOperation.updated_at < now - timeout,
        )
        .values(state="pending", next_attempt_at=now, updated_at=now)
    )
    db.commit()
    return result.rowcount or 0


def claim_operation(db: Session, operation_id: UUID) -> SyncOperation | None:
    operation = db.scalar(
        select(SyncOperation)
        .where(
            SyncOperation.id == operation_id,
            SyncOperation.state == "pending",
            (SyncOperation.next_attempt_at.is_(None))
            | (SyncOperation.next_attempt_at <= datetime.now(timezone.utc)),
        )
        .with_for_update(skip_locked=True)
    )
    if operation is None:
        return None
    operation.state = "uploading"
    operation.attempt_count += 1
    operation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(operation)
    return operation


async def process_operation(db: Session, operation_id: UUID) -> SyncOperation | None:
    """Claim and execute one operation, returning its durable final state."""
    operation = claim_operation(db, operation_id)
    if operation is None:
        return db.get(SyncOperation, operation_id)
    try:
        account = db.scalar(
            select(GoogleAccount).where(
                GoogleAccount.id == operation.id_google_account,
                GoogleAccount.id_user == operation.id_user,
            )
        )
        if account is None or not account.is_active:
            raise HTTPException(status_code=409, detail={"code": "resource_not_found"})
        payload = operation.request_payload or {}
        if operation.operation_kind == "list":
            response = await drive_request(
                account,
                db,
                "GET",
                "/files",
                params={
                    "spaces": "appDataFolder",
                    "fields": "files(id,name,version,size,appProperties)",
                },
            )
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail={"code": "drive_list_failed"})
            body = response.json()
            operation.result_payload = {"files": body.get("files", [])}
        elif operation.operation_kind in {"download", "metadata", "delete"}:
            backup = db.scalar(
                select(BackupFile).where(
                    BackupFile.id == operation.id_backup_file,
                    BackupFile.id_google_account == account.id,
                    BackupFile.operation_state == "completed",
                )
            )
            if backup is None:
                raise HTTPException(status_code=404, detail={"code": "resource_not_found"})
            metadata = await drive_request(
                account,
                db,
                "GET",
                f"/files/{backup.drive_file_id}",
                params={"fields": "id,parents,appProperties,version,size"},
            )
            remote = metadata.json() if metadata.status_code < 400 else {}
            if (
                metadata.status_code >= 400
                or "appDataFolder" not in (remote.get("parents") or [])
                or remote.get("appProperties", {}).get("noema_local_ref")
                != backup.local_ref
            ):
                raise HTTPException(
                    status_code=409,
                    detail={"code": "drive_revision_conflict"},
                )
            if operation.operation_kind == "download":
                operation.result_payload = {
                    "drive_file_id": backup.drive_file_id,
                    "drive_version": str(remote.get("version", "")),
                }
            elif operation.operation_kind == "metadata":
                backup.drive_version = str(remote.get("version", backup.drive_version))
                backup.drive_etag = metadata.headers.get("etag") or backup.drive_etag
                backup.updated_at = datetime.now(timezone.utc)
            else:
                expected = payload.get("if_match") or backup.drive_etag or backup.drive_version
                response = await drive_request(
                    account,
                    db,
                    "DELETE",
                    f"/files/{backup.drive_file_id}",
                    headers={"If-Match": expected} if expected else {},
                )
                if response.status_code == 412:
                    raise HTTPException(
                        status_code=409,
                        detail={"code": "drive_revision_conflict"},
                    )
                if response.status_code not in {200, 204, 404}:
                    raise HTTPException(status_code=502, detail={"code": "drive_delete_failed"})
                db.delete(backup)
        elif operation.operation_kind == "upload":
            raise HTTPException(
                status_code=422,
                detail={"code": "upload_requires_transfer_endpoint"},
            )
        else:
            raise HTTPException(status_code=422, detail={"code": "invalid_operation_kind"})
        operation.state = "completed"
        operation.error_code = None
        operation.next_attempt_at = None
        operation.updated_at = datetime.now(timezone.utc)
        db.commit()
    except HTTPException as exc:
        mark_failed(
            db,
            operation_id,
            str((exc.detail or {}).get("code", "operation_failed"))
            if isinstance(exc.detail, dict)
            else "operation_failed",
            retryable=exc.status_code >= 500,
        )
    except Exception:
        mark_failed(db, operation_id, "worker_failure", retryable=True)
    return db.get(SyncOperation, operation_id)


async def process_pending_operations(db: Session, limit: int = 20) -> int:
    """Recover stale rows and process due rows in one worker poll."""
    recover_stuck_operations(db)
    ids = list(
        db.scalars(
            select(SyncOperation.id)
            .where(
                SyncOperation.state == "pending",
                (SyncOperation.next_attempt_at.is_(None))
                | (SyncOperation.next_attempt_at <= datetime.now(timezone.utc)),
            )
            .order_by(SyncOperation.created_at)
            .limit(limit)
        )
    )
    for operation_id in ids:
        await process_operation(db, operation_id)
    return len(ids)


def mark_failed(
    db: Session,
    operation_id: UUID,
    error_code: str,
    *,
    retryable: bool = True,
) -> None:
    operation = db.get(SyncOperation, operation_id)
    if operation is None:
        return
    if retryable and operation.attempt_count < MAX_ATTEMPTS:
        operation.state = "pending"
        operation.next_attempt_at = datetime.now(timezone.utc) + timedelta(
            seconds=min(3600, 2 ** min(operation.attempt_count, 10))
        )
    else:
        operation.state = "failed"
        operation.next_attempt_at = None
    operation.error_code = error_code
    operation.updated_at = datetime.now(timezone.utc)
    db.commit()


def mark_completed(db: Session, operation_id: UUID) -> None:
    operation = db.get(SyncOperation, operation_id)
    if operation is None:
        return
    operation.state = "completed"
    operation.error_code = None
    operation.next_attempt_at = None
    operation.updated_at = datetime.now(timezone.utc)
    db.commit()


if __name__ == "__main__":
    raise SystemExit(
        "Run process_pending_operations from the application's scheduler with a managed DB session."
    )
