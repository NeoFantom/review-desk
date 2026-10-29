# Agent compatibility

Only what was actually run is marked tested. Test setup: the synthetic
example in `examples/synthetic/`, one note sent from the page, the agent
started with `adapters/AGENT_INSTRUCTIONS.md` as its project instructions.
"Pass" means: the paper source was edited as asked, the note was answered
(`done`), and the comment record got a response draft.

| Agent | Version | Mode | Result | Date |
|---|---|---|---|---|
| Claude Code | 2.1.312 | batch, `claude -p` | pass (≈30 s) | 2026-10-28 |
| Claude Code | 2.1.312 | resident, background `wait` in an interactive session | pass: `wait` exited on the note and woke the session; `reply` reached the page | 2026-10-28 |
| Codex CLI | 0.164.0 | batch, `codex exec -s workspace-write` | pass (≈70 s) via the offline fallback; the sandbox blocks 127.0.0.1 | 2026-10-28 |
| Codex CLI | 0.164.0 | resident / polling | not tested | |
| Codex CLI | 0.164.0 | batch with sandbox network access enabled | not tested | |
| Kimi CLI, OpenCode, Mimo Code, Qwen Code, Claude Code with GLM/Kimi/DeepSeek models | | any | not tested; see `adapters/generic.md` | |

Platform: Linux (WSL2), Python 3.12 and 3.10, Chrome 148 (headless) for the page.
macOS and native Windows: not tested (the file lock has a Windows code path
via `msvcrt` that has not been run).

## Adapter files

- `adapters/AGENT_INSTRUCTIONS.md` — the instructions any agent gets (copy
  into `CLAUDE.md` / `AGENTS.md` / rules file).
- `adapters/claude-code.md` — resident and headless use.
- `adapters/codex.md` — `codex exec`, sandbox notes.
- `adapters/generic.md` — any agent that can run shell commands; Chinese
  coding agents (untested) with what to change.

## Writing a new adapter

An adapter is only documentation: where the instructions go, which mode the
agent supports, and how to start it. The contract it relies on is the CLI:

| Command | Agent uses it to |
|---|---|
| `review-desk wait` / `wait --no-block` | get notes (claimed: `new` → `working`) |
| `review-desk reply ID --title T --reply R [--hold]` | answer a note (`done`, or `hold` = question back) |
| `review-desk comment RID --status --root-cause --response --changes` | keep a reviewer comment's record |
| `review-desk propose --title --text [--quote] [--comment]` | suggest a change for the author to approve |
| `review-desk list` / `show RID` | look around |

The same operations exist as HTTP endpoints (see `review_desk/server.py`) if
an agent framework prefers HTTP tools over shell commands.
