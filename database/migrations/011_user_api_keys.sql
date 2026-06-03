ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key VARCHAR(64);

UPDATE users SET api_key = encode(gen_random_bytes(32), 'hex') WHERE api_key IS NULL;

ALTER TABLE users ALTER COLUMN api_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);

COMMENT ON COLUMN users.api_key IS 'Per-user API key for Bearer token auth — auto-generated on creation';
