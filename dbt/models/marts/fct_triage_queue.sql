with polygon_summary as (
    select * from {{ ref('int_polygon_summary') }}
),

corrections as (
    select
        polygon_id,
        count(*) as correction_count,
        max(created_at) as last_corrected_at
    from {{ ref('stg_human_corrections') }}
    group by polygon_id
)

select
    ps.polygon_id,
    ps.polygon_set_id,
    ps.qa_status,
    ps.computed_confidence,
    ps.avg_deviation_m,
    ps.ambiguous_vertices,
    ps.vertex_count,
    coalesce(c.correction_count, 0) as correction_count,
    c.last_corrected_at,
    case
        when ps.computed_confidence >= 0.95 and ps.ambiguous_vertices = 0 then 'auto_approved'
        when ps.computed_confidence >= 0.70 then 'needs_review'
        when ps.computed_confidence >= 0.40 then 'needs_correction'
        else 'escalate'
    end as priority_tier,
    ps.created_at
from polygon_summary ps
left join corrections c on ps.polygon_id = c.polygon_id
where ps.qa_status not in ('corrected', 'validated')
   or (ps.qa_status = 'validated' and ps.computed_confidence < 0.70)
order by ps.computed_confidence asc
