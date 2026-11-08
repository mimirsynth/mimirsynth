---
name: remember
description: Propose a memory to the team's MimirSynth brain (it waits in quarantine for a curator), or review the session drafts the capture left. Use when the person asks to remember, save or record something in MimirSynth, or to review MimirSynth session drafts.
---

# Remember in MimirSynth

The command line is this plugin's `scripts/cli.py`, two folders up from this `SKILL.md` (on Windows, `python` instead of `python3`). Every command reaches the MimirSynth server over the network: if the sandbox blocks it, ask for the command to run outside the sandbox.

## A memory

Write one self-contained fact, decision or procedure: what, where, when and why, with names and dates, so it makes sense to someone who did not see this conversation. **Never include passwords, keys or tokens**: say where they are kept instead (the command also removes the ones it detects, but it works by patterns and is not infallible). Show the person the title and text and propose it once they agree:

```
python3 "<folder of this file>/../../scripts/cli.py" remember --title "<short title>" --content "<the memory>"
```

Add `--confidence 0.0-1.0` when you are not sure. With a contributor token the proposal waits for a curator; say so.

## The session drafts

When the person has the capture in `draft` mode, finished sessions wait on this machine, already redacted:

```
python3 "<folder of this file>/../../scripts/cli.py" drafts
```

Show them, and for each one ask whether to propose it (`send-draft <session>`) or forget it (`drop-draft <session>`).
