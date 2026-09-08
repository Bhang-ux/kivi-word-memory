-- 001_init.sql
-- Initial word-memory schema. Applied first; later migrations evolve it.
-- Runner: app/store.py::Store.migrate() applies files in lexicographic order.

CREATE TABLE IF NOT EXISTS word (
    id           TEXT PRIMARY KEY,
    word         TEXT NOT NULL UNIQUE,               -- canonical key, lowercase
    display      TEXT NOT NULL,                       -- user's preferred capitalisation
    pos          TEXT NOT NULL DEFAULT 'other'
                    CHECK (pos IN ('person','org','thing','acronym','other')),
    phonetic_key TEXT NOT NULL,                       -- from app/phonetics.py::encode_word
    status       TEXT NOT NULL DEFAULT 'candidate'
                    CHECK (status IN ('candidate','confirmed','needs_review','suppressed')),
    source       TEXT NOT NULL,
    provenance   TEXT NOT NULL DEFAULT '{}',          -- JSON: origin observation
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS word_form (
    id         TEXT PRIMARY KEY,
    word_id    TEXT NOT NULL REFERENCES word(id) ON DELETE CASCADE,
    form       TEXT NOT NULL,                        -- spelling seen/accepted for this word
    source     TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    UNIQUE (word_id, form)
);

CREATE TABLE IF NOT EXISTS word_context (
    id         TEXT PRIMARY KEY,
    word_id    TEXT NOT NULL REFERENCES word(id) ON DELETE CASCADE,
    context    TEXT NOT NULL,
    position   TEXT NOT NULL DEFAULT 'template'
                    CHECK (position IN ('template','token')),
    source     TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    UNIQUE (word_id, context, position)
);

CREATE TABLE IF NOT EXISTS word_event (
    id      TEXT PRIMARY KEY,
    kind    TEXT NOT NULL,
    payload TEXT NOT NULL,                            -- JSON: full observation/decision
    at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS word_stat (
    word_id       TEXT PRIMARY KEY REFERENCES word(id) ON DELETE CASCADE,
    occurrences   INTEGER NOT NULL DEFAULT 0,
    interventions INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_word_status   ON word(status);
CREATE INDEX IF NOT EXISTS idx_word_phonetic ON word(phonetic_key);
CREATE INDEX IF NOT EXISTS idx_form_form     ON word_form(form);
CREATE INDEX IF NOT EXISTS idx_context_ctx   ON word_context(context);
