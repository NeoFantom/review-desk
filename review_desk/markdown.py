"""Markdown -> blocks -> HTML (the subset papers drafted in Markdown use).

Headings, paragraphs, $$ display math $$, fenced code, images, lists,
blockquotes; inline $math$, `code`, **bold**, *italic*, [links](url).
"""
from __future__ import annotations

import re

from .doc import Block, esc, line_of
from .latex import Parsed

_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_IMG = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)[^)]*\)\s*$")
_INLINE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$|`([^`]+)`")


def parse(src: str) -> Parsed:
    clean = re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\n]", " ", m.group(0)), src, flags=re.S)
    p = Parsed("md", src, clean, [])
    lines = clean.split("\n")
    offs, o = [], 0
    for ln in lines:
        offs.append(o)
        o += len(ln) + 1
    blocks, i, n = [], 0, len(lines)
    if lines and lines[0].strip() == "---":           # YAML front matter
        for k in range(1, n):
            if lines[k].strip() == "---":
                for ln in lines[1:k]:
                    if ln.startswith("title:"):
                        p.title = ln[6:].strip().strip("\"'")
                i = k + 1
                break

    def end_of(k):            # offset just past line k's text
        return offs[k] + len(lines[k])

    while i < n:
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        h = _HEAD.match(ln)
        if h:
            if len(h.group(1)) == 1 and not blocks and h.group(2) == (p.title or h.group(2)):
                p.title = h.group(2)       # the leading H1 is the title, shown once
                i += 1
                continue
            s = offs[i] + ln.index(h.group(2)) if h.group(2) else offs[i]
            blocks.append(Block("heading", offs[i], end_of(i),
                                {"level": len(h.group(1)), "inner": (s, s + len(h.group(2)))}))
            i += 1
            continue
        if ln.lstrip().startswith("```"):
            j = i + 1
            while j < n and not lines[j].lstrip().startswith("```"):
                j += 1
            j = min(j, n - 1)
            blocks.append(Block("code", offs[i], end_of(j), {"text": "\n".join(lines[i + 1:j])}))
            i = j + 1
            continue
        if ln.strip().startswith("$$"):
            rest = ln.strip()[2:]
            if rest.rstrip().endswith("$$") and len(rest.strip()) > 2:
                tex, j = rest.rstrip()[:-2], i
            else:
                j = i + 1
                while j < n and "$$" not in lines[j]:
                    j += 1
                j = min(j, n - 1)
                tex = "\n".join([rest] + lines[i + 1:j] + [lines[j].split("$$")[0]])
            tag = re.search(r"\\tag\{([^}]*)\}", tex)
            blocks.append(Block("math", offs[i], end_of(j),
                                {"env": "displaymath", "tex": tex,
                                 "numbers": [tag.group(1)] if tag else []}))
            i = j + 1
            continue
        im = _IMG.match(ln)
        if im:
            blocks.append(Block("figure", offs[i], end_of(i),
                                {"env": "figure", "graphics": [im.group(2)], "name": "Figure",
                                 "inner": (offs[i] + ln.index("[") + 1, offs[i] + ln.index("]"))}))
            i += 1
            continue
        kind = "list" if _LIST.match(ln) else "para"
        j = i
        while j + 1 < n and lines[j + 1].strip() and not _HEAD.match(lines[j + 1]) \
                and not lines[j + 1].lstrip().startswith(("```", "$$")) \
                and (kind == "list" or not _LIST.match(lines[j + 1])):
            j += 1
        meta = {"inner": (offs[i], end_of(j))}
        if kind == "list":
            meta["tag"] = "ol" if re.match(r"^\s*\d", ln) else "ul"
        elif ln.lstrip().startswith(">"):
            meta["quote"] = True
        blocks.append(Block(kind, offs[i], end_of(j), meta))
        i = j + 1

    fig = 0
    for k, blk in enumerate(blocks):
        blk.id = f"b{k + 1}"
        blk.line = line_of(clean, blk.start)
        if blk.kind == "figure":
            fig += 1
            blk.meta["number"] = str(fig)
    p.blocks = blocks
    return p


def forbidden(p: Parsed, blk: Block):
    s, e = blk.meta["inner"]
    raw = p.clean[s:e]
    spans = [(s + m.start(), s + m.end()) for m in _INLINE.finditer(raw)]
    points = []
    if blk.kind == "list":
        points = [s + m.start() + 1 for m in re.finditer(r"\n\s*(?:[-*+]|\d+[.)])\s", raw)]
    return spans, points


def render(p: Parsed, blk: Block, raw: str) -> str:
    k = blk.kind
    if k == "heading":
        lv = min(blk.meta["level"] + 1, 4)
        return f"<h{lv}>{inline(raw)}</h{lv}>"
    if k == "para":
        if blk.meta.get("quote"):
            raw = re.sub(r"(?m)^\s*>\s?", "", raw)
            return "<blockquote><p>" + inline(raw) + "</p></blockquote>"
        return "<p>" + inline(raw) + "</p>"
    if k == "list":
        tag = blk.meta["tag"]
        items = re.split(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", raw)
        return f"<{tag}>" + "".join(f"<li>{inline(it)}</li>" for it in items if it.strip()) + f"</{tag}>"
    if k == "math":
        tex = re.sub(r"\\tag\{[^}]*\}|\\label\{[^}]*\}", "", blk.meta["tex"]).strip()
        nums = blk.meta.get("numbers")
        no = f"({nums[0]})" if nums else ""
        return f'<div class="rd-md">{esc(tex)}</div><span class="rd-eqno">{esc(no)}</span>'
    if k == "figure":
        g = blk.meta["graphics"][0]
        return (f'<figure><div class="rd-fig" data-src="{esc(g)}">{esc(g)}</div>'
                f"<figcaption><b>Figure {blk.meta['number']}.</b> {inline(raw)}</figcaption></figure>")
    if k == "code":
        return f"<pre>{esc(blk.meta['text'])}</pre>"
    return ""


def inline(s: str) -> str:
    out, last = [], 0
    for m in _INLINE.finditer(s):
        out.append(_text(s[last:m.start()]))
        if m.group(1) is not None:
            out.append(f'<span class="rd-m">{esc(m.group(1))}</span>')
        else:
            out.append(f"<code>{esc(m.group(2))}</code>")
        last = m.end()
    out.append(_text(s[last:]))
    return "".join(out)


def _text(s: str) -> str:
    t = esc(s.replace("\n", " "))
    t = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)|(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)",
               lambda m: f"<em>{m.group(1) or m.group(2)}</em>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1", t)
    return t.replace("\\$", "$")
