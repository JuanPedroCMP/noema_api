BEGIN;

ALTER TABLE google_drive.oauth_state
    ADD COLUMN IF NOT EXISTS error_code VARCHAR(64);

COMMIT;
