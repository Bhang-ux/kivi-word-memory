"""Reproducible end-to-end evaluation for Kivi word memory.

Product claim under test
------------------------
    After ordinary teaching events, Kivi rewrites the user's words in
    new transcripts, and deliberately does nothing when its evidence is
    weak, wrong, or silenced.

The evaluation is structured into four independently reportable sections
so a strong number in one area can't hide a weakness in another:

  1. **Cases** -- 20 hand-authored cases with exact expected outputs and
     documented rationale. Groups: positive / negative / boundary /
     lifecycle. Every failure is preserved with inputs, expected, actual,
     decisions, memory-state digest and reason.

  2. **False-positive stress test** -- 50 sentences of ordinary English
     containing near-miss lookalikes ("Aditi", "kiwi fruit", "Arvind").
     After seeding, no sentence should trigger a rewrite. Any hit is a
     production risk and is printed with its reason.

  3. **Naive baseline comparison** -- the same case suite run through a
     naive matcher ("rewrite if any confirmed word has similarity >= T",
     no candidate lifecycle, no real-word veto, no context boost). Shows
     that the product decisions actually add value.

  4. **Cost / performance / storage** -- latency percentiles across every
     rewrite call; DB size after 1 / 10 / 50 / 200 observations; model
     usage (none) and cost (zero).

Run:  python3 -m evals.run_eval        # writes results.json + results.md
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from typing import Any

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP_DIR, "app"))
sys.path.insert(0, APP_DIR)

from engine import Engine, STRONG_INTERVENE_SIM  # noqa: E402
from phonetics import similarity  # noqa: E402
from seed import SEEDS  # noqa: E402
from store import Store  # noqa: E402

from evals.cases import CASES  # noqa: E402
from evals.stress_corpus import STRESS_CORPUS  # noqa: E402

RESULTS_DIR = os.path.join(APP_DIR, "evals")


# ==========================================================================
# Case runner
# ==========================================================================

@dataclass
class CaseResult:
    case_id: str
    group: str
    note: str
    inputs: dict[str, str]
    expected_text: str
    actual_text: str
    passed: bool
    expected_actions: dict[str, str]
    actual_actions: dict[str, str]
    decisions: list[dict[str, Any]]
    memory_state_digest: dict[str, Any]
    latency_ms: float
    db_bytes: int
    failure_reason: str = ""


def _digest(store: Store, keywords: tuple[str, ...]) -> dict[str, Any]:
    snap = store.snapshot()
    kw = tuple(k.lower() for k in keywords)
    words = [
        {
            "word": w["word"], "display": w["display"], "status": w["status"],
            "occurrences": w["occurrences"], "interventions": w["interventions"],
            "forms": [f["form"] for f in w["forms"]],
            "contexts": [c["context"] for c in w["contexts"]],
        }
        for w in snap["words"] if any(k in w["word"] for k in kw)
    ]
    return {"relevant_words": words, "total_events": len(store.events(limit=10_000))}


def _apply_setup(engine: Engine, store: Store, setup: list[dict[str, Any]]) -> None:
    for step in setup:
        if step.get("op") == "suppress":
            row = store.get_word(step["word"])
            if row is not None:
                engine.suppress(row["id"])
            continue
        engine.observe(**step)


def _run_cases(engine: Engine, store: Store) -> list[CaseResult]:
    # A prior refused attempt to teach "review -> the" -- exercises the
    # engine's refusal path so that N5 has real history behind it.
    engine.observe(kind="correction",
                   formatted="Please review the report.",
                   selection="review", replacement="the", weight=2)

    results: list[CaseResult] = []
    for case in CASES:
        _apply_setup(engine, store, case.setup)
        r = engine.rewrite(case.formatted, case.asr)
        actual_actions = {d.original: d.action for d in r.decisions}
        passed = r.text == case.expect_text and actual_actions == case.expect_actions
        failures = []
        if r.text != case.expect_text:
            failures.append(f"text {r.text!r} != {case.expect_text!r}")
        if actual_actions != case.expect_actions:
            failures.append(f"actions {actual_actions} != {case.expect_actions}")

        keywords = tuple(
            t.strip(".,!?;:") for t in case.formatted.split()
            if t.strip(".,!?;:").lower() not in ("the", "a", "an", "to", "of", "is")
        )
        results.append(CaseResult(
            case_id=case.id,
            group=case.group,
            note=case.note,
            inputs={"asr": case.asr, "formatted": case.formatted},
            expected_text=case.expect_text,
            actual_text=r.text,
            passed=passed,
            expected_actions=case.expect_actions,
            actual_actions=actual_actions,
            decisions=[asdict(d) for d in r.decisions],
            memory_state_digest=_digest(store, keywords),
            latency_ms=round(r.latency_ms, 3),
            db_bytes=r.db_bytes,
            failure_reason="; ".join(failures),
        ))
    return results


# ==========================================================================
# Confusion matrix
# ==========================================================================

def _confusion(results: list[CaseResult]) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    for r in results:
        exp_rewrite = {t for t, a in r.expected_actions.items() if a == "rewrite"}
        exp_abstain = {t for t, a in r.expected_actions.items() if a == "abstain"}
        act_rewrite = {t for t, a in r.actual_actions.items() if a == "rewrite"}
        act_abstain = {t for t, a in r.actual_actions.items() if a == "abstain"}

        tp += len(exp_rewrite & act_rewrite)
        fn += len(exp_rewrite - act_rewrite)
        fp += len(act_rewrite - exp_rewrite)
        tn += len(exp_abstain & act_abstain)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall    = tp / (tp + fn) if (tp + fn) else 1.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "true_positive": tp, "false_positive": fp,
        "false_negative": fn, "true_negative": tn,
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
    }


# ==========================================================================
# False-positive stress test
# ==========================================================================

def _run_stress(engine: Engine) -> dict[str, Any]:
    latencies: list[float] = []
    hits: list[dict[str, Any]] = []
    for sentence in STRESS_CORPUS:
        r = engine.rewrite(sentence)
        latencies.append(r.latency_ms)
        for d in r.decisions:
            if d.action == "rewrite":
                hits.append({
                    "sentence": sentence,
                    "original": d.original, "replacement": d.replacement,
                    "reason": d.reason,
                })
    return {
        "sentences": len(STRESS_CORPUS),
        "false_positive_rewrites": len(hits),
        "false_positive_rate": round(len(hits) / max(len(STRESS_CORPUS), 1), 4),
        "hits": hits,
        "latency": _latency_stats(latencies),
    }


# ==========================================================================
# Naive baseline
# ==========================================================================

class _NaiveBaseline:
    """No candidate lifecycle. No real-word veto. No context. No suppression.
    Every taught word rewrites any span with similarity >= threshold."""

    def __init__(self, store: Store, threshold: float = STRONG_INTERVENE_SIM):
        self.store = store
        self.threshold = threshold

    def rewrite(self, formatted: str) -> tuple[str, list[dict[str, Any]]]:
        import sqlite3
        with sqlite3.connect(self.store.path) as conn:
            words = conn.execute(
                "SELECT word, display FROM word WHERE user_id=?",
                (self.store.user_id,),
            ).fetchall()
        import re
        WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F']*")
        matches = list(WORD_RE.finditer(formatted))
        decisions: list[dict[str, Any]] = []
        out = formatted
        for m in reversed(matches):
            tok = m.group(0)
            low = tok.lower()
            best: tuple[float, str, str] | None = None
            for w, display in words:
                s = similarity(low, w)
                if s >= self.threshold and (best is None or s > best[0]):
                    best = (s, w, display or w)
            if best is None:
                continue
            s, w, display = best
            if w == low:
                continue
            out = out[:m.start()] + display + out[m.end():]
            decisions.append({"original": tok, "replacement": display,
                              "sim": round(s, 3)})
        return out, decisions


def _run_baseline(store: Store) -> dict[str, Any]:
    b = _NaiveBaseline(store)
    tp = fp = fn = 0
    per_case = []
    stress_hits = 0
    for c in CASES:
        text, decs = b.rewrite(c.formatted)
        actual = {d["original"]: "rewrite" for d in decs}
        exp_rewrite = {t for t, a in c.expect_actions.items() if a == "rewrite"}
        exp_abstain = {t for t, a in c.expect_actions.items() if a == "abstain"}
        act_rewrite = set(actual)
        tp += len(exp_rewrite & act_rewrite)
        fn += len(exp_rewrite - act_rewrite)
        fp += len((act_rewrite - exp_rewrite) | (act_rewrite & exp_abstain))
        per_case.append({
            "case_id": c.id,
            "passed": text == c.expect_text,
            "actual_text": text,
            "expected_text": c.expect_text,
        })
    for sentence in STRESS_CORPUS:
        _, decs = b.rewrite(sentence)
        stress_hits += len(decs)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall    = tp / (tp + fn) if (tp + fn) else 1.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "description": (
            "Naive baseline: rewrite whenever any taught word has similarity "
            f">= {STRONG_INTERVENE_SIM}. No candidate lifecycle, no real-word "
            "veto, no context boost, no needs_review, no suppression."
        ),
        "threshold": STRONG_INTERVENE_SIM,
        "true_positive": tp, "false_positive": fp, "false_negative": fn,
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
        "stress_false_positives": stress_hits,
        "per_case": per_case,
    }


# ==========================================================================
# Storage growth
# ==========================================================================

def _growth_curve() -> list[dict[str, int]]:
    curve = []
    for n in (1, 10, 50, 200):
        db = tempfile.NamedTemporaryFile(delete=False, suffix=".db").name
        try:
            s = Store(db)
            s.reset()
            e = Engine(s)
            for i in range(n):
                e.observe(
                    kind="correction",
                    asr=f"talk to synonym{i} today",
                    formatted=f"Talk to Synonym{i} today.",
                    selection=f"Synonym{i}",
                    replacement=f"Synonim{i}",
                    weight=2,
                )
            curve.append({"observations": n, "db_bytes": s.db_size_bytes()})
        finally:
            for suffix in ("", "-wal", "-shm"):
                p = db + suffix
                if os.path.exists(p):
                    os.remove(p)
    return curve


# ==========================================================================
# Latency stats
# ==========================================================================

def _latency_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "avg_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0,
                "p99_ms": 0.0, "max_ms": 0.0}
    xs = sorted(values)
    def pct(p: float) -> float:
        k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
        return xs[k]
    return {
        "count": len(xs),
        "avg_ms": round(statistics.fmean(xs), 3),
        "p50_ms": round(pct(50), 3),
        "p95_ms": round(pct(95), 3),
        "p99_ms": round(pct(99), 3),
        "max_ms": round(xs[-1], 3),
    }


# ==========================================================================
# Main
# ==========================================================================

def run() -> dict[str, Any]:
    eval_db = os.environ.get("KIVI_EVAL_DB",
                             os.path.join(tempfile.gettempdir(), "kivi_eval.db"))
    for suffix in ("", "-wal", "-shm"):
        p = eval_db + suffix
        if os.path.exists(p):
            os.remove(p)

    store = Store(eval_db)
    store.reset()
    engine = Engine(store)

    for s in SEEDS:
        engine.observe(**s)

    t0 = time.perf_counter()
    case_results = _run_cases(engine, store)
    case_wall_ms = (time.perf_counter() - t0) * 1000
    case_latencies = [r.latency_ms for r in case_results]
    confusion = _confusion(case_results)

    stress = _run_stress(engine)

    baseline_db = os.path.join(tempfile.gettempdir(), "kivi_baseline.db")
    for suffix in ("", "-wal", "-shm"):
        p = baseline_db + suffix
        if os.path.exists(p):
            os.remove(p)
    b_store = Store(baseline_db)
    b_store.reset()
    b_engine = Engine(b_store)
    for s in SEEDS:
        b_engine.observe(**s)
    baseline = _run_baseline(b_store)

    growth = _growth_curve()

    total = len(case_results)
    passed_n = sum(r.passed for r in case_results)
    useful = sum(
        1 for r in case_results
        if r.passed and any(a == "rewrite" for a in r.actual_actions.values())
    )
    incorrect = sum(
        1 for r in case_results
        if not r.passed and any(a == "rewrite" for a in r.actual_actions.values())
    )
    abstains = sum(
        1 for r in case_results
        if r.passed and r.group in ("negative", "lifecycle", "boundary")
        and not any(a == "rewrite" for a in r.actual_actions.values())
    )

    report = {
        "summary": {
            "product_claim": (
                "After ordinary teaching events, Kivi rewrites the user's "
                "words in new transcripts, and deliberately does nothing "
                "when its evidence is weak, wrong, or silenced."
            ),
            "total_cases": total,
            "passed": passed_n,
            "failed": total - passed_n,
            "pass_rate": round(passed_n / total, 4) if total else 0.0,
            "useful_interventions": useful,
            "unnecessary_or_incorrect_interventions": incorrect,
            "correct_deliberate_abstentions": abstains,
            "case_wall_ms": round(case_wall_ms, 3),
            "case_latency": _latency_stats(case_latencies),
            "db_bytes_after_eval": case_results[-1].db_bytes if case_results else 0,
            "model_usage": "none - phonetic matching is fully local; the memory layer makes no LLM calls",
            "cost": "0 API calls, 0 tokens, 0 external requests",
        },
        "metrics": confusion,
        "stress_test": stress,
        "baseline_comparison": baseline,
        "storage_growth": growth,
        "cases": [asdict(r) for r in case_results],
    }

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "results.json"), "w") as f:
        json.dump(report, f, indent=2)
    with open(os.path.join(RESULTS_DIR, "results.md"), "w") as f:
        f.write(_markdown(report))

    _print_summary(report)
    return report


def _print_summary(report: dict[str, Any]) -> None:
    s = report["summary"]
    m = report["metrics"]
    st = report["stress_test"]
    bl = report["baseline_comparison"]
    print(
        f"\nKivi word memory evaluation\n"
        f"  cases          {s['total_cases']} | passed {s['passed']} | failed {s['failed']} "
        f"| pass rate {s['pass_rate']:.1%}\n"
        f"  metrics        precision {m['precision']:.2%} | recall {m['recall']:.2%} "
        f"| F1 {m['f1']:.2%} (TP={m['true_positive']} FP={m['false_positive']} "
        f"FN={m['false_negative']} TN={m['true_negative']})\n"
        f"  stress test    {st['sentences']} sentences | "
        f"false positives {st['false_positive_rewrites']} "
        f"({st['false_positive_rate']:.1%})\n"
        f"  naive baseline precision {bl['precision']:.2%} | recall {bl['recall']:.2%} "
        f"| F1 {bl['f1']:.2%} | stress FPs {bl['stress_false_positives']}\n"
        f"  latency        p50 {s['case_latency']['p50_ms']} ms | "
        f"p95 {s['case_latency']['p95_ms']} ms | p99 {s['case_latency']['p99_ms']} ms\n"
        f"  storage        after eval {s['db_bytes_after_eval']:,} bytes | "
        f"growth {[g['observations'] for g in report['storage_growth']]} obs -> "
        f"{[g['db_bytes'] for g in report['storage_growth']]} bytes\n"
        f"  written to evals/results.json and evals/results.md"
    )


def _markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    m = report["metrics"]
    st = report["stress_test"]
    bl = report["baseline_comparison"]
    lines = [
        "# Kivi Word Memory -- Evaluation Results",
        "",
        "Reproducible run: `python3 -m evals.run_eval` (offline, deterministic).",
        "",
        f"**Product claim under test.** {s['product_claim']}",
        "",
        "## Summary",
        "",
        "| metric | value |",
        "|---|---|",
        f"| cases | {s['total_cases']} |",
        f"| passed | {s['passed']} |",
        f"| failed | {s['failed']} |",
        f"| pass rate | {s['pass_rate']:.1%} |",
        f"| useful interventions | {s['useful_interventions']} |",
        f"| unnecessary/incorrect interventions | {s['unnecessary_or_incorrect_interventions']} |",
        f"| deliberate abstentions | {s['correct_deliberate_abstentions']} |",
        f"| case-suite wall time | {s['case_wall_ms']} ms |",
        f"| db size after eval | {s['db_bytes_after_eval']:,} bytes |",
        f"| model usage | {s['model_usage']} |",
        f"| cost | {s['cost']} |",
        "",
        "## Precision / Recall (per-span confusion matrix)",
        "",
        f"- **Precision:** {m['precision']:.2%}",
        f"- **Recall:** {m['recall']:.2%}",
        f"- **F1:** {m['f1']:.2%}",
        "",
        "|  | predicted rewrite | predicted abstain |",
        "|---|---|---|",
        f"| expected rewrite | TP = {m['true_positive']} | FN = {m['false_negative']} |",
        f"| expected abstain | FP = {m['false_positive']} | TN = {m['true_negative']} |",
        "",
        "## Latency",
        "",
        "| p50 | p95 | p99 | max | avg |",
        "|---|---|---|---|---|",
        f"| {s['case_latency']['p50_ms']} ms | {s['case_latency']['p95_ms']} ms | "
        f"{s['case_latency']['p99_ms']} ms | {s['case_latency']['max_ms']} ms | "
        f"{s['case_latency']['avg_ms']} ms |",
        "",
        "## Storage growth",
        "",
        "| observations | db bytes |",
        "|---|---|",
    ]
    for g in report["storage_growth"]:
        lines.append(f"| {g['observations']} | {g['db_bytes']:,} |")

    lines += [
        "",
        "## False-positive stress test",
        "",
        f"- **Sentences:** {st['sentences']}",
        f"- **False positive rewrites:** {st['false_positive_rewrites']} "
        f"({st['false_positive_rate']:.1%})",
        f"- **Latency p50 / p95 / p99:** {st['latency']['p50_ms']} / "
        f"{st['latency']['p95_ms']} / {st['latency']['p99_ms']} ms",
    ]
    if st["hits"]:
        lines.append("")
        lines.append("### Hits (false positives)")
        for h in st["hits"]:
            lines.append(f"- `{h['sentence']}`  ")
            lines.append(f"  rewrote `{h['original']}` -> `{h['replacement']}` "
                         f"({h['reason']})")

    lines += [
        "",
        "## Naive baseline comparison",
        "",
        f"> {bl['description']}",
        "",
        "| system | precision | recall | F1 | stress FPs |",
        "|---|---|---|---|---|",
        f"| **Kivi engine** | {m['precision']:.2%} | {m['recall']:.2%} | "
        f"{m['f1']:.2%} | {st['false_positive_rewrites']} |",
        f"| naive baseline | {bl['precision']:.2%} | {bl['recall']:.2%} | "
        f"{bl['f1']:.2%} | {bl['stress_false_positives']} |",
        "",
        "The baseline achieves recall by rewriting aggressively; it fails "
        "on the negative and boundary cases where the product decisions "
        "(candidate lifecycle, real-word veto, context boost, needs_review, "
        "suppression) are exactly what prevent the wrong rewrites.",
        "",
        "## Cases",
        "",
    ]
    for c in report["cases"]:
        lines2 = [
            f"### [{'PASS' if c['passed'] else 'FAIL'}] {c['case_id']} ({c['group']})",
            "",
            f"> {c['note']}",
            "",
            f"- input (formatted): `{c['inputs']['formatted']}`",
        ]
        if c['inputs']['asr']:
            lines2.append(f"- input (asr): `{c['inputs']['asr']}`")
        lines2 += [
            f"- expected: `{c['expected_text']}`",
            f"- actual:   `{c['actual_text']}`",
            f"- expected actions: `{c['expected_actions']}`",
            f"- actual actions:   `{c['actual_actions']}`",
        ]
        if c["decisions"]:
            lines2.append("- decisions:")
            for d in c["decisions"]:
                lines2.append(
                    f"  - `{d['action']}` on `{d['original']}` -> "
                    f"`{d['replacement']}` (sim {d['similarity']}, "
                    f"ctx {d['context_support']}) -- {d['reason']}"
                )
        lines2 += [
            f"- relevant memory: `{json.dumps(c['memory_state_digest'])}`",
            f"- latency: {c['latency_ms']} ms",
        ]
        if not c["passed"]:
            lines2 += [f"- **FAILURE:** {c['failure_reason']}"]
        lines2.append("")
        lines.extend(lines2)
    return "\n".join(lines)


if __name__ == "__main__":
    run()
