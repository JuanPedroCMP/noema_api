"""Recoverable synchronization worker primitives.

The deployment scheduler should call ``recover_stuck_operations`` and then
``process_operation`` from a separate worker process. PostgreSQL row locks
make claiming safe across multiple workers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ...core.db_models.google_drive_models import SyncOperation


def recover_stuck_operations(db: Session, timeout: timedelta = timedelta(minutes=15)) -> int:
    cutoff = datetime.now(timezone.utc) - timeout
    result = db.execute(
        update(SyncOperation)
        .where(
            SyncOperation.state == "uploading",
            SyncOperation.updated_at < cutoff,
        )
        .values(
            state="pending",
            next_attempt_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
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
    operation.state = "pending" if retryable else "failed"
    operation.error_code = error_code
    if retryable:
        delay = min(3600, 2 ** min(operation.attempt_count, 10))
        operation.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
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
