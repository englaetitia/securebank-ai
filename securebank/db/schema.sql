-- SecureBank AI: synthetic banking database schema
-- All data is fictional. Sensitive columns: national_id, address, account_number, password_hash.

PRAGMA foreign_keys = ON;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    phone         TEXT NOT NULL,
    national_id   TEXT NOT NULL UNIQUE,   -- sensitive: never shown
    address       TEXT NOT NULL,          -- sensitive: never shown
    created_date  TEXT NOT NULL           -- ISO date YYYY-MM-DD
);

CREATE TABLE accounts (
    account_id      INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    account_number  TEXT NOT NULL UNIQUE, -- sensitive: masked when shown
    account_type    TEXT NOT NULL CHECK (account_type IN ('savings', 'checking')),
    balance         REAL NOT NULL,
    opening_date    TEXT NOT NULL
);

CREATE TABLE transactions (
    transaction_id    INTEGER PRIMARY KEY,
    account_id        INTEGER NOT NULL REFERENCES accounts(account_id),
    amount            REAL NOT NULL CHECK (amount > 0),
    transaction_type  TEXT NOT NULL CHECK (transaction_type IN ('deposit', 'withdrawal')),
    transaction_date  TEXT NOT NULL,
    category          TEXT NOT NULL           -- spending category; 'income' for deposits
);

CREATE TABLE loans (
    loan_id      INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
    loan_amount  REAL NOT NULL CHECK (loan_amount > 0),
    loan_status  TEXT NOT NULL CHECK (loan_status IN ('active', 'closed')),
    start_date   TEXT NOT NULL,
    term_months      INTEGER NOT NULL CHECK (term_months > 0),
    interest_rate    REAL NOT NULL,          -- yearly rate, in percent
    monthly_payment  REAL NOT NULL
);

CREATE TABLE users (
    user_id        INTEGER PRIMARY KEY,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('manager', 'employee', 'customer')),
    customer_id    INTEGER REFERENCES customers(customer_id),
    -- a customer user must be linked to a customer; staff must not be
    CHECK ((role = 'customer') = (customer_id IS NOT NULL))
);

-- Indexes for the date filters used by most intents
CREATE INDEX idx_accounts_opening_date ON accounts(opening_date);
CREATE INDEX idx_transactions_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_account ON transactions(account_id);
