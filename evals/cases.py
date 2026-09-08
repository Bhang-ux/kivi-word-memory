"""Case fixtures for the Kivi word-memory evaluation.

Each ``Case`` has:
  * ``group``          -- positive | negative | boundary | lifecycle
  * ``formatted``      -- the input transcript
  * ``asr``            -- optional raw ASR (extra evidence)
  * ``expect_text``    -- the exact expected memory-aware output
  * ``expect_actions`` -- ``{token: "rewrite" | "abstain"}``
  * ``note``           -- documented rationale, propagated into the report
  * ``setup``          -- optional side-effects to apply BEFORE running
                          this case (list of ``Engine.observe`` kwargs
                          plus ``{"op": "suppress", "word": "kivi"}``)

Cases are ordered; ``setup`` side effects on the shared eval engine
happen in list order and are captured in the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Case:
    id: str
    group: str
    formatted: str
    asr: str = ""
    expect_text: str = ""
    expect_actions: dict[str, str] = field(default_factory=dict)
    note: str = ""
    setup: list[dict[str, Any]] = field(default_factory=list)


CASES: list[Case] = [
    # ==== POSITIVE: memory SHOULD intervene =================================
    Case(
        id="P1_brief_example",
        group="positive",
        formatted="Ask Aditya to review the Sarvam Kiwi service.",
        asr="ask aditya to review the sarvam kiwi service",
        expect_text="Ask Aaditya to review the Sarvam Kivi service.",
        expect_actions={"Aditya": "rewrite", "Kiwi": "rewrite"},
        note="The exact example from the brief, after teaching both words.",
    ),
    Case(
        id="P2_new_sentence_same_words",
        group="positive",
        formatted="Ping Aditya about the Sarvam Kiwi launch.",
        expect_text="Ping Aaditya about the Sarvam Kivi launch.",
        expect_actions={"Aditya": "rewrite", "Kiwi": "rewrite"},
        note="Memory must generalise beyond the sentence it was taught in.",
    ),
    Case(
        id="P3_lowercase_input",
        group="positive",
        formatted="can you ask aditya to join the kiwi call",
        expect_text="can you ask Aaditya to join the Kivi call",
        expect_actions={"aditya": "rewrite", "kiwi": "rewrite"},
        note="Proper nouns take their taught Title form regardless of the "
             "input's case; taught companion words supply context for kiwi.",
    ),
    Case(
        id="P4_paneer_variant",
        group="positive",
        formatted="Order more panner for the team lunch.",
        expect_text="Order more paneer for the team lunch.",
        expect_actions={"panner": "rewrite"},
        note="Food romanisation learned from a grocery correction; "
             "generalises to a work-lunch context.",
    ),
    Case(
        id="P5_caps_input",
        group="positive",
        formatted="Review the ADITYA migration before Friday.",
        expect_text="Review the Aaditya migration before Friday.",
        expect_actions={"ADITYA": "rewrite"},
        note="Proper nouns normalise to the taught Title form; the engine "
             "does not mirror SHOUTING because names are Title case in prose.",
    ),
    Case(
        id="P6_casing_preference",
        group="positive",
        formatted="Email the urzoo team about pricing.",
        expect_text="Email the UrZoo team about pricing.",
        expect_actions={"urzoo": "rewrite"},
        note="The user taught exact casing (UrZoo); even lowercase input "
             "is rewritten to the taught display form (not flattened).",
    ),
    Case(
        id="P7_multiple_taught_words_one_sentence",
        group="positive",
        formatted="Ping Aditya, tell UrZoo, and send Kiwi a note.",
        expect_text="Ping Aaditya, tell UrZoo, and send Kivi a note.",
        expect_actions={"Aditya": "rewrite", "UrZoo": "rewrite", "Kiwi": "rewrite"},
        note="Three independent memories co-fire in one sentence without "
             "interfering with each other's spans (right-to-left scan).",
    ),

    # ==== NEGATIVE: memory must deliberately do nothing =====================
    Case(
        id="N1_unrelated_text",
        group="negative",
        formatted="The quick brown fox jumps over the lazy dog.",
        expect_text="The quick brown fox jumps over the lazy dog.",
        expect_actions={},
        note="Ordinary English passes through untouched -- no spans "
             "resembled any confirmed memory.",
    ),
    Case(
        id="N2_similar_but_not_taught_name",
        group="negative",
        formatted="Ask Aditi to review the service.",
        expect_text="Ask Aditi to review the service.",
        expect_actions={"Aditi": "abstain"},
        note="'Aditi' resembles 'Aaditya' (sim 0.70) but is a different "
             "name; below the strong threshold and no context support, so "
             "the engine records an abstention instead of guessing.",
    ),
    Case(
        id="N3_common_word_homophone_risk",
        group="negative",
        formatted="I like kiwi fruit in the morning.",
        asr="i like kiwi fruit in the morning",
        expect_text="I like kiwi fruit in the morning.",
        expect_actions={"kiwi": "abstain"},
        note="'kiwi' here IS the fruit. Rewriting a dictionary word "
             "requires supporting context; none appears, so it abstains.",
    ),
    Case(
        id="N4_candidate_not_yet_confirmed",
        group="negative",
        formatted="Ship the flurbo widget to production.",
        expect_text="Ship the flurbo widget to production.",
        expect_actions={},
        setup=[
            {"kind": "confirm",
             "asr": "ship the flurbo widget",
             "formatted": "Ship the flurbo widget to production.",
             "selection": "flurbo"},
        ],
        note="Runs against a candidate-only word; candidates never rewrite.",
    ),
    Case(
        id="N5_replacement_is_common_word_rejected",
        group="negative",
        formatted="Please review the report.",
        expect_text="Please review the report.",
        expect_actions={},
        note="A prior correction attempt tried to teach 'review' -> 'the' "
             "and was refused at learn time; nothing in memory means "
             "nothing happens here either.",
    ),

    # ==== BOUNDARY: context rescues a sub-strong match =====================
    Case(
        id="B1_kiwi_with_service_context",
        group="boundary",
        formatted="The kiwi service is down.",
        expect_text="The Kivi service is down.",
        expect_actions={"kiwi": "rewrite"},
        note="Product-sense context (stored template '<word> service') "
             "pushes the match over the intervention threshold.",
    ),
    Case(
        id="B2_already_canonical",
        group="boundary",
        formatted="Buy paneer at the market.",
        expect_text="Buy paneer at the market.",
        expect_actions={},
        note="Already-canonical spelling is left alone (no churn).",
    ),
    Case(
        id="B3_short_word_low_sim_no_rewrite",
        group="boundary",
        formatted="The ok signal was clear.",
        expect_text="The ok signal was clear.",
        expect_actions={},
        note="Very short words never cross the similarity threshold to any "
             "taught word; the abstention isn't even recorded because no "
             "candidate match existed.",
    ),

    # ==== LIFECYCLE: candidate -> confirmed -> conflict -> suppressed ======
    Case(
        id="L1_candidate_never_rewrites",
        group="lifecycle",
        formatted="Email Ananya about the Mehta invoice.",
        expect_text="Email Ananya about the Mehta invoice.",
        expect_actions={},
        setup=[
            {"kind": "correction",
             "asr": "email ananya about the mehta invoice",
             "formatted": "Email Ananya about the Mehta invoice.",
             "selection": "Mehta", "replacement": "Mayhta", "weight": 1},
        ],
        note="First sighting of Mehta->Mayhta is only a candidate "
             "(weight 1): it must not rewrite yet.",
    ),
    Case(
        id="L2_confirmed_rewrites",
        group="lifecycle",
        formatted="Email Ananya about the Mehta invoice again.",
        expect_text="Email Ananya about the Mayhta invoice again.",
        expect_actions={"Mehta": "rewrite"},
        setup=[
            {"kind": "confirm",
             "asr": "call mehta about the invoice",
             "formatted": "Call Mehta about the invoice.",
             "selection": "Mehta"},
        ],
        note="After a confirming second sighting, the word rewrites new "
             "sentences.",
    ),
    Case(
        id="L3_user_override_pauses",
        group="lifecycle",
        formatted="File the Mehta report under M.",
        expect_text="File the Mehta report under M.",
        expect_actions={"Mehta": "abstain"},
        setup=[
            {"kind": "edit",
             "asr": "file the mehta report under m",
             "formatted": "File the Mehta report under M.",
             "selection": "Mayhta", "replacement": "Mehta"},
        ],
        note="The user re-edited our rewrite to a third spelling; the "
             "word is flagged needs_review and rewrites pause for it and "
             "all its forms until re-taught.",
    ),
    Case(
        id="L4_suppressed_word_never_rewritten",
        group="lifecycle",
        formatted="The Kiwi launch went well.",
        expect_text="The Kiwi launch went well.",
        expect_actions={"Kiwi": "abstain"},
        setup=[
            # Reinforce Kivi (also a rewrite of Kiwi during observe) so it's
            # firmly confirmed; then suppress it via the memory UI.
            {"kind": "correction",
             "asr": "the kivi launch went well",
             "formatted": "The Kiwi launch went well.",
             "selection": "Kiwi", "replacement": "Kivi", "weight": 2},
            {"op": "suppress", "word": "kivi"},
        ],
        note="After suppressing 'kivi' from the memory UI, the word (and "
             "its forms) is never rewritten again; the abstention is "
             "still logged for inspectability.",
    ),
    Case(
        id="L5_delete_removes_intervention",
        group="lifecycle",
        formatted="Order more panner for the potluck.",
        expect_text="Order more panner for the potluck.",
        expect_actions={},
        setup=[
            {"kind": "delete", "selection": "paneer"},
        ],
        note="After forgetting 'paneer' entirely, 'panner' is no longer "
             "recognised as anything the system knows -- the engine has "
             "nothing to abstain about.",
    ),
]
