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
    # The mock answers by echoing its memory, so: no memory → nothing but abstention is right,
    # retrieval finds the cat and the new city.
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
