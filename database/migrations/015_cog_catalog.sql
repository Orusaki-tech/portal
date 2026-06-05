-- COG Catalog — spatial inventory of every COG ever generated
-- Enables dedup by geometry hash and spatial overlap queries.
CREATE TABLE IF NOT EXISTS cog_catalog (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id       TEXT NOT NULL,
  scene_id        TEXT,
  geometry_hash   TEXT NOT NULL,
  cog_url         TEXT NOT NULL,
  cog_size_bytes  BIGINT,
  bounding_box    GEOMETRY(POLYGON, 4326) NOT NULL,
  area_km2        DOUBLE PRECISION,
  resolution      DOUBLE PRECISION,
  datetime        TIMESTAMPTZ,
  source_type     TEXT NOT NULL DEFAULT 'stac',
  access_count    INT DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(source_id, geometry_hash)
);

CREATE INDEX IF NOT EXISTS idx_cog_catalog_spatial
  ON cog_catalog USING GIST (bounding_box);
CREATE INDEX IF NOT EXISTS idx_cog_catalog_source
  ON cog_catalog (source_id);

-- Provider API keys — encrypted per-user credentials for commercial providers
CREATE TABLE IF NOT EXISTS provider_api_keys (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider_id     TEXT NOT NULL,
  encrypted_key   TEXT NOT NULL,
  label           TEXT DEFAULT '',
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, provider_id)
);
