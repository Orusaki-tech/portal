-- PostGIS is optional for local dev. Skip if not available.
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS postgis;
EXCEPTION
  WHEN OTHERS THEN
    RAISE NOTICE 'PostGIS not available — geometry columns will use TEXT fallback';
END $$;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email             VARCHAR(255) UNIQUE NOT NULL,
    name              VARCHAR(255) NOT NULL,
    role              VARCHAR(20) NOT NULL DEFAULT 'annotator'
                      CHECK (role IN ('admin', 'manager', 'annotator', 'reviewer')),
    credits_remaining DECIMAL(12,2) NOT NULL DEFAULT 0
                      CHECK (credits_remaining >= 0),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE users IS 'Platform users across all roles';
COMMENT ON COLUMN users.credits_remaining IS 'Must never be negative — enforced by CHECK constraint';
