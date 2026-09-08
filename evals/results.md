# Kivi Word Memory -- Evaluation Results

Reproducible run: `python3 -m evals.run_eval` (offline, deterministic).

**Product claim under test.** After ordinary teaching events, Kivi rewrites the user's words in new transcripts, and deliberately does nothing when its evidence is weak, wrong, or silenced.

## Summary

| metric | value |
|---|---|
| cases | 20 |
| passed | 20 |
| failed | 0 |
| pass rate | 100.0% |
| useful interventions | 9 |
| unnecessary/incorrect interventions | 0 |
| deliberate abstentions | 11 |
| case-suite wall time | 96.716 ms |
| db size after eval | 394,808 bytes |
| model usage | none - phonetic matching is fully local; the memory layer makes no LLM calls |
| cost | 0 API calls, 0 tokens, 0 external requests |

## Precision / Recall (per-span confusion matrix)

- **Precision:** 100.00%
- **Recall:** 100.00%
- **F1:** 100.00%

|  | predicted rewrite | predicted abstain |
|---|---|---|
| expected rewrite | TP = 14 | FN = 0 |
| expected abstain | FP = 0 | TN = 4 |

## Latency

| p50 | p95 | p99 | max | avg |
|---|---|---|---|---|
| 2.116 ms | 4.999 ms | 5.118 ms | 5.118 ms | 2.593 ms |

## Storage growth

| observations | db bytes |
|---|---|
| 1 | 94,208 |
| 10 | 102,400 |
| 50 | 180,224 |
| 200 | 507,904 |

## False-positive stress test

- **Sentences:** 49
- **False positive rewrites:** 0 (0.0%)
- **Latency p50 / p95 / p99:** 1.33 / 1.669 / 2.226 ms

## Naive baseline comparison

> Naive baseline: rewrite whenever any taught word has similarity >= 0.72. No candidate lifecycle, no real-word veto, no context boost, no needs_review, no suppression.

| system | precision | recall | F1 | stress FPs |
|---|---|---|---|---|
| **Kivi engine** | 100.00% | 100.00% | 100.00% | 0 |
| naive baseline | 78.57% | 78.57% | 78.57% | 3 |

The baseline achieves recall by rewriting aggressively; it fails on the negative and boundary cases where the product decisions (candidate lifecycle, real-word veto, context boost, needs_review, suppression) are exactly what prevent the wrong rewrites.

## Cases

### [PASS] P1_brief_example (positive)

> The exact example from the brief, after teaching both words.

- input (formatted): `Ask Aditya to review the Sarvam Kiwi service.`
- input (asr): `ask aditya to review the sarvam kiwi service`
- expected: `Ask Aaditya to review the Sarvam Kivi service.`
- actual:   `Ask Aaditya to review the Sarvam Kivi service.`
- expected actions: `{'Aditya': 'rewrite', 'Kiwi': 'rewrite'}`
- actual actions:   `{'Kiwi': 'rewrite', 'Aditya': 'rewrite'}`
- decisions:
  - `rewrite` on `Kiwi` -> `Kivi` (sim 0.825, ctx 0.15) -- phonetic match to confirmed word 'kivi' (sim 0.82, context +0.15)
  - `rewrite` on `Aditya` -> `Aaditya` (sim 0.8999999999999999, ctx 0.05) -- phonetic match to confirmed word 'aaditya' (sim 0.90, context +0.05)
- relevant memory: `{"relevant_words": [{"word": "aaditya", "display": "Aaditya", "status": "confirmed", "occurrences": 2, "interventions": 1, "forms": ["aaditya", "aditya"], "contexts": ["deploy", "ping <word>", "sarvam", "slack"]}], "total_events": 7}`
- latency: 4.999 ms

### [PASS] P2_new_sentence_same_words (positive)

> Memory must generalise beyond the sentence it was taught in.

