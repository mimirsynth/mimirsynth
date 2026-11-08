---
description: Configure MimirSynth — the server, the brain, the tokens and whether to capture what each session learned
allowed-tools: Bash(python3:*)
---
The plugin's scripts are in: !`python3 -c "import os; print(os.environ.get('CLAUDE_PLUGIN_ROOT', ''))"`

Current state:
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" status || true`

Tokens must never go through this conversation. Tell the user to run this in their own terminal (it asks for the tokens without showing them, and writes `~/.config/mimirsynth/config.json` readable only by them):

```
python3 "<the folder above>/scripts/cli.py" setup
```

What it asks for:
1. The MimirSynth URL and the brain's slug.
2. A **reader** token for recall (My account → API tokens, scope Recall).
3. Optionally a **contributor** token to propose memories. The capture never sends with a curator token, because its proposals would skip quarantine.
4. The capture mode: `off` (the default: nothing about the sessions is written or sent), `draft` (each session is kept on this machine, redacted, until the user reviews it with `/mimirsynth:remember`), or `send` (at the next session start, each finished session that changed files or ended with a substantial answer becomes one proposal, with low confidence, in quarantine).

When they are done, they can check it with `/mimirsynth:status`.
