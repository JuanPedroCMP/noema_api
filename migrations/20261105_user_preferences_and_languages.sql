BEGIN;

CREATE TABLE IF NOT EXISTS user_config.user_preferences (
    id_user UUID PRIMARY KEY REFERENCES app_auth."user"(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    preferences JSON NOT NULL DEFAULT '{}'::json,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO user_config.user_preferences (id_user, preferences, created_at, updated_at)
SELECT id_user, preferences, COALESCE(created_at, CURRENT_TIMESTAMP),
       COALESCE(updated_at, CURRENT_TIMESTAMP)
FROM user_config.user_global_config
ON CONFLICT (id_user) DO NOTHING;

INSERT INTO user_config.language
    (id, name, percentage_translated, verified_translation, automatic_translation)
VALUES
    ('c328f562-74b9-4c50-bc3d-d56d7e414b01', 'English', 100, true, false),
    ('c328f562-74b9-4c50-bc3d-d56d7e414b02', 'Japanese', 0, false, true),
    ('c328f562-74b9-4c50-bc3d-d56d7e414b03', 'Korean', 0, false, true),
    ('c328f562-74b9-4c50-bc3d-d56d7e414b04', 'Português (Brasil)', 100, true, false),
    ('c328f562-74b9-4c50-bc3d-d56d7e414b05', 'Spanish', 0, false, true),
    ('c328f562-74b9-4c50-bc3d-d56d7e414b06', 'French', 0, false, true),
    ('c328f562-74b9-4c50-bc3d-d56d7e414b07', 'German', 0, false, true)
ON CONFLICT (name) DO UPDATE SET
    percentage_translated = EXCLUDED.percentage_translated,
    verified_translation = EXCLUDED.verified_translation,
    automatic_translation = EXCLUDED.automatic_translation,
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
