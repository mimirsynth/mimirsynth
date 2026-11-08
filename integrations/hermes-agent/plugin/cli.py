"""`hermes mimirsynth …`: the plugin's commands in a terminal. Hermes shows them while MimirSynth is the active memory provider; the
first setup is `hermes memory setup mimirsynth`, which asks the same questions and activates the provider."""
from __future__ import annotations

from . import commands


def mimirsynth_command(args) -> int:
    cmd = getattr(args, "mimirsynth_command", None)
    if cmd == "setup":
        return commands.setup(url=args.url or "", brain=args.brain or "", capture_mode=args.capture or "")
    if cmd == "search":
        code, text = commands.search(" ".join(args.query))
    elif cmd == "remember":
        code, text = commands.remember(args.title, args.content, args.confidence)
    elif cmd == "drafts":
        code, text = commands.drafts()
    elif cmd == "send-draft":
        code, text = commands.send_draft(args.session)
    elif cmd == "drop-draft":
        code, text = commands.drop_draft(args.session)
    else:
        code, text = commands.status()
    print(text)
    return code


def register_cli(subparser) -> None:
    subs = subparser.add_subparsers(dest="mimirsynth_command")
    s = subs.add_parser("setup", help="Ask for the server, the brain and the tokens (hidden) and write the shared configuration")
    s.add_argument("--url")
    s.add_argument("--brain")
    s.add_argument("--capture", choices=("off", "draft", "send"))
    subs.add_parser("status", help="Connection, brain, role and expiry of each token, server version, capture mode")
    s = subs.add_parser("search", help="Recall on demand, with more results than before each turn")
    s.add_argument("query", nargs="+")
    s = subs.add_parser("remember", help="Propose a memory (redacted first); it waits in quarantine for a curator")
    s.add_argument("--title", required=True)
    s.add_argument("--content", required=True)
    s.add_argument("--confidence", type=float)
    subs.add_parser("drafts", help="The sessions the capture recorded and has not sent (capture = draft)")
    for name, what in (("send-draft", "Propose one of the drafts"), ("drop-draft", "Forget one of the drafts")):
        s = subs.add_parser(name, help=what)
        s.add_argument("session")
    subparser.set_defaults(func=mimirsynth_command)
