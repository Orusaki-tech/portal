with source as (
    select * from {{ source('postgres', 'users') }}
),

cleaned as (
    select
        id as user_id,
        email,
        name,
        role,
        credits_remaining,
        created_at,
        updated_at
    from source
)

select * from cleaned
