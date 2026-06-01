CREATE TABLE credit_transactions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id),
    amount           DECIMAL(12,2) NOT NULL,
    transaction_type VARCHAR(20) NOT NULL
                     CHECK (transaction_type IN ('top_up', 'validation', 'correction', 'purchase', 'refund')),
    reference_id     UUID,
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE credit_transactions IS 'Audit log of all credit movements — enables balance reconciliation and dbt reporting';
COMMENT ON COLUMN credit_transactions.transaction_type IS 'top_up=manual add, validation=per-polygon cost, correction=human edit cost, purchase=dataset buy, refund=reversal';

CREATE INDEX idx_credit_txns_user ON credit_transactions(user_id, created_at DESC);
CREATE INDEX idx_credit_txns_type ON credit_transactions(transaction_type);
