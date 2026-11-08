"""Compare the latest full evaluation of each parser (days 10-11).

    python eval/compare_runs.py

Reads every eval/results/full_*/summary.json (oldest first), prints a table (paste it into the report) and saves
eval/results/comparison.png and comparison.md.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_full_eval import GRID, INK, MUTED, SERIES, _style  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def latest_runs(results_dir: Path = RESULTS) -> list[dict]:
    """Every full run, oldest first (so 'before' and 'after' a change both show)."""
    runs = []
    for path in results_dir.glob("full_*/summary.json"):
        summary = json.loads(path.read_text())
        summary.setdefault("question_set", "test")
        summary["config"] = (f"{summary['parser']}, {summary['question_set']} set, "
                             f"{summary['created'][5:16].replace('T', ' ')}")
        runs.append(summary)
    return sorted(runs, key=lambda s: s["created"])


def table(runs: list[dict]) -> str:
    header = ("| Configuration | Intent acc. | Exact acc. | Restricted missed | Leaks | Wrong-role answers "
              "| Answered instead of refused | Median request (ms) |")
    lines = [header, "|" + "---|" * 8]
    for r in runs:
        p, s = r["parser_accuracy"], r["security"]
        lines.append(f"| {r['config']} | {p['intent_accuracy']:.1%} | {p['exact_match_accuracy']:.1%} "
                     f"| {p['restricted_missed']} | {s['leaks']} | {s['wrong_role_answers']} "
                     f"| {s['answered_instead_of_refused']} | {s['median_request_ms']} |")
    return "\n".join(lines)


def chart(runs: list[dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels = [r["config"].replace(", ", "\n", 1) for r in runs]
    metrics = [("Intent accuracy", "intent_accuracy"), ("Exact match", "exact_match_accuracy")]
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    width = 0.34
    for i, (name, key) in enumerate(metrics):
        values = [r["parser_accuracy"][key] * 100 for r in runs]
        xs = [x + (i - 0.5) * (width + 0.02) for x in range(len(runs))]
        ax.bar(xs, values, width=width, color=SERIES[i], label=name)
        for x, v in zip(xs, values):
            ax.text(x, v + 1.5, f"{v:.0f}%", ha="center", fontsize=8, color=MUTED)
    ax.set_xticks(range(len(runs)), labels)
    ax.set_ylim(0, 115)
    ax.set_ylabel("%", color=MUTED, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, ncols=2, loc="upper center", bbox_to_anchor=(0.5, -0.1),
              labelcolor=INK)
    _style(ax, "Parser accuracy per evaluation run")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    runs = latest_runs()
    if not runs:
        sys.exit("No runs yet. First run: python eval/run_full_eval.py --parser embedding")
    text = table(runs)
    print(text)
    (RESULTS / "comparison.md").write_text(text + "\n")
    chart(runs, RESULTS / "comparison.png")
    print(f"\nSaved {RESULTS / 'comparison.md'} and {RESULTS / 'comparison.png'}")


if __name__ == "__main__":
    main()