- input (formatted): `Ping Aditya about the Sarvam Kiwi launch.`
- expected: `Ping Aaditya about the Sarvam Kivi launch.`
- actual:   `Ping Aaditya about the Sarvam Kivi launch.`
- expected actions: `{'Aditya': 'rewrite', 'Kiwi': 'rewrite'}`
- actual actions:   `{'Kiwi': 'rewrite', 'Aditya': 'rewrite'}`
- decisions:
  - `rewrite` on `Kiwi` -> `Kivi` (sim 0.825, ctx 0.1) -- phonetic match to confirmed word 'kivi' (sim 0.82, context +0.10)
  - `rewrite` on `Aditya` -> `Aaditya` (sim 0.8999999999999999, ctx 0.05) -- phonetic match to confirmed word 'aaditya' (sim 0.90, context +0.05)
- relevant memory: `{"relevant_words": [{"word": "aaditya", "display": "Aaditya", "status": "confirmed", "occurrences": 2, "interventions": 2, "forms": ["aaditya", "aditya"], "contexts": ["deploy", "ping <word>", "sarvam", "slack"]}], "total_events": 7}`
- latency: 3.982 ms

### [PASS] P3_lowercase_input (positive)

> Proper nouns take their taught Title form regardless of the input's case; taught companion words supply context for kiwi.

- input (formatted): `can you ask aditya to join the kiwi call`
- expected: `can you ask Aaditya to join the Kivi call`
- actual:   `can you ask Aaditya to join the Kivi call`
- expected actions: `{'aditya': 'rewrite', 'kiwi': 'rewrite'}`
- actual actions:   `{'kiwi': 'rewrite', 'aditya': 'rewrite'}`
- decisions:
  - `rewrite` on `kiwi` -> `Kivi` (sim 0.825, ctx 0.05) -- phonetic match to confirmed word 'kivi' (sim 0.82, context +0.05)
  - `rewrite` on `aditya` -> `Aaditya` (sim 0.8999999999999999, ctx 0.0) -- phonetic match to confirmed word 'aaditya' (sim 0.90, context +0.00)
- relevant memory: `{"relevant_words": [{"word": "aaditya", "display": "Aaditya", "status": "confirmed", "occurrences": 2, "interventions": 3, "forms": ["aaditya", "aditya"], "contexts": ["deploy", "ping <word>", "sarvam", "slack"]}], "total_events": 7}`
- latency: 4.108 ms

### [PASS] P4_paneer_variant (positive)

> Food romanisation learned from a grocery correction; generalises to a work-lunch context.

- input (formatted): `Order more panner for the team lunch.`
- expected: `Order more paneer for the team lunch.`
- actual:   `Order more paneer for the team lunch.`
- expected actions: `{'panner': 'rewrite'}`
- actual actions:   `{'panner': 'rewrite'}`
- decisions:
  - `rewrite` on `panner` -> `paneer` (sim 0.8833333333333333, ctx 0.0) -- phonetic match to confirmed word 'paneer' (sim 0.88, context +0.00)
- relevant memory: `{"relevant_words": [], "total_events": 7}`
- latency: 3.084 ms

### [PASS] P5_caps_input (positive)

> Proper nouns normalise to the taught Title form; the engine does not mirror SHOUTING because names are Title case in prose.

- input (formatted): `Review the ADITYA migration before Friday.`
- expected: `Review the Aaditya migration before Friday.`
- actual:   `Review the Aaditya migration before Friday.`
- expected actions: `{'ADITYA': 'rewrite'}`
- actual actions:   `{'ADITYA': 'rewrite'}`
- decisions:
  - `rewrite` on `ADITYA` -> `Aaditya` (sim 0.8999999999999999, ctx 0.0) -- phonetic match to confirmed word 'aaditya' (sim 0.90, context +0.00)
