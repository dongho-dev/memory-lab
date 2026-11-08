"""Agentic search: the same raw store and BM25 as raw_search, but the model writes the queries.

Instead of one search with the question text, the model gets search / read / answer actions and
decides what to look up, step by step, up to a step limit. Every step is recorded with the
model's stated reason, the action, and what came back, so we can see how it searched and why
it decided what it did. (The reason is the model's own account, not its hidden reasoning.)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from ..bm25 import BM25
from ..data import Session, format_turns, session_header
from ..llm import open_chat
from ..prompts import AGENT_FIRST, AGENT_SYSTEM
from .baselines import RawSearch

_REASON = re.compile(r"REASON:\s*(.*?)(?=\n\s*ACTION:|\Z)", re.S | re.I)
_ACTION = re.compile(r"ACTION:\s*(search|read|answer)\s*:\s*(.*)", re.S | re.I)

FORMAT_HELP = "REASON: ...\nACTION: search: ... | read: ... | answer: ..."


@dataclass
class AgentResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    steps: list[dict] = field(default_factory=list)
    retrieved_session_ids: list[str] = field(default_factory=list)
    seen_text: str = ""
    ingest_input_tokens: int = 0
    ingest_output_tokens: int = 0


class AgenticSearch(RawSearch):
    name = "agentic_search"
    agentic = True

    def __init__(self, llm=None, k: int = 5, max_steps: int = 8, granularity: str = "round"):
        super().__init__(llm, top_k=int(k), granularity=granularity)
        self.params = {"k": int(k), "max_steps": int(max_steps), "granularity": granularity}
        self.k, self.max_steps = int(k), int(max_steps)

    def reset(self) -> None:
        super().reset()
        self.sessions: dict[str, Session] = {}

    def ingest(self, session: Session) -> None:
        super().ingest(session)
        self.sessions[session.session_id] = session

    def search(self, query: str) -> list[tuple[int, float]]:
        if self._index is None:
            self._index = BM25([c.text for c in self.chunks])
        scores = self._index.scores(query)
        ranked = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)
        return [(i, scores[i]) for i in ranked[: self.k] if scores[i] > 0]

    def build_context(self, question: str, question_date: str):
        raise NotImplementedError("agentic_search answers through run_agent()")

    def _do_search(self, query: str, step: dict, used: int, seen: dict, shown: list) -> str:
        hits = self.search(query)
        step["results"] = [{"session_id": self.chunks[i].session_id, "date": self.chunks[i].date,
                            "chunk": i, "score": round(s, 2)} for i, s in hits]
        parts = []
        for n, (i, _) in enumerate(hits, 1):
            c = self.chunks[i]
            parts.append(f"[{n}] session {c.session_id} · {c.date}\n{c.text}")
            seen.setdefault(c.session_id, None)
            shown.append(c.text)
        body = "\n\n".join(parts) or "(no matches)"
        return f'<results step="{used}" action="search" query="{query}">\n{body}\n</results>'

    def _do_read(self, arg: str, step: dict, used: int, seen: dict, shown: list) -> str:
        sid = arg.strip().strip("<>\"'`").removeprefix("session").strip()
        sess = self.sessions.get(sid)
        step["results"] = [{"session_id": sid, "found": sess is not None}]
        if sess:
            body = f"{session_header(sess)}\n{format_turns(sess.turns)}"
            seen.setdefault(sid, None)
            shown.append(body)
        else:
            body = f"(no session with id {sid!r})"
        return f'<results step="{used}" action="read" session="{sid}">\n{body}\n</results>'

    def run_agent(self, llm, question: str, question_date: str) -> AgentResult:
        chat = open_chat(llm, AGENT_SYSTEM.format(k=self.k, max_steps=self.max_steps))
        res = AgentResult(text="")
        seen: dict[str, None] = {}
        shown: list[str] = []
        message = AGENT_FIRST.format(question=question, question_date=question_date or "unknown")
        used = 0
        try:
            for turn in range(1, self.max_steps + 4):
                t0 = time.time()
                c = chat.send(message)
                res.input_tokens += c.input_tokens
                res.output_tokens += c.output_tokens
                reason_m, action_m = _REASON.search(c.text), _ACTION.search(c.text)
                step = {"step": turn, "reason": reason_m.group(1).strip() if reason_m else "",
                        "in_tokens": c.input_tokens, "out_tokens": c.output_tokens,
                        "sec": round(time.time() - t0, 2)}
                res.steps.append(step)
                if not action_m:
                    step.update(action="format_error", raw=c.text[:500])
                    if used >= self.max_steps:
                        res.text = c.text.strip()
                        break
                    used += 1
                    message = f"Format error. Reply with\n{FORMAT_HELP}\nSteps left: {self.max_steps - used}."
                    continue
                kind, arg = action_m.group(1).lower(), action_m.group(2).strip()
                step.update(action=kind, arg=arg)
                if kind == "answer":
                    res.text = arg
                    break
                if used >= self.max_steps:
                    step["note"] = "step limit reached; asked for the answer"
                    message = "No steps left. Reply now with\nREASON: ...\nACTION: answer: ..."
                    continue
                used += 1
                do = self._do_search if kind == "search" else self._do_read
                message = f"{do(arg, step, used, seen, shown)}\nSteps left: {self.max_steps - used}."
            if not res.text:
                res.text = "(no answer within the turn limit)"
        finally:
            chat.close()
        res.retrieved_session_ids = list(seen)
        res.seen_text = "\n".join(shown)
        return res
