"""Thin LLM wrappers: the real Anthropic client, a dry-run estimator and a test mock."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

CHARS_PER_TOKEN = 3.0


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN) + 1


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLM(Protocol):
    model: str

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion: ...


class AnthropicLLM:
    """Messages API wrapper. Reads ANTHROPIC_API_KEY from the environment."""

    def __init__(self, model: str = "claude-sonnet-5-5", effort: str | None = None,
                 max_retries: int = 8, timeout: float = 600.0):
        import anthropic

        self.client = anthropic.Anthropic(max_retries=max_retries, timeout=timeout)
        self.model = model
        self.effort = effort

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion:
        return self._create(system, [{"role": "user", "content": user}], max_tokens)

    def chat(self, system: str) -> "_ApiChat":
        return _ApiChat(self, system)

    def _create(self, system: str, messages: list[dict], max_tokens: int) -> Completion:
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system:
            kwargs["system"] = system
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        resp = self.client.messages.create(**kwargs)
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        u = resp.usage
        input_tokens = (
            (u.input_tokens or 0)
            + (getattr(u, "cache_creation_input_tokens", 0) or 0)
            + (getattr(u, "cache_read_input_tokens", 0) or 0)
        )
        return Completion(text, input_tokens, u.output_tokens or 0)


class ClaudeCodeLLM:
    """Runs each call through the local Claude Code CLI (`claude -p`), so it bills the
    user's Claude subscription instead of the API. Tools, MCP servers and session
    persistence are off, and our system prompt replaces Claude Code's default one.
    Runs in an empty temp directory so no project CLAUDE.md is picked up."""

    def __init__(self, model: str = "claude-sonnet-5-5", effort: str | None = None,
                 timeout: float = 900.0, max_retries: int = 3, exe: str = "claude"):
        import shutil
        import tempfile

        self.exe = shutil.which(exe) or exe
        self.model = model
        self.effort = effort
        self.timeout = timeout
        self.max_retries = max_retries
        self.cwd = tempfile.mkdtemp(prefix="memlab_cc_")

    def _cmd(self, system: str) -> list[str]:
        cmd = [self.exe, "-p", "--model", self.model, "--output-format", "json",
               "--tools", "", "--strict-mcp-config", "--no-session-persistence",
               "--disable-slash-commands",
               "--setting-sources", "",
               "--system-prompt", system or "You are a helpful assistant."]
        if self.effort:
            cmd += ["--effort", self.effort]
        return cmd

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion:
        import json
        import subprocess
        import time

        last = ""
        for attempt in range(self.max_retries):
            p = subprocess.run(self._cmd(system), input=user, capture_output=True, text=True,
                               encoding="utf-8", timeout=self.timeout, cwd=self.cwd)
            try:
                out = json.loads(p.stdout)
            except json.JSONDecodeError:
                last = (p.stdout + p.stderr).strip()[:500]
            else:
                if not out.get("is_error"):
                    u = out.get("usage") or {}
                    tin = sum(u.get(k) or 0 for k in
                              ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                    return Completion((out.get("result") or "").strip(), tin, u.get("output_tokens") or 0)
                last = str(out.get("result"))[:500]
                if "authenticate" in last.lower():
                    break
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"claude -p failed: {last}")


class _SessionProc:
    """One long-lived `claude -p` in stream-json mode. Every call starts with /clear,
    so each question sees a fresh conversation (checked 2026-11-08: after /clear the
    model no longer knows earlier turns). /clear leaves a fixed ~120-token marker,
    so input tokens are ~120 higher than ClaudeCodeLLM's one-shot calls."""

    def __init__(self, cmd: list[str], cwd: str):
        import queue
        import subprocess
        import threading

        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     cwd=cwd, bufsize=1)
        self.events: "queue.Queue[str | None]" = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.proc.stdout:
            self.events.put(line)
        self.events.put(None)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def turn(self, text: str, timeout: float) -> dict:
        import json
        import queue
        import time

        self.proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
        self.proc.stdin.flush()
        deadline = time.time() + timeout
        self.last: list[dict] = []
        while True:
            try:
                line = self.events.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                raise TimeoutError("claude session gave no result in time")
            if line is None:
                raise RuntimeError("claude session exited")
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.last.append(ev)
            if ev.get("type") == "result":
                return ev

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


