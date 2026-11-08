"""Measure how well a question parser maps questions to the right intent and params.

    python eval/run_parser_eval.py --parser llm
    python eval/run_parser_eval.py --parser embedding
    python eval/run_parser_eval.py --parser hybrid

Prints the summary and writes one row per question to eval/results/.
Params are compared by MEANING: "October" and "in october" are the same
because both resolve to the same date range.
"""
import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from securebank.intents.catalog import INTENTS, InvalidParams, validate_params  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = EVAL_DIR / "dev_questions.csv"


def normalize(intent: str, params: dict):
    """Resolve params to what the query would actually use."""
    try:
        clean, period = validate_params(INTENTS[intent], params)
    except InvalidParams as exc:
        return f"invalid: {exc}"
    clean.pop("period", None)
    if period:
        clean["date_range"] = (period.start.isoformat(), period.end.isoformat())
    return clean


def load_questions(path: Path = DEFAULT_QUESTIONS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [{"question": r["question"], "intent": r["intent"], "params": json.loads(r["params"])}
                for r in csv.DictReader(f)]


def evaluate(parser, questions: list[dict]) -> tuple[dict, list[dict]]:
    rows = []
    for q in questions:
        outcome = parser.parse(q["question"])
        got_intent = outcome.request.intent if outcome.request else None
        got_params = outcome.request.params if outcome.request else {}
        intent_ok = got_intent == q["intent"]
        params_ok = intent_ok and normalize(got_intent, got_params) == normalize(q["intent"], q["params"])
        rows.append({
            "question": q["question"], "expected_intent": q["intent"], "got_intent": got_intent,
            "expected_params": json.dumps(q["params"]), "got_params": json.dumps(got_params),
            "intent_ok": intent_ok, "exact_ok": params_ok, "source": outcome.source,
            "attempts": outcome.attempts, "latency_ms": outcome.latency_ms,
            "parse_failed": outcome.request is None, "raw": outcome.raw,
        })
    n = len(rows)
    latencies = sorted(r["latency_ms"] for r in rows)
    summary = {
        "questions": n,
        "intent_accuracy": sum(r["intent_ok"] for r in rows) / n,
        "exact_match_accuracy": sum(r["exact_ok"] for r in rows) / n,
        "parse_failure_rate": sum(r["parse_failed"] for r in rows) / n,
        "fallback_rate": sum(r["source"] == "embedding_fallback" for r in rows) / n,
        "retry_rate": sum(r["attempts"] > 1 for r in rows) / n,
        "median_latency_ms": statistics.median(latencies),
        "p95_latency_ms": latencies[min(n - 1, int(0.95 * n))],
        # security-relevant: restricted questions that were NOT labelled restricted/out_of_scope
        "restricted_missed": sum(1 for r in rows if r["expected_intent"] == "restricted_request"
                                 and r["got_intent"] not in ("restricted_request", "out_of_scope")),
    }
    return summary, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parser", default="llm", choices=["llm", "embedding", "hybrid"])
    ap.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    args = ap.parse_args()

    from securebank.intents.parser import build_parser
    print(f"Loading the {args.parser} parser...")
    parser = build_parser(args.parser)
    questions = load_questions(args.questions)
    print(f"Evaluating {len(questions)} questions...")
    t0 = time.time()
    summary, rows = evaluate(parser, questions)

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_csv = out_dir / f"parser_{args.parser}_{stamp}.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / f"parser_{args.parser}_{stamp}_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nDone in {time.time() - t0:.0f} s. Results: {out_csv}\n")
    for key, value in summary.items():
        print(f"  {key:<22} {value:.1%}" if isinstance(value, float) and key.endswith(("accuracy", "rate"))
              else f"  {key:<22} {value}")
    misses = [r for r in rows if not r["exact_ok"]]
    if misses:
        print(f"\nMisses ({len(misses)}):")
        for r in misses:
            print(f"  - {r['question']!r}\n      expected {r['expected_intent']} {r['expected_params']}"
                  f"\n      got      {r['got_intent']} {r['got_params']}")


if __name__ == "__main__":
    main()
