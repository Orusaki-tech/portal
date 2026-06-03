with source as (
    select * from {{ source('postgres', 'map_task_grid') }}
),

cleaned as (
    select
        grid_id,
        initiative_id,
        geometry,
        status,
        assigned_user_id,
        locked_at,
        completed_at,
        review_notes
    from source
)

select * from cleaned
