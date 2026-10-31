from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from ...core.db_models.google_drive_models import (
    BackupOperationState,
    ConflictStrategy,
    SyncDirection,
    SyncResult,
)

GOOGLE_DRIVE_APPDATA_SCOPE = "https://www.googleapis.com/auth/drive.appdata"
MAX_BACKUP_SIZE_BYTES = 10 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024
SAFE_LOG_METADATA_KEYS = {
    "snapshot_version",
    "drive_revision",
    "content_hash",
    "file_size_bytes",
    "installation_id",
    "operation_id",
}
SAFE_SYNC_EVENTS = {
    "sync_started",
    "sync_completed",
    "sync_failed",
    "conflict_detected",
    "authorization_refreshed",
    "backup_created",
    "backup_updated",
    "backup_deleted",
}
SAFE_SYNC_ERROR_CODES = {
    "google_authorization_revoked",
    "drive_appdata_scope_missing",
    "drive_revision_conflict",
    "drive_file_missing",
    "drive_quota_exceeded",
    "network_unavailable",
    "snapshot_validation_failed",
    "restore_failed",
    "unknown_error",
}
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?:bearer\s+\S+|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|"
    r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|"
    r"(?:access[_ -]?token|refresh[_ -]?token|password|secret|prompt|note|payload)\s*[:=])",
    re.IGNORECASE,
)


def _is_safe_log_metadata(key: str, value: Any) -> bool:
    if key not in SAFE_LOG_METADATA_KEYS:
        return False
    if key == "file_size_bytes":
        return type(value) is int and 0 <= value <= MAX_BACKUP_SIZE_BYTES
    if not isinstance(value, str) or len(value) > 128:
        return False
    if key == "content_hash":
        return bool(
            re.fullmatch(r"(?:[A-Za-z0-9_-]{1,16}:)?[A-Fa-f0-9]{16,128}", value)
        )
    return bool(
        re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value)
        and not SENSITIVE_VALUE_PATTERN.search(value)
    )


class GoogleAccountLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    google_id_token: SecretStr = Field(min_length=1, max_length=8192)
    google_access_token: SecretStr = Field(min_length=1, max_length=8192)


class GoogleAccountStatusOut(BaseModel):
    account_id: UUID | None
    google_email: str | None
    state: Literal["not_linked", "granted", "missing", "revoked", "unknown"]
    drive_appdata_granted: bool
    sync_available: bool
    granted_scopes: list[str]
    checked_at: datetime | None
    error: (
        Literal[
            "google_account_not_linked",
            "drive_appdata_scope_missing",
            "google_authorization_revoked",
            "google_authorization_unverified",
        ]
        | None
    )


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str = Field(min_length=1, max_length=64)
    schema_version: int = Field(ge=1, le=1_000_000, strict=True)
    snapshot_version: str = Field(min_length=1, max_length=128)
    created_at: datetime
    installation_id: str = Field(min_length=1, max_length=128)
    included_categories: list[str] = Field(max_length=64)
    excluded_categories: list[str] = Field(max_length=64)
    counts: dict[str, StrictInt] = Field(max_length=100)
    hashes: dict[str, StrictStr] = Field(max_length=100)

    @field_validator("format", "snapshot_version", "installation_id")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
            raise ValueError("value contains unsupported characters")
        return value

    @field_validator("included_categories", "excluded_categories")
    @classmethod
    def validate_categories(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("categories must be unique")
        if any(not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", item) for item in values):
            raise ValueError("category names must contain 1 to 64 characters")
        return values

    @field_validator("counts")
    @classmethod
    def validate_counts(cls, values: dict[str, int]) -> dict[str, int]:
        if any(
            not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", key)
            or count < 0
            or count > 10_000_000_000
            for key, count in values.items()
        ):
            raise ValueError("manifest counts must be non-negative integers")
        return values

    @field_validator("hashes")
    @classmethod
    def validate_hashes(cls, values: dict[str, str]) -> dict[str, str]:
        if any(
            not re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", key)
            or not re.fullmatch(r"(?:[A-Za-z0-9_-]{1,16}:)?[A-Fa-f0-9]{16,128}", value)
            for key, value in values.items()
        ):
            raise ValueError("manifest hashes must be bounded strings")
        return values

    @model_validator(mode="after")
    def enforce_size_limit(self) -> SnapshotManifest:
        if set(self.included_categories) & set(self.excluded_categories):
            raise ValueError("a category cannot be both included and excluded")
        if not set(self.counts) <= set(self.included_categories):
            raise ValueError("manifest counts must refer to included categories")
        if not set(self.hashes) <= set(self.included_categories):
            raise ValueError("manifest hashes must refer to included categories")
        if (
            len(
                json.dumps(self.model_dump(mode="json"), separators=(",", ":")).encode()
            )
            > MAX_MANIFEST_BYTES
        ):
            raise ValueError("manifest exceeds the 16 KiB limit")
        return self


class BackupMetadataFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_google_account: UUID
    id_device: UUID | None = None
    drive_file_id: str = Field(min_length=1, max_length=255)
    local_ref: str | None = Field(default=None, max_length=255)
    drive_version: str = Field(
        min_length=1,
        max_length=255,
        description="Drive API file version/revision; distinct from snapshot_version.",
    )
    snapshot_version: str = Field(
        min_length=1,
        max_length=128,
        description="Logical snapshot version assigned by the Flutter app.",
    )
    content_hash: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=0, le=MAX_BACKUP_SIZE_BYTES, strict=True)
    operation_state: BackupOperationState = BackupOperationState.COMPLETED
    manifest: SnapshotManifest | None = None

    @field_validator(
        "drive_file_id", "drive_version", "snapshot_version", "content_hash"
    )
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 32 for character in value):
            raise ValueError("control characters are not allowed")
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash_shape(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[A-Za-z0-9_-]{1,16}:)?[A-Fa-f0-9]{16,128}", value):
            raise ValueError("content_hash must be a bounded hexadecimal digest")
        return value


