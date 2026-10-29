# Codex CLI adapter

Tested with codex-cli 0.164.0 on Linux (WSL2), 2026-10-28.

## Setup

Codex reads `AGENTS.md`. In the folder with `review-desk.json`:

```sh
cat /path/to/review-desk/adapters/AGENT_INSTRUCTIONS.md >> AGENTS.md
```

## Batch mode (`codex exec`) — tested

```sh
codex exec -s workspace-write \
  "Process the review-desk inbox once in batch mode, following AGENTS.md." < /dev/null
```

Two things learned in the test:

- **The `workspace-write` sandbox blocks network access, including
  127.0.0.1.** The `review-desk` commands detect that the server is not
  reachable and work on `review-state.json` directly (under a file lock);
  the running page picks the changes up within two seconds. In the test the
  agent edited the conclusion of `paper.tex`, drafted the response for R2.3,
  set it to `revised` and replied to the note — about 70 s. Before this
  fallback existed, Codex worked around the blocked server by editing the
  JSON file by hand; the instructions now forbid that.
- **Close stdin** (`< /dev/null`) when you call `codex exec` from a script;
  otherwise it waits for more input on stdin.

If you prefer the HTTP path, allow network access in the sandbox
(`-c sandbox_workspace_write.network_access=true`); not tested.

## Resident mode — not tested

Codex has no background-task wake-up comparable to Claude Code's. Two
options, neither tested:

- In an interactive session, ask it to run `review-desk wait --timeout 540`
  in the foreground (under the shell tool's time limit), handle what arrives,
  and repeat.
- Or run batch mode from a loop outside Codex:

  ```sh
  while review-desk wait > /tmp/notes.json; do
    codex exec -s workspace-write "Handle the notes in /tmp/notes.json (already claimed; do not run wait), following AGENTS.md." < /dev/null
  done
  ```
