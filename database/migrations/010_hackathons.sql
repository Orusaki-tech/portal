ALTER TABLE initiatives
    ADD COLUMN IF NOT EXISTS hackathon_mode BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS max_participants INTEGER;

CREATE TABLE IF NOT EXISTS hackathon_leaderboard (
    id UUID PRIMARY KEY,
    initiative_id UUID NOT NULL REFERENCES initiatives(id),
    user_id UUID NOT NULL REFERENCES users(id),
    score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    polygons_submitted INTEGER NOT NULL DEFAULT 0,
    accuracy_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (initiative_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_hackathon_leaderboard_initiative ON hackathon_leaderboard(initiative_id);
CREATE INDEX IF NOT EXISTS idx_hackathon_leaderboard_score ON hackathon_leaderboard(initiative_id, score DESC);
