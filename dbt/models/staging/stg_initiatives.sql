with source as (
    select * from {{ source('postgres', 'initiatives') }}
),

cleaned as (
    select
        id as initiative_id,
        owner_id,
        name,
        description,
        region,
        status,
        grid_size_m,
        budget_credits,
        created_at,
        completed_at
    from source
)

select * from cleaned
