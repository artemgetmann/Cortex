-- Deterministic reset for each session.
DROP TABLE IF EXISTS inventory;

CREATE TABLE inventory (
  sku TEXT PRIMARY KEY,
  product TEXT NOT NULL,
  quantity INTEGER NOT NULL
);
