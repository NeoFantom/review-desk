"""Config and the state file (the single source of truth for decisions).

review-desk.json (config, next to your paper):

    {"paper": "paper.tex", "reviews": "reviews.md",
     "state": "review-state.json", "port": 8765, "lang": "en",
     "build_cmd": null}

review-state.json (written by the page and the agent, readable by both):

    {"version": 1,
     "comments": {"R1.2": {"status": "revised", "root_cause": "structure",
                           "root_cause_note": "", "response": "...",
                           "changes": "...", "updated": "..."}},
     "notes": [{"id": "n...", "status": "new|working|done|hold", ...}]}
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:          # Windows
    fcntl = None
    import msvcrt

STATUSES = ["todo", "analyzing", "revised", "replied"]
ROOT_CAUSES = ["misread", "our_error", "weak_evidence", "structure", "other"]
NOTE_STATUSES = ["new", "working", "done", "hold"]
CONFIG_NAME = "review-desk.json"
DEFAULTS = {"paper": None, "reviews": None, "state": "review-state.json",
            "port": 8765, "lang": "en", "build_cmd": None, "title": None}


class Config(dict):
    @property
    def root(self) -> Path:
        return Path(self["_root"])

    def path(self, key) -> Path | None:
        v = self.get(key)
        return (self.root / v).resolve() if v else None

    @property
    def cache(self) -> Path:
        return self.root / ".review-desk"


def find_config(explicit: str | None = None) -> Path | None:
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("REVIEW_DESK_CONFIG")
    if env:
        return Path(env).resolve()
    d = Path.cwd().resolve()
    for cand in [d, *d.parents]:
        if (cand / CONFIG_NAME).exists():
            return cand / CONFIG_NAME
    return None


def load_config(path: Path) -> Config:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg = Config({**DEFAULTS, **data})
    cfg["_root"] = str(Path(path).resolve().parent)
    if not cfg.get("paper"):
        raise SystemExit(f"{path}: 'paper' is required")
    return cfg


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class State:
    """JSON state file: atomic writes, thread lock + OS file lock for read-modify-write."""

    class Unchanged(Exception):
        """Raise inside transaction() to leave the file untouched."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)

    def load(self) -> dict:
        with self.lock:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            else:
                d = {}
            d.setdefault("version", 1)
            d.setdefault("comments", {})
            d.setdefault("notes", [])
            return d

    def save(self, d: dict):
        with self.lock:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
            self.changed.notify_all()

    @contextmanager
    def _file_lock(self):
        with open(str(self.path) + ".lock", "a+") as f:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            else:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_UN)
                else:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    @contextmanager
    def transaction(self):
        """with state.transaction() as d: change d; it is saved on exit."""
        with self.lock, self._file_lock():
            d = self.load()
            try:
                yield d
            except State.Unchanged:
                return
            self.save(d)
