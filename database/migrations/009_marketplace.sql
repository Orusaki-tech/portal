ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(20) NOT NULL DEFAULT 'free'
    CHECK (subscription_tier IN ('free', 'starter', 'professional'));

COMMENT ON COLUMN users.subscription_tier IS 'Subscription plan determining platform features and pricing';

CREATE TABLE marketplace_listings (
    listing_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seller_id       UUID NOT NULL REFERENCES users(id),
    dataset_id      UUID NOT NULL REFERENCES ml_polygon_sets(id),
    title           VARCHAR(255) NOT NULL,
    description     TEXT,
    price_tokens    DECIMAL(12,2) NOT NULL CHECK (price_tokens > 0),
    geometry_count  INT NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'sold', 'archived')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE marketplace_listings IS 'Public marketplace for buying/selling annotated datasets';

CREATE TABLE dataset_purchases (
    purchase_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id      UUID NOT NULL REFERENCES marketplace_listings(listing_id),
    buyer_id        UUID NOT NULL REFERENCES users(id),
    dataset_id      UUID NOT NULL REFERENCES ml_polygon_sets(id),
    tokens_paid     DECIMAL(12,2) NOT NULL,
    purchased_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE dataset_purchases IS 'Audit log of dataset marketplace transactions';

CREATE INDEX idx_listings_status ON marketplace_listings(status, created_at DESC);
CREATE INDEX idx_listings_seller ON marketplace_listings(seller_id);
CREATE INDEX idx_purchases_buyer ON dataset_purchases(buyer_id);
