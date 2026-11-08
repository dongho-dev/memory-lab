"""Thin LLM wrappers: the real Anthropic client, a dry-run estimator and a test mock."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

# Rough English chars-per-token for cost estimates only (deliberately conservative).
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
        import anthropic  # imported lazily so tests and dry runs need no key

        self.client = anthropic.Anthropic(max_retries=max_retries, timeout=timeout)
        self.model = model
        self.effort = effort

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion:
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
        )
        if system:
            kwargs["system"] = system
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        resp = self.client.messages.create(**kwargs)
        # Thinking blocks (if any) are skipped; only text blocks form the answer.
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
               # No user/project/local settings: otherwise the user's global CLAUDE.md is
               # injected into every answer (checked 2026-11-08). Leaves ~940 fixed tokens of
               # Claude Code overhead per call, counted in input_tokens.
               "--setting-sources", "",
               # The CLI always sends a system prompt and the API rejects a blank one, so a
               # call with no system (the judge) gets the most neutral text instead of
               # Claude Code's long default prompt.
               "--system-prompt", system or "You are a helpful assistant."]
        if self.effort:
            cmd += ["--effort", self.effort]
        return cmd

    def complete(self, system: str, user: str, max_tokens: int = 8192) -> Completion:
        # max_tokens is not exposed by the CLI; answers are short, so it is ignored.
        import json
        import subprocess
        import time

        last = ""
        for attempt in range(self.max_retries):
            # The prompt goes through stdin: full histories exceed the Windows command-line limit.
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
                    break  # retrying cannot fix a login problem
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
        self.events.put(None)  # process ended

    def alive(self) -> bool:
        return self.proc.poll() is None

    def turn(self, text: str, timeout: float) -> dict:
        import json
        import queue
        import time

        self.proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n")
        self.proc.stdin.flush()
        deadline = time.time() + timeout
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

        atexit.register(self.close)  # Windows does not end child processes with the parent

    def _cmd(self, system: str) -> list[str]:
        cmd = super()._cmd(system)
        cmd.remove("--disable-slash-commands")  # /clear is a slash command
        return cmd + ["--input-format", "stream-json", "--verbose",
                      "--output-format", "stream-json"]

    def _checkout(self, system: str) -> _SessionProc:
        import queue

        with self._lock:
            q = self._idle.setdefault(system, queue.Queue())
        try:
            return q.get_nowait()
        except queue.Empty:  # pool grows to the number of concurrent callers
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
                sp.close()  # drop a broken process; the next try starts a new one
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

    def close(self) -> None:
        for sp in self._all:
            sp.close()


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
        m = _MEMORY_RE.search(user)
        ctx = m.group(1).strip() if m else ""
        from .prompts import NO_MEMORY

        text = ctx if ctx and ctx != NO_MEMORY else "I don't know."
        return Completion(text, estimate_tokens(system + user), estimate_tokens(text))
