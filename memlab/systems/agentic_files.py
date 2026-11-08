"""Free agentic search: memory laid out as files, and the model just looks things up.

Each past session becomes a file (sessions/<date>_<session id>.md) in a folder. Claude Code runs
in that folder with its own read-only tools left on (Read, Grep, Glob) and is simply told to look
up what it needs. How to search, and for how long, is entirely the model's choice.

Default backend (claude-code-session): kept-alive `claude` processes, each with its own fixed
folder. Before every question the folder is rewritten and the conversation cleared with /clear.

Every tool call is recorded with the sentence the model wrote just before it (asked to say why),
the tool input, and an excerpt of what came back. The runner marks which results held an
answer turn. (The stated reason is the model's own account, not its hidden reasoning.)

Compare with agentic_search, where the model may only send queries to our BM25.
"""
from __future__ import annotations

import atexit
import json
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from ..data import Session, format_turns
from ..llm import ClaudeCodeLLM, ClaudeCodeSessionLLM, EstimateLLM, MockLLM, _SessionProc
from ..prompts import AGENT_FIRST, FILES_BASH_RULE, FILES_SYSTEM
from .agentic import AgentResult
from .base import MemorySystem

READ_ONLY_TOOLS = "Read,Grep,Glob"
_LINE_NO = re.compile(r"^\s*\d+[\t→]", re.M)

_WIN_PATH = re.compile(r"(?<![\w])[A-Za-z]:[\\/][^\s\"'`|;&<>()]*")
_UNIX_PATH = re.compile(r"(?<![\w.])/[a-zA-Z]/[^\s\"'`|;&<>()]*")
_POSIX_ROOT = re.compile(r"(?<![\w.])/(?:tmp|home|etc|usr|var|root|mnt|Users|proc)(?:/[^\s\"'`|;&<>()]*)?(?![\w])")
_ESCAPE = re.compile(r"(?<![\w.])\.\.(?:[\\/]|$)|~[\\/]|~(?=\s|$)|\$HOME|\$\{?USERPROFILE|\$\{?TEMP|\$\{?TMP|"
                     r"%[A-Za-z]+%|\$env:", re.I)
_OWN_SPILL = re.compile(r"\\\.claude\\projects\\[^\\]*memlab-files-")
_NETWORK = re.compile(r"\b(curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Start-BitsTransfer|"
                      r"git\s+clone|pip3?\s+install|npm\s+i|huggingface|requests\.|urllib|http\.client|"
                      r"socket\.|nc\s|ssh\s|scp\s)\b|https?://", re.I)


def outside_access(arg, root: Path) -> list[str]:
    """Reasons a tool call reached outside its folder (other paths, home/temp variables, '..',
    or the network). Empty if it stayed inside."""
    text = arg if isinstance(arg, str) else json.dumps(arg, ensure_ascii=False)
    text = text.replace("\\\\", "\\")
    base = str(root.resolve()).lower().replace("/", "\\").rstrip("\\")
    found = []
    for p in _WIN_PATH.findall(text):
        q = p.lower().replace("/", "\\")
        if not q.startswith(base) and not _OWN_SPILL.search(q):
            found.append(f"path {p[:120]}")
    for p in _UNIX_PATH.findall(text):
        win = (p[1] + ":" + p[2:]).lower().replace("/", "\\")
        if not win.startswith(base):
            found.append(f"path {p[:120]}")
    for p in _POSIX_ROOT.findall(text):
        if f"/{root.name.lower()}" not in p.lower():
            found.append(f"path {p[:120]}")
    found += [f"escape {m.group(0)}" for m in _ESCAPE.finditer(text)]
    found += [f"network {m.group(0)}" for m in _NETWORK.finditer(text)]
    return found

_POOLS: dict[int, "queue.Queue"] = {}
_ALL: list = []
_LOCK = threading.Lock()


def _pool(llm) -> "queue.Queue":
    with _LOCK:
        return _POOLS.setdefault(id(llm), queue.Queue())


