DROP TABLE IF EXISTS ledger;
DROP TABLE IF EXISTS rejects;
DROP TABLE IF EXISTS checkpoint_log;

CREATE TABLE ledger (
  event_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  amount INTEGER NOT NULL,
  batch_id TEXT NOT NULL,
  checkpoint_tag TEXT NOT NULL
);

CREATE TABLE rejects (
  event_id TEXT NOT NULL,
  reason TEXT NOT NULL
);

CREATE TABLE checkpoint_log (
  checkpoint_tag TEXT PRIMARY KEY,
  row_count INTEGER NOT NULL
);
