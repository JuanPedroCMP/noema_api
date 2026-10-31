from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.db_models.google_drive_models import (
    BackupFile,
    BackupOperationIdempotency,
    BackupOperationState,
    ConflictStrategy,
    SyncDirection,
    SyncResult,
)
from app.core.security import oauth2_scheme
from app.modules.auth.router import router as auth_router
from app.modules.auth import service as auth_service
from app.modules.auth.models import GoogleAccountOut
from app.modules.google_drive import oauth, services
from app.modules.google_drive.models import (
    GOOGLE_DRIVE_APPDATA_SCOPE,
    BackupFileCreate,
    BackupFileOut,
    BackupMetadataCreate,
    BackupMetadataUpdate,
    GoogleAccountLinkRequest,
    SnapshotManifest,
    SyncLogCreate,
    SyncLogOut,
)
from app.modules.google_drive import router as google_drive_router
from app.modules.google_drive.router import (
    api_rate_limit,
    google_oauth_rate_limit,
    router,
)
from app.modules.user import service as user_service
from app.modules.user.models import UserCreate, UserUpdate, validate_password_strength

USER_ID = UUID("b08c5a73-2437-4e15-8a3c-d46e010f2367")
OTHER_USER_ID = UUID("fba7e7b0-a629-4d05-b55c-2b7c37686098")
ACCOUNT_ID = UUID("971235ac-66ed-4e27-8b5a-8d8a4c75361f")
DEVICE_ID = UUID("39bb5203-46ed-442c-829c-714d10bfc3e5")
BACKUP_ID = UUID("8ae81c4a-9b57-47b6-9a7e-41830dd228c5")


class ScalarRows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def all(self):
        return self.rows


class MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self.row


class FakeDB:
    def __init__(self, scalar_results=(), rows_results=(), execute_row=None):
        self.scalar_results = list(scalar_results)
        self.rows_results = list(rows_results)
        self.execute_row = execute_row
        self.added = []
        self.deleted = []
        self.commits = 0
        self.rollbacks = 0
        self.executed_statements = []

    def scalar(self, _statement):
        return self.scalar_results.pop(0) if self.scalar_results else None

    def execute(self, statement):
        self.executed_statements.append(statement)
        if getattr(statement, "is_delete", False):
            return SimpleNamespace(rowcount=1)
        return MappingResult(
            self.execute_row
            or {
                "id": ACCOUNT_ID,
                "id_user": USER_ID,
                "google_user_id": "google-subject",
                "email_google": "reader@example.com",
                "granted_scopes": "openid",
                "is_active": True,
                "expires_at": None,
                "last_refresh_at": None,
                "updated_at": None,
                "created_at": None,
                "drive_appdata_status": "unknown",
                "scope_checked_at": None,
            }
        )

    def scalars(self, _statement):
        rows = self.rows_results.pop(0) if self.rows_results else []
        return ScalarRows(rows)

    def add(self, value):
        self.added.append(value)

    def delete(self, value):
        self.deleted.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, _value):
        return None


def account(
    owner=USER_ID,
    *,
    scopes=GOOGLE_DRIVE_APPDATA_SCOPE,
    state="granted",
    google_user_id="google-subject",
):
    return SimpleNamespace(
        id=ACCOUNT_ID,
        id_user=owner,
        google_user_id=google_user_id,
        email_google="reader@example.com",
        granted_scopes=scopes,
        drive_appdata_status=state,
        scope_checked_at=datetime(2026, 10, 31, tzinfo=timezone.utc),
        is_active=True,
        access_token_enc=None,
        refresh_token_enc=None,
    )


