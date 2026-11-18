import asyncio
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.modules.google_drive.worker import (
    mark_failed,
    process_operation,
    request_hash,
)


def test_request_hash_is_order_independent_and_payload_sensitive():
    first = request_hash("metadata", {"backup_id": "a", "revision": "1"})
    reordered = request_hash("metadata", {"revision": "1", "backup_id": "a"})
    changed = request_hash("metadata", {"backup_id": "a", "revision": "2"})

    assert first == reordered
    assert first != changed


def test_mark_failed_schedules_capped_retry():
    operation = SimpleNamespace(
        attempt_count=3,
        state="uploading",
        next_attempt_at=None,
        error_code=None,
        updated_at=None,
    )
    db = SimpleNamespace(
        get=lambda _model, _id: operation,
        commit=lambda: None,
    )

    mark_failed(db, uuid4(), "network_unavailable")

    assert operation.state == "pending"
    assert operation.error_code == "network_unavailable"
    assert operation.next_attempt_at > datetime.now(timezone.utc)


def test_mark_failed_moves_exhausted_operation_to_failed():
    operation = SimpleNamespace(
        attempt_count=8,
        state="uploading",
        next_attempt_at=None,
        error_code=None,
        updated_at=None,
    )
    db = SimpleNamespace(
        get=lambda _model, _id: operation,
        commit=lambda: None,
    )

    mark_failed(db, uuid4(), "worker_failure")

    assert operation.state == "failed"
    assert operation.next_attempt_at is None


def test_legacy_worker_fails_queued_operation_without_drive_io():
    operation = SimpleNamespace(
        state="pending",
        error_code=None,
        next_attempt_at=datetime.now(timezone.utc),
        updated_at=None,
    )
    commits = []
    db = SimpleNamespace(
        get=lambda _model, _id: operation,
        commit=lambda: commits.append(True),
    )

    result = asyncio.run(process_operation(db, uuid4()))

    assert result is operation
    assert operation.state == "failed"
    assert operation.error_code == "client_side_drive_sync_required"
    assert operation.next_attempt_at is None
    assert commits == [True]
