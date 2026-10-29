"""Load reviewer comments from Markdown/plain text, JSON or YAML.

Text format (Markdown or .txt), one block per reviewer:

    ## Reviewer 1
    Comment 1: The abstract does not say how the energy error is measured.
    @anchor: energy error
    Comment 2: ...

A reviewer starts at a line containing "Reviewer N" / "Referee N"
(also 审稿人 N); a comment at "Comment N" or, if a reviewer has none, at a
numbered item "1." / "1)".  `@anchor: text` lines name the exact source
substring the comment is about (repeatable).  Without one, quoted phrases
of 12+ characters in the comment are tried as anchors (marked "guessed").

JSON/YAML: {"reviewers": [{"id": "1", "comments": [{"id": "1", "text": ...,
"anchors": [...]}]}]} or a flat list [{"reviewer": "1", "id": "1", ...}].
YAML needs PyYAML (optional dependency).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_REV = re.compile(r"^\W*(?:reviewer|referee|审稿人|审稿专家)\s*#?\s*([0-9A-Za-z]+)\b.*$", re.I)
_COM = re.compile(r"^\W*(?:comment|point|issue|意见)\s*#?\s*(\d+[a-z]?)\s*[:.)\-–]?\**\s*(.*)$", re.I)
_NUM = re.compile(r"^\s*\(?(\d+)[.)]\s+(.*)$")
_ANCH = re.compile(r"^\s*@anchor\s*:\s*(.*?)\s*$", re.I)
_QUOTE = re.compile(r"[\"“]([^\"”]{12,300})[\"”]")


def _comment(rid, cid, text, anchors=None, **extra):
    text = re.sub(r"[ \t]*(?<!\n)\n(?!\n)[ \t]*", " ", text.strip())   # unwrap hard line breaks
    c = {"id": f"R{rid}.{cid}", "reviewer": str(rid), "num": str(cid), "text": text,
         "anchors": [a for a in (anchors or []) if a], "guessed": False}
    if not c["anchors"]:
        c["anchors"] = [m.group(1).strip() for m in _QUOTE.finditer(text)]
        c["guessed"] = bool(c["anchors"])
    for k in ("section", "occurrence", "tags"):
        if extra.get(k) is not None:
            c[k] = extra[k]
    return c


def parse_text(src: str):
    reviewers, cur = [], None          # cur = [rid, [ (cid, lines, anchors) ], preamble]
    for ln in src.splitlines():
        rm = _REV.match(ln)
        if rm and not _COM.match(ln) and len(ln.strip()) < 80:
            cur = [rm.group(1), [], []]
            reviewers.append(cur)
            continue
        if cur is None:
            continue
        am = _ANCH.match(ln)
        if am and cur[1]:
            cur[1][-1][2].append(am.group(1).strip().strip("\"“”"))
            continue
        cm = _COM.match(ln)
        if cm:
            cur[1].append([cm.group(1), [cm.group(2)], []])
            continue
        if cur[1]:
            cur[1][-1][1].append(ln)
        else:
            cur[2].append(ln)
    out = []
    for rid, comments, pre in reviewers:
        if not comments:                  # fall back to "1." numbered items
            for ln in pre:
                nm = _NUM.match(ln)
                am = _ANCH.match(ln)
                if am and comments:
                    comments[-1][2].append(am.group(1).strip().strip("\"“”"))
                elif nm:
                    comments.append([nm.group(1), [nm.group(2)], []])
                elif comments:
                    comments[-1][1].append(ln)
        for cid, lines, anchors in comments:
            out.append(_comment(rid, cid, "\n".join(lines), anchors))
    return out


def _extra(c):
    return {k: c.get(k) for k in ("section", "occurrence", "tags")}


def parse_data(data):
    out = []
    if isinstance(data, dict):
        for r in data.get("reviewers", []):
            rid = str(r.get("id", len(out) + 1))
            for k, c in enumerate(r.get("comments", []), 1):
                if isinstance(c, str):
                    c = {"text": c}
                out.append(_comment(rid, c.get("id", k), c.get("text", ""),
                                    c.get("anchors") or ([c["anchor"]] if c.get("anchor") else []), **_extra(c)))
    elif isinstance(data, list):
        for k, c in enumerate(data, 1):
            out.append(_comment(c.get("reviewer", "1"), c.get("id", k), c.get("text", ""),
                                c.get("anchors") or ([c["anchor"]] if c.get("anchor") else []), **_extra(c)))
    return out


def load(path) -> list:
    path = Path(path)
    src = path.read_text(encoding="utf-8")
    suf = path.suffix.lower()
    if suf == ".json":
        comments = parse_data(json.loads(src))
    elif suf in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise SystemExit("YAML reviews need PyYAML (pip install pyyaml); "
                             "or use .json / .md") from e
        comments = parse_data(yaml.safe_load(src))
    else:
        comments = parse_text(src)
    seen = {}
    for c in comments:                     # keep ids unique
        if c["id"] in seen:
            seen[c["id"]] += 1
            c["id"] += f"-{seen[c['id']]}"
        else:
            seen[c["id"]] = 0
    return comments