- relevant memory: `{"relevant_words": [{"word": "aaditya", "display": "Aaditya", "status": "confirmed", "occurrences": 2, "interventions": 4, "forms": ["aaditya", "aditya"], "contexts": ["deploy", "ping <word>", "sarvam", "slack"]}], "total_events": 7}`
- latency: 2.891 ms

### [PASS] P6_casing_preference (positive)

> The user taught exact casing (UrZoo); even lowercase input is rewritten to the taught display form (not flattened).

- input (formatted): `Email the urzoo team about pricing.`
- expected: `Email the UrZoo team about pricing.`
- actual:   `Email the UrZoo team about pricing.`
- expected actions: `{'urzoo': 'rewrite'}`
- actual actions:   `{'urzoo': 'rewrite'}`
- decisions:
  - `rewrite` on `urzoo` -> `UrZoo` (sim 1.0, ctx 0.0) -- phonetic match to confirmed word 'urzoo' (sim 1.00, context +0.00)
- relevant memory: `{"relevant_words": [{"word": "urzoo", "display": "UrZoo", "status": "confirmed", "occurrences": 1, "interventions": 1, "forms": ["urzoo"], "contexts": ["com", "dot", "veena"]}], "total_events": 7}`
- latency: 2.844 ms

### [PASS] P7_multiple_taught_words_one_sentence (positive)

> Three independent memories co-fire in one sentence without interfering with each other's spans (right-to-left scan).

- input (formatted): `Ping Aditya, tell UrZoo, and send Kiwi a note.`
- expected: `Ping Aaditya, tell UrZoo, and send Kivi a note.`
- actual:   `Ping Aaditya, tell UrZoo, and send Kivi a note.`
- expected actions: `{'Aditya': 'rewrite', 'UrZoo': 'rewrite', 'Kiwi': 'rewrite'}`
- actual actions:   `{'Kiwi': 'rewrite', 'UrZoo': 'rewrite', 'Aditya': 'rewrite'}`
- decisions:
  - `rewrite` on `Kiwi` -> `Kivi` (sim 0.825, ctx 0.05) -- phonetic match to confirmed word 'kivi' (sim 0.82, context +0.05)
  - `rewrite` on `UrZoo` -> `UrZoo` (sim 1.0, ctx 0.0) -- phonetic match to confirmed word 'urzoo' (sim 1.00, context +0.00)
  - `rewrite` on `Aditya` -> `Aaditya` (sim 0.8999999999999999, ctx 0.0) -- phonetic match to confirmed word 'aaditya' (sim 0.90, context +0.00)
- relevant memory: `{"relevant_words": [{"word": "aaditya", "display": "Aaditya", "status": "confirmed", "occurrences": 2, "interventions": 5, "forms": ["aaditya", "aditya"], "contexts": ["deploy", "ping <word>", "sarvam", "slack"]}, {"word": "urzoo", "display": "UrZoo", "status": "confirmed", "occurrences": 1, "interventions": 2, "forms": ["urzoo"], "contexts": ["com", "dot", "veena"]}], "total_events": 7}`
- latency: 5.118 ms

### [PASS] N1_unrelated_text (negative)

> Ordinary English passes through untouched -- no spans resembled any confirmed memory.

- input (formatted): `The quick brown fox jumps over the lazy dog.`
- expected: `The quick brown fox jumps over the lazy dog.`
- actual:   `The quick brown fox jumps over the lazy dog.`
- expected actions: `{}`
- actual actions:   `{}`
- relevant memory: `{"relevant_words": [], "total_events": 7}`
- latency: 2.116 ms

### [PASS] N2_similar_but_not_taught_name (negative)

> 'Aditi' resembles 'Aaditya' (sim 0.70) but is a different name; below the strong threshold and no context support, so the engine records an abstention instead of guessing.

- input (formatted): `Ask Aditi to review the service.`
- expected: `Ask Aditi to review the service.`
- actual:   `Ask Aditi to review the service.`
- expected actions: `{'Aditi': 'abstain'}`
- actual actions:   `{'Aditi': 'abstain'}`
- decisions:
  - `abstain` on `Aditi` -> `aaditya` (sim 0.7, ctx 0.0) -- similarity 0.70 below strong threshold 0.72 and context support 0.00 insufficient