@atexit.register
def _close_all() -> None:
    for sp, root in _ALL:
        sp.close()
        shutil.rmtree(root, ignore_errors=True)


def _file_name(s: Session) -> str:
    day = re.sub(r"[^0-9]", "-", s.date[:10]) if s.date else "undated"
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", s.session_id)
    return f"{day}_{sid}.md"


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return str(content)


class AgenticFiles(MemorySystem):
    name = "agentic_files"
    agentic = True

    def __init__(self, llm=None, timeout: float = 600.0, bash: bool = False):
        super().__init__(llm, bash=bool(bash))
        self.timeout = float(timeout)
        self.bash = bool(bash)
        self.extra_system = ""
        self.reset()

    def reset(self) -> None:
        self.sessions: list[Session] = []

    def ingest(self, session: Session) -> None:
        self.sessions.append(session)

    def build_context(self, question: str, question_date: str):
        raise NotImplementedError("agentic_files answers through run_agent()")

    def _write_store(self, root: Path) -> None:
        """(Re)write sessions/ for this question. Rewriting gives every file a new mtime, so a
        kept-alive process never reuses a read from an earlier question."""
        d = root / "sessions"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        for s in self.sessions:
            (d / _file_name(s)).write_text(f"# Session {s.session_id} · {s.date}\n\n{format_turns(s.turns)}\n",
                                           encoding="utf-8")

    def run_agent(self, llm, question: str, question_date: str) -> AgentResult:
        if isinstance(llm, EstimateLLM):
            return AgentResult(text="[dry-run]")
        prompt = AGENT_FIRST.format(question=question, question_date=question_date or "unknown")
        if isinstance(llm, MockLLM):
            root = Path(tempfile.mkdtemp(prefix="memlab_files_"))
            try:
                self._write_store(root)
                return self._mock(root, question)
            finally:
                shutil.rmtree(root, ignore_errors=True)
        if isinstance(llm, ClaudeCodeSessionLLM):
            return self._run_kept(llm, prompt)
        if isinstance(llm, ClaudeCodeLLM):
            return self._run_oneshot(llm, prompt)
        raise ValueError("agentic_files needs a Claude Code backend (claude-code-session or claude-code)")

    def after_run(self, root: Path, res: AgentResult) -> None:
        return None

    def extra_args(self) -> list[str]:
        return []

    def _cmd(self, llm: ClaudeCodeLLM) -> list[str]:
        tools = READ_ONLY_TOOLS + (",Bash" if self.bash else "")
        system = FILES_SYSTEM + (FILES_BASH_RULE if self.bash else "") + self.extra_system
        cmd = [llm.exe, "-p", "--model", llm.model, "--output-format", "stream-json", "--verbose",
               "--tools", tools, "--strict-mcp-config", "--no-session-persistence",
               "--setting-sources", "", "--system-prompt", system]
        if self.bash:
            cmd += ["--allowedTools", "Bash"]
        if llm.effort:
            cmd += ["--effort", llm.effort]
        return cmd + self.extra_args()

    def _run_kept(self, llm: ClaudeCodeSessionLLM, prompt: str) -> AgentResult:
        pool = _pool(llm)
        try:
            sp, root = pool.get_nowait()
        except queue.Empty:
            root = Path(tempfile.mkdtemp(prefix="memlab_files_"))
            sp = _SessionProc(self._cmd(llm) + ["--input-format", "stream-json"], str(root))
            with _LOCK:
                _ALL.append((sp, root))
        self._write_store(root)
        t0 = time.time()
        try:
            sp.turn("/clear", 60)
            sp.turn(prompt, self.timeout)
            res = self._parse(list(sp.last), t0, root)
            self.after_run(root, res)
        except Exception:
            sp.close()
            raise
        pool.put((sp, root))
        return res

    def _run_oneshot(self, llm: ClaudeCodeLLM, prompt: str) -> AgentResult:
        root = Path(tempfile.mkdtemp(prefix="memlab_files_"))
        try:
            self._write_store(root)
            t0 = time.time()
            p = subprocess.run(self._cmd(llm) + ["--disable-slash-commands"], input=prompt,
                               capture_output=True, text=True, encoding="utf-8",
                               timeout=self.timeout, cwd=root)
            events = []
            for line in p.stdout.splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            res = self._parse(events, t0, root, p.stderr)
            self.after_run(root, res)
            return res
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def _parse(self, events: list[dict], t0: float, root: Path, stderr: str = "") -> AgentResult:
        res = AgentResult(text="")
        steps: list[dict] = []
        by_id: dict[str, dict] = {}
        pending_text = ""
        shown: list[str] = []
        final = None
        for ev in events:
            if ev.get("type") == "assistant":
                for b in ev["message"].get("content", []):
                    if b.get("type") == "text":
                        pending_text = (pending_text + " " + b["text"]).strip()
                    elif b.get("type") == "tool_use":
                        st = {"step": len(steps) + 1, "action": b.get("name"), "arg": b.get("input", {}),
                              "reason": pending_text[:600]}
                        out = outside_access(b.get("input", {}), root)
                        if out:
                            st["outside"] = out
                        pending_text = ""
                        steps.append(st)
                        by_id[b.get("id")] = st
            elif ev.get("type") == "user":
                content = ev["message"].get("content")
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        text = _LINE_NO.sub("", _result_text(b.get("content")))
                        st = by_id.get(b.get("tool_use_id"))
                        if st is not None:
                            st["result_chars"] = len(text)
                            st["result_excerpt"] = text[:400]
                            st["result_text"] = text
                        shown.append(text)
            elif ev.get("type") == "result":
                final = ev
        if final is None or final.get("is_error"):
            msg = (final or {}).get("result") or stderr[-300:] or "no result event"
            raise RuntimeError(f"claude failed: {str(msg)[:300]}")
        u = final.get("usage") or {}
        res.text = (final.get("result") or "").strip()
        res.input_tokens = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                       "cache_read_input_tokens"))
        res.output_tokens = u.get("output_tokens") or 0
        steps.append({"step": len(steps) + 1, "action": "answer", "arg": res.text[:600],
                      "reason": pending_text[:600] if pending_text and pending_text != res.text else "",
                      "sec": round(time.time() - t0, 2)})
        res.steps = steps
        res.seen_text = "\n".join(shown)
        res.retrieved_session_ids = sorted({s.session_id for s in self.sessions
                                            if s.session_id in res.seen_text or _file_name(s) in res.seen_text})
        return res

    def _mock(self, root: Path, question: str) -> AgentResult:
        """Test stand-in: 'grep' the longest question word, read the matching files, echo them."""
        words = sorted(re.findall(r"[A-Za-z]{3,}", question), key=len, reverse=True)
        files = sorted((root / "sessions").glob("*.md"))
        hits = [f for f in files if words and words[0].lower() in f.read_text(encoding="utf-8").lower()]
        steps = [{"step": 1, "action": "Grep", "arg": {"pattern": words[0] if words else ""},
                  "reason": "find sessions that mention the key word.",
                  "result_text": "\n".join(f.name for f in hits), "result_chars": 0, "result_excerpt": ""}]
        shown = []
        for f in hits:
            text = f.read_text(encoding="utf-8")
            steps.append({"step": len(steps) + 1, "action": "Read", "arg": {"file_path": f.name},
                          "reason": "read the match.", "result_text": text, "result_chars": len(text),
                          "result_excerpt": text[:400]})
            shown.append(text)
        answer = "\n".join(shown) or "I don't know."
        steps.append({"step": len(steps) + 1, "action": "answer", "arg": answer[:600], "reason": ""})
        seen = "\n".join(shown)
        return AgentResult(text=answer, steps=steps, seen_text=seen,
                           retrieved_session_ids=sorted({s.session_id for s in self.sessions if s.session_id in seen}))
