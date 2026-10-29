"""Shared document model: a paper is a list of blocks with source spans.

A block knows its span [start, end) in the *cleaned* source (comments blanked
out, so offsets and line numbers equal those of the original file).  Anchors
are located in that source, then turned into marks: an inline mark when the
anchor sits inside one block's prose, a block mark otherwise.

Inline marks travel through the converters as private-use sentinel characters,
so a converter never needs to know about marks:

    OPEN  = \\ue000 <n> \\ue001      CLOSE = \\ue002 <n> \\ue003
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

OPEN_A, OPEN_B, CLOSE_A, CLOSE_B = "", "", "", ""
_SENT_RE = re.compile("(\\d+)|(\\d+)")


@dataclass
class Block:
    kind: str                 # heading | para | math | figure | list | code | note
    start: int
    end: int
    meta: dict = field(default_factory=dict)
    id: str = ""
    line: int = 0
    marks: list = field(default_factory=list)       # [(rel_start, rel_end, mark_no)]
    block_marks: list = field(default_factory=list)  # [mark_no]
    html: str = ""


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def insert_sentinels(raw: str, marks) -> str:
    """Insert OPEN/CLOSE sentinels for marks [(s, e, n)] (relative offsets).

    At one position, closes come before opens; outer marks open first and
    close last, so properly nested marks give properly nested HTML.
    """
    events = []
    for s, e, n in marks:
        events.append((s, 1, -(e - s), OPEN_A + str(n) + OPEN_B))
        events.append((e, 0, (e - s), CLOSE_A + str(n) + CLOSE_B))
    events.sort()
    out, last = [], 0
    for pos, _, _, tok in events:
        out.append(raw[last:pos])
        out.append(tok)
        last = pos
    out.append(raw[last:])
    return "".join(out)


def strip_sentinels(s: str) -> str:
    return _SENT_RE.sub("", s)


def sentinels_to_html(s: str, mark_ids: dict) -> str:
    def rep(m):
        if m.group(1) is not None:
            cid = mark_ids.get(int(m.group(1)), "")
            return f'<mark class="rd-mark" data-cid="{html.escape(cid)}">'
        return "</mark>"
    return _SENT_RE.sub(rep, s)


def overlaps_partially(a, b) -> bool:
    """True when spans a and b intersect without one containing the other."""
    (s1, e1), (s2, e2) = a, b
    if e1 <= s2 or e2 <= s1:
        return False
    return not ((s1 <= s2 and e2 <= e1) or (s2 <= s1 and e1 <= e2))
