BEGIN;

ALTER TABLE user_config.language
    ADD COLUMN IF NOT EXISTS is_native BOOLEAN NOT NULL DEFAULT false;

UPDATE user_config.language
SET is_native = NOT COALESCE(automatic_translation, true);

COMMIT;