class BackupMetadataCreate(BackupMetadataFields):
    id_device: UUID
    operation_state: BackupOperationState
    manifest: SnapshotManifest
    idempotency_key: str = Field(min_length=16, max_length=128)


class BackupMetadataUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_drive_version: str | None
    expected_content_hash: str | None
    idempotency_key: str = Field(min_length=16, max_length=128)
    drive_version: str = Field(min_length=1, max_length=255)
    snapshot_version: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=0, le=MAX_BACKUP_SIZE_BYTES, strict=True)
    operation_state: BackupOperationState
    manifest: SnapshotManifest

    @field_validator(
        "expected_drive_version",
        "expected_content_hash",
        "drive_version",
        "snapshot_version",
        "content_hash",
    )
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(character) < 32 for character in value):
            raise ValueError("control characters are not allowed")
        return value

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash_shape(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[A-Za-z0-9_-]{1,16}:)?[A-Fa-f0-9]{16,128}", value):
            raise ValueError("content_hash must be a bounded hexadecimal digest")
        return value


class BackupFileCreate(BaseModel):
    """Compatibility input for the original /backup_file/create contract."""

    model_config = ConfigDict(extra="forbid")

    id_google_account: UUID
    drive_file_id: str = Field(min_length=1, max_length=255)
    local_ref: str | None = Field(default=None, max_length=255)
    drive_version: str = Field(min_length=1, max_length=255)
    content_hash: str = Field(min_length=1, max_length=128)
    snapshot_version: str = Field(default="legacy", min_length=1, max_length=128)
    id_device: UUID | None = None
    size_bytes: int = Field(default=0, ge=0, le=MAX_BACKUP_SIZE_BYTES)
    operation_state: BackupOperationState = BackupOperationState.COMPLETED
    manifest: SnapshotManifest | None = None
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)


class BackupFileFilters(BaseModel):
    id: UUID | None = None
    id_google_account: UUID | None = None
    id_device: UUID | None = None
    drive_file_id: str | None = Field(default=None, max_length=255)
    local_ref: str | None = Field(default=None, max_length=255)
    snapshot_version: str | None = Field(default=None, max_length=128)
    operation_state: BackupOperationState | None = None


class BackupFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    id_google_account: UUID
    id_device: UUID | None
    drive_file_id: str
    local_ref: str | None
    drive_version: str | None
    snapshot_version: str | None
    content_hash: str | None
    size_bytes: int | None
    operation_state: BackupOperationState
    manifest: dict[str, Any] | None = Field(validation_alias="manifest")
    created_at: datetime | None
    updated_at: datetime | None


class SyncLogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id_device: UUID
    id_backup_file: UUID | None = None
    id_google_account: UUID | None = None
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=128)
    event: Literal[
        "sync_started",
        "sync_completed",
        "sync_failed",
        "conflict_detected",
        "authorization_refreshed",
        "backup_created",
        "backup_updated",
        "backup_deleted",
    ]
    derection: SyncDirection = Field(
        validation_alias=AliasChoices("derection", "direction"),
        serialization_alias="derection",
    )
    result: SyncResult
    conflict_strategy: ConflictStrategy | None = None
    error_details: (
        Literal[
            "google_authorization_revoked",
            "drive_appdata_scope_missing",
            "drive_revision_conflict",
            "drive_file_missing",
            "drive_quota_exceeded",
            "network_unavailable",
            "snapshot_validation_failed",
            "restore_failed",
            "unknown_error",
        ]
        | None
    ) = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("metadata", "metadata_"),
        serialization_alias="metadata",
    )

    @field_validator("metadata")
    @classmethod
    def validate_safe_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        if any(not _is_safe_log_metadata(key, item) for key, item in value.items()):
            raise ValueError("sync log metadata contains unsupported or unsafe values")
        return value


class SyncLogFilters(BaseModel):
    id: UUID | None = None
    id_device: UUID | None = None
    id_backup_file: UUID | None = None
    id_google_account: UUID | None = None
    event: str | None = Field(default=None, max_length=64)
    derection: SyncDirection | None = Field(
        default=None,
        validation_alias=AliasChoices("derection", "direction"),
    )
    result: SyncResult | None = None
    conflict_strategy: ConflictStrategy | None = None


class SyncLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    id_device: UUID | None
    id_backup_file: UUID | None
    id_google_account: UUID | None
    id_user: UUID | None
    event: str | None
    derection: SyncDirection = Field(
        validation_alias=AliasChoices("derection", "direction"),
        serialization_alias="derection",
    )
    result: SyncResult
    conflict_strategy: ConflictStrategy | None
    error_details: str | None
    metadata: dict[str, Any] = Field(
        validation_alias=AliasChoices("metadata_", "metadata"),
        serialization_alias="metadata",
    )
    created_at: datetime | None

    @field_validator("event", mode="before")
    @classmethod
    def redact_legacy_event(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or value not in SAFE_SYNC_EVENTS:
            return "legacy_event_redacted"
        return value

    @field_validator("metadata", mode="before")
    @classmethod
    def redact_legacy_metadata(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {
            key: item for key, item in value.items() if _is_safe_log_metadata(key, item)
        }

    @field_validator("error_details", mode="before")
    @classmethod
    def redact_legacy_error_details(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or value not in SAFE_SYNC_ERROR_CODES:
            return "legacy_error_redacted"
        return value
