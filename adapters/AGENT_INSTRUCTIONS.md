# review-desk: instructions for the agent

Paste this block into your agent's project instructions (`CLAUDE.md`,
`AGENTS.md`, `.cursorrules`, a system prompt, ...) in the folder that holds
`review-desk.json`. It is written for any agent that can run shell commands
and edit files.

---

## Revising a paper with review-desk

The author reads the paper in review-desk (a local page) and sends you notes.
A note is an instruction from the author: act on it.

**Getting notes**

- Resident mode (you can run a command in the background and get woken up when
  it exits): run `review-desk wait` in the background. It exits when notes
  arrive and prints them as JSON. Handle them, then start `review-desk wait`
  again.
- Batch mode (you cannot keep a background process): run
  `review-desk wait --no-block` once. It prints every pending note (or `[]`)
  and returns at once. Handle them all, then stop.

Each note is JSON with: `id`, `text` (the instruction), `quote` (text the
author selected on the page), `line` and `context` (source line and the
LaTeX/Markdown source of that paragraph), `comment` and `comment_text` (the
reviewer comment it is about, if any), `thread` (earlier exchange), `paper`
(path of the source file).

**Handling a note**

1. Find the place in the source file (`paper`) using `line` and `context`;
   `quote` is rendered text, so it may differ from the source in markup.
2. Make the change the note asks for. When the author writes out the sentence
   they want, keep it; fix only grammar and unidiomatic phrasing.
3. If the note is about a reviewer comment (`comment` is set), keep that
   comment's record up to date:

       review-desk comment R1.2 --status revised \
           --response "draft reply to the reviewer" \
           --changes "what changed, where"

   You may also suggest a root cause with `--root-cause`
   (misread | our_error | weak_evidence | structure | other). Never mark a
   comment `replied`: only the author does that.
4. Report back with a short task title and what you changed:

       review-desk reply ID --title "Abstract: define energy" --reply "..."

   If you cannot act without a decision from the author, ask instead and add
   `--hold`; change nothing yet.
5. To suggest a change nobody asked for, do not edit; propose it:

       review-desk propose --title "..." --text "..." --quote "exact source text" --comment R2.1

   The author answers on the page (go ahead / don't change / a reply), and the
   answer comes back to you as a note.

If your sandbox blocks network access to 127.0.0.1, the commands say
"server not reachable ... using the state file directly" and keep working on
`review-state.json` (with a file lock). Always go through `review-desk`; do
not edit `review-state.json` by hand.

The page rebuilds itself when the source file changes; you do not need to run
a build. Long texts can be passed as `-` (stdin) or `@file` for `--reply`,
`--text` and `--response`.

Other commands: `review-desk list` (inbox overview), `review-desk show R1.2`
(one comment as JSON).
