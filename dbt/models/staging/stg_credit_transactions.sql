with source as (
    select * from {{ source('postgres', 'credit_transactions') }}
),

cleaned as (
    select
        id as transaction_id,
        user_id,
        amount,
        transaction_type,
        reference_id,
        description,
        created_at
    from source
)

select * from cleaned
