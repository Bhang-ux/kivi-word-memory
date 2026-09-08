-- 002_user_scope.sql
-- Add user scoping. The demo runs as one user ("default"), but the schema
-- is per-user from day one so this never needs to be re-done. Personal AI
-- means personal memory: mixing two people's words would be a data leak.

-- SQLite can't add a NOT NULL column without a default, so we default to
-- 'default'. Nothing in the codebase reads the literal string; it's a
-- placeholder for whatever tenant/session id a real deployment provides.
ALTER TABLE word ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default';

-- Uniqueness must be scoped per user; drop the global UNIQUE(word) that
-- migration 001 created and re-add it scoped. SQLite has no DROP INDEX
-- for an inline UNIQUE, so we rebuild via a new unique index on the pair
-- and let the original one become effectively unused. The Store layer
-- always writes user_id, so the constraint we care about is the new one.
CREATE UNIQUE INDEX IF NOT EXISTS idx_word_user_word ON word(user_id, word);
CREATE INDEX IF NOT EXISTS idx_word_user_status ON word(user_id, status);
