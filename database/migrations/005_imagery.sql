CREATE TABLE user_imagery (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id),
    original_filename   VARCHAR(500) NOT NULL,
    gcs_uri             TEXT NOT NULL,
    cog_uri             TEXT,
    bounding_box        TEXT,
    resolution_cm       INT,
    status              VARCHAR(20) NOT NULL DEFAULT 'uploaded'
                        CHECK (status IN ('uploaded', 'processing', 'ready', 'failed')),
    stac_record         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at        TIMESTAMPTZ
);

COMMENT ON TABLE user_imagery IS 'User-uploaded GeoTIFFs processed into COGs';

CREATE INDEX idx_user_imagery_user ON user_imagery(user_id);
CREATE INDEX idx_user_imagery_status ON user_imagery(status);

CREATE TABLE validation_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    polygon_set_id  UUID REFERENCES ml_polygon_sets(id),
    imagery_id      UUID REFERENCES user_imagery(id),
    region          TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'processing', 'complete', 'failed')),
    polygon_count   INT NOT NULL DEFAULT 0,
    ambiguous_count INT NOT NULL DEFAULT 0,
    cost_credits    DECIMAL(12,2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

COMMENT ON TABLE validation_runs IS 'Batch edge detection validation runs against chosen imagery';

CREATE INDEX idx_validation_runs_user ON validation_runs(user_id);
CREATE INDEX idx_validation_runs_status ON validation_runs(status);
