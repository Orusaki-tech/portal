CREATE TABLE edge_metrics (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    polygon_id        UUID NOT NULL REFERENCES ml_polygons(id) ON DELETE CASCADE,
    run_id            UUID NOT NULL,
    vertex_index      INT NOT NULL,
    deviation_meters  REAL,
    spectral_contrast REAL CHECK (spectral_contrast >= 0.0),
    snake_strain      REAL,
    confidence_score  REAL CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
    is_ambiguous      BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE edge_metrics IS 'Per-vertex edge detection metrics from a validation run';
COMMENT ON COLUMN edge_metrics.is_ambiguous IS 'True when confidence_score < threshold (default 0.70)';

CREATE INDEX idx_edge_metrics_polygon ON edge_metrics(polygon_id);
CREATE INDEX idx_edge_metrics_run ON edge_metrics(run_id);
CREATE INDEX idx_edge_metrics_ambiguous ON edge_metrics(is_ambiguous) WHERE is_ambiguous = true;

CREATE TABLE human_corrections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    polygon_id          UUID NOT NULL REFERENCES ml_polygons(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id),
    original_geometry   TEXT NOT NULL,
    corrected_geometry  TEXT NOT NULL,
    action              VARCHAR(20) NOT NULL DEFAULT 'correct'
                        CHECK (action IN ('correct', 'confirm', 'escalate', 'skip')),
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE human_corrections IS 'Human-verified geometry corrections with full provenance';
COMMENT ON COLUMN human_corrections.action IS 'correct=manual edit, confirm=auto-approved, escalate=needs senior review, skip=not fixable';

CREATE INDEX idx_human_corrections_polygon ON human_corrections(polygon_id);
CREATE INDEX idx_human_corrections_user ON human_corrections(user_id);
