# The Words Kivi Keeps

**A word-level phonetic memory system that survives across sessions,
learns from ordinary corrections, and rewrites new transcripts to match
the user's spellings -- with an inspectable reason for every intervention
and every deliberate non-intervention.**

Runs on **Python 3.10+ standard library only**. No `pip install`. No API
keys. No external services. Every decision is auditable in the UI and
logged to an append-only event table.

---

## What it does

Kivi's speech pipeline produces three layers:

```
   ASR raw   ->   Formatted   ->   Memory-aware
   (words)       (LM-cleaned)     (this system)
```

The memory-aware layer knows the user's personal words. Given the
system has been taught "Aditya -> Aaditya" and "Kiwi -> Kivi":

```
Input   Ask Aditya to review the Sarvam Kiwi service.
Output  Ask Aaditya to review the Sarvam Kivi service.
```

Given it has been taught "Aditya -> Aaditya" only, and the user then
says something with a fruit:

```
Input   I like kiwi fruit in the morning.
Output  I like kiwi fruit in the morning.    (kiwi left alone -- fruit sense)
```

Every rewrite (and every *considered-but-rejected* span) carries a
machine-readable reason that surfaces in the UI as a hover tooltip and
in the evaluation report as a decision log line.

---

## Architecture at a glance

```
                 +------------------------------------------------+
                 |                    HTTP API                    |
                 |   /observe /rewrite /suppress /delete /sweep   |
                 |          /memory /events /health /reset        |
                 +------------------------------------------------+
                                       |
                     +---------------------------------+
                     |            Engine               |
                     |  learn:   observe(kind, ...)    |
                     |  rewrite: formatted -> text     |
                     |                                 |
                     |  policies:  candidate lifecycle |
                     |             real-word veto      |
                     |             context boost       |
                     |             needs_review        |
                     |             suppression         |
                     +---------------------------------+
                       |                        |
              +----------------+       +--------------------+
              |   Phonetics    |       |       Store        |
              |  encode_word   |       |  migrations, CRUD, |
              |  similarity    |       |  snapshot, sweep   |
              +----------------+       +--------------------+
                                                 |
                                          SQLite (WAL)
                                          per-user scoped
```

Every arrow goes through public functions on named modules. Nothing
depends on private state.

---

## Data model

Five tables, five clear jobs. Full SQL: `db/schema.sql` (composite view)
and `db/migrations/*.sql` (source of truth, applied in order).

- **`word`** -- one row per taught spelling per user. Carries status,
  phonetic key, POS, display casing, `last_reinforced_at` for TTL,
  `promoted_at` for confirmation timestamp, `provenance` (the JSON of
  the observation that created it).
- **`word_form`** -- every spelling ever seen or accepted for this word
  (`aditya`, `aaditya`, `adithya`). Enables "find by any form".
- **`word_context`** -- phrase templates (`call <word>`, `<word> service`)
  and co-occurring content tokens. Drives the context boost.
- **`word_event`** -- append-only audit log of every learn / rewrite /
  suppress / conflict / delete / reset / sweep. Nothing deletes events.
- **`word_stat`** -- per-word counters (occurrences, interventions).

The full inspectable state comes out of `Store.snapshot()` -- one call,
one shape. If it isn't in that dict, no surface of the product can see it.

---

## Learning policy (the choices to defend)

Every knob has a rationale. The eval calibrates against these numbers
and will fail if any drifts silently.

