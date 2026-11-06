CREATE TABLE IF NOT EXISTS workspace_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO workspace_meta VALUES('version','0');
CREATE TABLE IF NOT EXISTS work_claims(
 sample_id INTEGER PRIMARY KEY REFERENCES samples(id),owner TEXT NOT NULL UNIQUE,
 reviewer TEXT NOT NULL,expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS work_drafts(
 owner TEXT NOT NULL,sample_id INTEGER NOT NULL REFERENCES samples(id),
 payload_json TEXT NOT NULL,updated_at TEXT NOT NULL,
 PRIMARY KEY(owner,sample_id));
CREATE TABLE IF NOT EXISTS operations(
 id TEXT PRIMARY KEY,kind TEXT NOT NULL,request_hash TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
