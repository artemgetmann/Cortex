-- Deterministic reset for each session.
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS error_log;

CREATE TABLE transactions (
  txn_id TEXT PRIMARY KEY,
  account TEXT NOT NULL,
  amount INTEGER NOT NULL
);

CREATE TABLE error_log (
  txn_id TEXT NOT NULL,
  reason TEXT NOT NULL
);
