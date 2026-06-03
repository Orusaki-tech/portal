with corrections as (
    select * from {{ ref('stg_human_corrections') }}
),

per_polygon as (
    select
        polygon_id,
        count(*) as correction_count,
        count(distinct user_id) as unique_annotators,
        bool_or(corrected_geometry is not null) as has_merged_geometry
    from corrections
    group by polygon_id
)

select
    polygon_id,
    correction_count,
    unique_annotators,
    case
        when correction_count >= 3 then 'majority_consensus'
        when correction_count = 2 then 'paired_consensus'
        else 'single_annotation'
    end as consensus_type,
    has_merged_geometry
from per_polygon
