CREATE TABLE IF NOT EXISTS import_batches(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,user_id INTEGER NOT NULL REFERENCES auth_users(id),
 requested INTEGER NOT NULL DEFAULT 0,added INTEGER NOT NULL DEFAULT 0,duplicates INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','undone')),
 created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_batch_samples(
 batch_id TEXT NOT NULL REFERENCES import_batches(id),sample_id INTEGER NOT NULL REFERENCES samples(id),
 undo_archived_at TEXT,PRIMARY KEY(batch_id,sample_id));
CREATE INDEX IF NOT EXISTS idx_import_sample ON import_batch_samples(sample_id);
