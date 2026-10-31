BEGIN;

ALTER TABLE app_auth.google_account
    ALTER COLUMN granted_scopes TYPE VARCHAR(2048);
ALTER TABLE app_auth.google_account
    ADD COLUMN IF NOT EXISTS drive_appdata_status VARCHAR(16) NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS scope_checked_at TIMESTAMPTZ;

-- Existing server-side OAuth credentials are no longer used by the native flow.
UPDATE app_auth.google_account
SET access_token_enc = NULL,
    refresh_token_enc = NULL
WHERE access_token_enc IS NOT NULL
   OR refresh_token_enc IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'google_drive'
          AND t.typname = 'backup_operation_state'
    ) THEN
        CREATE TYPE google_drive.backup_operation_state AS ENUM (
            'pending', 'completed', 'failed'
        );
    END IF;
END;
$$;

ALTER TABLE google_drive.backup_file
    ADD COLUMN IF NOT EXISTS id_device UUID,
    ADD COLUMN IF NOT EXISTS snapshot_version VARCHAR(128),
    ADD COLUMN IF NOT EXISTS size_bytes BIGINT,
    ADD COLUMN IF NOT EXISTS operation_state google_drive.backup_operation_state
        NOT NULL DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS manifest JSONB,
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128),
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

UPDATE google_drive.backup_file
SET snapshot_version = 'legacy'
WHERE snapshot_version IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'backup_device_fk'
          AND conrelid = 'google_drive.backup_file'::regclass
    ) THEN
        ALTER TABLE google_drive.backup_file
            ADD CONSTRAINT backup_device_fk
            FOREIGN KEY (id_device) REFERENCES device.device(id)
            ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS backup_file_owner_created_idx
    ON google_drive.backup_file (id_google_account, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS backup_file_idempotency_idx
    ON google_drive.backup_file (id_google_account, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS google_drive.backup_operation_idempotency (
    id UUID NOT NULL,
    id_google_account UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    operation_kind VARCHAR(16) NOT NULL
        CHECK (operation_kind IN ('create', 'update')),
    request_hash VARCHAR(64) NOT NULL,
    id_backup_file UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT backup_operation_idempotency_pk PRIMARY KEY (id),
    CONSTRAINT backup_operation_account_fk
        FOREIGN KEY (id_google_account)
        REFERENCES app_auth.google_account(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT backup_operation_file_fk
        FOREIGN KEY (id_backup_file)
        REFERENCES google_drive.backup_file(id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT backup_operation_kind_ck
        CHECK (operation_kind IN ('create', 'update')),
    CONSTRAINT backup_operation_idempotency_uq
        UNIQUE (id_google_account, idempotency_key)
);

ALTER TABLE google_drive.sync_log
    ADD COLUMN IF NOT EXISTS id_google_account UUID,
    ADD COLUMN IF NOT EXISTS id_user UUID,
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128);

UPDATE google_drive.sync_log AS log
SET id_google_account = backup.id_google_account
FROM google_drive.backup_file AS backup
WHERE log.id_backup_file = backup.id
  AND log.id_google_account IS NULL;

UPDATE google_drive.sync_log AS log
SET id_user = device_row.id_user
FROM device.device AS device_row
WHERE log.id_device = device_row.id
  AND log.id_user IS NULL;

UPDATE google_drive.sync_log AS log
SET id_user = account.id_user
FROM app_auth.google_account AS account
WHERE log.id_google_account = account.id
  AND log.id_user IS NULL;

UPDATE google_drive.sync_log AS log
SET id_user = account.id_user
FROM google_drive.backup_file AS backup
JOIN app_auth.google_account AS account
  ON account.id = backup.id_google_account
WHERE log.id_backup_file = backup.id
  AND log.id_user IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'sync_log_google_account_fk'
          AND conrelid = 'google_drive.sync_log'::regclass
    ) THEN
        ALTER TABLE google_drive.sync_log
            ADD CONSTRAINT sync_log_google_account_fk
            FOREIGN KEY (id_google_account)
            REFERENCES app_auth.google_account(id)
            ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'sync_log_user_fk'
          AND conrelid = 'google_drive.sync_log'::regclass
    ) THEN
        ALTER TABLE google_drive.sync_log
            ADD CONSTRAINT sync_log_user_fk
            FOREIGN KEY (id_user)
            REFERENCES app_auth.user(id)
            ON DELETE SET NULL ON UPDATE CASCADE;
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS sync_log_account_created_idx
    ON google_drive.sync_log (id_google_account, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS sync_log_idempotency_idx
    ON google_drive.sync_log (id_user, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

COMMIT;