def backup_row(**overrides):
    values = {
        "id": BACKUP_ID,
        "id_google_account": ACCOUNT_ID,
        "id_device": DEVICE_ID,
        "drive_file_id": "drive-file-1",
        "local_ref": "primary",
        "drive_version": "42",
        "snapshot_version": "17",
        "content_hash": "sha256:5c2d7f0bb5921471021c99efb2e357d5",
        "size_bytes": 84210,
        "operation_state": BackupOperationState.COMPLETED,
        "manifest": None,
        "idempotency_key": "37d19871-7e6a-4b1f-bcff-53dc0d397a44",
        "created_at": datetime(2026, 10, 31, tzinfo=timezone.utc),
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def create_payload(**overrides):
    values = {
        "id_google_account": ACCOUNT_ID,
        "id_device": DEVICE_ID,
        "drive_file_id": "drive-file-1",
        "local_ref": "primary",
        "drive_version": "42",
        "snapshot_version": "17",
        "content_hash": "sha256:5c2d7f0bb5921471021c99efb2e357d5",
        "size_bytes": 84210,
        "operation_state": "completed",
        "idempotency_key": "37d19871-7e6a-4b1f-bcff-53dc0d397a44",
        "manifest": {
            "format": "noema-snapshot",
            "schema_version": 1,
            "snapshot_version": "17",
            "created_at": datetime(2026, 10, 31, tzinfo=timezone.utc),
            "installation_id": "install-7d2c",
            "included_categories": ["local_library"],
            "excluded_categories": ["global_preferences"],
            "counts": {"local_library": 12},
            "hashes": {"local_library": "sha256:5c2d7f0bb5921471021c99efb2e357d5"},
        },
    }
    values.update(overrides)
    return BackupMetadataCreate.model_validate(values)


def install_identity(monkeypatch, user_id=USER_ID):
    monkeypatch.setattr(
        services,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=user_id),
    )


def test_new_routes_require_authentication_and_have_no_file_transfer_contract():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: FakeDB()
    client = TestClient(app)

    response = client.get("/google_drive/backups")
    assert response.status_code == 401

    schema = app.openapi()
    required_paths = {
        "/google_drive/account/status",
        "/google_drive/account/link",
        "/google_drive/account/status/refresh",
        "/google_drive/backups",
        "/google_drive/backups/{backup_id}",
        "/google_drive/sync_log/create",
    }
    assert required_paths <= schema["paths"].keys()
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            assert operation.get("security")
    assert not any(
        "upload" in path.lower() or "download" in path.lower()
        for path in schema["paths"]
    )
    serialized = str(schema["paths"])
    assert "application/octet-stream" not in serialized
    assert "multipart/form-data" not in serialized


