DROP TABLE IF EXISTS ledger;
DROP TABLE IF EXISTS rejects;

CREATE TABLE ledger (
  event_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  amount INTEGER NOT NULL,
  batch_id TEXT NOT NULL
);

CREATE TABLE rejects (
  event_id TEXT NOT NULL,
  reason TEXT NOT NULL
);
