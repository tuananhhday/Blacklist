CREATE TABLE IF NOT EXISTS parquet_import_runs(
 batch_id TEXT PRIMARY KEY REFERENCES import_batches(id),user_id INTEGER NOT NULL REFERENCES auth_users(id),
 file_name TEXT NOT NULL,signature TEXT NOT NULL,options_json TEXT NOT NULL,total INTEGER NOT NULL,
 processed INTEGER NOT NULL DEFAULT 0,added INTEGER NOT NULL DEFAULT 0,duplicates INTEGER NOT NULL DEFAULT 0,
 skipped_empty INTEGER NOT NULL DEFAULT 0,skipped_too_long INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL CHECK(state IN ('running','paused','done','error')),error TEXT,
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_parquet_run_owner ON parquet_import_runs(user_id,updated_at);
