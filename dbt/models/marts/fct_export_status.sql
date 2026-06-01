with exports as (
    select * from {{ ref('stg_export_jobs') }}
),

users as (
    select * from {{ source('postgres', 'users') }}
)

select
    e.export_id,
    e.user_id,
    u.name as user_name,
    e.export_format,
    e.source_type,
    e.source_id,
    e.status,
    e.output_url,
    e.created_at,
    e.completed_at,
    case
        when e.status = 'completed' then
            extract(epoch from (e.completed_at - e.created_at))::int
        else null
    end as duration_seconds
from exports e
left join users u on e.user_id = u.id
