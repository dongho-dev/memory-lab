"""Free search with a trial-and-error log: agentic_files plus a progress.md state document.

progress.md starts with the owner's instruction: memory is larger than the context, keep searching,
build up what was tried and what came of it, decide when to stop. No step limit. Claude Code
compacts the conversation on its own when the context fills (autoCompactWindow), and the
log in progress.md carries over. The final progress.md is kept in the trace.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..io import redact
from ..prompts import SEARCH_LOG_SEED, SEARCH_LOG_SYSTEM
from .agentic import AgentResult
from .agentic_files import AgenticFiles


class SearchLog(AgenticFiles):
    name = "search_log"
    agentic = True

    def __init__(self, llm=None, timeout: float = 1800.0, bash: bool = True, compact_window: int = 100_000):
        super().__init__(llm, timeout=timeout, bash=bash)
        self.params["compact_window"] = int(compact_window)
        self.compact_window = int(compact_window)
        self.extra_system = SEARCH_LOG_SYSTEM

    def extra_args(self) -> list[str]:
        return ["--settings", json.dumps({"autoCompactWindow": self.compact_window})]

    def _write_store(self, root: Path) -> None:
        super()._write_store(root)
        (root / "progress.md").write_text(SEARCH_LOG_SEED, encoding="utf-8")

    def after_run(self, root: Path, res: AgentResult) -> None:
        f = root / "progress.md"
        text = redact(f.read_text(encoding="utf-8")) if f.exists() else ""
        if res.steps:
            res.steps[-1]["progress_md"] = text
