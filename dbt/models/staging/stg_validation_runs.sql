with source as (
    select * from {{ source('postgres', 'validation_runs') }}
),

cleaned as (
    select
        id as run_id,
        user_id,
        polygon_set_id,
        imagery_id,
        region,
        status,
        polygon_count,
        ambiguous_count,
        cost_credits,
        created_at,
        completed_at
    from source
)

select * from cleaned