- relevant memory: `{"relevant_words": [], "total_events": 7}`
- latency: 1.917 ms

### [PASS] N3_common_word_homophone_risk (negative)

> 'kiwi' here IS the fruit. Rewriting a dictionary word requires supporting context; none appears, so it abstains.

- input (formatted): `I like kiwi fruit in the morning.`
- input (asr): `i like kiwi fruit in the morning`
- expected: `I like kiwi fruit in the morning.`
- actual:   `I like kiwi fruit in the morning.`
- expected actions: `{'kiwi': 'abstain'}`
- actual actions:   `{'kiwi': 'abstain'}`
- decisions:
  - `abstain` on `kiwi` -> `kivi` (sim 0.825, ctx 0.0) -- real-word risk: 'kiwi' is a common word; rewriting to 'kivi' requires supporting context, which is absent
- relevant memory: `{"relevant_words": [{"word": "aaditya", "display": "Aaditya", "status": "confirmed", "occurrences": 2, "interventions": 5, "forms": ["aaditya", "aditya"], "contexts": ["deploy", "ping <word>", "sarvam", "slack"]}, {"word": "kivi", "display": "Kivi", "status": "confirmed", "occurrences": 1, "interventions": 4, "forms": ["kivi", "kiwi"], "contexts": ["<word> service", "aditya", "sarvam"]}], "total_events": 7}`
- latency: 1.751 ms

### [PASS] N4_candidate_not_yet_confirmed (negative)

> Runs against a candidate-only word; candidates never rewrite.

- input (formatted): `Ship the flurbo widget to production.`
- expected: `Ship the flurbo widget to production.`
- actual:   `Ship the flurbo widget to production.`
- expected actions: `{}`
- actual actions:   `{}`
- relevant memory: `{"relevant_words": [{"word": "flurbo", "display": "flurbo", "status": "candidate", "occurrences": 1, "interventions": 0, "forms": ["flurbo"], "contexts": []}], "total_events": 8}`
- latency: 1.996 ms

### [PASS] N5_replacement_is_common_word_rejected (negative)

> A prior correction attempt tried to teach 'review' -> 'the' and was refused at learn time; nothing in memory means nothing happens here either.

- input (formatted): `Please review the report.`
- expected: `Please review the report.`
- actual:   `Please review the report.`
- expected actions: `{}`
- actual actions:   `{}`
- relevant memory: `{"relevant_words": [], "total_events": 8}`
- latency: 1.766 ms

### [PASS] B1_kiwi_with_service_context (boundary)

> Product-sense context (stored template '<word> service') pushes the match over the intervention threshold.

- input (formatted): `The kiwi service is down.`
- expected: `The Kivi service is down.`
- actual:   `The Kivi service is down.`
- expected actions: `{'kiwi': 'rewrite'}`
- actual actions:   `{'kiwi': 'rewrite'}`
- decisions:
  - `rewrite` on `kiwi` -> `Kivi` (sim 0.825, ctx 0.1) -- phonetic match to confirmed word 'kivi' (sim 0.82, context +0.10)
- relevant memory: `{"relevant_words": [], "total_events": 8}`
- latency: 2.546 ms

### [PASS] B2_already_canonical (boundary)

> Already-canonical spelling is left alone (no churn).

- input (formatted): `Buy paneer at the market.`
- expected: `Buy paneer at the market.`
- actual:   `Buy paneer at the market.`
- expected actions: `{}`
- actual actions:   `{}`
- relevant memory: `{"relevant_words": [{"word": "paneer", "display": "paneer", "status": "confirmed", "occurrences": 1, "interventions": 1, "forms": ["paneer", "panner"], "contexts": ["add", "grocery", "list"]}], "total_events": 8}`
- latency: 1.684 ms

