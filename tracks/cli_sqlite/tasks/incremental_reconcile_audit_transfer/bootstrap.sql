DROP TABLE IF EXISTS ledger;
DROP TABLE IF EXISTS rejects;
DROP TABLE IF EXISTS batch_audit;

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

CREATE TABLE batch_audit (
  batch_tag TEXT PRIMARY KEY,
  accepted_count INTEGER NOT NULL,
  rejected_count INTEGER NOT NULL
);
