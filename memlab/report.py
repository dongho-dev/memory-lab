"""Compare every evaluated run in one table.

    python -m memlab.report results

Reads results/*/summary.json and writes results/REPORT.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .data import CATEGORIES, SHORT
from .io import read_json
from .io import utf8_stdout


def _pct(x) -> str:
    return "–" if x is None else f"{100 * x:.0f}"


def build_report(results_dir: str | Path) -> str:
    results_dir = Path(results_dir)
    summaries = [read_json(p) for p in sorted(results_dir.glob("*/summary.json"))]
    summaries.sort(key=lambda s: (s["accuracy"] is None, -(s["accuracy"] or 0)))
    cats = [c for c in CATEGORIES if any(c in s["per_category"] for s in summaries)]
    head = ["run", "model", "data", "n", "acc %", "task-avg %"] + [SHORT[c] for c in cats] + [
        "in tok/q", "ingest tok/q", "evidence recall %", "answer-turn recall %", "steps/q", "answer $"]
    lines = ["# Results", "",
             "acc = share of questions judged correct; task-avg = mean over categories; "
             "evidence recall = share of evidence sessions the memory surfaced; "
             "answer-turn recall = share of the turns that hold the answer that reached the model "
             "(stricter: a session can be found while the turn that matters is left out). "
             "steps/q = search/read/answer turns for agentic systems.", "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for s in summaries:
        row = [s["name"], s.get("model", "?"), s["data"], str(s["n"]), _pct(s["accuracy"]), _pct(s["task_averaged_accuracy"])]
        row += [_pct(s["per_category"].get(c, {}).get("accuracy")) for c in cats]
        row += [f"{s['avg_input_tokens']:,.0f}", f"{s.get('avg_ingest_tokens', 0):,.0f}",
                _pct(s["evidence_recall"]), _pct(s.get("answer_turn_recall")),
                "–" if s.get("avg_steps") is None else f"{s['avg_steps']:.1f}",
                "–" if s["answer_cost_usd"] is None else f"{s['answer_cost_usd']:.2f}"]
        lines.append("| " + " | ".join(row) + " |")
    if not summaries:
        lines.append("_No evaluated runs yet._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir", nargs="?", default="results")
    args = ap.parse_args(argv)
    text = build_report(args.results_dir)
    out = Path(args.results_dir) / "REPORT.md"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
