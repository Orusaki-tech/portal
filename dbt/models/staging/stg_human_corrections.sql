with source as (
    select * from {{ source('postgres', 'human_corrections') }}
),

cleaned as (
    select
        id as correction_id,
        polygon_id,
        user_id,
        original_geometry,
        corrected_geometry,
        action,
        notes,
        created_at
    from source
)

select * from cleaned
