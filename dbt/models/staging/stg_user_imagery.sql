with source as (
    select * from {{ source('postgres', 'user_imagery') }}
),

cleaned as (
    select
        id as imagery_id,
        user_id,
        original_filename,
        gcs_uri,
        cog_uri,
        bounding_box,
        resolution_cm,
        status,
        stac_record,
        created_at,
        processed_at
    from source
)

select * from cleaned
