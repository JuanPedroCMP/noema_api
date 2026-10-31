import datetime
import enum
import uuid
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ConflictStrategy(str, enum.Enum):
    KEEP_LOCAL = 'keep_local'
    KEEP_REMOTE = 'keep_remote'
    MERGE = 'merge'
    DUPLICATE = 'duplicate'


class SyncDirection(str, enum.Enum):
    UPLOAD = 'upload'
    DOWNLOAD = 'download'


class SyncResult(str, enum.Enum):
    SUCCESS = 'success'
    FAILURE = 'failure'
    IN_CONFLICT = 'in_conflict'


class BackupOperationState(str, enum.Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'


class User(Base):
    __tablename__ = 'user'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='user_pk'),
        UniqueConstraint('primary_email', name='primary_email_uq'),
        UniqueConstraint('user_name', name='user_name_uq'),
        {'schema': 'app_auth'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_name: Mapped[str] = mapped_column(String(128), nullable=False)
    primary_email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    user_display_name: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    is_verified: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))

    google_account: Mapped['GoogleAccount'] = relationship('GoogleAccount', uselist=False, back_populates='user')
    device: Mapped[list['Device']] = relationship('Device', back_populates='user')


class GoogleAccount(Base):
    __tablename__ = 'google_account'
    __table_args__ = (
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='google_account_pk'),
        UniqueConstraint('email_google', name='email_google_uq'),
        UniqueConstraint('google_user_id', name='google_user_id_uq'),
        UniqueConstraint('id_user', name='google_account_uq'),
        {'schema': 'app_auth'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    google_user_id: Mapped[Optional[str]] = mapped_column(Text)
    email_google: Mapped[Optional[str]] = mapped_column(String(254))
    access_token_enc: Mapped[Optional[str]] = mapped_column(Text)
    refresh_token_enc: Mapped[Optional[str]] = mapped_column(Text)
    granted_scopes: Mapped[Optional[str]] = mapped_column(String(2048))
    drive_appdata_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'unknown'")
    )
    scope_checked_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    last_refresh_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    user: Mapped['User'] = relationship('User', back_populates='google_account')
    backup_file: Mapped[list['BackupFile']] = relationship('BackupFile', back_populates='google_account')


class Device(Base):
    __tablename__ = 'device'
    __table_args__ = (
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='user_fk'),
        PrimaryKeyConstraint('id', name='device_pk'),
        {'schema': 'device'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_user: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    device_name: Mapped[Optional[str]] = mapped_column(String(64))
    platform: Mapped[Optional[str]] = mapped_column(String(32))
    last_seen_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    user: Mapped['User'] = relationship('User', back_populates='device')
    sync_log: Mapped[list['SyncLog']] = relationship('SyncLog', back_populates='device')


class BackupFile(Base):
    __tablename__ = 'backup_file'
    __table_args__ = (
        ForeignKeyConstraint(['id_google_account'], ['app_auth.google_account.id'], ondelete='RESTRICT', onupdate='CASCADE', match='FULL', name='google_account_fk'),
        ForeignKeyConstraint(['id_device'], ['device.device.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='backup_device_fk'),
        PrimaryKeyConstraint('id', name='workspace_drive_pk'),
        Index('backup_file_owner_created_idx', 'id_google_account', 'created_at'),
        Index(
            'backup_file_idempotency_idx',
            'id_google_account',
            'idempotency_key',
            unique=True,
            postgresql_where=text('idempotency_key IS NOT NULL'),
        ),
        {'schema': 'google_drive'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_google_account: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    id_device: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    drive_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    local_ref: Mapped[Optional[str]] = mapped_column(String(255))
    drive_version: Mapped[Optional[str]] = mapped_column(String(255))
    snapshot_version: Mapped[Optional[str]] = mapped_column(String(128))
    content_hash: Mapped[Optional[str]] = mapped_column(Text)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    operation_state: Mapped[BackupOperationState] = mapped_column(
        Enum(
            BackupOperationState,
            values_callable=lambda cls: [member.value for member in cls],
            name='backup_operation_state',
            schema='google_drive',
        ),
        nullable=False,
        server_default=text("'completed'"),
    )
    manifest: Mapped[Optional[dict]] = mapped_column(JSONB)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))

    google_account: Mapped['GoogleAccount'] = relationship('GoogleAccount', back_populates='backup_file')
    device: Mapped[Optional['Device']] = relationship()
    sync_log: Mapped[list['SyncLog']] = relationship('SyncLog', back_populates='backup_file')


class BackupOperationIdempotency(Base):
    __tablename__ = 'backup_operation_idempotency'
    __table_args__ = (
        ForeignKeyConstraint(
            ['id_google_account'],
            ['app_auth.google_account.id'],
            ondelete='CASCADE',
            onupdate='CASCADE',
            name='backup_operation_account_fk',
        ),
        ForeignKeyConstraint(
            ['id_backup_file'],
            ['google_drive.backup_file.id'],
            ondelete='SET NULL',
            onupdate='CASCADE',
            name='backup_operation_file_fk',
        ),
        PrimaryKeyConstraint('id', name='backup_operation_idempotency_pk'),
        UniqueConstraint(
            'id_google_account',
            'idempotency_key',
            name='backup_operation_idempotency_uq',
        ),
        CheckConstraint(
            "operation_kind IN ('create', 'update')",
            name='backup_operation_kind_ck',
        ),
        {'schema': 'google_drive'},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id_google_account: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    id_backup_file: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=text('CURRENT_TIMESTAMP')
    )


class SyncLog(Base):
    __tablename__ = 'sync_log'
    __table_args__ = (
        ForeignKeyConstraint(['id_backup_file'], ['google_drive.backup_file.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='backup_file_fk'),
        ForeignKeyConstraint(['id_device'], ['device.device.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='device_fk'),
        ForeignKeyConstraint(['id_google_account'], ['app_auth.google_account.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='sync_log_google_account_fk'),
        ForeignKeyConstraint(['id_user'], ['app_auth.user.id'], ondelete='SET NULL', onupdate='CASCADE', match='FULL', name='sync_log_user_fk'),
        PrimaryKeyConstraint('id', name='sync_log_pk'),
        Index('sync_log_account_created_idx', 'id_google_account', 'created_at'),
        Index(
            'sync_log_idempotency_idx',
            'id_user',
            'idempotency_key',
            unique=True,
            postgresql_where=text('idempotency_key IS NOT NULL'),
        ),
        {'schema': 'google_drive'}
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    direction: Mapped[SyncDirection] = mapped_column(Enum(SyncDirection, values_callable=lambda cls: [member.value for member in cls], name='sync_direction', schema='google_drive'), nullable=False)
    result: Mapped[SyncResult] = mapped_column(Enum(SyncResult, values_callable=lambda cls: [member.value for member in cls], name='sync_result', schema='google_drive'), nullable=False)
    id_device: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    event: Mapped[Optional[str]] = mapped_column(Text)
    conflict_strategy: Mapped[Optional[ConflictStrategy]] = mapped_column(Enum(ConflictStrategy, values_callable=lambda cls: [member.value for member in cls], name='conflict_strategy', schema='google_drive'))
    error_details: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSON)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('CURRENT_TIMESTAMP'))
    id_backup_file: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    id_google_account: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    id_user: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128))

    backup_file: Mapped[Optional['BackupFile']] = relationship('BackupFile', back_populates='sync_log')
    device: Mapped[Optional['Device']] = relationship('Device', back_populates='sync_log')
