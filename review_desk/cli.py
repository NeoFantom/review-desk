"""review-desk command line: set up, build, serve, and the agent's side of the mailbox.

    review-desk init paper.tex reviews.md     write review-desk.json
    review-desk build                         paper + reviews -> page data, anchor report
    review-desk serve [--open]                page + mailbox on http://127.0.0.1:PORT/

  agent side (talks to the running server):
    review-desk wait [--timeout S]            block until notes arrive, print them (JSON), exit
    review-desk wait --no-block               take whatever is pending now (polling / batch mode)
    review-desk list [--all] [--json]         inbox: open notes + comments not yet replied
    review-desk show R1.2                     one comment with its decision fields
    review-desk reply ID --title T --reply R [--hold]
    review-desk propose --title T --text X [--quote Q] [--comment R1.2]
    review-desk comment R1.2 [--status S] [--root-cause C] [--response R] [--changes X]
    review-desk export [--format md|tex] [-o FILE]

  If the server cannot be reached (not running, or an agent sandbox without
  network), the agent-side commands work on the state file directly.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import build as buildmod
from . import export as exportmod
from .store import CONFIG_NAME, ROOT_CAUSES, STATUSES, State, find_config, load_config


def _cfg(a, required=True):
    path = find_config(a.config)
    if not path or not path.exists():
        if required:
            raise SystemExit(f"no {CONFIG_NAME} found (run `review-desk init` or pass --config)")
        return None
    return load_config(path)


def _base(a) -> str:
    if a.url:
        return a.url.rstrip("/")
    if os.environ.get("REVIEW_DESK_URL"):
        return os.environ["REVIEW_DESK_URL"].rstrip("/")
    cfg = _cfg(a, required=False)
    port = a.port or (cfg["port"] if cfg else 8765)
    return f"http://127.0.0.1:{port}"


def _http(a, path, data, timeout):
    req = urllib.request.Request(_base(a) + path,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body, ctype = r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"error {e.code}: {e.read().decode(errors='replace')}")
    return json.loads(body) if "json" in ctype else body.decode()


_LOCAL = {"/api/reply": "reply", "/api/propose": "propose", "/api/comment": "set_comment"}


def _local(a, path, data):
    """Same operations straight on the state file (server down, or sandbox without network)."""
    from .core import Desk
    if getattr(a, "_desk", None) is None:
        a._desk = Desk(_cfg(a))
    route = path.split("?")[0]
    if route == "/api/state":
        return a._desk.snapshot()
    if route == "/api/wait":
        return a._desk.claim(mark_poll=True)
    try:
        return getattr(a._desk, _LOCAL[route])(data)
    except (ValueError, KeyError) as e:
        raise SystemExit(f"error: {str(e).strip(chr(39))}")


def call(a, path, data=None, timeout=70):
    """Talk to the server; fall back to the state file when it cannot be reached."""
    if not a.offline:
        try:
            return _http(a, path, data, timeout)
        except (urllib.error.URLError, OSError) as e:
            if a.url or os.environ.get("REVIEW_DESK_URL") or not _cfg(a, required=False):
                raise
            print(f"[review-desk] server not reachable at {_base(a)} ({getattr(e, 'reason', e)}); "
                  "using the state file directly", file=sys.stderr)
            a.offline = True
    return _local(a, path, data)


def _text(v):
    """'-' reads the value from stdin; '@file' reads it from a file."""
    if v == "-":
        return sys.stdin.read()
    if v and v.startswith("@") and Path(v[1:]).is_file():
        return Path(v[1:]).read_text(encoding="utf-8")
    return v


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- commands

def cmd_init(a):
    paper = Path(a.paper).resolve()
    if not paper.exists():
        raise SystemExit(f"{paper} not found")
    where = paper.parent
    target = where / CONFIG_NAME
    if target.exists() and not a.force:
        raise SystemExit(f"{target} exists (use --force)")
    cfg = {"paper": paper.name, "reviews": None, "state": "review-state.json",
           "port": a.port or 8765, "lang": a.lang, "build_cmd": None}
    if a.reviews:
        rv = Path(a.reviews).resolve()
        cfg["reviews"] = os.path.relpath(rv, where)
    target.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {target}")


def cmd_build(a):
    cfg = _cfg(a)
    b = buildmod.build(cfg.path("paper"), cfg.path("reviews"))
    cfg.cache.mkdir(exist_ok=True)
    (cfg.cache / "build.json").write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8")
    print(buildmod.format_report(b))
    if cfg.get("build_cmd") and not a.no_cmd:
        print(f"$ {cfg['build_cmd']}")
        r = subprocess.run(cfg["build_cmd"], shell=True, cwd=cfg.root)
        if r.returncode:
            raise SystemExit(r.returncode)
    if a.strict and b["report"]:
        raise SystemExit(1)


def cmd_serve(a):
    from .server import serve
    cfg = _cfg(a)
    if a.port:
        cfg["port"] = a.port
    serve(cfg, open_browser=a.open)


def cmd_wait(a):
    if a.no_block:
        out(call(a, "/api/wait?timeout=0"))
        return
    deadline = time.time() + a.timeout if a.timeout else None
    while True:
        step = 50 if deadline is None else max(0, min(50, deadline - time.time()))
        try:
            got = call(a, f"/api/wait?timeout={step:.0f}", timeout=step + 20)
        except (urllib.error.URLError, OSError) as e:      # explicit --url that is down
            print(f"review-desk server unreachable at {_base(a)}: {e}", file=sys.stderr)
            raise SystemExit(2)
        if got:
            out(got)
            return
        if deadline is not None and time.time() >= deadline:
            out([])
            return
        if a.offline:
            time.sleep(2)


def cmd_list(a):
    s = call(a, "/api/state")
    notes = [n for n in s["notes"] if a.all or n["status"] != "done"]
    comments = [c for c in s["comments"] if a.all or c["status"] != "replied"]
    if a.json:
        out({"notes": notes, "comments": comments, "report": s["report"]})
        return
    print(f"# {s['title']}  (build {s['build_id']})")
    print(f"\nnotes ({len(notes)}):")
    for n in notes:
        where = f"line {n['line']}" if n.get("line") else (n.get("comment") or "-")
        print(f"  {n['id']}  {n['status']:<7} {n['author']:<5} {where:<10} | "
              f"{n['text'][:70].replace(chr(10), ' ')}" + (f" | {n['title']}" if n.get("title") else ""))
    print(f"\ncomments ({len(comments)}):")
    for c in comments:
        print(f"  {c['id']:<7} {c['status']:<9} {(c['root_cause'] or '-'):<13} "
              f"{c['anchor_status']:<9} | {c['text'][:70].replace(chr(10), ' ')}")
    if s["report"]:
        print("\nanchor problems:")
        for r in s["report"]:
            print(f"  {r['comment']}: {r['problem']}")


def cmd_show(a):
    s = call(a, "/api/state")
    for c in s["comments"]:
        if c["id"] == a.id:
            out(c)
            return
    raise SystemExit(f"no comment {a.id}")


def cmd_reply(a):
    out(call(a, "/api/reply", {"id": a.id, "status": "hold" if a.hold else "done",
                               "title": a.title, "reply": _text(a.reply)}))


def cmd_propose(a):
    d = {"title": a.title, "text": _text(a.text), "quote": a.quote}
    if a.comment:
        d["comment"] = a.comment
    out(call(a, "/api/propose", d))


def cmd_comment(a):
    d = {"id": a.id, "actor": "agent"}
    for k in ("status", "root_cause", "root_cause_note", "response", "changes"):
        v = getattr(a, k)
        if v is not None:
            d[k] = _text(v)
    out(call(a, "/api/comment", d))


def cmd_export(a):
    cfg = _cfg(a)
    b = buildmod.build(cfg.path("paper"), cfg.path("reviews"))
    state = State(cfg.path("state")).load()["comments"]
    text = (exportmod.latex if a.format == "tex" else exportmod.markdown)(b["title"], b["comments"], state)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"wrote {a.output}")
    else:
        sys.stdout.write(text)


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)     # accepted before or after the command
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help=f"path to {CONFIG_NAME} (default: search upward from cwd)")
    common.add_argument("--url", default=argparse.SUPPRESS,
                        help="server URL (default: http://127.0.0.1:<port from config>)")
    common.add_argument("--port", type=int, default=argparse.SUPPRESS)
    common.add_argument("--offline", action="store_true", default=argparse.SUPPRESS,
                        help="work on the state file directly, without the server")
    ap = argparse.ArgumentParser(prog="review-desk", description=__doc__, parents=[common],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    _add = sub.add_parser
    sub.add_parser = lambda *x, **k: _add(*x, parents=[common], **k)

    p = sub.add_parser("init", help="write review-desk.json next to the paper")
    p.add_argument("paper")
    p.add_argument("reviews", nargs="?")
    p.add_argument("--lang", default="en", choices=["en", "zh"])
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("build", help="render the paper and locate the comments")
    p.add_argument("--no-cmd", action="store_true", help="skip build_cmd from the config")
    p.add_argument("--strict", action="store_true", help="exit 1 if any anchor is not found")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("serve", help="serve the page and the mailbox on 127.0.0.1")
    p.add_argument("--open", action="store_true")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("wait", help="agent: block until notes arrive")
    p.add_argument("--timeout", type=float, default=0, help="give up after S seconds (0 = never)")
    p.add_argument("--no-block", action="store_true", help="return pending notes now, maybe []")
    p.set_defaults(fn=cmd_wait)

    p = sub.add_parser("list", help="open notes and unreplied comments")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show", help="one comment (JSON)")
    p.add_argument("id")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("reply", help="agent: answer a note")
    p.add_argument("id")
    p.add_argument("--title", default="", help="short task title shown on the page")
    p.add_argument("--reply", default="", help="what was done ('-' = stdin, '@file')")
    p.add_argument("--hold", action="store_true", help="question back to the author; nothing done yet")
    p.set_defaults(fn=cmd_reply)

    p = sub.add_parser("propose", help="agent: suggest a change the author must approve")
    p.add_argument("--title", required=True)
    p.add_argument("--text", required=True, help="the proposal ('-' = stdin, '@file')")
    p.add_argument("--quote", default="", help="exact source text the proposal is about")
    p.add_argument("--comment", help="reviewer comment id, e.g. R1.2")
    p.set_defaults(fn=cmd_propose)

    p = sub.add_parser("comment", help="agent: update a reviewer comment's decision fields")
    p.add_argument("id")
    p.add_argument("--status", choices=[s for s in STATUSES if s != "replied"])
    p.add_argument("--root-cause", dest="root_cause", choices=ROOT_CAUSES)
    p.add_argument("--root-cause-note", dest="root_cause_note")
    p.add_argument("--response", help="draft reply to the reviewer ('-' = stdin, '@file')")
    p.add_argument("--changes", help="what changed in the manuscript")
    p.set_defaults(fn=cmd_comment)

    p = sub.add_parser("export", help="response-letter skeleton")
    p.add_argument("--format", choices=["md", "tex"], default="md")
    p.add_argument("-o", "--output")
    p.set_defaults(fn=cmd_export)

    a = ap.parse_args(argv)
    for k in ("config", "url", "port", "offline"):
        if not hasattr(a, k):
            setattr(a, k, None)
    a.fn(a)


if __name__ == "__main__":
    main()
