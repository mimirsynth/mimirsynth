---
name: status
description: Show whether MimirSynth memory works in Codex - the server, the brain, each token's role, scopes and expiry, whether the hooks are trusted, and the capture mode. Use when the person asks about MimirSynth's status or why memory is not being recalled.
---

# MimirSynth status

Run this plugin's command line, two folders up from this `SKILL.md` (on Windows, `python` instead of `python3`):

```
python3 "<folder of this file>/../../scripts/cli.py" status
```

It reaches the MimirSynth server over the network: if the sandbox blocks it, ask for the command to run outside the sandbox.

Show the person its output as it is. If it says the hooks are not trusted, tell them to open `/hooks` in Codex and trust the `mimirsynth` ones. If it says it is not configured, use the `setup` skill. A token that is expired, revoked or lacks a scope is said with the server's own message: suggest creating or rotating the token in MimirSynth (My account → API tokens) and running setup again.
