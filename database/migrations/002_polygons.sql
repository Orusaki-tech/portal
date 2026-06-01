CREATE TABLE ml_polygon_sets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    model_version   VARCHAR(100),
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ml_polygons (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    polygon_set_id      UUID NOT NULL REFERENCES ml_polygon_sets(id) ON DELETE CASCADE,
    original_geometry   TEXT NOT NULL,
    qa_status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (qa_status IN ('pending', 'validated', 'low_confidence', 'corrected', 'escalated')),
    confidence_avg      REAL,
    corrected_geometry  TEXT,
    properties          JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE ml_polygon_sets IS 'Named collections of ML-predicted polygons uploaded by a user';
COMMENT ON TABLE ml_polygons IS 'Individual polygon predictions from ML models';
COMMENT ON COLUMN ml_polygons.qa_status IS 'Lifecycle: pending → validated/low_confidence → corrected/escalated';

CREATE INDEX idx_ml_polygons_set ON ml_polygons(polygon_set_id);
CREATE INDEX idx_ml_polygons_qa ON ml_polygons(qa_status);
