CREATE TABLE export_jobs (
    export_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id),
    export_format  VARCHAR(20) NOT NULL
                   CHECK (export_format IN ('geojson', 'coco', 'yolo', 'pascal_voc', 'tfrecord')),
    source_type    VARCHAR(20) NOT NULL
                   CHECK (source_type IN ('dataset', 'initiative', 'grid')),
    source_id      UUID NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    output_url     TEXT,
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ
);

COMMENT ON TABLE export_jobs IS 'Tracks async ML format export requests with status and output artifact URL';
COMMENT ON COLUMN export_jobs.export_format IS 'Target ML export format (geojson, coco, yolo, pascal_voc, tfrecord)';
COMMENT ON COLUMN export_jobs.source_type IS 'What to export (dataset, initiative, or single grid)';
COMMENT ON COLUMN export_jobs.source_id IS 'UUID of the dataset, initiative, or grid being exported';

CREATE INDEX idx_export_jobs_user ON export_jobs(user_id, created_at DESC);
CREATE INDEX idx_export_jobs_status ON export_jobs(status);
