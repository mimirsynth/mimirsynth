"""MimirSynth for Hermes Agent: a memory provider that recalls from a MimirSynth brain before each turn, says what changed at session
start, gives the agent `mimirsynth_search` and `mimirsynth_remember` (a proposal, in quarantine), and, only when it is turned on, captures
what a session learned. See README.md."""
from __future__ import annotations

from .provider import MimirSynthProvider


def register(ctx) -> None:
    ctx.register_memory_provider(MimirSynthProvider())
    from .commands import slash
    try:
        ctx.register_command("mimirsynth", slash, description="MimirSynth: status, search, remember, drafts",
                             args_hint="<status|search|remember|drafts|send-draft|drop-draft> …")
    except Exception:  # noqa: BLE001  (an older Hermes without chat commands: the terminal and the tools still work)
        pass
