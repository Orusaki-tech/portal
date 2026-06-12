-- COG Job tracking — persistent status across Cloud Run instances/restarts
CREATE TABLE IF NOT EXISTS cog_jobs (
  job_hash       TEXT PRIMARY KEY,
  status         TEXT NOT NULL DEFAULT 'processing'
                 CHECK (status IN ('processing', 'ready', 'error')),
  result         JSONB,
  error          TEXT,
  source_id      TEXT,
  geometry_hash  TEXT,
  user_id        TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW(),
  updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cog_jobs_status ON cog_jobs (status);
