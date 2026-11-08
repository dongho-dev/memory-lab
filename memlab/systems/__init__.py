"""Registry of memory systems. Add a new layer by implementing MemorySystem and listing it here."""
from __future__ import annotations

from .base import MemorySystem, Retrieval
from .agentic import AgenticSearch
from .agentic_files import AgenticFiles
from .baselines import FullContext, NoMemory, RawSearch
from .progress_md import ProgressMd
from .search_log import SearchLog

SYSTEMS: dict[str, type[MemorySystem]] = {
    NoMemory.name: NoMemory,
    FullContext.name: FullContext,
    RawSearch.name: RawSearch,
    AgenticSearch.name: AgenticSearch,
    AgenticFiles.name: AgenticFiles,
    ProgressMd.name: ProgressMd,
    SearchLog.name: SearchLog,
}


def make_system(name: str, llm=None, **params) -> MemorySystem:
    if name not in SYSTEMS:
        raise ValueError(f"unknown system '{name}'. available: {', '.join(SYSTEMS)}")
    return SYSTEMS[name](llm=llm, **params)


__all__ = ["MemorySystem", "Retrieval", "SYSTEMS", "make_system"]
