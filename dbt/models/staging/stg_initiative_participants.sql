with source as (
    select * from {{ source('postgres', 'initiative_participants') }}
),

cleaned as (
    select
        initiative_id,
        user_id,
        role,
        joined_at
    from source
)

select * from cleaned
