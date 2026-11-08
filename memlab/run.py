"""Run a memory system over LongMemEval questions and record its answers.

    python -m memlab.run --system raw_search --param top_k=10 --subset subsets/dev42.json
    python -m memlab.run --system full_context --subset subsets/dev42.json --dry-run

Writes results/<name>/config.json and hypotheses.jsonl. Re-running the same command resumes:
questions already answered are skipped. --dry-run makes no API calls and prints a cost estimate.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .data import Question, load_questions, load_subset
from .io import JsonlWriter, read_json, read_jsonl, write_json
from .llm import EstimateLLM, MockLLM, estimate_tokens, make_llm
from .pricing import cost_usd
from .prompts import ANSWER_SYSTEM, build_answer_prompt
from .systems import make_system
from .io import utf8_stdout

_IDENTITY_KEYS = ("data", "subset", "system", "params", "model", "effort", "backend")


def parse_params(items: list[str]) -> dict:
    params = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"--param expects key=value, got '{item}'")
        key, value = item.split("=", 1)
        for cast in (int, float):
            try:
                params[key] = cast(value)
                break
            except ValueError:
                continue
        else:
            params[key] = {"true": True, "false": False}.get(value.lower(), value)
    return params


def default_name(system: str, params: dict, data: str) -> str:
    parts = [system] + [f"{k}{v}" for k, v in sorted(params.items())]
    if "oracle" in Path(data).name:
        parts.insert(0, "oracle")
    return "_".join(str(p) for p in parts)


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except Exception:
        return None


def _answer_turns(q: Question) -> list[str]:
    """Turns LongMemEval marks as holding the answer (never shown to systems)."""
    return [t.content for s in q.sessions for t in s.turns if t.has_answer]


def _turn_recall(q: Question, shown: str) -> float | None:
    """Share of answer turns whose text reached the model. Stricter than session recall:
    a session can be retrieved while the one turn that matters is left out."""
    turns = _answer_turns(q)
    if not turns:
        return None
    return sum(1 for t in turns if t[:200] in shown) / len(turns)


def _annotate_trace(q: Question, steps: list[dict], chunks) -> list[dict]:
    """Mark, for each result the model saw, whether it came from an evidence session and
    whether it contained an answer turn. Done here so the system never sees the labels."""
    evidence = set(q.answer_session_ids)
    answers = [t[:200] for t in _answer_turns(q)]
    sessions = {s.session_id: s for s in q.sessions}
    for st in steps:
        if "result_text" in st:
            text = st.pop("result_text")
            where = text + " " + json.dumps(st.get("arg", ""), ensure_ascii=False)
            st["has_answer_turn"] = any(a in text for a in answers)
            st["evidence_session"] = any(e in where for e in evidence)
        for r in st.get("results", []):
            r["evidence_session"] = r["session_id"] in evidence
            if "chunk" in r:
                text = chunks[r["chunk"]].text
            else:
                s = sessions.get(r["session_id"])
                text = "\n".join(t.content for t in s.turns) if s else ""
            r["has_answer_turn"] = any(a in text for a in answers)
    return steps


def answer_one(q: Question, system_name: str, params: dict, llm, max_tokens: int) -> dict:
    system = make_system(system_name, llm=llm, **params)
    t0 = time.time()
    system.reset()
    for session in q.sessions:
        system.ingest(session)
    evidence = set(q.answer_session_ids)
    row = {"question_id": q.question_id, "category": q.category}
    if getattr(system, "agentic", False):
        a = system.run_agent(llm, q.question, q.question_date)
        steps = _annotate_trace(q, a.steps, getattr(system, "chunks", []))
        got, shown = set(a.retrieved_session_ids), a.seen_text
        row.update(hypothesis=a.text, input_tokens=a.input_tokens, output_tokens=a.output_tokens,
                   ingest_input_tokens=0, ingest_output_tokens=0,
                   context_tokens_est=estimate_tokens(shown) if shown else 0,
                   n_steps=len(steps),
                   n_search=sum(1 for s in steps if s.get("action") in ("search", "Grep", "Glob")),
                   n_read=sum(1 for s in steps if s.get("action") in ("read", "Read")),
                   n_bash=sum(1 for s in steps if s.get("action") == "Bash"),
                   n_outside=sum(1 for s in steps if s.get("outside")),
                   trace=steps)
    else:
        r = system.build_context(q.question, q.question_date)
        prompt = build_answer_prompt(r.context, q.question, q.question_date)
        c = llm.complete(ANSWER_SYSTEM, prompt, max_tokens=max_tokens)
        got, shown = set(r.retrieved_session_ids), r.context
        row.update(hypothesis=c.text, input_tokens=c.input_tokens, output_tokens=c.output_tokens,
                   ingest_input_tokens=r.ingest_input_tokens, ingest_output_tokens=r.ingest_output_tokens,
                   context_tokens_est=estimate_tokens(r.context) if r.context else 0)
    row.update(retrieved_session_ids=sorted(got),
               evidence_recall=(len(evidence & got) / len(evidence)) if evidence else None,
               answer_turn_recall=_turn_recall(q, shown),
               latency_s=round(time.time() - t0, 2))
    return row


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True)
    ap.add_argument("--param", action="append", default=[], help="system parameter key=value (repeatable)")
    ap.add_argument("--data", default="data/longmemeval_s_cleaned.json")
    ap.add_argument("--subset", default=None, help="JSON file with question_ids (default: all questions)")
    ap.add_argument("--limit", type=int, default=None, help="only the first N questions")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--effort", default="medium", help="low|medium|high|xhigh|max, or 'none' for the model default")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--name", default=None, help="run name (default derived from system and params)")
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--dry-run", action="store_true", help="no API calls; print token and cost estimate")
    ap.add_argument("--mock", action="store_true", help="use the deterministic mock model (tests)")
    ap.add_argument("--backend", default="claude-code-session",
                    help="claude-code-session (kept-alive `claude` processes, /clear per call; subscription) | "
                         "claude-code (one `claude -p` process per call; subscription) | api (Anthropic API key)")
    args = ap.parse_args(argv)

    params = parse_params(args.param)
    effort = None if args.effort in (None, "", "none") else args.effort
    ids = load_subset(args.subset) if args.subset else None
    questions = load_questions(args.data, ids)
    if args.limit:
        questions = questions[: args.limit]

    if args.dry_run:
        return dry_run(questions, args.system, params, args.model, args.max_tokens, Path(args.data).name)

    name = args.name or default_name(args.system, params, args.data)
    run_dir = Path(args.out_dir) / name
    config = {
        "name": name,
        "data": args.data,
        "subset": args.subset,
        "system": args.system,
        "params": params,
        "model": "mock" if args.mock else args.model,
        "effort": effort,
        "backend": "mock" if args.mock else args.backend,
        "max_tokens": args.max_tokens,
        "git_commit": git_commit(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    cfg_path = run_dir / "config.json"
    if cfg_path.exists():
        old = read_json(cfg_path)
        diff = [k for k in _IDENTITY_KEYS if old.get(k) != config.get(k)]
        if diff:
            raise SystemExit(f"{run_dir} already holds a different run ({', '.join(diff)} differ). "
                             f"Use another --name.")
        config["started_at"] = old.get("started_at", config["started_at"])
    write_json(cfg_path, config)

    hyp_path = run_dir / "hypotheses.jsonl"
    done = {row["question_id"] for row in read_jsonl(hyp_path)}
    todo = [q for q in questions if q.question_id not in done]
    print(f"[{name}] {len(questions)} questions, {len(done)} already done, {len(todo)} to run")
    if not todo:
        return 0

    llm = MockLLM() if args.mock else make_llm(args.backend, args.model, effort)
    writer = JsonlWriter(hyp_path)
    trace_writer = JsonlWriter(run_dir / "traces.jsonl")
    failures = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(answer_one, q, args.system, params, llm, args.max_tokens): q for q in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            q = futures[fut]
            try:
                row = fut.result()
            except Exception as e:
                failures += 1
                print(f"  ! {q.question_id}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            trace = row.pop("trace", None)
            if trace is not None:
                trace_writer.write({"question_id": q.question_id, "question": q.question,
                                    "answer": q.answer, "hypothesis": row["hypothesis"], "steps": trace})
            writer.write(row)
            extra = f" steps={row['n_steps']}" if "n_steps" in row else ""
            print(f"  {i}/{len(todo)} {q.question_id} ({row['category']}) "
                  f"in={row['input_tokens']:,} out={row['output_tokens']:,}{extra} {row['latency_s']}s")
    if failures:
        print(f"{failures} questions failed; run the same command again to retry them.", file=sys.stderr)
        return 1
    print(f"done → {hyp_path}")
    return 0


def dry_run(questions: list[Question], system: str, params: dict, model: str, max_tokens: int,
            data_name: str = "") -> int:
    llm = EstimateLLM(model)
    rows = [answer_one(q, system, params, llm, max_tokens) for q in questions]
    n = len(rows)
    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    recalls = [r["evidence_recall"] for r in rows if r["evidence_recall"] is not None]
    cost = cost_usd(model, tin, tout)
    label = system + (f" {params}" if params else "")
    print(f"[dry-run] {label} on {n} questions from {data_name or 'data'} with {model}")
    print(f"  avg input tokens/question ≈ {tin // max(n, 1):,}   max ≈ {max((r['input_tokens'] for r in rows), default=0):,}")
    print(f"  total ≈ {tin:,} in + {tout:,} out (output assumed {llm.assumed_output_tokens}/question)")
    if recalls:
        print(f"  evidence recall (no API needed) = {sum(recalls) / len(recalls):.2f}")
    turn = [r["answer_turn_recall"] for r in rows if r.get("answer_turn_recall") is not None]
    if turn and not any("n_steps" in r for r in rows):
        print(f"  answer-turn recall (no API needed) = {sum(turn) / len(turn):.2f}")
    if any("n_steps" in r for r in rows):
        print("  (agentic: the estimator never answers, so this is the worst case: every step used)")
    print(f"  estimated answer cost ≈ ${cost:.2f}" if cost is not None else "  (no price for this model)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
