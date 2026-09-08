"""Behaviour tests for the Kivi word memory engine.

Covers: learning lifecycle, rewrite decisions, override/needs_review,
suppression, deletion, persistence, and the candidate TTL sweep. Phonetics
have their own module in tests/test_phonetics.py.

Run:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_DIR, "app"))

from engine import Engine  # noqa: E402
from seed import SEEDS  # noqa: E402
from store import Store  # noqa: E402


def fresh_engine() -> tuple[Engine, Store]:
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    store = Store(path)
    store.reset()
    return Engine(store), store


class TestLearning(unittest.TestCase):
    def test_first_correction_is_candidate(self):
        e, _ = fresh_engine()
        r = e.observe(kind="correction",
                      asr="ping mehta", formatted="Ping Mehta.",
                      selection="Mehta", replacement="Mayhta", weight=1)
        self.assertEqual(r.status, "candidate")
        self.assertFalse(r.promoted)

    def test_second_sighting_confirms(self):
        e, _ = fresh_engine()
        e.observe(kind="correction",
                  asr="ping mehta", formatted="Ping Mehta.",
                  selection="Mehta", replacement="Mayhta", weight=1)
        r = e.observe(kind="correction",
                      asr="call mehta now", formatted="Call Mehta.",
                      selection="Mehta", replacement="Mayhta", weight=1)
        self.assertTrue(r.promoted)
        self.assertEqual(r.status, "confirmed")

    def test_common_word_replacement_rejected(self):
        # Formatting-model territory, not memory. Memory does not learn
        # dictionary words as targets even if the user asks.
        e, _ = fresh_engine()
        r = e.observe(kind="correction",
                      formatted="Send it.", selection="send",
                      replacement="the", weight=2)
        self.assertFalse(r.accepted)
        self.assertEqual(r.reason, "replacement is a common word")

    def test_candidate_never_rewrites(self):
        e, _ = fresh_engine()
        e.observe(kind="correction", formatted="Ping Mehta.",
                  selection="Mehta", replacement="Mayhta", weight=1)
        out = e.rewrite("Ping Mehta again.")
        self.assertEqual(out.text, "Ping Mehta again.")
        self.assertEqual(out.decisions, [])

    def test_confirmed_word_touches_last_reinforced(self):
        e, s = fresh_engine()
        e.observe(**SEEDS[0])
        e.observe(**SEEDS[1])  # second sighting -> confirmed
        row = s.get_word("aaditya")
        self.assertIsNotNone(row["last_reinforced_at"])
        self.assertIsNotNone(row["promoted_at"])


class TestRewrite(unittest.TestCase):
    def test_brief_example(self):
        e, _ = fresh_engine()
        for s in SEEDS:
            e.observe(**s)
        out = e.rewrite("Ask Aditya to review the Sarvam Kiwi service.")
        self.assertEqual(out.text, "Ask Aaditya to review the Sarvam Kivi service.")
        self.assertEqual(len(out.decisions), 2)

    def test_real_word_veto_without_context(self):
        e, _ = fresh_engine()
        for s in SEEDS:
            e.observe(**s)
        out = e.rewrite("I like kiwi fruit in the morning.")
        self.assertEqual(out.text, "I like kiwi fruit in the morning.")
        self.assertTrue(all(d.action == "abstain" for d in out.decisions))

    def test_context_rescues_common_word(self):
        e, _ = fresh_engine()
        for s in SEEDS:
            e.observe(**s)
        out = e.rewrite("The kiwi service is down.")
        self.assertEqual(out.text, "The Kivi service is down.")

    def test_unrelated_text_untouched(self):
        e, _ = fresh_engine()
        for s in SEEDS:
            e.observe(**s)
        out = e.rewrite("The quick brown fox jumps over the lazy dog.")
        self.assertEqual(out.text, "The quick brown fox jumps over the lazy dog.")

    def test_decisions_carry_reasons(self):
        e, _ = fresh_engine()
        for s in SEEDS:
            e.observe(**s)
        out = e.rewrite("Ask Aditya to review the Sarvam Kiwi service.")
        for d in out.decisions:
            self.assertTrue(d.reason)
            self.assertIsNotNone(d.similarity)

    def test_rewrite_records_intervention_stat(self):
        e, s = fresh_engine()
        for seed in SEEDS:
            e.observe(**seed)
        before = next(w for w in s.snapshot()["words"] if w["word"] == "kivi")
        e.rewrite("Ask Aditya to review the Sarvam Kiwi service.")
        after = next(w for w in s.snapshot()["words"] if w["word"] == "kivi")
        self.assertEqual(after["interventions"], before["interventions"] + 1)


class TestLifecycle(unittest.TestCase):
    def _taught_mehta(self):
        e, s = fresh_engine()
        e.observe(kind="correction",
                  formatted="Email Ananya about the Mehta invoice.",
                  selection="Mehta", replacement="Mayhta", weight=1)
        e.observe(kind="confirm",
                  formatted="Call Mehta about the invoice.",
                  selection="Mehta")
        return e, s

    def test_conflict_pauses_rewrites(self):
        e, _ = self._taught_mehta()
        out = e.rewrite("Email Ananya about the Mehta invoice.")
        self.assertEqual(out.text, "Email Ananya about the Mayhta invoice.")
        # user overrides our rewrite with a third spelling
        e.observe(kind="edit", formatted="File the Mayhta report.",
                  selection="Mayhta", replacement="Mehta")
        out2 = e.rewrite("Email Ananya about the Mayhta invoice again.")
        self.assertEqual(out2.text, "Email Ananya about the Mayhta invoice again.")

    def test_reconfirm_resumes_rewrites(self):
        e, s = self._taught_mehta()
        # trigger conflict
        e.observe(kind="edit", formatted="File the Mayhta report.",
                  selection="Mayhta", replacement="Mehta")
        row = s.get_word("mayhta")
        e.reconfirm(row["id"])
        out = e.rewrite("Email Mehta about the invoice.")
        self.assertEqual(out.text, "Email Mayhta about the invoice.")

    def test_suppressed_word_never_rewritten(self):
        e, s = fresh_engine()
        for seed in SEEDS:
            e.observe(**seed)
        row = s.get_word("kivi")
        e.suppress(row["id"])
        out = e.rewrite("The kiwi service is down.")
        self.assertEqual(out.text, "The kiwi service is down.")

    def test_delete_removes_memory(self):
        e, _ = fresh_engine()
        for seed in SEEDS:
            e.observe(**seed)
        e.observe(kind="delete", selection="Kivi")
        out = e.rewrite("The kiwi service is down.")
        self.assertEqual(out.text, "The kiwi service is down.")

    def test_sweep_deletes_stale_candidates_only(self):
        e, s = fresh_engine()
        # A candidate: one sighting.
        e.observe(kind="correction",
                  formatted="Ping Zhorb.",
                  selection="Zhorb", replacement="Zorb", weight=1)
        # A confirmed word: two sightings (via seed).
        e.observe(**SEEDS[0]); e.observe(**SEEDS[1])
        # Age the candidate manually.
        old = time.strftime("%Y-%m-%dT%H:%M:%S",
                            time.gmtime(time.time() - 30 * 86400)) + "Z"
        import sqlite3
        with sqlite3.connect(s.path) as c:
            c.execute("UPDATE word SET last_reinforced_at=?, created_at=? "
                      "WHERE word='zorb'", (old, old))
        removed = e.sweep(ttl_days=14)
        self.assertEqual(removed, ["zorb"])
        # Confirmed word survived.
        self.assertIsNotNone(s.get_word("aaditya"))


class TestPersistence(unittest.TestCase):
    def test_state_survives_reconnect(self):
        e, s = fresh_engine()
        for seed in SEEDS:
            e.observe(**seed)
        store2 = Store(s.path)
        engine2 = Engine(store2)
        out = engine2.rewrite("Ask Aditya to review the Sarvam Kiwi service.")
        self.assertEqual(out.text, "Ask Aaditya to review the Sarvam Kivi service.")

    def test_reset_clears_everything(self):
        e, s = fresh_engine()
        for seed in SEEDS:
            e.observe(**seed)
        e.forget_all()
        self.assertEqual(s.snapshot()["words"], [])
        out = e.rewrite("Ask Aditya to review the Sarvam Kiwi service.")
        self.assertEqual(out.text, "Ask Aditya to review the Sarvam Kiwi service.")


class TestEventLog(unittest.TestCase):
    def test_every_material_action_is_logged(self):
        e, s = fresh_engine()
        e.observe(**SEEDS[0])  # learn
        e.observe(**SEEDS[1])  # confirm via reinforcement
        row = s.get_word("aaditya")
        e.suppress(row["id"])
        kinds = {ev["kind"] for ev in s.snapshot()["events"]}
        self.assertIn("learn", kinds)
        self.assertIn("confirm", kinds)
        self.assertIn("suppress", kinds)


if __name__ == "__main__":
    unittest.main()
