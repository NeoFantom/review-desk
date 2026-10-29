# Any other agent

review-desk needs only two abilities from an agent: **run a shell command**
and **edit a text file**. Everything else is the CLI.

## Steps

1. Put `adapters/AGENT_INSTRUCTIONS.md` where the agent reads project
   instructions (its rules file, `AGENTS.md`, a system prompt, or paste it
   into the first message).
2. Pick the mode the agent supports:

   | the agent can... | use |
   |---|---|
   | run a background command and be woken up when it exits | resident: `review-desk wait` in the background |
   | run long foreground commands | polling: `review-desk wait --timeout 300`, handle, repeat |
   | only run one task per invocation | batch: `review-desk wait --no-block` once per run |

3. If the agent runs in a sandbox without network access, nothing to do: the
   CLI falls back to the state file (`--offline` forces this).
4. If the agent cannot run commands at all (chat-only), use the page's
   export and copy notes by hand; review-desk is not much help there.

## Chinese coding agents (all untested)

The tools below can run shell commands and edit files, so the same
instructions should work. None of them has been tested with review-desk;
treat this as a starting point.

| Tool | Where the instructions go | Mode to try first | Notes |
|---|---|---|---|
| Kimi CLI (Moonshot) | `AGENTS.md` or the first message | batch | check whether shell commands need approval each time |
| Claude Code with a GLM / Kimi / DeepSeek / MiniMax model behind an Anthropic-compatible endpoint | `CLAUDE.md` | resident, as for Claude Code | the CLI is the same; only the model changes, so tool use quality is the variable |
| OpenCode | `AGENTS.md` | batch (`opencode run "..."`) | supports many model providers |
| Mimo Code and other Claude-Code-style CLIs | the tool's rules file | batch | if it has background tasks with notifications, try resident |
| Qwen Code / iFlow CLI | `AGENTS.md` / `QWEN.md` | batch | Gemini-CLI derivatives; check the shell tool timeout |

What to change if something does not work:

- **The agent does not find the command**: put the full path
  (`/path/to/venv/bin/review-desk`) or `python -m review_desk` in the
  instructions.
- **Shell tool times out on `wait`**: use `--timeout` below the tool's limit,
  or batch mode.
- **Model ignores the reply step**: put "Always finish with
  `review-desk reply ID ...`" at the top of the instructions; check with
  `review-desk list` that notes do not stay `working`.
- **Notes stay `working` after a crash**: answer them again on the page
  (follow-up) to send them back as `new`.

If you test one of these, please send the version and the result so the
table can say "tested".
