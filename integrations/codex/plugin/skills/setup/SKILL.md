---
name: setup
description: Connect Codex to a MimirSynth brain (server, brain, tokens, capture mode). Use when the person asks to set up, configure or connect MimirSynth, or when another MimirSynth skill says it is not configured.
---

# Set up MimirSynth

The configuration is one file, `~/.config/mimirsynth/config.json`, shared with every MimirSynth agent integration: if MimirSynth is already set up for another agent on this machine, Codex uses it as it is.

Setup asks for API tokens **hidden, in a terminal**. Never ask the person to paste a token into this conversation, and never write one yourself.

1. Find this plugin's `scripts/cli.py`: it is two folders up from this `SKILL.md`, at `<folder of this file>/../../scripts/cli.py`. Resolve it to an absolute path.
2. Tell the person to run, in their own terminal (on Windows, `python` instead of `python3`):
   ```
   python3 "<absolute path to scripts/cli.py>" setup
   ```
   It asks for the server URL, the brain's slug, a **reader** token for recall, an optional **contributor** token to propose, and the capture mode (`off`, the default; `draft`; or `send`). Tokens are created in MimirSynth, in My account → API tokens.
3. Then remind them that Codex only runs a plugin's hooks once they are trusted: open `/hooks` in Codex and trust the `mimirsynth` ones (and again after each update of the plugin). Without that, recall before each prompt and the news at session start do not happen.
4. When they are done, run the `status` command (below) to check the connection.

Status, from here: `python3 "<absolute path to scripts/cli.py>" status`. It needs network access to the MimirSynth server: if the sandbox blocks it, ask for the command to run outside the sandbox.
