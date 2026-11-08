"""Small helpers for append-only JSONL files (safe to resume after a crash)."""
from __future__ import annotations

import functools
import json
import threading
from pathlib import Path


def read_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


@functools.lru_cache(maxsize=1)
def _account_email() -> str:
    """Claude Code tells the model the signed-in account's email; it must never be saved."""
    try:
        data = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
        return str((data.get("oauthAccount") or {}).get("emailAddress") or "")
    except Exception:
        return ""


def redact(text: str) -> str:
    email = _account_email()
    return text.replace(email, "[account-email]") if email and email in text else text


class JsonlWriter:
    """Thread-safe appender; each row is flushed immediately."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, row: dict) -> None:
        line = redact(json.dumps(row, ensure_ascii=False))
        with self._lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()


def write_json(path: str | Path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_json(path: str | Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def utf8_stdout() -> None:
    """Windows consoles default to a legacy code page (e.g. cp949) that cannot print
    characters like '≈' or '–'; switch the CLI's output streams to UTF-8."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
