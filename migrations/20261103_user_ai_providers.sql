ALTER TABLE ai.ai_provider
    ADD COLUMN IF NOT EXISTS id_user uuid,
    ADD COLUMN IF NOT EXISTS protocol varchar(32) NOT NULL DEFAULT 'native';

UPDATE ai.ai_provider SET is_active = true WHERE is_active IS NULL;
ALTER TABLE ai.ai_provider ALTER COLUMN is_active SET NOT NULL;

ALTER TABLE ai.ai_provider
    DROP CONSTRAINT IF EXISTS ai_provider_slug_uq;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ai_provider_user_fk'
          AND conrelid = 'ai.ai_provider'::regclass
    ) THEN
        ALTER TABLE ai.ai_provider
            ADD CONSTRAINT ai_provider_user_fk
            FOREIGN KEY (id_user) REFERENCES app_auth."user"(id)
            ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ai_provider_global_slug_uq
    ON ai.ai_provider (slug) WHERE id_user IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ai_provider_user_slug_uq
    ON ai.ai_provider (id_user, slug) WHERE id_user IS NOT NULL;

ALTER TABLE ai.ai_model
    DROP CONSTRAINT IF EXISTS ai_model_slug_uq;
UPDATE ai.ai_model SET is_active = true WHERE is_active IS NULL;
ALTER TABLE ai.ai_model ALTER COLUMN is_active SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ai_model_provider_slug_uq
    ON ai.ai_model (id_ai_provider, slug);

ALTER TABLE ai.agent
    ADD COLUMN IF NOT EXISTS id_user uuid,
    ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'agent_user_fk'
          AND conrelid = 'ai.agent'::regclass
    ) THEN
        ALTER TABLE ai.agent
            ADD CONSTRAINT agent_user_fk
            FOREIGN KEY (id_user) REFERENCES app_auth."user"(id)
            ON DELETE CASCADE ON UPDATE CASCADE;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ai_agent_user_alias_uq
    ON ai.agent (id_user, alias) WHERE id_user IS NOT NULL;

ALTER TABLE ai.agent_model
    ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS ai_agent_model_active_idx
    ON ai.agent_model (id_agent, is_active);
