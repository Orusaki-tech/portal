with source as (
    select * from {{ source('postgres', 'export_jobs') }}
),

cleaned as (
    select
        export_id,
        user_id,
        export_format,
        source_type,
        source_id,
        status,
        output_url,
        error_message,
        created_at,
        completed_at
    from source
)

select * from cleaned
