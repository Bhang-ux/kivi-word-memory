"""SQLite-backed durable store for Kivi word memory.

Design decisions
----------------
- **Real migrations.** ``db/migrations/*.sql`` is applied in lexicographic
  order by ``Store.migrate()``. ``schema_migration`` tracks what's been
  run; re-running is a no-op. There is no separate "schema.sql apply"
  path -- ``db/schema.sql`` is documentation only.
- **User-scoped from day one.** Every row on ``word`` carries a
  ``user_id``. The demo hardcodes ``"default"`` but a real deployment
  would pass the tenant/session id. Multi-user is a config flag, not a
  rebuild.
- **Auditable.** ``word_event`` is append-only; every learn/rewrite/
  suppress/reset decision is logged with its payload. Nothing in the
  engine deletes events.
- **Inspectable.** ``snapshot()`` returns the full memory state as a
  plain dict, so the UI, the tests, and the evaluation all read from
  the same source of truth.

Tables (final shape, see ``db/schema.sql`` for the SQL):
  word         one memory entry per (user_id, canonical word)
  word_form    every spelling seen/accepted for that word
  word_context phrase templates ("call <word>") and co-occurring tokens
  word_event   append-only audit log
  word_stat    per-word counters (occurrences, interventions)

Lifecycle: candidate -> confirmed -> {needs_review | suppressed}.
Only ``confirmed`` words ever rewrite text.
"""

from __future__ import annotations

import glob
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("KIVI_DB", os.path.join(APP_DIR, "db", "kivi.db"))
MIGRATIONS_DIR = os.path.join(APP_DIR, "db", "migrations")

