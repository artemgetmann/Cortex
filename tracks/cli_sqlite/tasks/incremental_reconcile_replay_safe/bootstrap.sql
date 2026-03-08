DROP TABLE IF EXISTS ledger;
DROP TABLE IF EXISTS rejects;
DROP TABLE IF EXISTS replay_log;
DROP TABLE IF EXISTS batch_audit;

CREATE TABLE ledger (
  event_id TEXT PRIMARY KEY,
  category TEXT NOT NULL,
  amount INTEGER NOT NULL,
  batch_id TEXT NOT NULL
);

-- Intentionally no uniqueness here. A naive replay will duplicate rejects.
CREATE TABLE rejects (
  event_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  batch_id TEXT NOT NULL
);

CREATE TABLE replay_log (
  batch_tag TEXT NOT NULL,
  replay_step INTEGER NOT NULL,
  PRIMARY KEY (batch_tag, replay_step)
);

CREATE TABLE batch_audit (
  batch_tag TEXT PRIMARY KEY,
  accepted_count INTEGER NOT NULL,
  rejected_count INTEGER NOT NULL,
  replay_count INTEGER NOT NULL
);
