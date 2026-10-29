# Claude Code adapter

Tested with Claude Code 2.1.312 on Linux (WSL2), 2026-10-28.

## Setup

In the folder with `review-desk.json`, add the agent instructions to
`CLAUDE.md` (or reference them from it):

```sh
cat /path/to/review-desk/adapters/AGENT_INSTRUCTIONS.md >> CLAUDE.md
```

`review-desk` must be on the `PATH` that Claude Code sees (`pip install .`
into the environment you start `claude` from, or use `python -m review_desk`
and say so in `CLAUDE.md`).

## Resident mode (interactive session) — tested

Claude Code can run a shell command in the background and is woken up when
it exits. Start a session and say:

> Start `review-desk wait` in the background and handle notes as they arrive
> (see CLAUDE.md).

What happens: the page shows "Agent listening"; when you send a note,
`wait` exits with the note as JSON, Claude Code gets the task notification,
edits the paper, runs `review-desk reply`, and starts `wait` again.

## Batch mode (headless) — tested

```sh
claude -p "Process the review-desk inbox once in batch mode, following CLAUDE.md." \
  --allowedTools "Bash(review-desk:*)" Read Edit --permission-mode acceptEdits
```

Result of the test (synthetic example, one note about comment R1.3): the
agent ran `wait --no-block`, edited one sentence of `paper.tex`, set R1.3 to
`revised` with a root cause and a response draft, and replied to the note —
about 30 s. It also flagged a consistency question in its reply on its own.

## Permissions

`Bash(review-desk:*)` lets the agent use the mailbox without prompting. Keep
file edits on approval (`default` permission mode) if you want to review
each change before it lands.
