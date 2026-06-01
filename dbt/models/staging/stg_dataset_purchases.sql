with source as (
    select * from {{ source('postgres', 'dataset_purchases') }}
),

cleaned as (
    select
        purchase_id,
        listing_id,
        buyer_id,
        dataset_id,
        tokens_paid,
        purchased_at
    from source
)

select * from cleaned
