-- Extend cog_catalog for mosaic pipeline metadata.
-- This is additive — no breaking changes.

ALTER TABLE cog_catalog
  ADD COLUMN IF NOT EXISTS scene_count     INTEGER,
  ADD COLUMN IF NOT EXISTS date_from       DATE,
  ADD COLUMN IF NOT EXISTS date_to         DATE,
  ADD COLUMN IF NOT EXISTS max_cloud_cover REAL,
  ADD COLUMN IF NOT EXISTS cloud_cover_avg REAL;
