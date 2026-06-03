select
    id,
    initiative_id,
    user_id,
    score,
    polygons_submitted,
    accuracy_pct,
    submitted_at
from {{ source('postgres', 'hackathon_leaderboard') }}
