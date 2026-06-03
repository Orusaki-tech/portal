select
    user_id,
    email,
    credits_remaining
from {{ ref('stg_users') }}
where credits_remaining < 0
