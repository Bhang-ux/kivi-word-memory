# RUN.md -- Reviewer Instructions

**Primary review method: local Python web app.** Zero external
dependencies, zero API keys, offline. Ships with a browser UI at
`http://127.0.0.1:8000` and a full command-line evaluation.

Everything below follows the 10 items in section 5 of the assignment
brief.

---

### 1. Runtime

**Python >= 3.10** (uses PEP 604 `str | None` union syntax).

Check yours:
```bash
python3 --version
```

### 2. Environment / API keys

**None.** No `.env` values are required. `KIVI_PORT` and `KIVI_DB` are
optional overrides (defaults: 8000 and `db/kivi.db`).

### 3. Install

```bash
# No pip install required -- Python standard library only.
```

Optional convenience:
```bash
make install   # verifies python version, prints readiness
```

### 4. First-time setup (migrations + demo seed)

Applies all migrations and loads the demo seed observations:
```bash
python3 -m app.seed --reset
```

Expected output:
```
  [OK]     Aditya -> aaditya    [candidate] stored as candidate
  [OK]     Aditya -> aaditya    [confirmed] reinforced
  [OK]       Kiwi -> kivi       [confirmed] stored as confirmed
  [OK]     panner -> paneer     [confirmed] stored as confirmed
  [OK]      urzoo -> urzoo      [confirmed] stored as confirmed

Seeded 5 observations into .../db/kivi.db
```

### 5. Start the demo

```bash
python3 app/server.py
# or:  make serve
```

Log line will read:
```
Kivi word memory demo listening on http://127.0.0.1:8000
  db: .../db/kivi.db (user: default)
```

### 6. Open the UI

**<http://127.0.0.1:8000>** in any modern browser.

### 7. Primary interactions

The UI has three panels:

**Rewrite panel** (top-left). Type or paste a formatted sentence
(optionally with the ASR raw), press **"Rewrite with memory"**. The
memory-aware output renders inline with:
- Green highlights on **rewritten** spans (hover for the reason).
- Amber highlights on **considered-but-abstained** spans (hover for
  the reason).
Underneath is the full decision list with similarity and context scores.

Try:
- `Ask Aditya to review the Sarvam Kiwi service.` -> both nouns rewrite.
- `I like kiwi fruit in the morning.` -> `kiwi` stays (real-word veto).
- `The kiwi service is down.` -> `kiwi` rewrites to `Kivi` (context rescues).
- `Ask Aditi to review the service.` -> `Aditi` recorded as an abstention.

**Teach panel** (top-right). Fill in the fields for a correction /
confirm / edit / delete and press **"Teach Kivi"**. Also holds:
- **Bulk import (JSONL)** -- paste one observation per line.
- **Load demo seeds** -- (re)apply the canonical seeds.
- **Sweep stale candidates** -- run the TTL sweep.
- **Reset memory** -- wipe everything (with confirmation).

**Memory panel** (below). Every taught word with its status colour
band (green confirmed, amber candidate, red needs-review, grey
suppressed), sighting counts, forms, learned contexts, and per-word
Suppress / Forget buttons.

**Recent events** (bottom). Append-only audit log of every learn,
rewrite, suppress, delete, reset, sweep.

### 8. Run the evaluation

```bash
python3 -m evals.run_eval
# or:  make eval
```

Runtime: about 3-6 seconds (hermetic, offline, deterministic).

Prints a summary to stdout. Writes two files:
- `evals/results.md`   -- human-readable report
- `evals/results.json` -- full machine-readable output

### 9. Where the results live

- Console summary at the end of the run.
- `evals/results.md` -- summary, precision/recall/F1 with confusion
  matrix, latency percentiles, storage-growth curve, false-positive
  stress test with any hits printed, naive-baseline comparison, per-case
  detail with expected vs actual, decisions and memory-state digest.
- `evals/results.json` -- everything above, machine-readable.

### 10. Reset

**From the UI:** memory panel -> "Reset memory" (asks for confirmation).

**From the command line:**
```bash
rm -f db/kivi.db*
python3 -m app.seed --reset
# or:  make reset
```

---

## Test suite (optional)

Full test suite (engine, phonetics, store, HTTP server integration):
```bash
python3 -m unittest discover -s tests -v
# or:  make test
```

Current baseline: **41/41 tests passing** in ~1.5s.

## Makefile targets

```bash
make install   # verify python version
make seed      # migrate + load demo seeds (hermetic --reset)
make serve     # start the demo server
make test      # run the test suite
make eval      # run the evaluation
make reset     # wipe the demo DB and re-seed
make clean     # remove pycache and the demo DB
```

## Troubleshooting

- **Port 8000 in use.** `KIVI_PORT=9000 python3 app/server.py`
- **Fresh start.** `make reset`
- **Read the migrations.** `db/migrations/*.sql` -- three files, applied
  in order by `app/store.py::Store.migrate()`.
