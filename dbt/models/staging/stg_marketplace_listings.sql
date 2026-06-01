with source as (
    select * from {{ source('postgres', 'marketplace_listings') }}
),

cleaned as (
    select
        listing_id,
        seller_id,
        dataset_id,
        title,
        description,
        price_tokens,
        geometry_count,
        status,
        created_at
    from source
)

select * from cleaned
