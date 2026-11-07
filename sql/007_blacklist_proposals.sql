CREATE UNIQUE INDEX IF NOT EXISTS idx_rule_proposal_key ON rules(proposal_key) WHERE proposal_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rule_source_review ON rules(source_review_id);
