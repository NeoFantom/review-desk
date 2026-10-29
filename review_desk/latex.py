"""LaTeX -> blocks -> HTML, for reading (not typesetting).

Covers what a reviewer reads in a typical article/revtex paper: title,
abstract, (sub)sections, paragraphs, inline and display math, figure and
table placeholders with captions, lists, cross references and citations.
Math is left as TeX for KaTeX in the browser.  Anything unknown degrades to
its text content instead of failing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .doc import Block, esc, line_of

MATH_ENVS = {"equation", "equation*", "align", "align*", "gather", "gather*",
             "multline", "multline*", "eqnarray", "eqnarray*", "displaymath",
             "flalign", "flalign*"}
ALIGN_LIKE = {"align", "align*", "eqnarray", "eqnarray*", "flalign", "flalign*"}
FIG_ENVS = {"figure", "figure*", "table", "table*", "wrapfigure"}
LIST_ENVS = {"itemize": "ul", "enumerate": "ol", "description": "ul"}
VERB_ENVS = {"verbatim", "lstlisting", "minted"}
SKIP_ENVS = {"thebibliography", "comment"}

FMT = {"emph": "em", "textit": "em", "textsl": "em", "textbf": "strong",
       "texttt": "code", "underline": "u", "textsc": "span", "textrm": "span",
       "textsf": "span", "textup": "span", "textnormal": "span", "mbox": "span",
       "text": "span"}
CITE = {"cite", "citep", "citet", "citealp", "citeauthor", "citeyear", "onlinecite"}
REFS = {"ref", "eqref", "cref", "Cref", "autoref", "pageref"}
DROP_ARG = {"label", "vspace", "hspace", "bibliographystyle", "bibliography",
            "includegraphics", "phantom", "hphantom", "vphantom", "addcontentsline",
            "begin", "end", "pacs", "keywords", "thanks", "nocite", "input", "include",
            "title", "author", "affiliation", "address", "email", "date", "homepage",
            "altaffiliation", "collaboration"}
DROP = {"noindent", "centering", "small", "footnotesize", "scriptsize", "tiny",
        "normalsize", "large", "Large", "LARGE", "huge", "bigskip", "medskip",
        "smallskip", "par", "maketitle", "protect", "relax", "clearpage",
        "newpage", "indent", "raggedright", "item", "hfill", "vfill", "appendix",
        "tableofcontents", "nonumber", "notag", "selectfont", "normalfont"}
SYMBOLS = {"LaTeX": "LaTeX", "TeX": "TeX", "ldots": "…", "dots": "…",
           "textellipsis": "…", "S": "§", "P": "¶", "dag": "†", "ddag": "‡",
           "copyright": "©", "textendash": "–", "textemdash": "—",
           "newline": " ", "linebreak": " ", "quad": "\u2003", "qquad": "\u2003\u2003",
           "textasciitilde": "~", "textbackslash": "\\", "ss": "ß", "o": "ø",
           "ae": "æ", "aa": "å", "i": "ı", "etal": "et al."}
ESCAPES = {"%": "%", "&": "&amp;", "#": "#", "_": "_", "$": "$", "{": "{",
           "}": "}", " ": " ", ",": "\u2009", ";": " ", ":": " ", "!": "",
           "-": "", "/": "", "@": ""}

_CTRL = re.compile(r"\\([A-Za-z@]+)\*?|\\(.)", re.S)
_TOKEN = re.compile(
    r"\\((?:sub){0,2})section(\*?)\s*(?=[\[{])"
    r"|\\begin\s*\{([^}]*)\}|\\end\s*\{([^}]*)\}"
    r"|\\\[|\$\$|\n[ \t]*\n"
    r"|\\(?:maketitle|tableofcontents|appendix|bibliography\s*\{[^}]*\}|bibliographystyle\s*\{[^}]*\})")


# ---------------------------------------------------------------- helpers

def strip_comments(src: str) -> str:
    """Blank out % comments, keeping every offset and newline in place."""
    out = []
    for line in src.split("\n"):
        i = 0
        while True:
            j = line.find("%", i)
            if j < 0:
                break
            k = j - 1
            n = 0
            while k >= 0 and line[k] == "\\":
                n += 1
                k -= 1
            if n % 2 == 0:
                line = line[:j] + " " * (len(line) - j)
                break
            i = j + 1
        out.append(line)
    return "\n".join(out)


def read_group(s: str, i: int):
    """s[i:] starts (after optional spaces) with '{': return (content, start, end)."""
    j = i
    while j < len(s) and s[j] in " \t\n":
        j += 1
    if j >= len(s) or s[j] != "{":
        return None
    depth, k = 0, j
    while k < len(s):
        c = s[k]
        if c == "\\":
            k += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[j + 1:k], j + 1, k + 1
        k += 1
    return s[j + 1:], j + 1, len(s)


def skip_opt(s: str, i: int) -> int:
    """Skip spaces and any number of [optional] arguments."""
    while True:
        j = i
        while j < len(s) and s[j] in " \t\n":
            j += 1
        if j < len(s) and s[j] == "[":
            depth = 0
            while j < len(s):
                if s[j] == "[":
                    depth += 1
                elif s[j] == "]":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            i = j + 1
        else:
            return i


def math_spans(s: str):
    """Spans of inline math ($...$, \\(...\\)) in s, delimiters included."""
    spans, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\" and i + 1 < n:
            if s[i + 1] == "(":
                j = s.find("\\)", i + 2)
                j = n if j < 0 else j + 2
                spans.append((i, j))
                i = j
                continue
            i += 2
            continue
        if c == "$":
            j = i + 1
            while j < n and not (s[j] == "$" and s[j - 1] != "\\"):
                j += 1
            spans.append((i, min(j + 1, n)))
            i = j + 1
            continue
        i += 1
    return spans


def parse_macros(preamble: str) -> dict:
    """Zero/n-argument \\newcommand/\\renewcommand/\\def definitions."""
    macros = {}
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\s*\\([A-Za-z@]+)\s*\}?", preamble):
        i = m.end()
        nargs = 0
        mm = re.match(r"\s*\[(\d)\]", preamble[i:])
        if mm:
            nargs = int(mm.group(1))
            i += mm.end()
        i = skip_opt(preamble, i)
        g = read_group(preamble, i)
        if g:
            macros[m.group(1)] = (nargs, g[0])
    for m in re.finditer(r"\\def\s*\\([A-Za-z@]+)\s*(?=\{)", preamble):
        g = read_group(preamble, m.end())
        if g:
            macros[m.group(1)] = (0, g[0])
    return macros


# ---------------------------------------------------------------- parsing

@dataclass
class Parsed:
    kind: str
    src: str
    clean: str
    blocks: list
    title: str = ""
    macros: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)
    figures: list = field(default_factory=list)


def parse(src: str) -> Parsed:
    clean = strip_comments(src)
    b = re.search(r"\\begin\s*\{document\}", clean)
    body_start = b.end() if b else 0
    e = re.search(r"\\end\s*\{document\}", clean)
    body_end = e.start() if e else len(clean)
    preamble = clean[:body_start] if b else ""
    p = Parsed("tex", src, clean, [], macros=parse_macros(preamble))
    tm = re.search(r"\\title\s*(?=[\[{])", clean[:body_end])
    if tm:
        g = read_group(clean, skip_opt(clean, tm.end()))
        if g:
            p.title = g[0]

    blocks, i = [], body_start

    def para(s, e):
        seg = clean[s:e]
        if seg.strip():
            s2 = s + len(seg) - len(seg.lstrip())
            e2 = e - (len(seg) - len(seg.rstrip()))
            blocks.append(Block("para", s2, e2, {"inner": (s2, e2)}))

    while i < body_end:
        m = _TOKEN.search(clean, i, body_end)
        if not m:
            para(i, body_end)
            break
        para(i, m.start())
        t = m.group(0)
        if m.group(2) is not None and t.lstrip("\\").find("section") >= 0:
            j = skip_opt(clean, m.end())
            g = read_group(clean, j)
            if not g:
                i = m.end()
                continue
            blocks.append(Block("heading", m.start(), g[2],
                                {"level": len(m.group(1)) // 3 + 1, "star": bool(m.group(2)),
                                 "inner": (g[1], g[2] - 1)}))
            i = g[2]
        elif m.group(3) is not None:
            env = m.group(3).strip()
            end_re = re.compile(r"\\end\s*\{" + re.escape(env) + r"\}")
            em = end_re.search(clean, m.end(), body_end)
            stop = em.start() if em else body_end
            after = em.end() if em else body_end
            if env in MATH_ENVS:
                blocks.append(Block("math", m.start(), after,
                                    {"env": env, "tex": clean[m.end():stop]}))
                i = after
            elif env in FIG_ENVS:
                blocks.append(_figure(clean, m.start(), m.end(), stop, after, env))
                i = after
            elif env in LIST_ENVS:
                blocks.append(Block("list", m.start(), after,
                                    {"tag": LIST_ENVS[env], "inner": (m.end(), stop)}))
                i = after
            elif env in VERB_ENVS:
                blocks.append(Block("code", m.start(), after, {"text": clean[m.end():stop]}))
                i = after
            elif env in SKIP_ENVS:
                blocks.append(Block("note", m.start(), after, {"text": "[references omitted]"}))
                i = after
            elif env == "abstract":
                blocks.append(Block("heading", m.start(), m.end(),
                                    {"level": 1, "star": True, "label": "Abstract"}))
                i = m.end()
            else:            # theorem, center, quote, minipage, ...: transparent
                i = m.end()
        elif t in ("\\[", "$$"):
            close = "\\]" if t == "\\[" else "$$"
            j = clean.find(close, m.end(), body_end)
            j = body_end if j < 0 else j
            blocks.append(Block("math", m.start(), j + len(close),
                                {"env": "displaymath", "tex": clean[m.end():j]}))
            i = j + len(close)
        else:
            i = m.end()

    _number(p, blocks)
    for n, blk in enumerate(blocks):
        blk.id = f"b{n + 1}"
        blk.line = line_of(clean, blk.start)
    # drop paragraphs that render to nothing (\noindent, \label{...} alone)
    p.blocks = [blk for blk in blocks
                if blk.kind != "para" or re.sub(r"<[^>]+>|\s", "", render(p, blk, clean[blk.start:blk.end]))]
    return p


def _figure(clean, start, body_s, stop, after, env):
    body = clean[body_s:stop]
    meta = {"env": env, "graphics": [], "inner": None}
    for gm in re.finditer(r"\\includegraphics", body):
        g = read_group(body, skip_opt(body, gm.end()))
        if g:
            meta["graphics"].append(g[0].strip())
    cm = re.search(r"\\caption\s*(?=[\[{])", body)
    if cm:
        g = read_group(body, skip_opt(body, cm.end()))
        if g:
            meta["inner"] = (body_s + g[1], body_s + g[2] - 1)
    lm = re.search(r"\\label\s*\{([^}]*)\}", body)
    if lm:
        meta["label"] = lm.group(1).strip()
    return Block("figure", start, after, meta)


def _number(p: Parsed, blocks):
    sec = [0, 0, 0]
    eq = fig = tab = 0
    for blk in blocks:
        if blk.kind == "heading" and not blk.meta.get("star"):
            lv = blk.meta["level"] - 1
            sec[lv] += 1
            for k in range(lv + 1, 3):
                sec[k] = 0
            num = ".".join(str(x) for x in sec[:lv + 1])
            blk.meta["number"] = num
            lm = re.match(r"\s*\\label\s*\{([^}]*)\}", p.clean[blk.end:blk.end + 200])
            if lm:
                p.labels[lm.group(1).strip()] = ("sec", num)
        elif blk.kind == "math":
            env, tex = blk.meta["env"], blk.meta["tex"]
            numbered = env in MATH_ENVS and not env.endswith("*") and env != "displaymath"
            rows = re.split(r"\\\\", tex) if env in ALIGN_LIKE else [tex]
            nums = []
            for row in rows:
                if not row.strip():
                    continue
                if numbered and not re.search(r"\\no(?:number|tag)\b", row):
                    eq += 1
                    nums.append(eq)
                    for lm in re.finditer(r"\\label\s*\{([^}]*)\}", row):
                        p.labels[lm.group(1).strip()] = ("eq", str(eq))
                else:
                    for lm in re.finditer(r"\\label\s*\{([^}]*)\}", row):
                        if numbered:
                            p.labels[lm.group(1).strip()] = ("eq", str(eq))
            blk.meta["numbers"] = nums
        elif blk.kind == "figure":
            if blk.meta["env"].startswith("table"):
                tab += 1
                blk.meta["number"], blk.meta["name"] = str(tab), "Table"
            else:
                fig += 1
                blk.meta["number"], blk.meta["name"] = str(fig), "Figure"
            if blk.meta.get("label"):
                p.labels[blk.meta["label"]] = ("fig" if blk.meta["name"] == "Figure" else "tab",
                                               blk.meta["number"])


# ---------------------------------------------------------------- rendering

def inner_span(blk: Block):
    return blk.meta.get("inner")


def forbidden(p: Parsed, blk: Block):
    """Spans an inline mark may not cut through, and points it may not contain."""
    s, e = blk.meta["inner"]
    raw = p.clean[s:e]
    spans = [(s + a, s + b) for a, b in math_spans(raw)]
    points = []
    if blk.kind == "list":
        points = [s + m.start() for m in re.finditer(r"\\item\b", raw)]
    return spans, points


def render(p: Parsed, blk: Block, raw: str) -> str:
    """HTML for one block; raw is its inner source (with mark sentinels)."""
    k = blk.kind
    if k == "para":
        return "<p>" + inline(p, raw) + "</p>"
    if k == "heading":
        lv = min(blk.meta["level"] + 1, 4)
        num = blk.meta.get("number")
        title = esc(blk.meta["label"]) if "label" in blk.meta else inline(p, raw)
        pre = f'<span class="rd-secno">{num}</span> ' if num else ""
        return f"<h{lv}>{pre}{title}</h{lv}>"
    if k == "math":
        tex = re.sub(r"\\label\s*\{[^}]*\}|\\no(?:number|tag)\b", "", blk.meta["tex"]).strip()
        if blk.meta["env"] in ALIGN_LIKE:
            tex = "\\begin{aligned}" + tex + "\\end{aligned}"
        elif blk.meta["env"].startswith(("gather", "multline")):
            tex = "\\begin{gathered}" + tex + "\\end{gathered}"
        nums = blk.meta.get("numbers") or []
        no = ""
        if nums:
            no = f"({nums[0]})" if len(nums) == 1 else f"({nums[0]})–({nums[-1]})"
        return f'<div class="rd-md">{esc(tex)}</div><span class="rd-eqno">{no}</span>'
    if k == "figure":
        figs = "".join(f'<div class="rd-fig" data-src="{esc(g)}">{esc(g)}</div>'
                       for g in blk.meta["graphics"])
        if not figs:
            figs = f'<div class="rd-fig rd-fig-empty">[{blk.meta.get("name", "Figure").lower()}]</div>'
        cap = inline(p, raw) if blk.meta.get("inner") else ""
        return (f"<figure>{figs}<figcaption><b>{blk.meta.get('name', 'Figure')} "
                f"{blk.meta.get('number', '')}.</b> {cap}</figcaption></figure>")
    if k == "list":
        tag = blk.meta["tag"]
        items = re.split(r"\\item\b\s*(?:\[[^\]]*\])?", raw)
        lis = "".join(f"<li>{inline(p, it)}</li>" for it in items if it.strip())
        return f"<{tag}>{lis}</{tag}>"
    if k == "code":
        return f"<pre>{esc(blk.meta['text'].strip(chr(10)))}</pre>"
    return f'<p class="rd-note">{esc(blk.meta.get("text", ""))}</p>'


def inline(p: Parsed, s: str) -> str:
    out, last = [], 0
    for a, b in math_spans(s):
        out.append(_conv(p, s[last:a]))
        tex = s[a:b]
        tex = tex[2:-2] if tex.startswith("\\(") else tex[1:-1]
        out.append(f'<span class="rd-m">{esc(tex)}</span>')
        last = b
    out.append(_conv(p, s[last:]))
    return "".join(out)


def _ref(p: Parsed, name: str, keys: str) -> str:
    parts = []
    for key in [x.strip() for x in keys.split(",") if x.strip()]:
        kind, num = p.labels.get(key, ("?", "??"))
        if name == "eqref":
            parts.append(f"({num})")
        elif name in ("cref", "Cref", "autoref"):
            word = {"eq": "Eq.", "fig": "Fig.", "tab": "Table", "sec": "Sec."}.get(kind, "")
            parts.append(f"{word} ({num})" if kind == "eq" else f"{word} {num}".strip())
        else:
            parts.append(num)
    return '<span class="rd-ref">' + esc(", ".join(parts)) + "</span>"


def _conv(p: Parsed, s: str, depth: int = 0) -> str:
    if depth > 20:
        return esc(s)
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            m = _CTRL.match(s, i)
            if not m:
                i += 1
                continue
            j = m.end()
            if m.group(1):
                name = m.group(1)
                while j < n and s[j] in " \t\n" and name not in FMT and name not in CITE:
                    j += 1           # TeX eats spaces after a control word
                if name in FMT:
                    g = read_group(s, j)
                    if g:
                        tag = FMT[name]
                        out.append(f"<{tag}>" + _conv(p, g[0], depth + 1) + f"</{tag}>")
                        i = g[2]
                        continue
                elif name in CITE:
                    g = read_group(s, skip_opt(s, j))
                    if g:
                        keys = ", ".join(x.strip() for x in g[0].split(","))
                        out.append(f'<span class="rd-cite">[{esc(keys)}]</span>')
                        i = g[2]
                        continue
                elif name in REFS:
                    g = read_group(s, j)
                    if g:
                        out.append(_ref(p, name, g[0]))
                        i = g[2]
                        continue
                elif name == "footnote":
                    g = read_group(s, skip_opt(s, j))
                    if g:
                        out.append('<span class="rd-fn">(' + _conv(p, g[0], depth + 1) + ")</span>")
                        i = g[2]
                        continue
                elif name == "href":
                    g1 = read_group(s, j)
                    g2 = read_group(s, g1[2]) if g1 else None
                    if g2:
                        out.append(_conv(p, g2[0], depth + 1))
                        i = g2[2]
                        continue
                elif name == "url":
                    g = read_group(s, j)
                    if g:
                        out.append(f"<code>{esc(g[0])}</code>")
                        i = g[2]
                        continue
                elif name in DROP_ARG:
                    j = skip_opt(s, j)
                    g = read_group(s, j)
                    i = g[2] if g else j
                    continue
                elif name in DROP:
                    i = j
                    continue
                elif name in SYMBOLS:
                    out.append(esc(SYMBOLS[name]))
                    i = j
                    continue
                elif name in p.macros:
                    nargs, body = p.macros[name]
                    args = []
                    for _ in range(nargs):
                        g = read_group(s, j)
                        if not g:
                            break
                        args.append(g[0])
                        j = g[2]
                    for a_no, a in enumerate(args, 1):
                        body = body.replace(f"#{a_no}", a)
                    out.append(inline(p, body) if depth < 5 else esc(body))
                    i = j
                    continue
                # unknown command: keep the text of its first argument
                g = read_group(s, skip_opt(s, j)) if j < n and s[skip_opt(s, j):skip_opt(s, j) + 1] == "{" else None
                if g:
                    out.append(_conv(p, g[0], depth + 1))
                    i = g[2]
                else:
                    i = j
                continue
            sym = m.group(2)
            if sym == "\\":
                out.append(" ")
                i = skip_opt(s, j)
            elif sym in ESCAPES:
                out.append(ESCAPES[sym])
                i = j
            elif sym in "'\"`^~=.":        # accents: keep the letter
                g = read_group(s, j)
                if g:
                    out.append(esc(g[0]))
                    i = g[2]
                else:
                    i = j
            else:
                out.append(esc(sym))
                i = j
            continue
        if c == "{":
            g = read_group(s, i)
            out.append(_conv(p, g[0], depth + 1))
            i = g[2]
            continue
        if c == "}":
            i += 1
            continue
        if c == "~":
            out.append("\u00a0")
        elif s.startswith("---", i):
            out.append("—")
            i += 3
            continue
        elif s.startswith("--", i):
            out.append("–")
            i += 2
            continue
        elif s.startswith("``", i):
            out.append("“")
            i += 2
            continue
        elif s.startswith("''", i):
            out.append("”")
            i += 2
            continue
        elif c == "`":
            out.append("‘")
        elif c in "\n\t":
            out.append(" ")
        else:
            out.append(esc(c))
        i += 1
    return "".join(out)