### [PASS] B3_short_word_low_sim_no_rewrite (boundary)

> Very short words never cross the similarity threshold to any taught word; the abstention isn't even recorded because no candidate match existed.

- input (formatted): `The ok signal was clear.`
- expected: `The ok signal was clear.`
- actual:   `The ok signal was clear.`
- expected actions: `{}`
- actual actions:   `{}`
- relevant memory: `{"relevant_words": [], "total_events": 8}`
- latency: 1.655 ms

### [PASS] L1_candidate_never_rewrites (lifecycle)

> First sighting of Mehta->Mayhta is only a candidate (weight 1): it must not rewrite yet.

- input (formatted): `Email Ananya about the Mehta invoice.`
- expected: `Email Ananya about the Mehta invoice.`
- actual:   `Email Ananya about the Mehta invoice.`
- expected actions: `{}`
- actual actions:   `{}`
- relevant memory: `{"relevant_words": [], "total_events": 9}`
- latency: 2.026 ms

### [PASS] L2_confirmed_rewrites (lifecycle)

> After a confirming second sighting, the word rewrites new sentences.

- input (formatted): `Email Ananya about the Mehta invoice again.`
- expected: `Email Ananya about the Mayhta invoice again.`
- actual:   `Email Ananya about the Mayhta invoice again.`
- expected actions: `{'Mehta': 'rewrite'}`
- actual actions:   `{'Mehta': 'rewrite'}`
- decisions:
  - `rewrite` on `Mehta` -> `Mayhta` (sim 0.7666666666666666, ctx 0.1) -- phonetic match to confirmed word 'mayhta' (sim 0.77, context +0.10)
- relevant memory: `{"relevant_words": [], "total_events": 11}`
- latency: 3.073 ms

### [PASS] L3_user_override_pauses (lifecycle)

> The user re-edited our rewrite to a third spelling; the word is flagged needs_review and rewrites pause for it and all its forms until re-taught.

- input (formatted): `File the Mehta report under M.`
- expected: `File the Mehta report under M.`
- actual:   `File the Mehta report under M.`
- expected actions: `{'Mehta': 'abstain'}`
- actual actions:   `{'Mehta': 'abstain'}`
- decisions:
  - `abstain` on `Mehta` -> `None` (sim None, ctx None) -- word is flagged needs_review after user override; rewriting paused
- relevant memory: `{"relevant_words": [{"word": "mayhta", "display": "Mayhta", "status": "needs_review", "occurrences": 2, "interventions": 1, "forms": ["mayhta", "mehta"], "contexts": ["ananya", "call <word>", "invoice"]}], "total_events": 12}`
- latency: 1.555 ms

### [PASS] L4_suppressed_word_never_rewritten (lifecycle)

> After suppressing 'kivi' from the memory UI, the word (and its forms) is never rewritten again; the abstention is still logged for inspectability.

- input (formatted): `The Kiwi launch went well.`
- expected: `The Kiwi launch went well.`
- actual:   `The Kiwi launch went well.`
- expected actions: `{'Kiwi': 'abstain'}`
- actual actions:   `{'Kiwi': 'abstain'}`
- decisions:
  - `abstain` on `Kiwi` -> `None` (sim None, ctx None) -- word is suppressed by user; never rewritten
- relevant memory: `{"relevant_words": [], "total_events": 14}`
- latency: 1.233 ms

### [PASS] L5_delete_removes_intervention (lifecycle)

> After forgetting 'paneer' entirely, 'panner' is no longer recognised as anything the system knows -- the engine has nothing to abstain about.

- input (formatted): `Order more panner for the potluck.`
- expected: `Order more panner for the potluck.`
- actual:   `Order more panner for the potluck.`
- expected actions: `{}`
- actual actions:   `{}`
- relevant memory: `{"relevant_words": [], "total_events": 15}`
- latency: 1.523 ms
