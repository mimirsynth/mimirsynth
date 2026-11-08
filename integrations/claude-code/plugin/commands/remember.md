---
description: Propose a memory to MimirSynth (it waits for a curator), or review the drafts the session capture left
argument-hint: [title of what to remember]
allowed-tools: Bash(python3:*)
---
The plugin's scripts are in: !`python3 -c "import os; print(os.environ.get('CLAUDE_PLUGIN_ROOT', ''))"`

Drafts the capture left (only when capture is `draft`):
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" drafts || true`

What the user asked: $ARGUMENTS

- **If they gave a title:** write the memory yourself from this conversation. Keep it short and durable: stable facts, decisions and their reasons, changes to infrastructure, never passwords, tokens or keys (say where they are kept instead). Show it to the user and, once they agree, run with the Bash tool: `python3 "<the folder above>/scripts/cli.py" remember --title "<title>" --content "<the memory>"`.
- **If they gave nothing and there are drafts:** show each draft and ask, one by one, whether to send it (`… cli.py send-draft <session>`), forget it (`… cli.py drop-draft <session>`) or leave it.
- **If there is nothing to do:** say so.

Proposals wait in quarantine until a curator approves them. Secrets are removed by pattern before sending, which is not infallible: read what you send.
