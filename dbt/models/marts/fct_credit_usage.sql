with transactions as (
    select * from {{ ref('stg_credit_transactions') }}
),

users as (
    select * from {{ source('postgres', 'users') }}
)

select
    t.user_id,
    u.name as user_name,
    u.email as user_email,
    u.subscription_tier,
    count(*) as transaction_count,
    sum(case when t.transaction_type = 'top_up' then t.amount else 0 end) as total_top_ups,
    sum(case when t.transaction_type in ('validation', 'correction') then t.amount else 0 end) as total_spent,
    sum(t.amount) as net_credits,
    max(t.created_at) as last_transaction_at
from transactions t
left join users u on t.user_id = u.id
group by t.user_id, u.name, u.email, u.subscription_tier
