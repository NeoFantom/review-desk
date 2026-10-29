"""Local HTTP server: the page, the state file, and the agent mailbox.

Listens on 127.0.0.1 only.  Every request must carry a local Host header
(blocks DNS rebinding); every POST must be JSON from the page's own origin
(blocks cross-site form posts).  Only bundled static files and the figures
named by the paper are served.

    GET  /api/state             comments + decisions, notes, agent presence
    GET  /api/paper             rendered blocks (fetch again when build_id changes)
    GET  /api/wait?timeout=50   agent: claim 'new' notes (block up to timeout s)
    GET  /api/export?format=md  response-letter skeleton (md | tex)
    POST /api/notes             page: {text, quote?, block?, comment?}
    POST /api/answer            page: {id, text}       hold -> new (back to agent)
    POST /api/dismiss           page: {id}             close a note/proposal
    POST /api/comment           page/agent: {id, status?, root_cause?, response?, changes?, actor}
    POST /api/reply             agent: {id, status: done|hold, title, reply}
    POST /api/propose           agent: {title, text, quote?, comment?}
"""
from __future__ import annotations

import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import build as buildmod
from . import export
from .core import Desk
from .store import Config

STATIC = Path(__file__).resolve().parent / "static"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MAX_BODY = 1 << 20


def make_handler(desk: Desk):
    static = {str(p.relative_to(STATIC)).replace("\\", "/"): p for p in STATIC.rglob("*") if p.is_file()}
    port = desk.cfg["port"]
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    class H(BaseHTTPRequestHandler):
        server_version = "review-desk"

        def log_message(self, *a):
            pass

        # ------------------------------------------------ plumbing
        def send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def js(self, obj, code=200):
            self.send(code, json.dumps(obj, ensure_ascii=False).encode())

        def guard(self, post=False) -> bool:
            if self.headers.get("Host", "") not in hosts:
                self.js({"error": "bad host"}, 403)
                return False
            if not post:
                return True
            origin = self.headers.get("Origin")
            if origin is not None and origin not in origins:
                self.js({"error": "bad origin"}, 403)
                return False
            if self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
                self.js({"error": "cross-site"}, 403)
                return False
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self.js({"error": "json only"}, 415)
                return False
            return True

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("body too large")
            d = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(d, dict):
                raise ValueError("object expected")
            return d

        # ------------------------------------------------ GET
        def do_GET(self):
            if not self.guard():
                return
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            path = u.path
            if path in ("/", "/index.html"):
                return self.file(STATIC / "app.html")
            if path.startswith("/static/"):
                f = static.get(unquote(path[len("/static/"):]))
                return self.file(f) if f else self.js({"error": "not found"}, 404)
            if path.startswith("/figures/"):
                return self.figure(unquote(path[len("/figures/"):]))
            if path == "/api/state":
                return self.js(desk.snapshot())
            if path == "/api/paper":
                b = desk.current_build()
                return self.js({"build_id": b["build_id"], "blocks": b["blocks"]})
            if path == "/api/wait":
                return self.wait(float(q.get("timeout", 50)))
            if path == "/api/export":
                b = desk.current_build()
                fmt = q.get("format", "md")
                fn = export.latex if fmt == "tex" else export.markdown
                text = fn(b["title"], b["comments"], desk.state.load()["comments"])
                return self.send(200, text.encode(), "text/plain; charset=utf-8")
            self.js({"error": "not found"}, 404)

        def file(self, f: Path):
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self.send(200, f.read_bytes(), ctype)

        def figure(self, name):
            b = desk.current_build()
            base = desk.cfg.path("paper").parent
            if name not in b["figures"]:
                return self.js({"error": "not found"}, 404)
            for cand in (name, *(name + e for e in sorted(IMAGE_EXT))):
                f = (base / cand).resolve()
                if f.suffix.lower() in IMAGE_EXT and f.is_file() and base in f.parents:
                    return self.file(f)
            self.js({"error": "not found"}, 404)

        def wait(self, timeout):
            timeout = max(0.0, min(timeout, 600.0))
            deadline = time.time() + timeout
            cond = desk.state.changed
            desk.waiters += 1
            try:
                while True:
                    desk.last_poll = time.time()
                    got = desk.claim()
                    if got or time.time() >= deadline:
                        return self.js(got)
                    with cond:          # woken by any save; re-check every 5 s for offline writers
                        cond.wait(min(deadline - time.time(), 5))
            finally:
                desk.waiters -= 1

        # ------------------------------------------------ POST
        def do_POST(self):
            if not self.guard(post=True):
                return
            try:
                d = self.body()
                fn = {"/api/notes": desk.new_note, "/api/answer": desk.answer,
                      "/api/dismiss": desk.dismiss, "/api/comment": desk.set_comment,
                      "/api/reply": desk.reply, "/api/propose": desk.propose}.get(urlparse(self.path).path)
                if not fn:
                    return self.js({"error": "not found"}, 404)
                return self.js(fn(d))
            except (ValueError, KeyError, TypeError) as e:
                return self.js({"error": str(e).strip("'\"")}, 400)

    return H


def serve(cfg: Config, open_browser=False):
    desk = Desk(cfg)
    b = desk.current_build()
    print(buildmod.format_report(b) if desk.build_error is None else f"build error: {desk.build_error}")
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", cfg["port"]), make_handler(desk))
    except OSError as e:
        raise SystemExit(f"cannot listen on 127.0.0.1:{cfg['port']} ({e.strerror}); "
                         "set another \"port\" in review-desk.json or pass --port") from None
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{cfg['port']}/"
    print(f"review-desk on {url}  (Ctrl-C to stop)", flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return httpd