| Decision                        | Setting                        | Why                                                                                                                                                                                     |
|---------------------------------|--------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Two-sighting confirmation**   | `CONFIRM_MIN = 2`              | One correction is a slip. Two is the smallest number requiring independent evidence. Below 2, a keystroke becomes a permanent rewrite; above 2 the system feels forgetful.              |
| **Strong rewrite threshold**    | `similarity >= 0.72`           | Calibrated so ASR respellings pass (aditya/aaditya 0.90, kiwi/kivi 0.82) and different names stay apart (aditi/aaditya 0.70). Below the bar, context must lift the match over.          |
| **Weak consider threshold**     | `similarity >= 0.60`           | Below this the engine doesn't even record an abstention -- it stops looking.                                                                                                            |
| **Real-word veto**              | context required               | Rewriting "kiwi" (fruit) to "Kivi" (product) silently would corrupt ordinary prose. Dictionary words are rewritten only when supporting context appears.                                |
| **Context boost cap**           | +0.15 max                      | Context rescues borderline matches but never overrides a low similarity. A short lookalike can't be dragged over the bar by a coincidental co-occurring token.                          |
| **Conflict pauses**             | `needs_review`                 | When the user re-edits our rewrite to a different spelling, our memory is wrong. Pause rewriting for that word and all its forms until re-taught, rather than overwrite silently.       |
| **Per-form suppression**        | any form -> all forms silent  | A silenced word is never rewritten again in any spelling; the abstention is still logged so nothing disappears silently.                                                                 |
| **Candidate TTL**               | 14 days                        | Un-reinforced candidates decay. A candidate is unproven; if the user never mentions it again for two weeks, the guess was wrong.                                                        |
| **Confirmed words never decay** | no TTL on `confirmed`          | A family member mentioned twice a year is a real memory; ephemeral personal facts must persist.                                                                                         |
| **User-scoped from day one**    | `user_id` on every row         | Personal AI = personal memory. Mixing users would be a data leak; the demo hardcodes `"default"` but the schema is per-user so multi-user is a config flag, not a rebuild.              |
| **Post-hoc rewrite** (not prompt-injection into the formatter) | | Deterministic, auditable, zero LLM cost/latency, testable byte-for-byte. Trade-off documented in *Limitations*.                                                            |

---

## Why a custom phonetic encoder?

Off-the-shelf phonetic algorithms (Soundex, Metaphone, Double Metaphone)
were designed for English surnames on 1960s-era hardware. They collapse
or drop features that matter here:

- **Vowel patterns in Indian names** (Aditya / Aaditya) -- Soundex
  discards vowels entirely.
- **The /v/-/w/ pair** (Kivi / Kiwi) -- classical algorithms don't
  treat these as interchangeable.
- **Long/short vowel distinctions** (paneer / panner) -- collapsed by
  most standard encoders.

The custom encoder is small enough to audit on one screen
(`app/phonetics.py`, ~120 lines), deterministic, and calibrated against
the evaluation fixtures. Its exact behaviour is *pinned* in
`ENCODING_REGRESSIONS`; any drift breaks a test on purpose.

The similarity metric is a **0.3 phonetic + 0.7 orthographic** blend.
The orthographic component keeps different names with similar sound
apart ("Aditi" is not "Aaditya"); the phonetic component catches
ASR-style respellings.

---

## Evaluation

`python3 -m evals.run_eval` runs a hermetic evaluation in four
independent sections so a strong number in one area can't hide a
weakness in another:

1. **20 hand-authored cases**, grouped positive / negative / boundary /
   lifecycle, with exact expected outputs and documented rationale.
   Failure preserves inputs, expected, actual, decisions, memory-state
   digest and the failure reason.
2. **50-sentence false-positive stress test** on ordinary English
   containing near-miss lookalikes ("Aditi", "kiwi fruit", "Arvind").
   After seeding, every intervention here is a production risk.
3. **Naive baseline comparison** -- same case suite run through a
   naive "rewrite whenever similarity >= threshold" matcher with none
   of the product decisions. Shows the delta the lifecycle, veto,
   context and suppression logic actually buy.
4. **Cost / performance / storage** -- latency percentiles (p50/p95/p99),
   DB growth curve at 1 / 10 / 50 / 200 observations, model usage
   (none), cost (zero).

Current headline result: **20/20 cases pass, 100% precision / recall /
F1, 0 false positives on 49 stress sentences, p50 latency ~2 ms.** The
naive baseline sits at ~79% F1 with 3 stress-test false positives on
the same seeded memory.

Full report: `evals/results.md` (human), `evals/results.json` (machine).

---

## HTTP API

All JSON. No auth (demo). See `app/server.py` for the tiny stdlib
implementation.

