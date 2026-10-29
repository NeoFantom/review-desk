"""Build: paper + reviews -> build.json (rendered blocks, located comments, report).

The build output is derived data; it is rebuilt whenever the paper or the
reviews file changes.  Human/agent decisions live in the state file.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import latex, markdown, reviews
from .doc import esc, insert_sentinels, overlaps_partially, sentinels_to_html, strip_sentinels


def locate(clean: str, anchor: str, occurrence: int = 1):
    """Find anchor in clean source: (start, end, method) or None.

    Exact match first, then a whitespace-insensitive match (line breaks and
    indentation in the source often differ from what was copied).
    """
    if not anchor:
        return None
    pos = -1
    for _ in range(max(occurrence, 1)):
        pos = clean.find(anchor, pos + 1)
        if pos < 0:
            break
    if pos >= 0:
        return pos, pos + len(anchor), "exact"
    norm, idx, prev_ws = [], [], False
    for k, ch in enumerate(clean):
        if ch.isspace():
            if not prev_ws:
                norm.append(" ")
                idx.append(k)
            prev_ws = True
        else:
            norm.append(ch)
            idx.append(k)
            prev_ws = False
    target = re.sub(r"\s+", " ", anchor.strip())
    j = "".join(norm).find(target)
    if j < 0 or not target:
        return None
    return idx[j], idx[j + len(target) - 1] + 1, "whitespace"


def _module(kind):
    return latex if kind == "tex" else markdown


def build(paper: Path, reviews_path: Path | None) -> dict:
    paper = Path(paper)
    src = paper.read_text(encoding="utf-8")
    kind = "tex" if paper.suffix.lower() in (".tex", ".ltx") else "md"
    mod = _module(kind)
    doc = mod.parse(src)
    comments = reviews.load(reviews_path) if reviews_path else []

    marks = {}                 # mark_no -> comment id
    report = []
    for c in comments:
        c["blocks"], c["anchor_status"] = [], "none"
        for a in c["anchors"]:
            hit = locate(doc.clean, a, int(c.get("occurrence", 1) or 1))
            if not hit:
                continue
            s, e, how = hit
            n = len(marks)
            marks[n] = c["id"]
            hit_blocks = [b for b in doc.blocks if b.start < e and s < b.end]
            if len(hit_blocks) == 1 and _inline_ok(doc, mod, hit_blocks[0], s, e):
                b = hit_blocks[0]
                b.marks.append((s, e, n))
            else:
                for b in hit_blocks:
                    b.block_marks.append(n)
            c["blocks"] += [b.id for b in hit_blocks if b.id not in c["blocks"]]
            c["anchor_status"] = "guessed" if c["guessed"] else ("ok" if how == "exact" else "fuzzy")
            c["line"] = c.get("line") or latex.line_of(doc.clean, s)
        if c["anchors"] and not c["blocks"]:
            c["anchor_status"] = "unmatched" if not c["guessed"] else "none"
            if not c["guessed"]:
                report.append({"comment": c["id"], "problem": "anchor not found in paper",
                               "anchors": c["anchors"]})

    blocks = []
    for b in doc.blocks:
        inner = b.meta.get("inner")
        raw = doc.clean[inner[0]:inner[1]] if inner else ""
        rel = [(s - inner[0], e - inner[0], n) for s, e, n in b.marks] if inner else []
        html = mod.render(doc, b, insert_sentinels(raw, rel))
        for _, _, n in b.marks:      # a mark lost or split by the converter -> block mark
            o, cl = html.count(f"{n}"), html.count(f"{n}")
            if o != 1 or cl != 1 or html.find(f"{n}") > html.find(f"{n}"):
                html = html.replace(f"{n}", "").replace(f"{n}", "")
                b.block_marks.append(n)
        html = sentinels_to_html(html, marks)
        blocks.append({"id": b.id, "kind": b.kind, "line": b.line, "start": b.start, "end": b.end,
                       "html": strip_sentinels(html),
                       "cids": sorted({marks[n] for n in b.block_marks})})

    figures = sorted({g for b in doc.blocks if b.kind == "figure" for g in b.meta.get("graphics", [])})
    title = latex._conv(doc, doc.title) if kind == "tex" and doc.title else esc(doc.title or paper.stem)
    digest = hashlib.sha1((src + json.dumps(comments, sort_keys=True)).encode()).hexdigest()[:12]
    return {"build_id": digest, "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "paper": paper.name, "kind": kind, "title": title,
            "macros": {k: v[1] for k, v in getattr(doc, "macros", {}).items() if v[0] == 0},
            "blocks": blocks, "comments": comments, "report": report, "figures": figures}


def _inline_ok(doc, mod, b, s, e) -> bool:
    inner = b.meta.get("inner")
    if not inner or s < inner[0] or e > inner[1]:
        return False
    spans, points = mod.forbidden(doc, b)
    if any(overlaps_partially((s, e), sp) for sp in spans):
        return False
    if any(s < p < e for p in points):
        return False
    return not any(overlaps_partially((s, e), (s2, e2)) for s2, e2, _ in b.marks)


def block_for(build_out: dict, clean_src: str, quote: str):
    """Block id holding quote in the source (used for agent proposals)."""
    hit = locate(clean_src, quote)
    if not hit:
        return None
    for b in build_out["blocks"]:
        if b["start"] <= hit[0] < b["end"]:
            return b["id"]
    return None


def format_report(out: dict) -> str:
    lines = [f"built {out['paper']}: {len(out['blocks'])} blocks, {len(out['comments'])} comments"]
    stat = {}
    for c in out["comments"]:
        stat[c["anchor_status"]] = stat.get(c["anchor_status"], 0) + 1
    lines.append("anchors: " + ", ".join(f"{k}={v}" for k, v in sorted(stat.items())))
    for r in out["report"]:
        lines.append(f"  ! {r['comment']}: {r['problem']}: " + " | ".join(r["anchors"])[:160])
    return "\n".join(lines)