def test_backup_list_accepts_optional_filters_and_account_uuid(monkeypatch):
    seen_backups = []
    seen_logs = []

    def list_backups(_token, _db, filters, *, limit, offset):
        seen_backups.append((filters, limit, offset))
        return []

    def list_logs(_token, _db, filters, *, limit, offset):
        seen_logs.append((filters, limit, offset))
        return []

    monkeypatch.setattr(google_drive_router, "list_backup_files", list_backups)
    monkeypatch.setattr(google_drive_router, "list_sync_logs", list_logs)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: FakeDB()
    app.dependency_overrides[oauth2_scheme] = lambda: "test-noema-token"
    app.dependency_overrides[api_rate_limit] = lambda: None
    client = TestClient(app)

    response = client.get(
        "/google_drive/backups",
        params={
            "id_google_account": str(ACCOUNT_ID),
            "limit": 100,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    assert response.json() == []
    legacy_response = client.get(
        "/google_drive/backup_file/list",
        params={"id_google_account": str(ACCOUNT_ID)},
    )
    assert legacy_response.status_code == 200
    log_response = client.get(
        "/google_drive/sync_log/list",
        params={"direction": "upload"},
    )
    assert log_response.status_code == 200
    legacy_log_response = client.get(
        "/google_drive/sync_log/list",
        params={"derection": "download"},
    )
    assert legacy_log_response.status_code == 200
    conflicting_log_response = client.get(
        "/google_drive/sync_log/list",
        params={"direction": "upload", "derection": "download"},
    )
    assert conflicting_log_response.status_code == 422
    assert conflicting_log_response.json()["detail"]["code"] == (
        "conflicting_direction_filters"
    )
    assert seen_backups == [
        ({"id_google_account": ACCOUNT_ID}, 100, 0),
        ({"id_google_account": ACCOUNT_ID}, 100, 0),
    ]
    assert seen_logs == [
        ({"derection": SyncDirection.UPLOAD}, 100, 0),
        ({"derection": SyncDirection.DOWNLOAD}, 100, 0),
    ]


def test_backup_reads_and_account_writes_hide_cross_user_resources(monkeypatch):
    install_identity(monkeypatch)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: FakeDB(
        scalar_results=[None, account(owner=OTHER_USER_ID)]
    )
    app.dependency_overrides[oauth2_scheme] = lambda: "test-noema-token"
    app.dependency_overrides[api_rate_limit] = lambda: None
    client = TestClient(app)

    missing_backup = client.get(f"/google_drive/backups/{BACKUP_ID}")
    other_users_account = client.post(
        "/google_drive/backups",
        json=create_payload().model_dump(mode="json"),
    )
    assert missing_backup.status_code == 404
    assert other_users_account.status_code == 404


def test_oauth_verifies_and_persists_only_granted_scope_names(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", "android-client,ios-client")
    now = int(datetime.now(timezone.utc).timestamp())
    identity = {
        "aud": "android-client",
        "iss": "https://accounts.google.com",
        "exp": str(now + 600),
        "sub": "google-subject",
        "email": "reader@example.com",
        "email_verified": "true",
    }
    access = {
        "issued_to": "android-client",
        "user_id": "google-subject",
        "scope": f"openid {GOOGLE_DRIVE_APPDATA_SCOPE}",
    }

    async def token_info(parameter, _token):
        return identity if parameter == "id_token" else access

    monkeypatch.setattr(oauth, "_fetch_token_info", token_info)
    subject, email, scopes = asyncio.run(oauth.verify_google_tokens("id", "access"))

    assert subject == "google-subject"
    assert email == "reader@example.com"
    assert scopes == ["https://www.googleapis.com/auth/drive.appdata", "openid"]


def test_oauth_tokeninfo_request_logs_redact_google_tokens(monkeypatch, caplog):
    real_async_client = httpx.AsyncClient

    async def handle_request(_request):
        return httpx.Response(
            200,
            json={
                "issued_to": "android-client",
                "user_id": "google-subject",
                "scope": GOOGLE_DRIVE_APPDATA_SCOPE,
            },
        )

    def client_factory(**kwargs):
        return real_async_client(
            transport=httpx.MockTransport(handle_request),
            **kwargs,
        )

    monkeypatch.setattr(oauth.httpx, "AsyncClient", client_factory)
    caplog.set_level(logging.INFO, logger="httpx")

    asyncio.run(oauth._fetch_token_info("access_token", "do-not-log-this-token"))

    assert "do-not-log-this-token" not in caplog.text
    assert "tokeninfo" in caplog.text


def test_oauth_rejects_broad_drive_and_unrelated_scopes(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", "android-client")
    now = int(datetime.now(timezone.utc).timestamp())
    identity = {
        "aud": "android-client",
        "iss": "accounts.google.com",
        "exp": str(now + 600),
        "sub": "google-subject",
        "email": "reader@example.com",
        "email_verified": "true",
    }

    async def token_info(parameter, _token):
        if parameter == "id_token":
            return identity
        return {
            "aud": "android-client",
            "user_id": "google-subject",
            "scope": "https://www.googleapis.com/auth/drive.file",
        }

    monkeypatch.setattr(oauth, "_fetch_token_info", token_info)
    with pytest.raises(HTTPException) as denied:
        asyncio.run(oauth.verify_google_tokens("id", "access"))
    assert denied.value.status_code == 403
    assert denied.value.detail["code"] == "google_scope_not_allowed"


@pytest.mark.parametrize(
    ("scopes", "expected_state", "expected_granted"),
    [
        (GOOGLE_DRIVE_APPDATA_SCOPE, "granted", True),
        ("openid email", "missing", False),
    ],
)
def test_link_status_reflects_verified_granted_and_missing_scopes(
    monkeypatch, scopes, expected_state, expected_granted
):
    install_identity(monkeypatch)
    monkeypatch.setattr(
        services,
        "verify_google_tokens",
        lambda _id_token, _access_token: _async_result(
            ("google-subject", "reader@example.com", scopes.split())
        ),
    )
    db = FakeDB(rows_results=[[]])
    request = GoogleAccountLinkRequest(
        google_id_token="google-id-token",
        google_access_token="google-access-token",
    )

    result = asyncio.run(services.link_google_account("noema", request, db))

    assert result.state == expected_state
    assert result.drive_appdata_granted is expected_granted
    assert result.sync_available is expected_granted
    assert db.commits == 1
    stored = db.added[0]
    assert stored.granted_scopes == scopes
    assert stored.access_token_enc is None
    assert stored.refresh_token_enc is None


def test_google_account_link_route_verifies_and_returns_status_without_tokens(
    monkeypatch,
):
    install_identity(monkeypatch)
    verified_tokens = []
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", "android-client")
    now = int(datetime.now(timezone.utc).timestamp())
    identity = {
        "aud": "android-client",
        "iss": "https://accounts.google.com",
        "exp": str(now + 600),
        "sub": "google-subject",
        "email": "reader@example.com",
        "email_verified": "true",
    }
    authorization = {
        "issued_to": "android-client",
        "user_id": "google-subject",
        "scope": f"openid {GOOGLE_DRIVE_APPDATA_SCOPE}",
    }

    async def fetch_token_info(parameter, token_value):
        verified_tokens.append((parameter, token_value))
        return identity if parameter == "id_token" else authorization

    monkeypatch.setattr(oauth, "_fetch_token_info", fetch_token_info)
    db = FakeDB(rows_results=[[]])
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[oauth2_scheme] = lambda: "test-noema-token"
    app.dependency_overrides[api_rate_limit] = lambda: None
    app.dependency_overrides[google_oauth_rate_limit] = lambda: None

    response = TestClient(app).post(
        "/google_drive/account/link",
        json={
            "google_id_token": "short-lived-id-token",
            "google_access_token": "short-lived-access-token",
        },
    )

    assert response.status_code == 200
    assert response.json()["state"] == "granted"
    assert response.json()["sync_available"] is True
    assert response.json()["google_email"] == "reader@example.com"
    assert "short-lived-id-token" not in response.text
    assert "short-lived-access-token" not in response.text
    assert verified_tokens == [
        ("id_token", "short-lived-id-token"),
        ("access_token", "short-lived-access-token"),
    ]
    assert db.commits == 1
    assert len(db.added) == 1
    assert db.added[0].access_token_enc is None
    assert db.added[0].refresh_token_enc is None


def test_link_google_account_rejects_identity_owned_by_another_user(monkeypatch):
    install_identity(monkeypatch)
    monkeypatch.setattr(
        services,
        "verify_google_tokens",
        lambda _id_token, _access_token: _async_result(
            ("google-subject", "reader@example.com", [GOOGLE_DRIVE_APPDATA_SCOPE])
        ),
    )
    db = FakeDB(rows_results=[[account(owner=OTHER_USER_ID)]])
    request = GoogleAccountLinkRequest(
        google_id_token="google-id-token",
        google_access_token="google-access-token",
    )

    with pytest.raises(HTTPException) as unavailable:
        asyncio.run(services.link_google_account("noema", request, db))

    assert unavailable.value.status_code == 409
    assert unavailable.value.detail["code"] == "google_account_unavailable"
    assert db.added == []
    assert db.commits == 0


def _async_result(value):
    async def result():
        return value

    return result()


def test_revoked_authorization_is_typed_and_clears_granted_scopes(monkeypatch):
    install_identity(monkeypatch)
    linked = account()
    monkeypatch.setattr(
        services,
        "verify_google_identity",
        lambda _id_token: _async_result(("google-subject", "reader@example.com")),
    )

    async def invalid_access_token(_access_token, _subject):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_google_authorization"},
        )

    monkeypatch.setattr(services, "verify_google_access_token", invalid_access_token)
    request = GoogleAccountLinkRequest(
        google_id_token="google-id-token",
        google_access_token="revoked-access-token",
    )
    db = FakeDB(scalar_results=[linked])

    result = asyncio.run(services.refresh_google_account_status("noema", request, db))

    assert result.state == "revoked"
    assert result.error == "google_authorization_revoked"
    assert linked.granted_scopes is None
    assert linked.is_active is False
    assert db.commits == 1


def test_account_status_never_exposes_legacy_token_columns(monkeypatch):
    install_identity(monkeypatch)
    linked = account()
    linked.access_token_enc = "must-not-be-returned"
    linked.refresh_token_enc = "must-not-be-returned"
    db = FakeDB(scalar_results=[linked])

    result = services.get_google_account_status("noema", db)

    assert result.state == "granted"
    assert "access_token" not in result.model_dump()
    assert "refresh_token" not in result.model_dump()
    assert "access_token_enc" not in GoogleAccountOut.model_fields
    assert "refresh_token_enc" not in GoogleAccountOut.model_fields


def test_unlink_google_account_requires_backup_metadata_to_be_deleted(monkeypatch):
    linked = account()
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    db = FakeDB(scalar_results=[linked, BACKUP_ID])

    with pytest.raises(HTTPException) as conflict:
        auth_service.delete_google_account("noema", str(ACCOUNT_ID), db)

    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "google_account_has_backups"
    assert db.deleted == []
    assert db.commits == 0


def test_unlink_google_account_handles_backup_insert_race(monkeypatch):
    linked = account()
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    db = FakeDB(scalar_results=[linked, None])

    def fail_commit():
        raise IntegrityError("delete", {}, Exception("foreign key violation"))

    db.commit = fail_commit

    with pytest.raises(HTTPException) as conflict:
        auth_service.delete_google_account("noema", str(ACCOUNT_ID), db)

    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "google_account_has_backups"
    assert db.rollbacks == 1


def test_unlink_google_account_deletes_account_after_backups_are_removed(monkeypatch):
    linked = account()
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    db = FakeDB(scalar_results=[linked, None])

    result = auth_service.delete_google_account("noema", str(ACCOUNT_ID), db)

    assert result is True
    assert db.deleted == [linked]
    assert db.commits == 1


def test_google_account_delete_route_unlinks_account(monkeypatch):
    linked = account()
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    db = FakeDB(scalar_results=[linked, None])
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[oauth2_scheme] = lambda: "test-noema-token"

    response = TestClient(app).delete(f"/auth/google/delete/{ACCOUNT_ID}")

    assert response.status_code == 200
    assert response.json() is True
    assert db.deleted == [linked]
    assert db.commits == 1


def test_unlink_google_account_returns_not_found_for_other_user(monkeypatch):
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    db = FakeDB(scalar_results=[None])

    with pytest.raises(HTTPException) as missing:
        auth_service.delete_google_account("noema", str(ACCOUNT_ID), db)

    assert missing.value.status_code == 404
    assert db.commits == 0


def test_legacy_google_account_get_works_before_schema_migration(monkeypatch):
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    db = FakeDB(
        execute_row={
            "id": ACCOUNT_ID,
            "id_user": USER_ID,
            "google_user_id": "google-subject",
            "email_google": "reader@example.com",
            "granted_scopes": "openid",
            "is_active": True,
            "expires_at": None,
            "last_refresh_at": None,
            "updated_at": None,
            "created_at": None,
            "drive_appdata_status": "unknown",
            "scope_checked_at": None,
        }
    )

    result = auth_service.get_google_account_out("noema", str(USER_ID), db)

    selected_columns = str(db.executed_statements[0])
    assert "to_jsonb(google_account)->>'drive_appdata_status'" in selected_columns
    assert "to_jsonb(google_account)->>'scope_checked_at'" in selected_columns
    assert "access_token_enc" not in selected_columns
    assert "refresh_token_enc" not in selected_columns
    assert result.drive_appdata_status == "unknown"
    assert result.scope_checked_at is None


def test_legacy_google_account_get_returns_persisted_status_after_migration(
    monkeypatch,
):
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    row = {
        "id": ACCOUNT_ID,
        "id_user": USER_ID,
        "google_user_id": "google-subject",
        "email_google": "reader@example.com",
        "granted_scopes": GOOGLE_DRIVE_APPDATA_SCOPE,
        "is_active": True,
        "expires_at": None,
        "last_refresh_at": None,
        "updated_at": None,
        "created_at": None,
        "drive_appdata_status": "granted",
        "scope_checked_at": datetime(2026, 10, 31, tzinfo=timezone.utc),
    }
    db = FakeDB(execute_row=row)

    result = auth_service.get_google_account_out("noema", str(USER_ID), db)

    assert result.drive_appdata_status == "granted"
    assert result.scope_checked_at == row["scope_checked_at"]


def test_legacy_google_account_get_defaults_missing_sync_metadata(monkeypatch):
    monkeypatch.setattr(
        auth_service,
        "get_current_user",
        lambda _token, _db: SimpleNamespace(id=USER_ID),
    )
    db = FakeDB(
        execute_row={
            "id": ACCOUNT_ID,
            "id_user": USER_ID,
            "google_user_id": "google-subject",
            "email_google": "reader@example.com",
            "granted_scopes": "openid",
            "is_active": True,
            "expires_at": None,
            "last_refresh_at": None,
            "updated_at": None,
            "created_at": None,
        }
    )

    result = auth_service.get_google_account_out("noema", str(USER_ID), db)

    assert result.drive_appdata_status == "unknown"
    assert result.scope_checked_at is None


def test_backup_metadata_create_retry_is_idempotent_and_owner_checked(monkeypatch):
    install_identity(monkeypatch)
    payload = create_payload()
    owned_account = account()
    owned_device = SimpleNamespace(id=DEVICE_ID, id_user=USER_ID)
    db = FakeDB(scalar_results=[owned_account, owned_device, None])

    created = services.create_backup_metadata("noema", payload, db)
    assert db.commits == 1
    assert created.drive_version == "42"
    assert created.snapshot_version == "17"
    assert created.size_bytes == 84210
    receipt = next(
        row for row in db.added if isinstance(row, BackupOperationIdempotency)
    )

    retry_db = FakeDB(scalar_results=[owned_account, owned_device, receipt, created])
    retried = services.create_backup_metadata("noema", payload, retry_db)
    assert retried is created
    assert retry_db.commits == 0

    different = create_payload(content_hash="sha256:1234567890abcdef")
    conflict_db = FakeDB(scalar_results=[owned_account, owned_device, receipt])
    with pytest.raises(HTTPException) as conflict:
        services.create_backup_metadata("noema", different, conflict_db)
    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "idempotency_key_reused"


def test_backup_metadata_update_checks_both_expected_versions(monkeypatch):
    install_identity(monkeypatch)
    current = backup_row()
    update = BackupMetadataUpdate(
        expected_drive_version="42",
        expected_content_hash=current.content_hash,
        idempotency_key="7ef7aeb7-3032-4c56-99a4-b03364d28e12",
        drive_version="43",
        snapshot_version="18",
        content_hash="sha256:95734f510aa6f18433bc87be9385ea12",
        size_bytes=85200,
        operation_state="completed",
        manifest=SnapshotManifest(
            format="noema-snapshot",
            schema_version=1,
            snapshot_version="18",
            created_at=datetime(2026, 10, 31, 0, 10, tzinfo=timezone.utc),
            installation_id="install-7d2c",
            included_categories=["local_library"],
            excluded_categories=["global_preferences"],
            counts={"local_library": 13},
            hashes={"local_library": "sha256:95734f510aa6f18433bc87be9385ea12"},
        ),
    )
    db = FakeDB(scalar_results=[current, None])

    updated = services.update_backup_metadata("noema", BACKUP_ID, update, db)
    assert updated.drive_version == "43"
    assert updated.snapshot_version == "18"
    assert db.commits == 1
    receipt = next(
        row for row in db.added if isinstance(row, BackupOperationIdempotency)
    )

    current.drive_version = "44"
    replay_db = FakeDB(scalar_results=[current, receipt])
    replay = services.update_backup_metadata("noema", BACKUP_ID, update, replay_db)
    assert replay.drive_version == "44"
    assert replay_db.commits == 0

    stale = BackupMetadataUpdate(
        **{
            **update.model_dump(),
            "expected_drive_version": "41",
            "idempotency_key": "another-idempotency-key-1234",
        }
    )
    conflict_db = FakeDB(scalar_results=[current, None])
    with pytest.raises(HTTPException) as conflict:
        services.update_backup_metadata("noema", BACKUP_ID, stale, conflict_db)
    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "backup_version_conflict"
    assert conflict.value.detail["current"]["drive_version"] == "44"
    assert conflict_db.commits == 0


def test_legacy_backup_create_uses_stable_retry_key(monkeypatch):
    install_identity(monkeypatch)
    payload = BackupFileCreate(
        id_google_account=ACCOUNT_ID,
        drive_file_id="legacy-drive-file",
        local_ref="legacy-ref",
        drive_version="7",
        content_hash="legacy-hash",
    )
    owned_account = account()
    first_db = FakeDB(scalar_results=[owned_account, None])
    created = services.create_legacy_backup_file("noema", payload, first_db)
    receipt = next(
        row for row in first_db.added if isinstance(row, BackupOperationIdempotency)
    )

    retry_db = FakeDB(scalar_results=[owned_account, receipt, created])
    retried = services.create_legacy_backup_file("noema", payload, retry_db)

    assert retried is created
    assert retry_db.commits == 0


def test_backup_get_list_and_delete_are_metadata_only(monkeypatch):
    install_identity(monkeypatch)
    row = backup_row()
    get_db = FakeDB(scalar_results=[row])
    assert services.get_backup_file("noema", str(BACKUP_ID), get_db) is row

    list_db = FakeDB(rows_results=[[row]])
    assert services.list_backup_files("noema", list_db) == [row]

    delete_db = FakeDB(scalar_results=[row])
    services.delete_backup_metadata("noema", BACKUP_ID, delete_db)
    assert delete_db.deleted == [row]
    assert delete_db.commits == 1


def test_sync_log_preserves_legacy_wire_name_and_rejects_sensitive_data():
    log = SimpleNamespace(
        id=uuid4(),
        id_device=DEVICE_ID,
        id_backup_file=BACKUP_ID,
        id_google_account=ACCOUNT_ID,
        id_user=USER_ID,
        event="sync_completed",
        direction=SyncDirection.UPLOAD,
        result=SyncResult.SUCCESS,
        conflict_strategy=ConflictStrategy.KEEP_REMOTE,
        error_details=None,
        metadata_={"snapshot_version": "18"},
        created_at=datetime(2026, 10, 31, tzinfo=timezone.utc),
    )
    serialized = SyncLogOut.model_validate(log).model_dump(by_alias=True)
    assert serialized["derection"] == "upload"
    assert "direction" not in serialized

    with pytest.raises(ValueError):
        SyncLogCreate(
            id_device=DEVICE_ID,
            id_google_account=ACCOUNT_ID,
            event="sync_completed",
            derection="upload",
            result="success",
            metadata={"payload": "snapshot bytes"},
        )
    with pytest.raises(ValueError):
        SyncLogCreate(
            id_device=DEVICE_ID,
            id_google_account=ACCOUNT_ID,
            event="sync_completed",
            derection="upload",
            result="success",
            error_details="Bearer top-secret",
        )


def test_sync_log_creation_is_owned_idempotent_and_records_client_strategy(monkeypatch):
    install_identity(monkeypatch)
    device = SimpleNamespace(id=DEVICE_ID, id_user=USER_ID)
    linked = account()
    request = SyncLogCreate(
        id_device=DEVICE_ID,
        id_google_account=ACCOUNT_ID,
        idempotency_key="454d8074-3110-438b-b4f3-a3f604f9b9e8",
        event="sync_completed",
        derection="upload",
        result="success",
        conflict_strategy="keep_remote",
        metadata={
            "snapshot_version": "18",
            "content_hash": "sha256:95734f510aa6f18433bc87be9385ea12",
        },
    )
    db = FakeDB(scalar_results=[device, linked, None])

    created = services.create_sync_log("noema", request, db)

    assert created.id_user == USER_ID
    assert created.direction == SyncDirection.UPLOAD
    assert created.conflict_strategy == ConflictStrategy.KEEP_REMOTE
    assert created.metadata_["snapshot_version"] == "18"
    assert db.commits == 1

    retry_db = FakeDB(scalar_results=[device, linked, created])
    assert services.create_sync_log("noema", request, retry_db) is created
    assert retry_db.commits == 0

    foreign_device_db = FakeDB(scalar_results=[None])
    with pytest.raises(HTTPException) as denied:
        services.create_sync_log("noema", request, foreign_device_db)
    assert denied.value.status_code == 404


def test_legacy_backup_contract_and_additive_migration_are_preserved():
    legacy = BackupFileCreate(
        id_google_account=ACCOUNT_ID,
        drive_file_id="old-drive-id",
        local_ref="legacy-ref",
        drive_version="7",
        content_hash="legacy-hash",
    )
    assert legacy.snapshot_version == "legacy"
    migration = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "20261031_google_drive_sync_metadata.sql"
    ).read_text()
    assert "UPDATE google_drive.backup_file" in migration
    assert "UPDATE google_drive.sync_log" in migration
    assert "DROP TABLE" not in migration.upper()
    assert "DELETE FROM google_drive.backup_file" not in migration.upper()


def test_snapshot_manifest_rejects_payload_fields_and_oversized_manifest():
    with pytest.raises(ValueError):
        SnapshotManifest.model_validate(
            {
                "format": "noema-snapshot",
                "schema_version": 1,
                "snapshot_version": "1",
                "created_at": datetime.now(timezone.utc),
                "installation_id": "install",
                "included_categories": [],
                "excluded_categories": [],
                "counts": {},
                "hashes": {},
                "payload": "not allowed",
            }
        )
    manifest = SnapshotManifest(
        format="noema-snapshot",
        schema_version=1,
        snapshot_version="1",
        created_at=datetime.now(timezone.utc),
        installation_id="install",
        included_categories=[f"{index:02}" + "x" * 62 for index in range(64)],
        excluded_categories=[],
        counts={},
        hashes={},
    )
    assert len(manifest.model_dump_json()) < 16 * 1024


@pytest.mark.parametrize(
    "password",
    ["short1", "letters-only", "12345678", "       1"],
)
def test_password_policy_requires_eight_characters_letter_and_number(password):
    with pytest.raises(ValueError):
        validate_password_strength(password)


def test_password_policy_does_not_trim_and_update_requires_current_password(
    monkeypatch,
):
    password = "  LocalPass1  "
    assert validate_password_strength("  SenhaÁrvore١  ") == "  SenhaÁrvore١  "
    assert (
        UserCreate(primary_email="reader@example.com", password=password).password
        == password
    )
    update = UserUpdate(password="NewLocalPass2")
    user = SimpleNamespace(password_hash="stored-hash")
    install = monkeypatch.setattr
    install(user_service, "get_current_user", lambda token, db: user)
    install(user_service, "verify_password", lambda _plain, _hash: False)
    with pytest.raises(HTTPException) as denied:
        user_service.up_user(update, "noema", FakeDB())
    assert denied.value.status_code == 401

    monkeypatch.setattr(
        user_service,
        "verify_password",
        lambda plain, _stored: plain == "OldPass1",
    )
    monkeypatch.setattr(user_service, "hash_password", lambda _plain: "new-hash")
    success_db = FakeDB()
    user_service.up_user(
        UserUpdate(current_password="OldPass1", password="NewPass2"),
        "noema",
        success_db,
    )
    assert user.password_hash == "new-hash"
    assert success_db.commits == 1


def test_password_reset_consumes_code_and_changes_password_atomically(monkeypatch):
    user = SimpleNamespace(id=USER_ID, password_hash="old-hash", updated_at=None)
    reset_token = SimpleNamespace(used_at=None)
    monkeypatch.setattr(
        auth_service,
        "get_user_by_identificator",
        lambda **_kwargs: user,
    )
    monkeypatch.setattr(auth_service, "hash_password", lambda _password: "new-hash")
    db = FakeDB(scalar_results=[reset_token])

    result = auth_service.confirm_password_reset(
        "valid-code", "reader@example.com", db, "NewPass123"
    )

    assert result == "Sucesso"
    assert reset_token.used_at is not None
    assert user.password_hash == "new-hash"
    assert db.commits == 1


def test_direct_transfer_and_merge_are_not_implemented_in_backend():
    from app.main import app

    paths = app.openapi()["paths"]
    assert not any(
        word in path.lower()
        for path in paths
        for word in ("upload-payload", "download-payload", "merge")
    )
    assert BackupFileOut.model_fields["content_hash"]
    assert "bytes" not in BackupFileOut.model_fields
    assert not hasattr(BackupFile, "payload")
