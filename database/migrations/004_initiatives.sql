CREATE TABLE initiatives (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES users(id),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    region          TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'active', 'paused', 'complete', 'archived')),
    grid_size_m     INT NOT NULL DEFAULT 1000,
    budget_credits  DECIMAL(12,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

COMMENT ON TABLE initiatives IS 'Named annotation projects covering a region of interest';
COMMENT ON COLUMN initiatives.region IS 'Area of interest in WKT format — converted to GEOMETRY when PostGIS is available';

CREATE TABLE initiative_participants (
    initiative_id   UUID NOT NULL REFERENCES initiatives(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id),
    role            VARCHAR(20) NOT NULL DEFAULT 'annotator'
                    CHECK (role IN ('annotator', 'reviewer', 'manager')),
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (initiative_id, user_id)
);

COMMENT ON TABLE initiative_participants IS 'Junction table linking users to initiatives with role';

CREATE TABLE map_task_grid (
    grid_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    initiative_id    UUID NOT NULL REFERENCES initiatives(id) ON DELETE CASCADE,
    geometry         TEXT NOT NULL,
    status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'in_progress', 'awaiting_review', 'complete', 'disputed')),
    assigned_user_id UUID REFERENCES users(id),
    locked_at        TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    review_notes     TEXT
);

COMMENT ON TABLE map_task_grid IS '1km² grid blocks — the consistency boundary for multi-user annotation';

CREATE INDEX idx_task_grid_initiative ON map_task_grid(initiative_id);
CREATE INDEX idx_task_grid_status ON map_task_grid(status);
CREATE INDEX idx_task_grid_assigned ON map_task_grid(assigned_user_id);

ALTER TABLE ml_polygons ADD COLUMN IF NOT EXISTS task_grid_id UUID REFERENCES map_task_grid(grid_id) ON DELETE SET NULL;
COMMENT ON COLUMN ml_polygons.task_grid_id IS 'Optional link to parent task grid — populated when polygons belong to an initiative';
