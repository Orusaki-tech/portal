with source as (
    select * from {{ source('postgres', 'edge_metrics') }}
),

cleaned as (
    select
        id as metric_id,
        polygon_id,
        run_id,
        vertex_index,
        deviation_meters,
        spectral_contrast,
        snake_strain,
        confidence_score,
        is_ambiguous,
        created_at
    from source
)

select * from cleaned
