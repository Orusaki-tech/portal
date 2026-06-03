with leaderboard as (
    select
        hl.initiative_id,
        hl.user_id,
        hl.score,
        hl.polygons_submitted,
        hl.accuracy_pct,
        hl.submitted_at,
        i.name as initiative_name,
        u.name as user_name,
        row_number() over (partition by hl.initiative_id order by hl.score desc) as place
    from {{ ref('stg_hackathon_leaderboard') }} hl
    left join {{ ref('stg_initiatives') }} i on hl.initiative_id = i.initiative_id
    left join {{ ref('stg_users') }} u on hl.user_id = u.user_id
)

select * from leaderboard