| Method | Path                   | Purpose                                                     |
|--------|------------------------|-------------------------------------------------------------|
| GET    | `/`                    | Demonstration UI                                            |
| GET    | `/api/health`          | Liveness + `user_id` + DB size                              |
| GET    | `/api/memory`          | Full inspectable memory state (`Store.snapshot()`)          |
| GET    | `/api/events?limit=N`  | Recent audit log entries                                    |
| POST   | `/api/observe`         | One observation (correction / confirm / edit / delete)      |
| POST   | `/api/observe/bulk`    | Many observations at once (JSONL body)                      |
| POST   | `/api/rewrite`         | `{formatted, asr?}` -> rewritten text + decisions           |
| POST   | `/api/suppress`        | Silence a word (never rewritten again, still logged)        |
| POST   | `/api/delete`          | Forget a word entirely                                      |
| POST   | `/api/sweep`           | Drop un-reinforced candidates older than TTL                |
| POST   | `/api/reset`           | Wipe memory (`{confirm: true}` required)                    |
| POST   | `/api/seed`            | Apply the canonical demo seed observations                  |

---

## Limitations (honest ones)

- **Single-word entities only.** "New York" would need span-level
  memory; today the engine matches token-by-token. The schema is not
  the blocker (a `word` row already carries display text with spaces
  is fine); the engine's tokeniser is.
- **English only.** The phonetic encoder is calibrated for
  English-alphabet inputs and Indian-name ASR patterns; Devanagari and
  other scripts would need their own encoder.
- **No cross-language transliteration reasoning.** The system won't
  know that "Aaditya" and "आदित्य" are the same person.
- **No LLM re-prompting.** By choice (see *Why post-hoc?*). A production
  version could route the pre-rewrite formatted text and the decisions
  to a small model that decides among "keep abstention", "apply rewrite",
  "propose a third option" -- gaining context sensitivity at the cost
  of the current auditability.
- **Suppression is per-word, not per-context.** If you silence "Kivi",
  it stays silent everywhere; you can't say "rewrite it in tech contexts
  only". A follow-up feature would filter suppression by learned
  templates.
- **Single-tenant demo.** The schema is per-user from day one, but the
  server hardcodes `user_id="default"` because it has no auth. Adding
  a request header or JWT is a one-file change.
- **No fuzzy tokeniser.** A user typing `@Aditya` with a stray tag
  character will still hit the word matcher via `strip`, but arbitrary
  glyph noise around a name is not currently handled.

## What I'd build next

- **Multi-word entity memory** (span rewriter).
- **A learned per-user threshold** based on their historical acceptance
  rate of borderline rewrites.
- **A tiny LLM re-prompt on abstentions**: when the engine is unsure,
  ask a model with the memory as context whether to intervene. Keep
  the deterministic path as fallback.
- **Context-scoped suppression** (silence "Kivi" in food contexts only).

---

## Repo layout

```
app/               engine, phonetics, store, server, seed, common words
db/migrations/     001_init, 002_user_scope, 003_candidate_lifecycle
db/schema.sql      composite reference (documentation only, not applied)
evals/             cases, stress corpus, run_eval, results.{md,json}
static/index.html  demonstration UI (visual diff + memory browser)
tests/             engine, phonetics, store, HTTP integration
docs/              design walkthrough PDF
```

---

## AI use in this build

I used an AI assistant (Claude) during development, in these ways:

- **Boilerplate and shape review** -- scaffolding files, cleaning
  duplication, catching an inconsistent function signature or a
  missing docstring.
- **Editorial pass on prose** -- README, RUN, module docstrings and
  the decision-rationale copy; the substantive design choices
  (post-hoc rewrite, real-word veto, `CONFIRM_MIN = 2`, per-form
  suppression, per-user schema from day one) are mine.
- **Test-case brainstorming** -- I authored the case *shapes* and
  their expected behaviour; the assistant helped stress-test my
  wording by suggesting edge cases I initially missed
  (`P7_multiple_taught_words_one_sentence`,
  `N5_replacement_is_common_word_rejected`,
  `B3_short_word_low_sim_no_rewrite`,
  `L5_delete_removes_intervention`).

Nothing was accepted without reading, thinking through the trade-offs
and running it against the eval. If a piece of code is in the repo, I
can explain why it's there.

---

## Running

See **[RUN.md](./RUN.md)**.
