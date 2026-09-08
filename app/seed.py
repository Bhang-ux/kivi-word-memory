"""Reproducible seed data for Kivi word memory.

Applies a small, realistic set of observations through the same
``Engine.observe`` API the UI uses, so the seeded state is byte-for-byte
identical to what a user clicking through the demo would produce.

Usage
-----
  python3 -m app.seed                # migrate + seed (idempotent)
  python3 -m app.seed --reset        # wipe, migrate, seed (hermetic)
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import Engine  # noqa: E402
from store import Store  # noqa: E402

# The canonical demo journey. Each entry becomes one observation.
SEEDS: list[dict] = [
    # ---- The brief's example: two spellings learned as corrections. -----
    # "Aditya" appears twice with weight 1 each -- the second sighting
    # confirms it. "Kiwi" appears once with weight 2 because the
    # correction itself is unambiguous (a brand name in a company context).
    {
        "kind": "correction",
        "asr": "ask aditya to review the sarvam kiwi service",
        "formatted": "Ask Aditya to review the Sarvam Kiwi service.",
        "selection": "Aditya",
        "replacement": "Aaditya",
        "weight": 1,
    },
    {
        "kind": "correction",
        "asr": "ping aditya on slack about the deploy",
        "formatted": "Ping Aditya on Slack about the deploy.",
        "selection": "Aditya",
        "replacement": "Aaditya",
        "weight": 1,
    },
    {
        "kind": "correction",
        "asr": "ask aditya to review the sarvam kiwi service",
        "formatted": "Ask Aditya to review the Sarvam Kiwi service.",
        "selection": "Kiwi",
        "replacement": "Kivi",
        "weight": 2,
    },
    # ---- A food word the ASR habitually romanises wrong. -----------------
    {
        "kind": "correction",
        "asr": "add milk and panner to the grocery list",
        "formatted": "Add milk and panner to the grocery list.",
        "selection": "panner",
        "replacement": "paneer",
        "weight": 2,
    },
    # ---- A company name with unusual casing the user cares about. --------
    {
        "kind": "correction",
        "asr": "email veena at urzoo dot com",
        "formatted": "Email Veena at urzoo dot com.",
        "selection": "urzoo",
        "replacement": "UrZoo",
        "weight": 2,
    },
]


def seed(engine: Engine) -> list[dict]:
    return [engine.observe(**s) for s in SEEDS]


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate + seed the Kivi word-memory DB.")
    ap.add_argument("--reset", action="store_true",
                    help="Drop every table and start hermetic. Deletes learned data.")
    args = ap.parse_args()

    store = Store()
    if args.reset:
        store.reset()
    else:
        store.migrate()
    eng = Engine(store)
    for s, r in zip(SEEDS, seed(eng)):
        marker = "OK" if r.accepted else "--"
        print(f"  [{marker}] {s['selection']:>10} -> {r.word or '(none)':<10} "
              f"[{r.status}] {r.reason}")
    print(f"\nSeeded {len(SEEDS)} observations into {store.path}")


if __name__ == "__main__":
    main()
