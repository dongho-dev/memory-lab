"""The interface every memory system implements.

Life cycle for one question (LongMemEval gives each question its own history):

    system.reset()
    for session in question.sessions:      # chronological, one at a time
        system.ingest(session)             # the "write" path: store, take notes, consolidate...
    retrieval = system.build_context(question.question, question.question_date)   # "read" path

The runner then puts retrieval.context into the shared answer prompt. Systems never see the
gold answer or the evidence labels.

Layers added later (notes, index, dreaming) are new systems behind this same interface,
so every layer is measured on exactly the same harness as the baselines it must beat.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..data import Session
from ..llm import LLM


@dataclass
class Retrieval:
    context: str
    retrieved_session_ids: list[str] = field(default_factory=list)
    ingest_input_tokens: int = 0
    ingest_output_tokens: int = 0


class MemorySystem(ABC):
    name = "base"

    def __init__(self, llm: LLM | None = None, **params):
        self.llm = llm
        self.params = params

    def reset(self) -> None:
        """Forget everything (called before each question's history)."""

    @abstractmethod
    def ingest(self, session: Session) -> None: ...

    @abstractmethod
    def build_context(self, question: str, question_date: str) -> Retrieval: ...

    def config(self) -> dict:
        return {"system": self.name, "params": dict(self.params)}
