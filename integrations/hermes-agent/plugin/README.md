**English** · [Español](README.es.md)

# MimirSynth for Hermes Agent

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) **memory provider** that connects the agent to a [MimirSynth](https://github.com/mimirsynth/mimirsynth) brain, the shared memory of a team:

- **Recall before each turn.** Hermes asks MimirSynth what it knows about your message and the answer reaches the model inside `<mimirsynth-memory brain="…">`, with no tool call. Short messages ("ok", "go on") and slash commands are not recalled.
- **What changed, at session start.** The facts the brain learned or dropped since your last session arrive once, with the first message, inside `<mimirsynth-news>`.
- **Two tools for the agent.** `mimirsynth_search` looks for more; `mimirsynth_remember` proposes a durable fact, decision or procedure. A proposal **waits in quarantine** until a curator approves it.
- **Commands.** `hermes mimirsynth setup | status | search | remember | drafts` in a terminal, and `/mimirsynth status | search | remember | drafts` in a chat.
- **Session capture, off by default.** When you turn it on, what a session learned (its task, its outcome and the files it changed, never the transcript) becomes one quarantined proposal, or a draft for you to review.
- **It never stops the agent.** Every call has a short timeout; when MimirSynth is down or slow, Hermes carries on without memory. An expired or revoked token is said once, so memory does not stop without anyone noticing.

It is built on MimirSynth's shared agent library and reads the same configuration as every other MimirSynth integration (Claude Code, Codex, OpenCode, OpenClaw): one setup serves them all.

## Install

You need a MimirSynth server, a brain and an API token for it (a **reader** token to recall, a **contributor** token to propose; see [Connect agents](https://github.com/mimirsynth/mimirsynth/wiki/Connect-agents)). Then, in a terminal:

```bash
hermes plugins install mimirsynth/mimirsynth/integrations/hermes-agent/plugin && hermes memory setup mimirsynth
```

The first command installs the plugin into your Hermes profile (`$HERMES_HOME/plugins/mimirsynth`); the second asks for the server, the brain and the tokens (hidden, never through the chat), writes the shared configuration and makes MimirSynth the profile's memory provider. Start a new session and it is working: `hermes mimirsynth status` says what it connected to.

Hermes Agent 0.21.4 or later. The plugin has no dependencies beyond Python's standard library.

To stop using it, choose another provider with `hermes memory setup` (or `hermes memory off`), and remove it with `hermes plugins remove mimirsynth`.

## Configuration

`hermes memory setup mimirsynth` (or `hermes mimirsynth setup`) writes `~/.config/mimirsynth/config.json`, readable only by you. It is the file every MimirSynth integration reads; its keys are documented in [AGENT_CLIENT.md](https://github.com/mimirsynth/mimirsynth/blob/main/docs/AGENT_CLIENT.md):

| Key | Default | Meaning |
|---|---|---|
| `url`, `brain`, `token` | — | The server, the brain's slug and an API token (reader is enough to recall) |
| `write_token` | `token` | A contributor token, to propose |
| `timeout` | `4` | Seconds a call may take before it gives up |
| `max_chars` | `4000` | Most characters the recall injects before each turn |
| `recall`, `news` | on | Recall before each turn; what changed at session start |
| `capture` | `off` | `off`, `draft` or `send` (below) |
| `projects` | — | Another brain (and its tokens) for some folders |

Any key can also come from a `MIMIRSYNTH_<KEY>` variable (`MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_BRAIN`…), which wins over the file. Inside Hermes these are read through Hermes's own secret scope, so a profile can keep its own brain and token in its `.env` (`$HERMES_HOME/.env`) while other profiles use the shared file.

## Commands

| In a terminal | In a chat | What it does |
|---|---|---|
| `hermes mimirsynth setup` | — | Asks for the server, the brain and the tokens, hidden, and writes the configuration |
| `hermes mimirsynth status` | `/mimirsynth status` | Connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts |
| `hermes mimirsynth search <query>` | `/mimirsynth search <query>` | Recall on demand, with more results than before each turn |
| `hermes mimirsynth remember --title T --content C` | `/mimirsynth remember <title> :: <content>` | Proposes a memory (redacted first); it waits for a curator |
| `hermes mimirsynth drafts` | `/mimirsynth drafts` | The sessions the capture kept for you to review |
| `hermes mimirsynth send-draft <session>` / `drop-draft <session>` | the same | Proposes one of them, or forgets it |

Hermes shows the `hermes mimirsynth …` commands while MimirSynth is the active memory provider.

## Session capture

| `capture` | What happens |
|---|---|
| `off` | The default. Nothing about your sessions is written or sent |
| `draft` | Each session is kept on this machine, already redacted, until you review it (`hermes mimirsynth drafts`) |
| `send` | At the **next** session start, each finished session worth it becomes one proposal, in quarantine |

Only sessions that changed files (with Hermes's `write_file` or `patch`) or ended with an answer of at least 400 characters are worth it, at most one proposal per session, and only with a **contributor** token: with any other role the capture refuses and says so, because a curator's proposal would skip quarantine. The records are built from the turns Hermes hands its memory provider, live in `$HERMES_HOME/mimirsynth/sessions/` (one JSON file per session, per Hermes profile, readable only by you) and are deleted after 14 days. Subagents and scheduled (cron) runs are never captured.

## Privacy and what it does on your machine

- **Network:** it only talks to the MimirSynth server you configure: your message (up to 1,500 characters) for each recall, and what you or the agent choose to remember. With capture on `send`, a summary of each finished session.
- **Secrets:** everything it proposes or records is redacted first with MimirSynth's own secret detector (tokens, keys, passwords, URL credentials become `[secret removed]`). It works by patterns and is not infallible: do not paste secrets.
- **Files:** it reads `~/.config/mimirsynth/config.json` (which holds your MimirSynth tokens) and, only with capture on, writes `$HERMES_HOME/mimirsynth/sessions/`.
- **Background work:** one short thread at session start (the news and the capture's sends), bounded by the timeout. No telemetry.

## Troubleshooting

- `hermes mimirsynth status` checks each token against the server and says why it fails.
- Nothing is recalled: check `recall` is on and that the brain has memory on the topic (`hermes mimirsynth search …`). A server that does not answer within `timeout` is skipped silently; `hermes logs errors` shows why.
- `hermes memory status` says whether MimirSynth is the active provider and, if it is not available, what is missing.

The plugin lives in [`integrations/hermes-agent`](https://github.com/mimirsynth/mimirsynth/tree/main/integrations/hermes-agent) of the MimirSynth repository and is versioned with it. Apache-2.0.
