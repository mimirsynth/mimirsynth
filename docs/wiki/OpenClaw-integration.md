**English** · [Español](Integraci%C3%B3n-con-OpenClaw)

# OpenClaw integration

[OpenClaw](https://github.com/openclaw/openclaw) gets MimirSynth through a native **companion plugin**: it does not take OpenClaw's exclusive memory slot, so OpenClaw's own memory (`MEMORY.md`, its memory search, dreaming) keeps working, and MimirSynth adds what the team knows. OpenClaw 2026.9.36 or later.

## Install
On the machine where OpenClaw's Gateway runs:
```bash
openclaw plugins install npm:@mimirsynth/openclaw && openclaw mimirsynth setup
```
The plugin is on npm, not on ClawHub, hence the `npm:` prefix. OpenClaw warns that the source is outside ClawHub's review and asks you to confirm, then shows the plugin's capabilities (two tools, its hooks, a CLI command, a skill) and asks you to accept them.

To try a change from a clone: `cd integrations/openclaw && npm ci && openclaw plugins install "npm-pack:./$(npm pack | tail -1)"`.

## Setup
`openclaw mimirsynth setup` asks, in the terminal and never through a chat, for the URL, the brain, a **reader** token for recall, optionally a **contributor** token to propose (hidden) and the capture mode, and writes the shared file ([[Agent plugin configuration]]). It then offers to grant the conversation access OpenClaw requires ([below](#conversation-access)). Check it with `openclaw mimirsynth status`, or `/mimirsynth status` in a chat.

## What it does
| When | What |
|---|---|
| First prompt of a new session | The facts learned and invalidated since the last session, inside `<mimirsynth-news>`. With capture on `send`, the finished sessions are proposed |
| Each prompt | The recall for the message, inside `<mimirsynth-memory brain="…">`, added to the turn. Prompts shorter than 12 characters and slash commands are skipped |
| A session ends (`/new`, `/reset`, idle or daily reset, deletion) | With capture on, the session is closed and kept or queued |

Every call has the configured timeout, on top of OpenClaw's own 15 s budget for the prompt phase: when MimirSynth is down or slow, nothing is injected and the assistant carries on. An expired or revoked token is said once.

## Commands and tools
The agent has two tools, `mimirsynth_search` (recall on demand, with more results) and `mimirsynth_remember` (a proposal that waits in quarantine), and a skill that tells it to read what is recalled as data, not instructions, and when to propose a memory.

| Command | What it does |
|---|---|
| `openclaw mimirsynth setup` | Asks for the server, the brain, the tokens (hidden) and the capture mode, and offers the conversation access |
| `status` | Connection, brain, role, scopes and expiry of each token, server version, what is on, capture mode and drafts |
| `search <query>` | Recall on demand |
| `remember --title … --content …` | A proposal with the write token (terminal; in a chat, ask the agent to remember it) |
| `drafts`, `send-draft <session>`, `drop-draft <session>` | Review what the capture keeps (capture = `draft`) |

They work in a terminal (`openclaw mimirsynth …`) and in any chat (`/mimirsynth …`).

## Capture
Off by default; `capture` decides it ([[Agent plugin configuration]]). What is particular to OpenClaw:
- Files changed are those of OpenClaw's `write`, `edit` and `apply_patch`.
- A session ends when OpenClaw starts a new one (`/new`, `/reset`, idle or daily reset) or deletes it; a restart or a compaction does not end it.
- What MimirSynth itself injected is never part of the record.

## What it writes on your machine
- `~/.config/mimirsynth/config.json`, the shared configuration (by `setup`).
- `plugins.entries.mimirsynth.hooks.allowConversationAccess` in OpenClaw's configuration, if you accept it in `setup`.
- With capture on: `~/.config/mimirsynth/state/openclaw/sessions/`, one file per session, readable only by you, deleted after 14 days.

## Conversation access
OpenClaw only runs a third-party plugin's hooks that read the conversation (the recall before each prompt, the capture) once you allow it. `setup` offers to write it through OpenClaw's own configuration writer; by hand:
```bash
openclaw config set plugins.entries.mimirsynth.hooks.allowConversationAccess true
```

## Who sees the brain
By default only **your own** conversations see what the brain knows. In a turn with other people (OpenClaw's `conversation` memory audience: a group, a channel, another sender) there is no recall, no news, no MimirSynth tools and no capture, and `/mimirsynth search` answers only to you. To let those conversations use it too:
```bash
openclaw config set plugins.entries.mimirsynth.config.conversations true
```
The recall also follows each turn's tool policy: a turn that may not call `mimirsynth_search` gets no recall either. The plugin adds its tools to OpenClaw's built-in tool profiles; if you keep an explicit `tools.allow` list, add them with `openclaw config set tools.alsoAllow '["mimirsynth"]' --strict-json --merge`. Incognito sessions never see the brain.

## Update and remove
- Update: with the Gateway stopped, `openclaw plugins update mimirsynth`.
- Remove: `openclaw plugins uninstall mimirsynth`.

## Troubleshooting
| Symptom | What to do |
|---|---|
| No memory before the prompts | `openclaw mimirsynth status`: conversation access not granted, `url`, `brain` or `token` missing, or a conversation with other people |
| The recall works in a direct chat but not in a group | Expected: set `plugins.entries.mimirsynth.config.conversations` to `true` |
| The tools are not offered to the model | An explicit `tools.allow` list: add them with `tools.alsoAllow` (above). The Gateway log says so once per session |
| «token expired» or «revoked» | Create or rotate the token ([[Connect agents]]) and run `openclaw mimirsynth setup` again |
| The capture sends nothing | It needs a contributor `write_token`; a session is sent at the next session start |

Full detail: [the plugin's README](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/openclaw/README.md).
