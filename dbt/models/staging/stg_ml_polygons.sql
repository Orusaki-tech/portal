with source as (
    select * from {{ source('postgres', 'ml_polygons') }}
),

cleaned as (
    select
        id as polygon_id,
        polygon_set_id,
        original_geometry,
        qa_status,
        confidence_avg,
        corrected_geometry,
        properties,
        created_at
    from source
)

select * from cleaned
