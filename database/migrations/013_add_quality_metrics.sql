-- Add quality metrics columns to marketplace_listings

ALTER TABLE marketplace_listings
  ADD COLUMN IF NOT EXISTS quality_score DECIMAL(3,2)
    CHECK (quality_score IS NULL OR (quality_score >= 0.0 AND quality_score <= 1.0)),
  ADD COLUMN IF NOT EXISTS completion_rate DECIMAL(3,2)
    CHECK (completion_rate IS NULL OR (completion_rate >= 0.0 AND completion_rate <= 1.0));

COMMENT ON COLUMN marketplace_listings.quality_score IS 'Average confidence score of all polygons in the dataset';
COMMENT ON COLUMN marketplace_listings.completion_rate IS 'Fraction of polygons that are validated/corrected';
