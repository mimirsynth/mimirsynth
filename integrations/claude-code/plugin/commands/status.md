---
description: MimirSynth status — connection, brain, the role and expiry of each token, server version, capture mode and drafts
allowed-tools: Bash(python3:*)
---
!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cli.py" status || true`

Show the status above to the user as it is. If a token is expired, revoked or missing, or the server cannot be reached, say what to do: create or rotate the token in MimirSynth (My account → API tokens) and run `/mimirsynth:setup`.
