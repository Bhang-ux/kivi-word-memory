-- schema.sql (REFERENCE ONLY -- not applied by the code)
-- =========================================================
-- The runtime schema is built by applying db/migrations/*.sql in order via
-- app/store.py::Store.migrate(). This file mirrors the final shape after
-- all migrations, provided for reviewers who want a single-page overview.
--
-- To regenerate the runtime DB from scratch:  python3 -m app.seed --reset
-- =========================================================

CREATE TABLE word (
    id                 TEXT PRIMARY KEY,
    word               TEXT NOT NULL,                 -- canonical key, lowercase
    display            TEXT NOT NULL,                 -- user's preferred capitalisation
    pos                TEXT NOT NULL DEFAULT 'other'
                          CHECK (pos IN ('person','org','thing','acronym','other')),
    phonetic_key       TEXT NOT NULL,                 -- from app/phonetics.py
    status             TEXT NOT NULL DEFAULT 'candidate'
                          CHECK (status IN ('candidate','confirmed','needs_review','suppressed')),
    source             TEXT NOT NULL,                 -- user_correction | user_confirm | ...
    provenance         TEXT NOT NULL DEFAULT '{}',    -- JSON: origin observation
    user_id            TEXT NOT NULL DEFAULT 'default',
    last_reinforced_at TEXT,                          -- for candidate TTL
    promoted_at        TEXT,                          -- when a candidate became confirmed
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE UNIQUE INDEX idx_word_user_word          ON word(user_id, word);
CREATE INDEX        idx_word_user_status        ON word(user_id, status);
CREATE INDEX        idx_word_phonetic           ON word(phonetic_key);
CREATE INDEX        idx_word_status_reinforced  ON word(status, last_reinforced_at);

CREATE TABLE word_form (
    id         TEXT PRIMARY KEY,
    word_id    TEXT NOT NULL REFERENCES word(id) ON DELETE CASCADE,
    form       TEXT NOT NULL,                        -- spelling seen/accepted for this word
    source     TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    UNIQUE (word_id, form)
);
CREATE INDEX idx_form_form ON word_form(form);

CREATE TABLE word_context (
    id         TEXT PRIMARY KEY,
    word_id    TEXT NOT NULL REFERENCES word(id) ON DELETE CASCADE,
    context    TEXT NOT NULL,                        -- phrase template or co-occurring token
    position   TEXT NOT NULL DEFAULT 'template'
                    CHECK (position IN ('template','token')),
    source     TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    UNIQUE (word_id, context, position)
);
CREATE INDEX idx_context_ctx ON word_context(context);

CREATE TABLE word_event (
    id      TEXT PRIMARY KEY,
    kind    TEXT NOT NULL,                            -- learn|confirm|conflict|suppress|delete|reset|...
    payload TEXT NOT NULL,                            -- JSON: full observation/decision
    at      TEXT NOT NULL
);

CREATE TABLE word_stat (
    word_id       TEXT PRIMARY KEY REFERENCES word(id) ON DELETE CASCADE,
    occurrences   INTEGER NOT NULL DEFAULT 0,
    interventions INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE schema_migration (
    name       TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
