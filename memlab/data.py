"""Loading LongMemEval questions and their chat histories.

Format reference: https://github.com/xiaowu0162/LongMemEval (README, "Dataset Format").
Each question carries its own haystack of timestamped user-assistant sessions; a memory
system ingests that haystack in chronological order and then answers the question.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Question categories. Abstention questions are marked by a question_id ending in "_abs";
# we report them as their own category, the same way the LongMemEval paper does.
CATEGORIES = [
    "single-session-user",
    "single-session-assistant",
    "single-session-preference",
    "multi-session",
    "knowledge-update",
    "temporal-reasoning",
    "abstention",
]
SHORT = {
    "single-session-user": "SSU",
    "single-session-assistant": "SSA",
    "single-session-preference": "SSP",
    "multi-session": "MS",
    "knowledge-update": "KU",
    "temporal-reasoning": "TR",
    "abstention": "ABS",
}


@dataclass
class Turn:
    role: str
    content: str
    has_answer: bool = False  # LongMemEval marks evidence turns; never shown to systems


@dataclass
class Session:
    session_id: str
    date: str
    turns: list[Turn]


@dataclass
class Question:
    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str
    sessions: list[Session]
    answer_session_ids: list[str] = field(default_factory=list)

    @property
    def is_abstention(self) -> bool:
        return self.question_id.endswith("_abs")

    @property
    def category(self) -> str:
        return "abstention" if self.is_abstention else self.question_type


_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})(?:\D+?(\d{1,2}):(\d{2}))?")


def date_key(text: str) -> tuple:
    """Sort key for LongMemEval dates such as '2023/05/20 (Sat) 02:21'."""
    m = _DATE_RE.search(text or "")
    if not m:
        return (0, 0, 0, 0, 0)
    return tuple(int(g) if g else 0 for g in m.groups())


def parse_question(raw: dict) -> Question:
    sessions_raw = raw["haystack_sessions"]
    ids = raw.get("haystack_session_ids") or [f"s{i}" for i in range(len(sessions_raw))]
    dates = raw.get("haystack_dates") or [""] * len(ids)
    sessions = [
        Session(
            session_id=str(sid),
            date=str(d),
            turns=[
                Turn(t["role"], t["content"], bool(t.get("has_answer", False)))
                for t in turns
            ],
        )
        for sid, d, turns in zip(ids, dates, sessions_raw)
    ]
    # The _s/_m files are already chronological; the oracle file is not.
    sessions.sort(key=lambda s: date_key(s.date))
    return Question(
        question_id=str(raw["question_id"]),
        question_type=raw["question_type"],
        question=raw["question"],
        answer=str(raw["answer"]),
        question_date=str(raw.get("question_date", "")),
        sessions=sessions,
        answer_session_ids=[str(x) for x in (raw.get("answer_session_ids") or [])],
    )


def load_raw(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_questions(path: str | Path, ids: list[str] | None = None) -> list[Question]:
    """Load questions, optionally restricted to (and ordered by) the given ids."""
    raw = load_raw(path)
    if ids is None:
        return [parse_question(r) for r in raw]
    wanted = set(ids)
    by_id = {str(r["question_id"]): r for r in raw if str(r["question_id"]) in wanted}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ValueError(f"{len(missing)} question ids not found in {path}: {missing[:5]}")
    return [parse_question(by_id[i]) for i in ids]


def load_subset(path: str | Path) -> list[str]:
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    return [str(x) for x in (obj["question_ids"] if isinstance(obj, dict) else obj)]


def format_turns(turns: list[Turn]) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in turns)


def session_header(session: Session) -> str:
    return f"[{session.date}] (session {session.session_id})"
