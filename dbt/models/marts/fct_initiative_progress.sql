with initiatives as (
    select * from {{ ref('stg_initiatives') }}
),

grids as (
    select
        initiative_id,
        count(*) as total_blocks,
        sum(case when status = 'complete' then 1 else 0 end) as completed_blocks,
        sum(case when status = 'in_progress' then 1 else 0 end) as in_progress_blocks,
        sum(case when status = 'pending' then 1 else 0 end) as pending_blocks,
        sum(case when status = 'disputed' then 1 else 0 end) as disputed_blocks
    from {{ source('postgres', 'map_task_grid') }}
    group by initiative_id
)

select
    i.initiative_id,
    i.name as initiative_name,
    i.status,
    i.grid_size_m,
    i.budget_credits,
    coalesce(g.total_blocks, 0) as total_blocks,
    coalesce(g.completed_blocks, 0) as completed_blocks,
    coalesce(g.in_progress_blocks, 0) as in_progress_blocks,
    coalesce(g.pending_blocks, 0) as pending_blocks,
    coalesce(g.disputed_blocks, 0) as disputed_blocks,
    case
        when g.total_blocks > 0
        then round(100.0 * g.completed_blocks / g.total_blocks, 1)
        else 0
    end as completion_pct,
    i.created_at,
    i.completed_at
from initiatives i
left join grids g on i.initiative_id = g.initiative_id
