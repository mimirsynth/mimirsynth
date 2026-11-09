**English** · [Español](Integraci%C3%B3n-con-Hermes-Agent)

# Hermes Agent integration

[Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous Research) gets MimirSynth as a **memory provider**: the brain's recall reaches the model before each turn, what changed arrives with the first message of a session, and the agent has two tools. Hermes Agent 0.21.4 or later; the plugin has no dependencies beyond Python's standard library.

## Install
In a terminal:
```bash
hermes plugins install mimirsynth/mimirsynth/integrations/hermes-agent/plugin && hermes memory setup mimirsynth
```
The first command installs the plugin into your Hermes profile (`$HERMES_HOME/plugins/mimirsynth`); the second configures it and makes it the profile's memory provider.

## Setup
`hermes memory setup mimirsynth` (or `hermes mimirsynth setup`, which only writes the file) asks for the server, the brain, a **reader** token to recall and a **contributor** token to propose, hidden and never through the chat, and writes the shared file ([[Agent plugin configuration]]). Start a new session and it is working: `hermes mimirsynth status` says what it connected to.

## What it does
| When | What |
|---|---|
| First message of a session | The facts the brain learned or dropped since your last session, once, inside `<mimirsynth-news>`. With capture on `send`, the finished sessions are proposed, in a short background thread |
| Each turn | The recall for your message, inside `<mimirsynth-memory brain="…">`, with no tool call. Short messages («ok», «go on») and slash commands are not recalled |
| Each turn, with capture on | The task, the outcome and the files changed (with Hermes's `write_file` or `patch`) are noted for the session |

Every call has a short timeout: when MimirSynth is down or slow, Hermes carries on without memory. An expired or revoked token is said once.

## Commands and tools
The agent has two tools: `mimirsynth_search` looks for more, and `mimirsynth_remember` proposes a durable fact, decision or procedure, which waits in quarantine.

| In a terminal | In a chat | What it does |
|---|---|---|
| `hermes mimirsynth setup` | — | Asks for the server, the brain and the tokens, hidden, and writes the configuration |
| `hermes mimirsynth status` | `/mimirsynth status` | Connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts |
| `hermes mimirsynth search <query>` | `/mimirsynth search <query>` | Recall on demand, with more results than before each turn |
| `hermes mimirsynth remember --title T --content C` | `/mimirsynth remember <title> :: <content>` | Proposes a memory (redacted first); it waits for a curator |
| `hermes mimirsynth drafts` | `/mimirsynth drafts` | The sessions the capture kept for you to review |
| `hermes mimirsynth send-draft <session>` / `drop-draft <session>` | the same | Proposes one of them, or forgets it |

Hermes shows the `hermes mimirsynth …` commands while MimirSynth is the active memory provider.

## Capture
Off by default; `capture` decides it ([[Agent plugin configuration]]). What is particular to Hermes: the records are built from the turns Hermes hands its memory provider, one set per Hermes profile, and subagents and scheduled (cron) runs are never captured.

## What it writes on your machine
- `~/.config/mimirsynth/config.json`, the shared configuration (by `setup`).
- `memory.provider: mimirsynth` in the profile's Hermes configuration (by `hermes memory setup mimirsynth`).
- With capture on: `$HERMES_HOME/mimirsynth/sessions/`, one file per session, readable only by you, deleted after 14 days.

It only talks to the MimirSynth server you configure, sends your message (up to 1,500 characters) for each recall, and has no telemetry.

## One memory provider per profile
Hermes uses **one** memory provider at a time, set in `memory.provider`. `hermes memory setup mimirsynth` sets it to `mimirsynth`; if it cannot, it says so, and you set it with `hermes config set memory.provider mimirsynth`. Choosing MimirSynth replaces the provider the profile had. `hermes memory status` says which provider is active and, if MimirSynth is not available, what is missing.

Each profile can use another brain: put `MIMIRSYNTH_URL`, `MIMIRSYNTH_BRAIN` and `MIMIRSYNTH_TOKEN` (and `MIMIRSYNTH_WRITE_TOKEN`) in its `.env` (`$HERMES_HOME/.env`). Inside Hermes they are read through its own secret scope and win over the shared file.

## Update and remove
- Update: `hermes plugins update mimirsynth`.
- Stop using it: choose another provider with `hermes memory setup`, or `hermes memory off`.
- Remove: `hermes plugins remove mimirsynth`.

## Troubleshooting
| Symptom | What to do |
|---|---|
| No memory in the turns | `hermes memory status`: MimirSynth is not the active provider, or the configuration lacks `url`, `brain` or `token` |
| The `hermes mimirsynth` commands do not exist | They appear only while MimirSynth is the active memory provider |
| Nothing is recalled for a topic the brain knows | `hermes mimirsynth search …`; a server that does not answer within `timeout` is skipped silently, and `hermes logs errors` shows why |
| «token expired» or «revoked» | Create or rotate the token ([[Connect agents]]) and run `hermes mimirsynth setup` again |
| The capture sends nothing | It needs a contributor `write_token`; subagents and cron runs are never captured |

Full detail: [the plugin's README](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/hermes-agent/plugin/README.md).
