BEGIN;

CREATE TABLE IF NOT EXISTS ai.shared_api_key (
    id UUID PRIMARY KEY,
    id_ai_provider UUID NOT NULL
        REFERENCES ai.ai_provider(id) ON DELETE CASCADE ON UPDATE CASCADE,
    name VARCHAR(128) NOT NULL,
    encrypted_key TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT shared_api_key_provider_name_uq UNIQUE (id_ai_provider, name)
);

COMMIT;
