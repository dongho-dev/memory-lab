"""End-to-end checks with the mock model: no API key or network needed.

    python -m pytest -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from memlab.data import load_questions
from memlab.prompts import judge_prompt
from memlab.systems import make_system

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "tiny_longmemeval.json"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def build(system: str, q, **params):
    s = make_system(system, **params)
    s.reset()
    for session in q.sessions:
        s.ingest(session)
    return s.build_context(q.question, q.question_date)


def test_loader_marks_abstention_and_sorts_sessions():
    qs = {q.question_id: q for q in load_questions(FIXTURE)}
    assert qs["q_dog_abs"].category == "abstention"
    assert qs["q_city"].category == "knowledge-update"
    dates = [s.date for s in qs["q_city"].sessions]
    assert dates == sorted(dates)


def test_raw_search_finds_the_evidence_round():
    q = next(q for q in load_questions(FIXTURE) if q.question_id == "q_cat")
    r = build("raw_search", q, top_k=1)
    assert "Miso" in r.context
    assert r.retrieved_session_ids == ["answer_cat"]


def test_raw_search_keeps_chronological_order_for_updates():
    q = next(q for q in load_questions(FIXTURE) if q.question_id == "q_city")
    r = build("raw_search", q, top_k=3)
    assert r.context.index("Busan") < r.context.index("Seoul")


def test_no_memory_and_full_context():
    q = load_questions(FIXTURE)[0]
    assert build("no_memory", q).context == ""
    full = build("full_context", q)
    assert all(s.session_id in full.context for s in q.sessions)


def test_judge_prompt_routes_by_type():
    assert "updated answer" in judge_prompt("knowledge-update", "q", "a", "r")
    assert "unanswerable" in judge_prompt("single-session-user", "q", "a", "r", abstention=True)
    with pytest.raises(ValueError):
        judge_prompt("made-up-type", "q", "a", "r")


def test_end_to_end_with_mock(tmp_path):
    out = tmp_path / "results"
    for system, extra in [("no_memory", []), ("raw_search", ["--param", "top_k=2"]), ("full_context", [])]:
        name = f"t_{system}"
        p = run_cli("memlab.run", "--system", system, *extra, "--data", str(FIXTURE), "--mock",
                    "--name", name, "--out-dir", str(out))
        assert p.returncode == 0, p.stderr
        p = run_cli("memlab.evaluate", str(out / name), "--mock")
        assert p.returncode == 0, p.stderr

    summaries = {d.name: json.loads((d / "summary.json").read_text(encoding="utf-8")) for d in out.iterdir()}
    assert summaries["t_no_memory"]["per_category"]["single-session-user"]["accuracy"] == 0
    assert summaries["t_raw_search"]["per_category"]["single-session-user"]["accuracy"] == 1
    assert summaries["t_raw_search"]["evidence_recall"] == 1
    assert summaries["t_full_context"]["avg_input_tokens"] > summaries["t_raw_search"]["avg_input_tokens"]

    p = run_cli("memlab.report", str(out))
    assert p.returncode == 0, p.stderr
    assert "t_raw_search" in (out / "REPORT.md").read_text(encoding="utf-8")


def test_resume_skips_done_questions_and_refuses_mixed_runs(tmp_path):
    out = tmp_path / "results"
    args = ["memlab.run", "--system", "no_memory", "--data", str(FIXTURE), "--mock",
            "--name", "r", "--out-dir", str(out)]
    assert run_cli(*args).returncode == 0
    again = run_cli(*args)
    assert again.returncode == 0 and "3 already done, 0 to run" in again.stdout
    mixed = run_cli("memlab.run", "--system", "raw_search", "--data", str(FIXTURE), "--mock",
                    "--name", "r", "--out-dir", str(out))
    assert mixed.returncode != 0 and "different run" in mixed.stderr


def test_dry_run_makes_no_files(tmp_path):
    p = run_cli("memlab.run", "--system", "full_context", "--data", str(FIXTURE), "--dry-run",
                "--out-dir", str(tmp_path / "results"))
    assert p.returncode == 0, p.stderr
    assert "estimated answer cost" in p.stdout
    assert not (tmp_path / "results").exists()


def test_agentic_search_with_mock_writes_traces(tmp_path):
    out = tmp_path / "results"
    p = run_cli("memlab.run", "--system", "agentic_search", "--param", "k=2", "--data", str(FIXTURE),
                "--mock", "--name", "t_agent", "--out-dir", str(out))
    assert p.returncode == 0, p.stderr
    assert run_cli("memlab.evaluate", str(out / "t_agent"), "--mock").returncode == 0
    hyps = {r["question_id"]: r for r in map(json.loads, (out / "t_agent" / "hypotheses.jsonl").read_text(encoding="utf-8").splitlines())}
    assert "Miso" in hyps["q_cat"]["hypothesis"]
    assert hyps["q_cat"]["n_search"] == 1 and hyps["q_cat"]["answer_turn_recall"] == 1
    traces = [json.loads(l) for l in (out / "t_agent" / "traces.jsonl").read_text(encoding="utf-8").splitlines()]
    cat = next(t for t in traces if t["question_id"] == "q_cat")
    first = cat["steps"][0]
    assert first["action"] == "search" and first["reason"]
    assert any(r["has_answer_turn"] for r in first["results"])
    assert cat["steps"][-1]["action"] == "answer"
    p = run_cli("memlab.trace", str(out / "t_agent"))
    assert p.returncode == 0 and "answer turn was shown" in p.stdout
    p = run_cli("memlab.trace", str(out / "t_agent"), "--show", "q_cat")
    assert p.returncode == 0 and "why:" in p.stdout


def test_answer_turn_recall_for_plain_retrieval(tmp_path):
    out = tmp_path / "results"
    p = run_cli("memlab.run", "--system", "raw_search", "--param", "top_k=1", "--data", str(FIXTURE),
                "--mock", "--name", "t_turn", "--out-dir", str(out))
    assert p.returncode == 0, p.stderr
    rows = [json.loads(l) for l in (out / "t_turn" / "hypotheses.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all("answer_turn_recall" in r for r in rows)


def test_agentic_files_with_mock(tmp_path):
    out = tmp_path / "results"
    p = run_cli("memlab.run", "--system", "agentic_files", "--data", str(FIXTURE), "--mock",
                "--name", "t_files", "--out-dir", str(out))
    assert p.returncode == 0, p.stderr
    hyps = {r["question_id"]: r for r in map(json.loads, (out / "t_files" / "hypotheses.jsonl").read_text(encoding="utf-8").splitlines())}
    assert "Miso" in hyps["q_cat"]["hypothesis"] and hyps["q_cat"]["answer_turn_recall"] == 1
    traces = {t["question_id"]: t for t in map(json.loads, (out / "t_files" / "traces.jsonl").read_text(encoding="utf-8").splitlines())}
    steps = traces["q_cat"]["steps"]
    assert steps[0]["action"] == "Grep" and any(s.get("has_answer_turn") for s in steps)
    assert all("result_text" not in s for s in steps)
    p = run_cli("memlab.trace", str(out / "t_files"), "--show", "all")
    assert p.returncode == 0 and "Grep" in p.stdout


def test_outside_access_flags_paths_escapes_and_network(tmp_path):
    from memlab.systems.agentic_files import outside_access
    root = tmp_path / "store"
    root.mkdir()
    inside = str(root / "sessions" / "a.md")
    assert outside_access({"file_path": inside}, root) == []
    assert outside_access({"command": "grep -ri rachel sessions/ | head"}, root) == []
    assert outside_access({"command": "cat C:/Users/x/memory-lab/data/longmemeval_s_cleaned.json"}, root)
    assert outside_access({"command": "cat /c/Users/x/memory-lab/data/a.json"}, root)
    assert outside_access({"command": "ls ../.."}, root)
    assert outside_access({"command": "ls $HOME"}, root)
    assert outside_access({"command": "curl -L https://huggingface.co/x"}, root)
    spill = r"C:\Users\x\.claude\projects\C--Users-x-Temp-memlab-files-ab12\t\tool-results\o.txt"
    assert outside_access({"file_path": spill}, root) == []


def test_outside_access_ignores_grep_patterns_and_own_tmp(tmp_path):
    from memlab.systems.agentic_files import outside_access
    root = tmp_path / "memlab_files_abc"
    root.mkdir()
    assert outside_access({"command": 'grep -n "^user:" sessions/a.md'}, root) == []
    assert outside_access({"command": "cd /tmp/memlab_files_abc && ls sessions"}, root) == []
    assert outside_access({"command": "ls /tmp/other"}, root)
    assert outside_access({"command": "cat /home/u/x"}, root)


def test_proportional_counts_sum_and_shape():
    from memlab.subset import proportional_counts
    sizes = {"single-session-user": 64, "single-session-assistant": 56, "single-session-preference": 30,
             "multi-session": 121, "knowledge-update": 72, "temporal-reasoning": 127, "abstention": 30}
    c = proportional_counts(sizes, 100)
    assert sum(c.values()) == 100 and c["single-session-preference"] == 6 and c["temporal-reasoning"] >= 25


def test_extract_keeps_only_subset_questions(tmp_path):
    pytest.importorskip("ijson")
    from memlab.extract import extract
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    want = {str(raw[0]["question_id"])}
    out = tmp_path / "small.json"
    assert extract(FIXTURE, want, out) == 1
    assert [q["question_id"] for q in json.loads(out.read_text(encoding="utf-8"))] == list(want)


def test_progress_md_with_mock_writes_notes_steps(tmp_path):
    out = tmp_path / "results"
    p = run_cli("memlab.run", "--system", "progress_md", "--data", str(FIXTURE), "--mock",
                "--name", "t_notes", "--out-dir", str(out))
    assert p.returncode == 0, p.stderr
    traces = [json.loads(l) for l in (out / "t_notes" / "traces.jsonl").read_text(encoding="utf-8").splitlines()]
    steps = traces[0]["steps"]
    assert steps[0]["action"] == "notes" and "notes_text" in [k for s in steps for k in s]
    assert [s["step"] for s in steps] == list(range(1, len(steps) + 1))


def test_chunk_sessions_respects_budget():
    from memlab.data import load_questions
    from memlab.systems.progress_md import chunk_sessions
    q = load_questions(FIXTURE)[0]
    parts = chunk_sessions(q.sessions, 1)
    assert len(parts) == len(q.sessions) and sum(len(p) for p in parts) == len(q.sessions)


def test_redact_replaces_account_email(monkeypatch):
    from memlab import io
    io._account_email.cache_clear()
    monkeypatch.setattr(io, "_account_email", lambda: "someone@example.com")
    assert io.redact("mail someone@example.com now") == "mail [account-email] now"
    assert io.redact("nothing here") == "nothing here"


def test_search_log_seeds_progress_and_sets_compact(tmp_path):
    import json as _json
    from memlab.prompts import SEARCH_LOG_SEED
    s = make_system("search_log", compact_window=100000)
    s.reset()
    s._write_store(tmp_path)
    assert (tmp_path / "progress.md").read_text(encoding="utf-8") == SEARCH_LOG_SEED
    args = s.extra_args()
    assert args[0] == "--settings" and _json.loads(args[1])["autoCompactWindow"] == 100000
