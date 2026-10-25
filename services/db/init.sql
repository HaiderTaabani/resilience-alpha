CREATE TABLE IF NOT EXISTS transactions (
    id           SERIAL PRIMARY KEY,
    from_account VARCHAR(34)   NOT NULL,
    to_account   VARCHAR(34)   NOT NULL,
    amount       NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    status       VARCHAR(10)   NOT NULL DEFAULT 'OK',
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
);
