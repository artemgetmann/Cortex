-- Deterministic reset for each session.
DROP TABLE IF EXISTS sales;
CREATE TABLE sales (
  category TEXT NOT NULL,
  amount INTEGER NOT NULL
);
