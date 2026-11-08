"""Stage 0 baselines.

- no_memory     floor: the model sees only the question.
- full_context  everything, verbatim. A cost reference, and (on the oracle file) the
                reading ceiling: the score you get when retrieval is perfect.
- raw_search    BM25 over raw conversation chunks. The simplest real memory, and the one every
                later layer has to beat on accuracy or on tokens.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..bm25 import BM25
from ..data import Session, format_turns, session_header
from .base import MemorySystem, Retrieval


class NoMemory(MemorySystem):
    name = "no_memory"

    def ingest(self, session: Session) -> None:
        pass

    def build_context(self, question: str, question_date: str) -> Retrieval:
        return Retrieval(context="")


class FullContext(MemorySystem):
    name = "full_context"

    def __init__(self, llm=None, **params):
        super().__init__(llm, **params)
        self.sessions: list[Session] = []

    def reset(self) -> None:
        self.sessions = []

    def ingest(self, session: Session) -> None:
        self.sessions.append(session)

    def build_context(self, question: str, question_date: str) -> Retrieval:
        context = "\n\n".join(f"{session_header(s)}\n{format_turns(s.turns)}" for s in self.sessions)
        return Retrieval(context=context, retrieved_session_ids=[s.session_id for s in self.sessions])


@dataclass
class _Chunk:
    session_id: str
    date: str
    order: tuple[int, int]  # (session index, round index) for chronological output
    text: str


class RawSearch(MemorySystem):
    """BM25 over 'rounds' (a user turn plus the assistant replies that follow it) or sessions."""

    name = "raw_search"

    def __init__(self, llm=None, top_k: int = 10, granularity: str = "round"):
        if granularity not in ("round", "session"):
            raise ValueError("granularity must be 'round' or 'session'")
        super().__init__(llm, top_k=int(top_k), granularity=granularity)
        self.top_k = int(top_k)
        self.granularity = granularity
        self.reset()

    def reset(self) -> None:
        self.chunks: list[_Chunk] = []
        self._n_sessions = 0
        self._index: BM25 | None = None

    def ingest(self, session: Session) -> None:
        si = self._n_sessions
        self._n_sessions += 1
        self._index = None
        if self.granularity == "session":
            self.chunks.append(_Chunk(session.session_id, session.date, (si, 0), format_turns(session.turns)))
            return
        rounds: list[list] = []
        for turn in session.turns:
            if turn.role == "user" or not rounds:
                rounds.append([turn])
            else:
                rounds[-1].append(turn)
        for ri, turns in enumerate(rounds):
            self.chunks.append(_Chunk(session.session_id, session.date, (si, ri), format_turns(turns)))

    def build_context(self, question: str, question_date: str) -> Retrieval:
        if not self.chunks:
            return Retrieval(context="")
        if self._index is None:
            self._index = BM25([c.text for c in self.chunks])
        scores = self._index.scores(question)
        ranked = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)
        top = [i for i in ranked[: self.top_k] if scores[i] > 0]
        selected = sorted((self.chunks[i] for i in top), key=lambda c: c.order)
        context = "\n\n".join(
            f"[{c.date}] (session {c.session_id})\n{c.text}" for c in selected
        )
        seen: dict[str, None] = {}
        for c in selected:
            seen.setdefault(c.session_id, None)
        return Retrieval(context=context, retrieved_session_ids=list(seen))
