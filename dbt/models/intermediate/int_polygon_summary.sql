with polygons as (
    select * from {{ ref('stg_ml_polygons') }}
),

metrics as (
    select * from {{ ref('stg_edge_metrics') }}
),

per_polygon as (
    select
        polygon_id,
        avg(confidence_score) as avg_confidence,
        min(confidence_score) as min_confidence,
        count(*) as vertex_count,
        sum(case when is_ambiguous then 1 else 0 end) as ambiguous_vertices,
        avg(deviation_meters) as avg_deviation_m
    from metrics
    group by polygon_id
)

select
    p.polygon_id,
    p.polygon_set_id,
    p.qa_status,
    p.confidence_avg as cached_confidence,
    pp.avg_confidence as computed_confidence,
    pp.min_confidence,
    pp.vertex_count,
    pp.ambiguous_vertices,
    pp.avg_deviation_m,
    p.corrected_geometry is not null as has_correction,
    p.created_at
from polygons p
left join per_polygon pp on p.polygon_id = pp.polygon_id
