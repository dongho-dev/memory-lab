"""Read the step-by-step traces of an agentic run: what the model searched, why, and what it got.

    python -m memlab.trace results/<run>                 # summary over all questions
    python -m memlab.trace results/<run> --show all      # every question, step by step
    python -m memlab.trace results/<run> --show wrong    # only questions graded wrong
    python -m memlab.trace results/<run> --show <question_id> [<question_id> ...]

In the step view, '*' marks a result that contains a turn holding the answer and '+' a result
from an evidence session without that turn. The REASON lines are the model's own account.
"""
from __future__ import annotations

import argparse
import statistics as st
from collections import Counter
from pathlib import Path

from .io import read_jsonl, utf8_stdout


def _mark(r: dict) -> str:
    return "*" if r.get("has_answer_turn") else ("+" if r.get("evidence_session") else " ")


def _step_mark(s: dict) -> str:
    """Step-level mark for agentic_files, where a whole tool output is one result."""
    if "has_answer_turn" not in s:
        return ""
    return "* " if s["has_answer_turn"] else ("+ " if s.get("evidence_session") else "  ")


def _saw_answer(s: dict) -> bool:
    return bool(s.get("has_answer_turn")) or any(r.get("has_answer_turn") for r in s.get("results", []))


def show(t: dict, label: bool | None) -> None:
    verdict = {True: "correct", False: "WRONG", None: "not graded"}[label]
    print(f"\n=== {t['question_id']} · {verdict}")
    print(f"Q: {t['question']}\ngold: {t['answer']}\nanswer: {t['hypothesis'][:300]}")
    for s in t["steps"]:
        act = s.get("action", "?")
        arg = f" {s['arg']!r}"[:200] if s.get("arg") and act != "answer" else ""
        cost = f"  ({s.get('in_tokens', 0):,} in / {s.get('sec', 0)}s)" if "in_tokens" in s else ""
        print(f"  #{s['step']} {_step_mark(s)}{act}{arg}{cost}")
        if s.get("reason"):
            print(f"     why: {s['reason'][:300]}")
        if s.get("result_excerpt") is not None and act != "answer":
            print(f"     got {s.get('result_chars', 0):,} chars: {s['result_excerpt'][:160]!r}")
        for r in s.get("results", []):
            extra = f" score {r['score']}" if "score" in r else ("" if r.get("found", True) else " NOT FOUND")
            print(f"     {_mark(r)} {r['session_id']} {r.get('date', '')[:10]}{extra}")
        for o in s.get("outside", []):
            print(f"     !! OUTSIDE: {o}")
        if s.get("note"):
            print(f"     note: {s['note']}")
        if act == "format_error":
            print(f"     raw: {s.get('raw', '')[:200]!r}")


def summary(traces: list[dict], labels: dict) -> None:
    n = len(traces)
    steps = [len(t["steps"]) for t in traces]
    acts = Counter(s.get("action") for t in traces for s in t["steps"])
    found_at, found = [], 0
    for t in traces:
        hit = next((s["step"] for s in t["steps"] if _saw_answer(s)), None)
        if hit:
            found += 1
            found_at.append(hit)
    print(f"{n} questions · steps per question: mean {st.mean(steps):.1f}, max {max(steps)}")
    print("actions: " + ", ".join(f"{k} {v}" for k, v in acts.most_common()))
    print(f"an answer turn was shown to the model in {found}/{n} questions"
          + (f" (first at step {st.median(found_at):.0f} on median)" if found_at else ""))
    out = [t["question_id"] for t in traces if any(s.get("outside") for s in t["steps"])]
    print(f"reached outside its folder (check by hand, may be contaminated): {len(out)}/{n}"
          + (f" -> {', '.join(out)}" if out else ""))
    if labels:
        graded =[t for t in traces if t["question_id"] in labels]
        right = [t for t in graded if labels[t["question_id"]]]
        wrong = [t for t in graded if not labels[t["question_id"]]]
        def saw(ts):
            return sum(any(_saw_answer(s) for s in t["steps"]) for t in ts)
        print(f"correct {len(right)}: saw an answer turn in {saw(right)}")
        print(f"wrong   {len(wrong)}: saw an answer turn in {saw(wrong)}  "
              "(saw it but still wrong = reading/decision failure; never saw it = search failure)")


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--show", nargs="*", default=None, help="'all', 'wrong', or question ids")
    args = ap.parse_args(argv)
    run = Path(args.run_dir)
    traces = read_jsonl(run / "traces.jsonl")
    if not traces:
        print(f"no traces in {run} (only agentic systems write traces.jsonl)")
        return 1
    labels = {r["question_id"]: bool(r["autoeval_label"]) for r in read_jsonl(run / "eval.jsonl")}
    if args.show is None:
        summary(traces, labels)
        return 0
    for t in traces:
        qid = t["question_id"]
        if (args.show == ["all"] or (args.show == ["wrong"] and labels.get(qid) is False)
                or qid in args.show):
            show(t, labels.get(qid))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
