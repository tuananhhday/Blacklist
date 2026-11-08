CREATE TABLE IF NOT EXISTS studio_blacklist_items(
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 category TEXT NOT NULL REFERENCES categories(code),
 match_type TEXT NOT NULL CHECK(match_type IN ('combined','phrase','domain','url')),
 mode TEXT NOT NULL DEFAULT 'signal' CHECK(mode IN ('signal','block')),
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','disabled','archived')),
 version INTEGER NOT NULL DEFAULT 1,
 config_json TEXT NOT NULL,
 definition_hash TEXT NOT NULL,
 created_by_user_id INTEGER NOT NULL REFERENCES auth_users(id),
 created_at TEXT NOT NULL,
 updated_by_user_id INTEGER NOT NULL REFERENCES auth_users(id),
 updated_at TEXT NOT NULL,
 published_version INTEGER,
 published_snapshot_json TEXT,
 published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_studio_items_owner_status ON studio_blacklist_items(created_by_user_id,status,id DESC);
CREATE INDEX IF NOT EXISTS idx_studio_items_status ON studio_blacklist_items(status,id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_studio_items_owner_definition ON studio_blacklist_items(created_by_user_id,definition_hash);
CREATE TABLE IF NOT EXISTS studio_blacklist_examples(
 id INTEGER PRIMARY KEY,
 item_id INTEGER NOT NULL REFERENCES studio_blacklist_items(id),
 text TEXT NOT NULL,
 context TEXT NOT NULL DEFAULT '',
 expected TEXT NOT NULL CHECK(expected IN ('MATCH','REVIEW','NO_MATCH')),
 role TEXT NOT NULL CHECK(role IN ('violation','counterexample')),
 source_kind TEXT NOT NULL CHECK(source_kind IN ('manual','sample','imported')),
 source_sample_id INTEGER REFERENCES samples(id),
 source_review_id INTEGER REFERENCES reviews(id),
 source_labels_json TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL,
 UNIQUE(item_id,text,context)
);
CREATE INDEX IF NOT EXISTS idx_studio_examples_source ON studio_blacklist_examples(source_sample_id,source_review_id);
CREATE TABLE IF NOT EXISTS studio_blacklist_history(
 item_id INTEGER NOT NULL REFERENCES studio_blacklist_items(id),
 version INTEGER NOT NULL,
 snapshot_json TEXT NOT NULL,
 actor_user_id INTEGER NOT NULL REFERENCES auth_users(id),
 created_at TEXT NOT NULL,
 PRIMARY KEY(item_id,version)
);
CREATE TABLE IF NOT EXISTS studio_curation_bookmarks(
 user_id INTEGER NOT NULL REFERENCES auth_users(id),
 sample_id INTEGER NOT NULL REFERENCES samples(id),
 review_id INTEGER NOT NULL REFERENCES reviews(id),
 candidate_evidence TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL,
 PRIMARY KEY(user_id,sample_id)
);
CREATE INDEX IF NOT EXISTS idx_studio_bookmarks_sample ON studio_curation_bookmarks(sample_id,review_id);
CREATE TABLE IF NOT EXISTS studio_editor_drafts(
 user_id INTEGER NOT NULL REFERENCES auth_users(id),
 client_id TEXT NOT NULL,
 draft_key TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 PRIMARY KEY(user_id,client_id,draft_key)
);
