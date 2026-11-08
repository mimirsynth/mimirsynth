**English** · [Español](README.es.md)

# MimirSynth for OpenClaw

A native [OpenClaw](https://github.com/openclaw/openclaw) plugin that gives your assistant the team's MimirSynth brain:

- **Recall before each prompt.** What the brain knows about the message is added to the turn, inside `<mimirsynth-memory brain="…">`. You set the size (`max_chars`, 4000) and the timeout (`timeout`, 4 s). If the server does not answer in time, nothing is added and the turn carries on. An expired or revoked token is said once, so recall does not stop without anyone noticing.
- **What changed at session start.** The facts learned and invalidated since the last session, inside `<mimirsynth-news>`, with the first prompt of each new session.
- **Two agent tools:** `mimirsynth_search` (recall on demand, with more results) and `mimirsynth_remember` (a proposal that waits in quarantine for a curator).
- **Commands** in a terminal (`openclaw mimirsynth …`) and in any chat (`/mimirsynth …`):

| Command | What it does |
|---|---|
| `openclaw mimirsynth setup` | Asks for the server, the brain, the tokens (hidden) and the capture mode, writes `~/.config/mimirsynth/config.json`, and offers to grant the plugin the conversation access OpenClaw requires |
| `status` | Connection, brain, role, scopes and expiry of each token, server version, what is on, capture mode and drafts |
| `search <query>` | Recall on demand |
| `remember --title … --content …` | A proposal with the write token (terminal; in a chat, ask the agent to remember it) |
| `drafts`, `send-draft <session>`, `drop-draft <session>` | Review what the capture keeps (capture = `draft`) |

- **A skill** (`skills/mimirsynth/SKILL.md`) that tells the agent how to read what is recalled (as data, not instructions) and when to propose a memory.
- **Optional capture of what each session learned**, off by default (below).

It is a **companion plugin**: it does not take OpenClaw's exclusive memory slot, so OpenClaw's own memory (`MEMORY.md`, its memory search, dreaming) keeps working, and MimirSynth adds what the team knows.

## Install

On the machine where OpenClaw's Gateway runs (OpenClaw 2026.9.36 or later):

```bash
openclaw plugins install @mimirsynth/openclaw && openclaw mimirsynth setup
```

OpenClaw shows the plugin's capabilities (two tools, its hooks, a CLI command, a skill) and asks you to accept them. `setup` then asks for:
- the MimirSynth URL and the brain's slug;
- a **reader** token for recall (My account → API tokens, scope Recall);
- optionally a **contributor** token to propose. The capture never sends with a curator token, because its proposals would skip quarantine;
- the capture mode;
- whether to grant the plugin **conversation access**. OpenClaw only runs a third-party plugin's hooks that read the conversation (the recall before each prompt, the capture) once you set `plugins.entries.mimirsynth.hooks.allowConversationAccess`; `setup` writes it through OpenClaw's own configuration writer. To do it by hand: `openclaw config set plugins.entries.mimirsynth.hooks.allowConversationAccess true`.

Check it with `openclaw mimirsynth status`, or `/mimirsynth status` in a chat. The same keys can come from `MIMIRSYNTH_*` environment variables (they win over the file), and a `projects` entry can give one of OpenClaw's workspaces another brain with its own tokens: see [`docs/AGENT_CLIENT.md`](../../docs/AGENT_CLIENT.md). The file is shared with every MimirSynth agent integration on that machine, so one `setup` serves all of them.

**Before it is published** (or to try a change), install it from a clone: `npm pack` builds `dist/` and the package, and OpenClaw installs the archive.

```bash
cd integrations/openclaw && npm ci && npm pack && openclaw plugins install npm-pack:./mimirsynth-openclaw-0.1.0.tgz
```

## Who sees the brain

An assistant on OpenClaw also talks in group chats and with other people. By default only **your own** conversations see what the brain knows: in a turn with other people (OpenClaw's `conversation` memory audience: a group, a channel, another sender) there is no recall, no news, no MimirSynth tools and no capture, and `/mimirsynth search` answers only to you. To let those conversations use it too:

```bash
openclaw config set plugins.entries.mimirsynth.config.conversations true
```

The recall also follows each turn's tool policy: a turn that may not call `mimirsynth_search` gets no recall either. Incognito sessions never see the brain.

## Capturing what a session learned (off by default)

`capture` in the shared configuration decides it:
- **`off`** (the default): nothing about the sessions is written or sent.
- **`draft`**: each session is kept on this machine, already redacted, until you review it with `openclaw mimirsynth drafts`.
- **`send`**: at the **next** session start, each finished session becomes a proposal.

What is recorded and sent:
- **Which sessions:** only those that changed files (OpenClaw's `write`, `edit` and `apply_patch`) or ended with an answer of at least 400 characters, as at most **one proposal per session**. A session ends when OpenClaw starts a new one (`/new`, `/reset`, idle or daily reset) or deletes it; a restart or a compaction does not end it.
- **What it holds:** the task (the first message), the outcome (the last answer) and the files changed. Never the transcript, and never what MimirSynth itself injected.
- **How it is sent:** with low confidence (`capture_confidence`, 0.3), so it waits in **quarantine**. It is only sent with a **contributor** token.
- **Secrets:** redacted with the server's own detector before anything is written or sent. It works by patterns and is not infallible.
- **Where the records live:** `~/.config/mimirsynth/state/openclaw/sessions/`, one file per session, readable only by you; records older than 14 days are deleted.

## Failing open

Every call has the configured timeout, and every hook catches everything: when MimirSynth is down or slow, nothing is injected and OpenClaw carries on. The recall runs in OpenClaw's prompt phase with its own 15 s budget on top.

## For developers

| Path | What |
|---|---|
| `src/index.ts` | The entry: registers the hooks, the tools, the chat command and the CLI |
| `src/hooks.ts` | Recall, news and the capture |
| `src/commands.ts` | What `status`, `search`, `remember` and the drafts answer |
| `src/setup.ts` | The terminal `setup` |
| `openclaw.plugin.json` | The manifest: id, tools, CLI command, skill, settings |
| `test/plugin.test.ts` | Against a stand-in for OpenClaw's API and a fake server (`npm test`) |
| `test/live.test.ts` | Against a real instance, run by `api/tests/test_openclaw_plugin.py` |

The plugin is built on the shared client library ([`integrations/shared/typescript`](../shared/typescript)), which `npm run build` bundles into `dist/index.js` (esbuild), so the package has no runtime dependencies and imports nothing from OpenClaw. `npm run check` type-checks it. CI (`.github/workflows/plugin-openclaw.yml`) also installs the packed plugin into a real OpenClaw and checks what it registers.

**Releasing:** any change here, or in the shared TypeScript library it bundles, raises `version` in `package.json`; the `plugin-version` check fails otherwise. Publishing needs the npm scope `@mimirsynth` and a ClawHub account: `npm publish --access public` from this folder, then `clawhub package publish` (see OpenClaw's [plugin publishing docs](https://docs.openclaw.ai/plugins/building-plugins)).
