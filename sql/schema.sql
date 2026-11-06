PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS categories(code TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS samples(
 id INTEGER PRIMARY KEY, text TEXT NOT NULL, context TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL, synthetic INTEGER NOT NULL CHECK(synthetic IN(0,1)),
 fingerprint TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reviews(
 id INTEGER PRIMARY KEY, sample_id INTEGER NOT NULL REFERENCES samples(id),
 revision INTEGER NOT NULL, decision TEXT NOT NULL CHECK(decision IN('ALLOW','VIOLATION','UNSURE')),
 labels_json TEXT NOT NULL, intent TEXT NOT NULL, evidence TEXT NOT NULL,
 reason TEXT NOT NULL, reviewer TEXT NOT NULL, policy_version TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(sample_id,revision));
CREATE TABLE IF NOT EXISTS rules(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL REFERENCES categories(code),
 kind TEXT NOT NULL CHECK(kind IN('exact','combined','url','domain')),
 config_json TEXT NOT NULL, tests_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN('draft','active','disabled')),
 version INTEGER NOT NULL, source_sample_id INTEGER REFERENCES samples(id),
 reviewer TEXT NOT NULL, reason TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rule_history(
 id INTEGER PRIMARY KEY, rule_id INTEGER NOT NULL REFERENCES rules(id),
 version INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(rule_id,version));
CREATE INDEX IF NOT EXISTS idx_reviews_sample ON reviews(sample_id,revision DESC);
