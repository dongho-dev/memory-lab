"""External memory file: the model has a progress.md it may use freely, then answers with free search.

Write path: the past sessions, in chronological order, are cut into parts of about chunk_tokens
tokens. Claude Code runs in a folder holding only progress.md, with Read, Write and Edit. Each part
is sent as one message; what the model does with progress.md is up to it.

Read path: exactly agentic_files (session files, Read/Grep/Glob, Bash if bash=true), plus the
final progress.md in the folder and one sentence in the system prompt saying it is there.
"""
from __future__ import annotations

import queue
import tempfile
import time
from pathlib import Path

from ..data import Session, format_turns, session_header
from ..io import redact
from ..llm import ClaudeCodeSessionLLM, EstimateLLM, MockLLM, _SessionProc, estimate_tokens
from ..prompts import FILES_NOTES, NOTES_SEED, NOTES_SYSTEM, NOTES_TEMPLATE
from .agentic import AgentResult
from .agentic_files import _ALL, _LOCK, AgenticFiles, outside_access

NOTE_TOOLS = "Read,Write,Edit"
_NOTE_POOLS: dict[int, "queue.Queue"] = {}


def _note_pool(llm) -> "queue.Queue":
    with _LOCK:
        return _NOTE_POOLS.setdefault(id(llm), queue.Queue())


def _session_block(s: Session) -> str:
    return f"{session_header(s)}\n{format_turns(s.turns)}"


def chunk_sessions(sessions: list[Session], chunk_tokens: int) -> list[list[Session]]:
    parts: list[list[Session]] = []
    size = 0
    for s in sessions:
        t = estimate_tokens(_session_block(s))
        if parts and size + t <= chunk_tokens:
            parts[-1].append(s)
            size += t
        else:
            parts.append([s])
            size = t
    return parts


class ProgressMd(AgenticFiles):
    name = "progress_md"
    agentic = True

    def __init__(self, llm=None, timeout: float = 900.0, bash: bool = True, chunk_tokens: int = 100_000):
        super().__init__(llm, timeout=timeout, bash=bash)
        self.params["chunk_tokens"] = int(chunk_tokens)
        self.chunk_tokens = int(chunk_tokens)
        self.extra_system = FILES_NOTES
        self.notes = ""

    def _write_store(self, root: Path) -> None:
        super()._write_store(root)
        (root / "progress.md").write_text(self.notes, encoding="utf-8")

    def _parts(self) -> list[list[Session]]:
        return chunk_sessions(sorted(self.sessions, key=lambda s: s.date or ""), self.chunk_tokens)

    def _note_cmd(self, llm) -> list[str]:
        cmd = [llm.exe, "-p", "--model", llm.model, "--output-format", "stream-json", "--verbose",
               "--input-format", "stream-json", "--tools", NOTE_TOOLS, "--allowedTools", NOTE_TOOLS,
               "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "",
               "--system-prompt", NOTES_SYSTEM]
        if llm.effort:
            cmd += ["--effort", llm.effort]
        return cmd

    def _build_notes(self, llm) -> tuple[list[dict], int, int]:
        parts = self._parts()
        pool = _note_pool(llm)
        try:
            sp, root = pool.get_nowait()
        except queue.Empty:
            root = Path(tempfile.mkdtemp(prefix="memlab_notes_"))
            sp = _SessionProc(self._note_cmd(llm), str(root))
            with _LOCK:
                _ALL.append((sp, root))
        notes_file = root / "progress.md"
        notes_file.write_text(NOTES_SEED, encoding="utf-8")
        steps, tin, tout = [], 0, 0
        try:
            for i, part in enumerate(parts, 1):
                t0 = time.time()
                sp.turn("/clear", 60)
                ev = sp.turn(NOTES_TEMPLATE.format(part=i, parts=len(parts),
                                                   sessions="\n\n".join(_session_block(s) for s in part)),
                             self.timeout)
                if ev.get("is_error"):
                    raise RuntimeError(f"claude failed while writing notes: {str(ev.get('result'))[:300]}")
                u = ev.get("usage") or {}
                cin = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                  "cache_read_input_tokens"))
                tin += cin
                tout += u.get("output_tokens") or 0
                calls = [b for e in sp.last if e.get("type") == "assistant"
                         for b in e["message"].get("content", []) if b.get("type") == "tool_use"]
                text = notes_file.read_text(encoding="utf-8") if notes_file.exists() else ""
                st = {"step": 0, "action": "notes", "arg": {"part": i, "of": len(parts), "sessions": len(part)},
                      "reason": "", "in_tokens": cin, "sec": round(time.time() - t0, 2),
                      "tools": [b.get("name") for b in calls], "result_chars": len(text),
                      "result_excerpt": text[:400]}
                out = [o for b in calls for o in outside_access(b.get("input", {}), root)]
                if out:
                    st["outside"] = out
                steps.append(st)
        except Exception:
            sp.close()
            raise
        notes = redact(notes_file.read_text(encoding="utf-8") if notes_file.exists() else "")
        pool.put((sp, root))
        if steps:
            steps[-1]["notes_text"] = notes
        self.notes = notes
        return steps, tin, tout

    def run_agent(self, llm, question: str, question_date: str) -> AgentResult:
        if isinstance(llm, EstimateLLM):
            parts = self._parts()
            body = sum(estimate_tokens(_session_block(s)) for p in parts for s in p)
            return AgentResult(text="[dry-run]", ingest_input_tokens=body, ingest_output_tokens=len(parts) * 1_000)
        if isinstance(llm, MockLLM):
            self.notes = "\n".join(session_header(s) for s in self.sessions)
            note_steps, tin, tout = [{"step": 0, "action": "notes", "arg": {"part": 1, "of": 1},
                                      "reason": "", "result_chars": len(self.notes),
                                      "result_excerpt": self.notes[:400], "notes_text": self.notes}], 0, 0
        elif isinstance(llm, ClaudeCodeSessionLLM):
            note_steps, tin, tout = self._build_notes(llm)
        else:
            raise ValueError("progress_md needs the claude-code-session backend")
        res = super().run_agent(llm, question, question_date)
        res.steps = note_steps + res.steps
        for n, st in enumerate(res.steps, 1):
            st["step"] = n
        res.ingest_input_tokens, res.ingest_output_tokens = tin, tout
        return res
