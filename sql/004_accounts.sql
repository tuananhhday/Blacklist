CREATE TABLE IF NOT EXISTS auth_users(
 id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,
 code_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','member')),
 active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS auth_sessions(
 token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES auth_users(id),
 csrf TEXT NOT NULL,expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_limits(
 key TEXT PRIMARY KEY,attempts INTEGER NOT NULL,window_start REAL NOT NULL);
CREATE TABLE IF NOT EXISTS task_assignments(
 sample_id INTEGER PRIMARY KEY REFERENCES samples(id),user_id INTEGER NOT NULL REFERENCES auth_users(id),
 assigned_by INTEGER NOT NULL REFERENCES auth_users(id),assigned_at TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','done')));
CREATE INDEX IF NOT EXISTS idx_task_user_state ON task_assignments(user_id,state);
CREATE TABLE IF NOT EXISTS annotation_attempts(
 id INTEGER PRIMARY KEY,sample_id INTEGER NOT NULL REFERENCES samples(id),user_id INTEGER NOT NULL REFERENCES auth_users(id),
 owner TEXT NOT NULL,started_at REAL NOT NULL,last_seen_at REAL NOT NULL,active_seconds REAL NOT NULL DEFAULT 0,
 was_active INTEGER NOT NULL DEFAULT 1,closed_at REAL);
CREATE INDEX IF NOT EXISTS idx_attempt_owner ON annotation_attempts(owner,sample_id,closed_at);
CREATE TABLE IF NOT EXISTS review_audits(
 review_id INTEGER PRIMARY KEY REFERENCES reviews(id),admin_id INTEGER NOT NULL REFERENCES auth_users(id),
 verdict TEXT NOT NULL CHECK(verdict IN ('approved','needs_fix')),note TEXT NOT NULL,created_at TEXT NOT NULL);
INSERT OR IGNORE INTO workspace_meta VALUES('fast_seconds','5');
