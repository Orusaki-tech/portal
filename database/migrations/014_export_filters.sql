ALTER TABLE export_jobs ADD COLUMN IF NOT EXISTS export_params JSONB DEFAULT '{}'::jsonb;
COMMENT ON COLUMN export_jobs.export_params IS 'Optional filter params: qa_status, confidence_min, confidence_max, annotator_id, include_original';

ALTER TABLE export_jobs DROP CONSTRAINT IF EXISTS export_jobs_export_format_check;
ALTER TABLE export_jobs ADD CONSTRAINT export_jobs_export_format_check
    CHECK (export_format IN ('geojson', 'coco', 'yolo', 'pascal_voc', 'tfrecord', 'parquet', 'geopackage'));