class ClaudeCodeSessionLLM(ClaudeCodeLLM):
    """Like ClaudeCodeLLM (subscription, no tools, no settings) but keeps a small pool of
    `claude` processes alive and clears the conversation between calls, instead of
    starting a new process per call. Much less CPU/RAM and ~2-3x faster per call."""

    def __init__(self, model: str = "claude-sonnet-5-5", effort: str | None = None,
                 timeout: float = 900.0, max_retries: int = 3, exe: str = "claude"):
        import queue
        import threading

        super().__init__(model, effort, timeout, max_retries, exe)
        self._idle: dict[str, "queue.Queue[_SessionProc]"] = {}
        self._all: list[_SessionProc] = []
        self._lock = threading.Lock()
        import atexit

        atexit.register(self.close)

    def _cmd(self, system: str) -> list[str]:
        cmd = super()._cmd(system)
        cmd.remove("--disable-slash-commands")
        return cmd + ["--input-format", "stream-json", "--verbose",
                      "--output-format", "stream-json"]

    def _checkout(self, system: str) -> _SessionProc:
        import queue

        with self._lock:
            q = self._idle.setdefault(system, queue.Queue())
        try:
            return q.get_nowait()
        except queue.Empty:
            sp = _SessionProc(self._cmd(system), self.cwd)
            with self._lock:
                self._all.append(sp)
            return sp

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion:
        import time

        last = ""
        for attempt in range(self.max_retries):
            sp = self._checkout(system)
            try:
                sp.turn("/clear", 60)
                ev = sp.turn(user, self.timeout)
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                sp.close()
            else:
                if not ev.get("is_error"):
                    self._idle[system].put(sp)
                    u = ev.get("usage") or {}
                    tin = sum(u.get(k) or 0 for k in
                              ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                    return Completion((ev.get("result") or "").strip(), tin, u.get("output_tokens") or 0)
                last = str(ev.get("result"))[:500]
                sp.close()
                if "authenticate" in last.lower():
                    break
            time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"claude session failed: {last}")

    def chat(self, system: str) -> "_ProcChat":
        """A multi-turn conversation on one kept-alive process (cleared once at the start)."""
        sp = self._checkout(system)
        try:
            sp.turn("/clear", 60)
        except Exception:
            sp.close()
            raise
        return _ProcChat(self, system, sp)

    def close(self) -> None:
        for sp in self._all:
            sp.close()


def _usage_completion(ev: dict) -> Completion:
    u = ev.get("usage") or {}
    tin = sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return Completion((ev.get("result") or "").strip(), tin, u.get("output_tokens") or 0)


class _ProcChat:
    def __init__(self, owner: ClaudeCodeSessionLLM, system: str, sp: _SessionProc):
        self.owner, self.system, self.sp, self.broken = owner, system, sp, False

    def send(self, text: str) -> Completion:
        try:
            ev = self.sp.turn(text, self.owner.timeout)
        except Exception:
            self.broken = True
            raise
        if ev.get("is_error"):
            self.broken = True
            raise RuntimeError(f"claude session error: {str(ev.get('result'))[:300]}")
        return _usage_completion(ev)

    def close(self) -> None:
        if self.broken:
            self.sp.close()
        else:
            self.owner._idle[self.system].put(self.sp)


class _ReplayChat:
    """Multi-turn on top of a single-shot complete(): resend the transcript every turn.
    Used by the one-process-per-call backend, the dry-run estimator and the test mock."""

    def __init__(self, llm, system: str):
        self.llm, self.system, self.turns = llm, system, []

    def send(self, text: str) -> Completion:
        self.turns.append(("user", text))
        if len(self.turns) == 1:
            prompt = text
        else:
            prompt = "\n\n".join(f"[{r}]\n{t}" for r, t in self.turns) + "\n\n[assistant]\n"
        c = self.llm.complete(self.system, prompt)
        self.turns.append(("assistant", c.text))
        return c

    def close(self) -> None:
        pass


class _ApiChat:
    def __init__(self, llm: "AnthropicLLM", system: str):
        self.llm, self.system, self.messages = llm, system, []

    def send(self, text: str) -> Completion:
        self.messages.append({"role": "user", "content": text})
        c = self.llm._create(self.system, self.messages, 8192)
        self.messages.append({"role": "assistant", "content": c.text or "(empty)"})
        return c

    def close(self) -> None:
        pass


def open_chat(llm, system: str):
    """Start a multi-turn conversation with any backend: chat.send(text) -> Completion, chat.close()."""
    return llm.chat(system) if hasattr(llm, "chat") else _ReplayChat(llm, system)


def make_llm(backend: str, model: str, effort: str | None):
    if backend == "api":
        return AnthropicLLM(model, effort=effort)
    if backend == "claude-code":
        return ClaudeCodeLLM(model, effort=effort)
    if backend == "claude-code-session":
        return ClaudeCodeSessionLLM(model, effort=effort)
    raise ValueError(f"unknown backend {backend!r} (api | claude-code | claude-code-session)")


class EstimateLLM:
    """Dry run: no API call, token counts estimated from text length."""

    def __init__(self, model: str, assumed_output_tokens: int = 500):
        self.model = model
        self.assumed_output_tokens = assumed_output_tokens

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion:
        return Completion("[dry-run]", estimate_tokens(system + user), self.assumed_output_tokens)


_MEMORY_RE = re.compile(r"<memory>\n?(.*?)\n?</memory>", re.S)


class MockLLM:
    """Deterministic stand-in for tests: 'answers' by echoing the memory it was given."""

    model = "mock"

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion:
        from .prompts import NO_MEMORY

        if "ACTION:" in system:
            if "<results" not in user:
                q = re.search(r"Question: (.*)", user)
                text = f"REASON: look up the question words.\nACTION: search: {q.group(1) if q else ''}"
            else:
                last = user.rsplit("<results", 1)[1]
                body = last.split(">", 1)[1].rsplit("</results>", 1)[0].strip()
                text = f"REASON: the results answer it.\nACTION: answer: {body or 'I dont know.'}"
            return Completion(text, estimate_tokens(system + user), estimate_tokens(text))
        m = _MEMORY_RE.search(user)
        ctx = m.group(1).strip() if m else ""
        text = ctx if ctx and ctx != NO_MEMORY else "I don't know."
        return Completion(text, estimate_tokens(system + user), estimate_tokens(text))
