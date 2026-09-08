"""Unit tests for the phonetic encoder + similarity + rewrite helpers.

If ``ENCODING_REGRESSIONS`` ever drifts, several other tests -- and the
eval thresholds -- will break. That's on purpose: the encoder's exact
behaviour is part of the product contract, not an implementation detail.

Run:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import unittest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_DIR, "app"))

from phonetics import (  # noqa: E402
    ENCODING_REGRESSIONS,
    encode_word,
    rewrite as rewrite_span,
    similarity,
)


class TestEncoding(unittest.TestCase):
    def test_encoding_pinned(self):
        """Every entry in ENCODING_REGRESSIONS must round-trip exactly.

        If this fails, the phonetic encoder's behaviour changed. That is
        a contract change -- update the fixture AND recalibrate the eval
        thresholds AND re-run the evaluation before shipping.
        """
        for word, expected in ENCODING_REGRESSIONS.items():
            with self.subTest(word=word):
                self.assertEqual(encode_word(word), expected)

    def test_encode_deterministic_across_case(self):
        for w in ("Kivi", "KIWI", "kIvI"):
            self.assertEqual(encode_word(w), encode_word("kivi"))

    def test_empty_input(self):
        self.assertEqual(encode_word(""), "")


class TestSimilarity(unittest.TestCase):
    def test_asr_respellings_score_high(self):
        # These pairs are what the eval calibration bakes into thresholds.
        self.assertGreater(similarity("aditya", "aaditya"), 0.85)
        self.assertGreater(similarity("kiwi", "kivi"), 0.75)
        self.assertGreater(similarity("panner", "paneer"), 0.80)

    def test_different_names_stay_apart(self):
        # Two very common failure modes we specifically don't want:
        self.assertLess(similarity("aditi", "aaditya"), 0.72)
        self.assertLess(similarity("arvind", "aaditya"), 0.60)

    def test_identical_words(self):
        self.assertEqual(similarity("kivi", "kivi"), 1.0)

    def test_empty_input(self):
        self.assertEqual(similarity("", "kivi"), 0.0)
        self.assertEqual(similarity("kivi", ""), 0.0)

    def test_bounded_zero_to_one(self):
        for a, b in [("cat", "dog"), ("abc", "xyz"), ("hello", "world"), ("kivi", "aaditya")]:
            s = similarity(a, b)
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)


class TestRewriteSpan(unittest.TestCase):
    def test_uppercase_span_normalised_to_title(self):
        # ADITYA in prose should not become AADITYA; names are Title-cased.
        self.assertEqual(
            rewrite_span("call ADITYA now", "Aaditya", 5, 11, preserve_case=True),
            "call AADITYA now",
        )

    def test_lowercase_span_stays_lowercase(self):
        self.assertEqual(
            rewrite_span("call aditya now", "Aaditya", 5, 11, preserve_case=True),
            "call aaditya now",
        )

    def test_preserve_case_off_uses_taught_form_verbatim(self):
        # This is how UrZoo survives -- taught internal casing is not flattened.
        self.assertEqual(
            rewrite_span("email urzoo now", "UrZoo", 6, 11, preserve_case=False),
            "email UrZoo now",
        )


if __name__ == "__main__":
    unittest.main()
