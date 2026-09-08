-- 003_candidate_lifecycle.sql
-- Track when a word was last reinforced, so unused candidates can decay.
-- Confirmed words are not decayed automatically -- a user must suppress or
-- forget them -- because "I only mention my sister every few months" is a
-- valid usage pattern for personal memory.

ALTER TABLE word ADD COLUMN last_reinforced_at TEXT;
ALTER TABLE word ADD COLUMN promoted_at        TEXT;

-- Backfill: any existing rows get their created_at as last_reinforced_at.
UPDATE word SET last_reinforced_at = created_at WHERE last_reinforced_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_word_status_reinforced ON word(status, last_reinforced_at);
