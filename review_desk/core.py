"""The desk: build + state + mailbox operations, shared by the server and the CLI.

The HTTP server is one front end; the CLI's offline mode (agent sandboxes
that block localhost networking) is another.  Both change the state file only
through State.transaction(), which also takes an OS file lock, so the page
and an offline agent never overwrite each other's edits.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from . import build as buildmod
from .store import ROOT_CAUSES, STATUSES, Config, State, now


class Desk:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = State(cfg.path("state"))
        self.build_lock = threading.Lock()
        self.build = None
        self.build_key = None
        self.build_error = None
        self.waiters = 0
        self.last_poll = 0.0

    # ------------------------------------------------------------ build
    def current_build(self) -> dict:
        """Rebuild when the paper or the reviews file changed on disk."""
        paper, rev = self.cfg.path("paper"), self.cfg.path("reviews")
        key = tuple(p.stat().st_mtime_ns if p and p.exists() else 0 for p in (paper, rev))
        with self.build_lock:
            if key != self.build_key or self.build is None:
                try:
                    self.build = buildmod.build(paper, rev)
                    self.build_error = None
                    self.cfg.cache.mkdir(exist_ok=True)
                    (self.cfg.cache / "build.json").write_text(
                        json.dumps(self.build, ensure_ascii=False), encoding="utf-8")
                except Exception as e:                       # keep the last good build
                    self.build_error = f"{type(e).__name__}: {e}"
                    if self.build is None:
                        self.build = {"build_id": "error", "title": paper.name, "blocks": [],
                                      "comments": [], "report": [], "figures": [], "macros": {}}
                self.build_key = key
            return self.build

    def block(self, bid):
        return next((b for b in self.current_build()["blocks"] if b["id"] == bid), None)

    def comment(self, cid):
        return next((c for c in self.current_build()["comments"] if c["id"] == cid), None)

    def context(self, bid) -> str:
        b = self.block(bid)
        if not b:
            return ""
        src = self.cfg.path("paper").read_text(encoding="utf-8")
        return src[b["start"]:b["end"]][:4000]

    # ------------------------------------------------------------ reads
    def snapshot(self) -> dict:
        b = self.current_build()
        st = self.state.load()
        comments = []
        for c in b["comments"]:
            d = {"status": "todo", "root_cause": None, "root_cause_note": "",
                 "response": "", "changes": ""}
            d.update(st["comments"].get(c["id"], {}))
            comments.append({**c, **d})
        last = max(self.last_poll, st.get("agent_poll", 0))
        return {"build_id": b["build_id"], "built_at": b.get("built_at"), "title": b["title"],
                "paper": b.get("paper"), "report": b["report"], "macros": b["macros"],
                "build_error": self.build_error, "comments": comments, "notes": st["notes"],
                "agent": {"listening": self.waiters > 0, "last_poll": int(last) if last else None,
                          "now": int(time.time())},
                "lang": self.cfg.get("lang", "en"), "statuses": STATUSES, "root_causes": ROOT_CAUSES}

    def for_agent(self, note: dict) -> dict:
        """A note with everything an agent needs to act on it."""
        n = dict(note)
        if n.get("comment"):
            c = self.comment(n["comment"])
            if c:
                n["comment_text"] = c["text"]
                n["comment_anchors"] = c["anchors"]
        n["paper"] = str(self.cfg.path("paper"))
        return n

    # ------------------------------------------------------------ mailbox
    def claim(self, mark_poll=False) -> list:
        """Hand every 'new' note to the agent ('working'); [] when none."""
        with self.state.transaction() as st:
            if mark_poll:
                st["agent_poll"] = time.time()
            new = [n for n in st["notes"] if n["status"] == "new"]
            for n in new:
                n["status"] = "working"
                n["claimed"] = now()
            if not new and not mark_poll:
                raise State.Unchanged
        return [self.for_agent(n) for n in new]

    def _note(self, author, d, status):
        text = str(d.get("text", "")).strip()
        if not text:
            raise ValueError("empty note")
        n = {"id": ("n" if author == "user" else "p") + uuid.uuid4().hex[:8],
             "time": now(), "author": author, "status": status,
             "text": text[:20000], "quote": str(d.get("quote") or "")[:2000],
             "block": d.get("block"), "line": None, "context": "",
             "comment": d.get("comment") or None, "title": str(d.get("title") or "")[:200],
             "reply": "", "thread": []}
        if n["comment"] and not self.comment(n["comment"]):
            raise ValueError(f"no comment {n['comment']}")
        if not n["block"] and n["quote"] and author == "agent":
            src = self.cfg.path("paper").read_text(encoding="utf-8")
            n["block"] = buildmod.block_for(self.current_build(), src, n["quote"])
        if n["block"]:
            b = self.block(n["block"])
            if b:
                n["line"] = b["line"]
                n["context"] = self.context(n["block"])
            else:
                n["block"] = None
        return n

    def new_note(self, d) -> dict:
        n = self._note("user", d, "new")
        with self.state.transaction() as st:
            st["notes"].append(n)
        return n

    def propose(self, d) -> dict:
        n = self._note("agent", d, "hold")
        with self.state.transaction() as st:
            st["notes"].append(n)
        return n

    @staticmethod
    def _find(st, nid):
        for n in st["notes"]:
            if n["id"] == nid:
                return n
        raise KeyError(f"no note {nid}")

    @staticmethod
    def _archive_reply(n):
        if n.get("reply"):
            n["thread"].append({"who": "agent", "time": n.get("replied", ""),
                                "text": (n.get("title", "") + "\n" + n["reply"]).strip()})

    def reply(self, d) -> dict:
        status = d.get("status", "done")
        if status not in ("done", "hold"):
            raise ValueError("status must be done or hold")
        with self.state.transaction() as st:
            n = self._find(st, d["id"])
            self._archive_reply(n)
            n.update(status=status, title=str(d.get("title") or n.get("title", ""))[:200],
                     reply=str(d.get("reply", ""))[:20000], replied=now())
        return n

    def answer(self, d) -> dict:
        with self.state.transaction() as st:
            n = self._find(st, d["id"])
            self._archive_reply(n)
            n["thread"].append({"who": "user", "time": now(), "text": str(d.get("text", ""))[:20000]})
            n.update(status="new", reply="")
        return n

    def dismiss(self, d) -> dict:
        with self.state.transaction() as st:
            n = self._find(st, d["id"])
            n.update(status="done", dismissed=now())
        return n

    def set_comment(self, d) -> dict:
        cid = d["id"]
        if not self.comment(cid):
            raise KeyError(f"no comment {cid}")
        actor = d.get("actor", "user")
        if "status" in d:
            if d["status"] not in STATUSES:
                raise ValueError(f"status must be one of {STATUSES}")
            if d["status"] == "replied" and actor != "user":
                raise ValueError("only the author marks a comment as replied")
        if "root_cause" in d and d["root_cause"] not in ROOT_CAUSES + [None, ""]:
            raise ValueError(f"root_cause must be one of {ROOT_CAUSES}")
        with self.state.transaction() as st:
            c = st["comments"].setdefault(cid, {})
            if "status" in d:
                c["status"] = d["status"]
            if "root_cause" in d:
                c["root_cause"] = d["root_cause"] or None
            for k in ("root_cause_note", "response", "changes"):
                if k in d:
                    c[k] = str(d[k])[:20000]
            c["updated"] = now()
            c["updated_by"] = actor
        return {"id": cid, **c}
