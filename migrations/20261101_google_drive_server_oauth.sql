BEGIN;

ALTER TYPE google_drive.backup_operation_state ADD VALUE IF NOT EXISTS 'uploading';

ALTER TABLE app_auth.google_account
    ADD COLUMN IF NOT EXISTS refresh_token_key_version VARCHAR(32),
    ADD COLUMN IF NOT EXISTS refresh_lock_until TIMESTAMPTZ;

ALTER TABLE google_drive.backup_file
    ADD COLUMN IF NOT EXISTS drive_etag VARCHAR(255);

CREATE TABLE IF NOT EXISTS google_drive.oauth_state (
    id UUID PRIMARY KEY,
    id_user UUID NOT NULL REFERENCES app_auth."user"(id) ON DELETE CASCADE,
    state_hash VARCHAR(128) NOT NULL UNIQUE,
    nonce_hash VARCHAR(128) NOT NULL,
    nonce_enc TEXT NOT NULL,
    code_verifier_enc TEXT NOT NULL,
    redirect_uri VARCHAR(2048) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    completion_consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE google_drive.oauth_state
    ADD COLUMN IF NOT EXISTS completion_consumed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS oauth_state_expiry_idx
    ON google_drive.oauth_state (expires_at);

CREATE TABLE IF NOT EXISTS google_drive.sync_operation (
    id UUID PRIMARY KEY,
    id_user UUID NOT NULL REFERENCES app_auth."user"(id) ON DELETE CASCADE,
    id_google_account UUID NOT NULL REFERENCES app_auth.google_account(id) ON DELETE CASCADE,
    id_backup_file UUID REFERENCES google_drive.backup_file(id) ON DELETE SET NULL,
    id_device UUID REFERENCES device.device(id) ON DELETE SET NULL,
    local_ref VARCHAR(255) NOT NULL,
    operation_kind VARCHAR(16) NOT NULL CHECK (operation_kind IN ('upload', 'download', 'list', 'metadata', 'delete')),
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    request_payload JSONB,
    drive_file_id VARCHAR(255),
    result_payload JSONB,
    state VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'uploading', 'completed', 'failed')),
    error_code VARCHAR(64),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_user, idempotency_key)
);
ALTER TABLE google_drive.sync_operation
    ADD COLUMN IF NOT EXISTS request_payload JSONB,
    ADD COLUMN IF NOT EXISTS drive_file_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS result_payload JSONB;
CREATE INDEX IF NOT EXISTS sync_operation_account_lock_idx
    ON google_drive.sync_operation (id_google_account, local_ref);
CREATE INDEX IF NOT EXISTS sync_operation_pending_idx
    ON google_drive.sync_operation (state, next_attempt_at, created_at)
    WHERE state IN ('pending', 'uploading');

COMMIT;
