"""Tests for the persistence layer.

Focuses on the things the engine's tests can't easily see: migration
idempotency, user-scoped isolation, and TTL sweep semantics.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import unittest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_DIR, "app"))

from engine import Engine  # noqa: E402
from store import Store, CANDIDATE_TTL_DAYS  # noqa: E402


def _tmp_db() -> str:
    return os.path.join(tempfile.mkdtemp(), "test.db")


class TestMigration(unittest.TestCase):
    def test_migrate_is_idempotent(self):
        path = _tmp_db()
        s = Store(path)
        first = s.migrate()
        second = s.migrate()
        third = s.migrate()
        self.assertTrue(first)          # applied on the first call
        self.assertEqual(second, [])    # no-op afterwards
        self.assertEqual(third, [])

    def test_all_migrations_applied(self):
        path = _tmp_db()
        s = Store(path)
        s.migrate()
        with sqlite3.connect(path) as c:
            rows = c.execute("SELECT name FROM schema_migration ORDER BY name").fetchall()
        names = [r[0] for r in rows]
        self.assertIn("001_init.sql", names)
        self.assertIn("002_user_scope.sql", names)
        self.assertIn("003_candidate_lifecycle.sql", names)

    def test_reset_reapplies_migrations(self):
        path = _tmp_db()
        s = Store(path)
        s.migrate()
        e = Engine(s)
        e.observe(kind="correction", formatted="Ping Mehta.",
                  selection="Mehta", replacement="Mayhta", weight=2)
        self.assertTrue(s.snapshot()["words"])
        s.reset()
        self.assertEqual(s.snapshot()["words"], [])
        # Everything still queryable = migrations re-applied cleanly.
        s.get_word("mehta")


class TestUserScoping(unittest.TestCase):
    def test_two_users_share_a_db_without_leaking(self):
        path = _tmp_db()
        alice = Store(path, user_id="alice")
        alice.migrate()
        bob = Store(path, user_id="bob")
        bob.migrate()

        ea = Engine(alice)
        eb = Engine(bob)
        ea.observe(kind="correction",
                   formatted="Ping Mehta.", selection="Mehta",
                   replacement="Mayhta", weight=2)
        eb.observe(kind="correction",
                   formatted="Ping Kumar.", selection="Kumar",
                   replacement="Kuumar", weight=2)

        alice_words = {w["word"] for w in alice.snapshot()["words"]}
        bob_words = {w["word"] for w in bob.snapshot()["words"]}
        self.assertEqual(alice_words, {"mayhta"})
        self.assertEqual(bob_words, {"kuumar"})

        # Alice's rewrite doesn't touch Bob's word and vice versa.
        self.assertEqual(ea.rewrite("Ping Kumar again.").text, "Ping Kumar again.")
        self.assertEqual(eb.rewrite("Ping Mehta again.").text, "Ping Mehta again.")


class TestSweep(unittest.TestCase):
    def test_sweep_default_ttl(self):
        s = Store(_tmp_db())
        s.migrate()
        e = Engine(s)
        e.observe(kind="correction", formatted="Ping Mehta.",
                  selection="Mehta", replacement="Mayhta", weight=1)
        # Not stale yet.
        self.assertEqual(e.sweep(), [])
        # Age it beyond the default TTL.
        old = time.strftime(
            "%Y-%m-%dT%H:%M:%S",
            time.gmtime(time.time() - (CANDIDATE_TTL_DAYS + 5) * 86400),
        ) + "Z"
        with sqlite3.connect(s.path) as c:
            c.execute("UPDATE word SET last_reinforced_at=?, created_at=? "
                      "WHERE word='mayhta'", (old, old))
        self.assertEqual(e.sweep(), ["mayhta"])

    def test_sweep_leaves_confirmed_words_alone(self):
        s = Store(_tmp_db())
        s.migrate()
        e = Engine(s)
        # Two sightings => confirmed
        e.observe(kind="correction", formatted="Ping Mehta.",
                  selection="Mehta", replacement="Mayhta", weight=1)
        e.observe(kind="correction", formatted="Call Mehta.",
                  selection="Mehta", replacement="Mayhta", weight=1)
        # Age it well past the TTL.
        old = time.strftime(
            "%Y-%m-%dT%H:%M:%S",
            time.gmtime(time.time() - 1000 * 86400),
        ) + "Z"
        with sqlite3.connect(s.path) as c:
            c.execute("UPDATE word SET last_reinforced_at=?, created_at=? "
                      "WHERE word='mayhta'", (old, old))
        self.assertEqual(e.sweep(ttl_days=14), [])
        self.assertIsNotNone(s.get_word("mayhta"))


if __name__ == "__main__":
    unittest.main()
