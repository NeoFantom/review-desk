"""Response-letter skeleton from the comments and their drafted responses."""
from __future__ import annotations

import re


def _groups(comments):
    out = {}
    for c in comments:
        out.setdefault(c["reviewer"], []).append(c)
    return out


def markdown(title: str, comments: list, state: dict) -> str:
    lines = [f"# Response to the reviewers — {title}", "",
             "We thank the reviewers for their careful reading. Our point-by-point "
             "responses follow; changes in the manuscript are listed under each response.", ""]
    for rid, cs in _groups(comments).items():
        lines += [f"## Reviewer {rid}", ""]
        for c in cs:
            st = state.get(c["id"], {})
            lines += [f"### Comment {c['num']}", ""]
            lines += ["> " + ln for ln in c["text"].splitlines()] + [""]
            lines += ["**Response.** " + (st.get("response") or "TODO"), ""]
            if st.get("changes"):
                lines += ["**Changes in the manuscript.** " + st["changes"], ""]
    return "\n".join(lines).rstrip() + "\n"


_TEX = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\^{}"}


def _tex_escape(s: str) -> str:
    """Escape text for LaTeX, leaving $...$ math alone."""
    parts = re.split(r"(\$[^$]*\$)", s)
    for k in range(0, len(parts), 2):
        parts[k] = re.sub(r"[\\&%#_{}~^]", lambda m: _TEX[m.group(0)], parts[k])
    return "".join(parts)


def latex(title: str, comments: list, state: dict) -> str:
    lines = [r"\documentclass[11pt]{article}", r"\usepackage{amsmath,xcolor}",
             r"\newenvironment{referee}{\begin{quote}\itshape\color{black!70}}{\end{quote}}",
             r"\begin{document}", r"\section*{Response to the reviewers}",
             r"\noindent Manuscript: " + _tex_escape(title), "",
             "We thank the reviewers for their careful reading. Our point-by-point responses follow.", ""]
    for rid, cs in _groups(comments).items():
        lines += [r"\subsection*{Reviewer " + _tex_escape(rid) + "}", ""]
        for c in cs:
            st = state.get(c["id"], {})
            lines += [r"\paragraph{Comment " + _tex_escape(c["num"]) + ".}",
                      r"\begin{referee}", _tex_escape(c["text"]), r"\end{referee}",
                      r"\noindent\textbf{Response.} " + (_tex_escape(st["response"]) if st.get("response") else "TODO"), ""]
            if st.get("changes"):
                lines += [r"\noindent\textbf{Changes.} " + _tex_escape(st["changes"]), ""]
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"
