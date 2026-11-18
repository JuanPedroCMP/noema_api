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

from ...core.db_models.google_drive_models import SyncOperation

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
    """Fail queued legacy work without contacting Google Drive."""
    operation = db.get(SyncOperation, operation_id)
    if operation is None:
        return None
    if operation.state in {"pending", "uploading"}:
        operation.state = "failed"
        operation.error_code = "client_side_drive_sync_required"
        operation.next_attempt_at = None
        operation.updated_at = datetime.now(timezone.utc)
        db.commit()
    return operation


async def process_pending_operations(db: Session, limit: int = 20) -> int:
    """Retire queued legacy work without performing Drive requests."""
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
