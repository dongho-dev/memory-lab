"""Grade a run with the LongMemEval judge prompts, then summarize it.

    python -m memlab.evaluate results/raw_search_top_k10

Writes eval.jsonl (one label per question; resumable) and summary.json.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .data import CATEGORIES, Question, load_questions
from .io import JsonlWriter, read_json, read_jsonl, write_json
from .llm import make_llm
from .pricing import cost_usd
from .prompts import judge_prompt
from .io import utf8_stdout


class LLMJudge:
    def __init__(self, model: str, effort: str | None, backend: str = "claude-code-session"):
        self.model = model
        self.llm = make_llm(backend, model, effort)

    def judge(self, q: Question, hypothesis: str) -> tuple[bool, dict]:
        prompt = judge_prompt(q.question_type, q.question, q.answer, hypothesis, q.is_abstention)
        c = self.llm.complete("", prompt, max_tokens=2048)
        label = "yes" in c.text.lower()
        return label, {"judge_raw": c.text[:200], "judge_input_tokens": c.input_tokens,
                       "judge_output_tokens": c.output_tokens}


class MockJudge:
    """Heuristic judge for tests: gold answer appears in the hypothesis; abstention = 'don't know'."""

    model = "mock"

    def judge(self, q: Question, hypothesis: str) -> tuple[bool, dict]:
        h = hypothesis.lower()
        if q.is_abstention:
            return ("don't know" in h or "do not know" in h), {}
        gold = re.sub(r"\s+", " ", q.answer.lower()).strip()
        return gold in h, {}


def summarize(run_dir: str | Path) -> dict:
    run_dir = Path(run_dir)
    cfg = read_json(run_dir / "config.json")
    hyps = {r["question_id"]: r for r in read_jsonl(run_dir / "hypotheses.jsonl")}
    evals = {r["question_id"]: r for r in read_jsonl(run_dir / "eval.jsonl")}
    graded = [qid for qid in hyps if qid in evals]

    by_cat: dict[str, list[bool]] = defaultdict(list)
    for qid in graded:
        by_cat[hyps[qid]["category"]].append(bool(evals[qid]["autoeval_label"]))
    labels = [v for vs in by_cat.values() for v in vs]
    per_cat = {c: (sum(v) / len(v), len(v)) for c, v in by_cat.items() if v}

    def avg(key: str) -> float:
        vals = [hyps[q][key] for q in graded if hyps[q].get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0

    tin = sum(hyps[q]["input_tokens"] + hyps[q].get("ingest_input_tokens", 0) for q in graded)
    tout = sum(hyps[q]["output_tokens"] + hyps[q].get("ingest_output_tokens", 0) for q in graded)
    recalls = [hyps[q]["evidence_recall"] for q in graded if hyps[q].get("evidence_recall") is not None]
    summary = {
        "name": cfg["name"],
        "system": cfg["system"],
        "params": cfg.get("params", {}),
        "model": cfg["model"],
        "data": Path(cfg["data"]).name,
        "n": len(graded),
        "n_answered": len(hyps),
        "accuracy": (sum(labels) / len(labels)) if labels else None,
        "task_averaged_accuracy": (sum(a for a, _ in per_cat.values()) / len(per_cat)) if per_cat else None,
        "per_category": {c: {"accuracy": per_cat[c][0], "n": per_cat[c][1]} for c in CATEGORIES if c in per_cat},
        "avg_input_tokens": avg("input_tokens"),
        "avg_output_tokens": avg("output_tokens"),
        "avg_ingest_tokens": avg("ingest_input_tokens") + avg("ingest_output_tokens"),
        "evidence_recall": (sum(recalls) / len(recalls)) if recalls else None,
        "answer_turn_recall": avg("answer_turn_recall") if any(hyps[q].get("answer_turn_recall") is not None for q in graded) else None,
        "avg_steps": avg("n_steps") if any("n_steps" in hyps[q] for q in graded) else None,
        "answer_cost_usd": cost_usd(cfg["model"], tin, tout),
        "judge_cost_usd": None,
    }
    jin = sum(evals[q].get("judge_input_tokens", 0) for q in graded)
    jout = sum(evals[q].get("judge_output_tokens", 0) for q in graded)
    judge_model = next((evals[q].get("judge_model") for q in graded if evals[q].get("judge_model")), None)
    if judge_model:
        summary["judge_model"] = judge_model
        summary["judge_cost_usd"] = cost_usd(judge_model, jin, jout)
    write_json(run_dir / "summary.json", summary)
    return summary


def print_summary(s: dict) -> None:
    acc = s["accuracy"]
    print(f"[{s['name']}] n={s['n']}  accuracy={acc:.3f}" if acc is not None else f"[{s['name']}] nothing graded")
    for c, v in s["per_category"].items():
        print(f"  {c:<28} {v['accuracy']:.2f}  (n={v['n']})")
    print(f"  avg input tokens/question = {s['avg_input_tokens']:,.0f}")
    if s["evidence_recall"] is not None:
        print(f"  evidence recall = {s['evidence_recall']:.2f}")
    if s.get("answer_turn_recall") is not None:
        print(f"  answer-turn recall = {s['answer_turn_recall']:.2f}")
    if s.get("avg_steps") is not None:
        print(f"  avg steps/question = {s['avg_steps']:.1f}")
    if s["answer_cost_usd"] is not None:
        print(f"  answer cost ≈ ${s['answer_cost_usd']:.2f}")


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--judge-model", default="claude-sonnet-5-5")
    ap.add_argument("--judge-effort", default="low")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--mock", action="store_true", help="heuristic judge, no API calls (tests)")
    ap.add_argument("--judge-backend", default="claude-code-session", help="claude-code-session | claude-code | api")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    cfg = read_json(run_dir / "config.json")
    hyps = read_jsonl(run_dir / "hypotheses.jsonl")
    eval_path = run_dir / "eval.jsonl"
    done = {r["question_id"] for r in read_jsonl(eval_path)}
    todo = [h for h in hyps if h["question_id"] not in done]
    if todo:
        questions = {q.question_id: q for q in load_questions(cfg["data"], [h["question_id"] for h in todo])}
        judge = MockJudge() if args.mock else LLMJudge(args.judge_model, None if args.judge_effort == "none" else args.judge_effort, args.judge_backend)
        writer = JsonlWriter(eval_path)
        failures = 0
        print(f"[{cfg['name']}] grading {len(todo)} answers with {judge.model}")
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {pool.submit(judge.judge, questions[h["question_id"]], h["hypothesis"]): h for h in todo}
            for fut in as_completed(futures):
                h = futures[fut]
                try:
                    label, extra = fut.result()
                except Exception as e:
                    failures += 1
                    print(f"  ! {h['question_id']}: {type(e).__name__}: {e}", file=sys.stderr)
                    continue
                writer.write({"question_id": h["question_id"], "category": h["category"],
                              "autoeval_label": label, "judge_model": judge.model, **extra})
        if failures:
            print(f"{failures} gradings failed; run again to retry.", file=sys.stderr)
    print_summary(summarize(run_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