# Learning policy constants -- the numbers that govern when evidence
# becomes durable memory. See README ("Learning policy") for rationale.
CONFIRM_MIN = 2                # observations required to confirm a candidate
CANDIDATE_TTL_DAYS = 14        # un-reinforced candidates decay after this
DEFAULT_USER = "default"       # single-user demo; multi-user is a config flag


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def connect(path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


class Store:
    """All persistence for Kivi word memory. Single class = single seam
    the engine, server, tests, and eval share."""

    def __init__(self, path: str | None = None, user_id: str = DEFAULT_USER):
        self.path = path or DB_PATH
        self.user_id = user_id
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

    # -- schema lifecycle ----------------------------------------------------
    def migrate(self) -> list[str]:
        """Apply every migration in ``db/migrations`` that hasn't been
        applied yet. Returns the names of newly-applied migrations."""
        applied: list[str] = []
        with connect(self.path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migration ("
                "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {
                r["name"]
                for r in conn.execute("SELECT name FROM schema_migration").fetchall()
            }
            for path in sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))):
                name = os.path.basename(path)
                if name in done:
                    continue
                with open(path) as f:
                    conn.executescript(f.read())
                conn.execute(
                    "INSERT INTO schema_migration(name, applied_at) VALUES(?,?)",
                    (name, now_iso()),
                )
                applied.append(name)
        return applied

    def drop_all(self) -> None:
        with connect(self.path) as conn:
            for t in ("word_event", "word_context", "word_form", "word_stat", "word",
                      "schema_migration"):
                conn.execute(f"DROP TABLE IF EXISTS {t}")

    def reset(self) -> None:
        """Wipe every table and re-apply migrations. Used by /api/reset
        and by every evaluation run for a hermetic starting state."""
        self.drop_all()
        self.migrate()

    # -- words ---------------------------------------------------------------
    def upsert_word(
        self,
        word: str,
        display: str,
        pos: str,
        phonetic_key: str,
        status: str,
        source: str,
        provenance: dict[str, Any] | None = None,
    ) -> str:
        prov = json.dumps(provenance or {})
        ts = now_iso()
        promoted_at = ts if status == "confirmed" else None
        with connect(self.path) as conn:
            conn.execute(
                """INSERT INTO word(
                       id, word, display, pos, phonetic_key, status, source,
                       provenance, user_id, last_reinforced_at, promoted_at,
                       created_at, updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id, word) DO UPDATE SET
                     display=excluded.display,
                     pos=excluded.pos,
                     status=excluded.status,
                     provenance=excluded.provenance,
                     last_reinforced_at=excluded.last_reinforced_at,
                     promoted_at=COALESCE(word.promoted_at, excluded.promoted_at),
                     updated_at=excluded.updated_at""",
                (new_id(), word, display, pos, phonetic_key, status, source,
                 prov, self.user_id, ts, promoted_at, ts, ts),
            )
            row = conn.execute(
                "SELECT id FROM word WHERE user_id=? AND word=?",
                (self.user_id, word),
            ).fetchone()
            return str(row["id"])

    def get_word(self, word: str) -> sqlite3.Row | None:
        with connect(self.path) as conn:
            return conn.execute(
                "SELECT * FROM word WHERE user_id=? AND word=?",
                (self.user_id, word.lower()),
            ).fetchone()

    def find_by_form(self, form: str) -> sqlite3.Row | None:
        """Find a word by canonical spelling OR any of its stored forms."""
        with connect(self.path) as conn:
            r = conn.execute(
                "SELECT * FROM word WHERE user_id=? AND word=?",
                (self.user_id, form.lower()),
            ).fetchone()
            if r:
                return r
            return conn.execute(
                """SELECT w.* FROM word w
                   JOIN word_form f ON f.word_id=w.id
                   WHERE w.user_id=? AND f.form=?""",
                (self.user_id, form.lower()),
            ).fetchone()

    def all_confirmed_words(self) -> list[sqlite3.Row]:
        with connect(self.path) as conn:
            return conn.execute(
                "SELECT * FROM word WHERE user_id=? AND status='confirmed' ORDER BY word",
                (self.user_id,),
            ).fetchall()

    def status_forms(self, status: str) -> set[str]:
        """All spellings (canonical + forms) that currently carry this status."""
        with connect(self.path) as conn:
            rows = conn.execute(
                """SELECT w.word AS word, f.form AS form
                   FROM word w LEFT JOIN word_form f ON f.word_id = w.id
                   WHERE w.user_id=? AND w.status=?""",
                (self.user_id, status),
            ).fetchall()
            out: set[str] = set()
            for r in rows:
                out.add(r["word"])
                if r["form"]:
                    out.add(r["form"])
            return out

    def delete_word(self, word_id: str) -> None:
        with connect(self.path) as conn:
            conn.execute("DELETE FROM word WHERE id=?", (word_id,))

    def set_status(self, word_id: str, status: str) -> None:
        ts = now_iso()
        with connect(self.path) as conn:
            if status == "confirmed":
                conn.execute(
                    "UPDATE word SET status=?, updated_at=?, "
                    "promoted_at=COALESCE(promoted_at, ?), last_reinforced_at=? "
                    "WHERE id=?",
                    (status, ts, ts, ts, word_id),
                )
            else:
                conn.execute(
                    "UPDATE word SET status=?, updated_at=? WHERE id=?",
                    (status, ts, word_id),
                )

    def touch_reinforced(self, word_id: str) -> None:
        """Update last_reinforced_at so this word survives the next TTL sweep."""
        with connect(self.path) as conn:
            conn.execute(
                "UPDATE word SET last_reinforced_at=?, updated_at=? WHERE id=?",
                (now_iso(), now_iso(), word_id),
            )

    def sweep_stale_candidates(self, ttl_days: int = CANDIDATE_TTL_DAYS) -> list[str]:
        """Delete un-reinforced candidates older than ``ttl_days``.

        Confirmed words are never swept -- a user may mention a family
        member only occasionally, and that pattern is exactly the kind of
        thing a personal memory should preserve. Only candidates decay.
        Returns the list of words removed.
        """
        cutoff = time.gmtime(time.time() - ttl_days * 86400)
        cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%S", cutoff) + "Z"
        with connect(self.path) as conn:
            rows = conn.execute(
                """SELECT id, word FROM word
                   WHERE user_id=? AND status='candidate'
                   AND COALESCE(last_reinforced_at, created_at) <= ?""",
                (self.user_id, cutoff_iso),
            ).fetchall()
            words = [r["word"] for r in rows]
            for r in rows:
                conn.execute("DELETE FROM word WHERE id=?", (r["id"],))
        return words

    # -- forms / contexts / stats -------------------------------------------
    def add_form(self, word_id: str, form: str, source: str) -> None:
        f = form.lower().strip()
        if not f:
            return
        ts = now_iso()
        with connect(self.path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO word_form(id, word_id, form, source, first_seen, last_seen) "
                "VALUES(?,?,?,?,?,?)",
                (new_id(), word_id, f, source, ts, ts),
            )
            conn.execute(
                "UPDATE word_form SET last_seen=? WHERE word_id=? AND form=?",
                (ts, word_id, f),
            )

    def add_context(self, word_id: str, context: str, position: str, source: str) -> None:
        ctx = context.lower().strip()
        if not ctx:
            return
        ts = now_iso()
        with connect(self.path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO word_context"
                "(id, word_id, context, position, source, first_seen, last_seen) "
                "VALUES(?,?,?,?,?,?,?)",
                (new_id(), word_id, ctx, position, source, ts, ts),
            )
            conn.execute(
                "UPDATE word_context SET last_seen=? WHERE word_id=? AND context=?",
                (ts, word_id, ctx),
            )

    def contexts_by_word(self) -> dict[str, list[str]]:
        """All contexts across all confirmed words for the current user,
        grouped by word_id -- one query per rewrite instead of one per word."""
        with connect(self.path) as conn:
            rows = conn.execute(
                """SELECT c.word_id AS word_id, c.context AS context
                   FROM word_context c JOIN word w ON w.id=c.word_id
                   WHERE w.user_id=?""",
                (self.user_id,),
            ).fetchall()
            out: dict[str, list[str]] = {}
            for r in rows:
                out.setdefault(r["word_id"], []).append(r["context"])
            return out

    def bump_stat(self, word_id: str, kind: str) -> None:
        col = "occurrences" if kind == "occurrence" else "interventions"
        with connect(self.path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO word_stat(word_id, occurrences, interventions) VALUES(?,0,0)",
                (word_id,),
            )
            conn.execute(f"UPDATE word_stat SET {col} = {col} + 1 WHERE word_id=?", (word_id,))

    # -- events --------------------------------------------------------------
    def log_event(self, kind: str, payload: dict[str, Any]) -> str:
        eid = new_id()
        with connect(self.path) as conn:
            conn.execute(
                "INSERT INTO word_event(id, kind, payload, at) VALUES(?,?,?,?)",
                (eid, kind, json.dumps(payload), now_iso()),
            )
        return eid

    def events(self, limit: int = 200) -> list[sqlite3.Row]:
        with connect(self.path) as conn:
            return conn.execute(
                "SELECT * FROM word_event ORDER BY at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()

    def db_size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            p = self.path + suffix
            if os.path.exists(p):
                total += os.path.getsize(p)
        return total

    # -- snapshot ------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Full inspectable memory state -- one call, one shape, used by
        the UI, the tests, and the evaluation. If it isn't in here, no
        surface of the product can see it."""
        with connect(self.path) as conn:
            words = conn.execute(
                "SELECT * FROM word WHERE user_id=? ORDER BY word",
                (self.user_id,),
            ).fetchall()
            out: dict[str, Any] = {
                "user_id": self.user_id,
                "words": [],
                "db_bytes": self.db_size_bytes(),
            }
            for w in words:
                forms = conn.execute(
                    "SELECT form, source, first_seen, last_seen FROM word_form WHERE word_id=?",
                    (w["id"],),
                ).fetchall()
                ctxs = conn.execute(
                    "SELECT context, position, source, first_seen, last_seen "
                    "FROM word_context WHERE word_id=?",
                    (w["id"],),
                ).fetchall()
                stats = conn.execute(
                    "SELECT occurrences, interventions FROM word_stat WHERE word_id=?",
                    (w["id"],),
                ).fetchone()
                out["words"].append({
                    "id": w["id"],
                    "word": w["word"],
                    "display": w["display"],
                    "pos": w["pos"],
                    "phonetic_key": w["phonetic_key"],
                    "status": w["status"],
                    "source": w["source"],
                    "provenance": json.loads(w["provenance"]),
                    "created_at": w["created_at"],
                    "updated_at": w["updated_at"],
                    "last_reinforced_at": w["last_reinforced_at"],
                    "promoted_at": w["promoted_at"],
                    "forms": [dict(r) for r in forms],
                    "contexts": [dict(r) for r in ctxs],
                    "occurrences": stats["occurrences"] if stats else 0,
                    "interventions": stats["interventions"] if stats else 0,
                })
            evs = conn.execute(
                "SELECT kind, payload, at FROM word_event ORDER BY at DESC, rowid DESC LIMIT 50"
            ).fetchall()
            out["events"] = [
                {"kind": e["kind"], "payload": json.loads(e["payload"]), "at": e["at"]} for e in evs
            ]
            return out
