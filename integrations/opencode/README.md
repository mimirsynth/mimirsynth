**English** · [Español](README.es.md)

# MimirSynth for OpenCode

A native [OpenCode](https://opencode.ai) plugin that gives the agent your team's memory, with the same features as the [Claude Code plugin](../claude-code/README.md):
- **What changed at session start.** The facts learned and invalidated since the last session (`POST /news`), inside `<mimirsynth-news>`, with the first message.
- **Recall before every prompt.** The memory for the prompt, inside `<mimirsynth-memory>`, added to the message before the model reads it. You set the size (`max_chars`, 4000) and the timeout (`timeout`, 4 s). The prompt is redacted before it leaves the machine. If the server does not answer, nothing is injected and the prompt carries on; an expired or revoked token is said in a notice.
- **Four commands:**

| Command | What it does |
|---|---|
| `/mimirsynth-setup` | Tells you how to configure it. Tokens never go through the conversation: you run the setup in your terminal, which asks for them hidden |
| `/mimirsynth-status` | Connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts, and other memory plugins here |
| `/mimirsynth-search <query>` | Recall on demand, with more results |
| `/mimirsynth-remember [title]` | The agent writes a memory from the conversation and proposes it once you agree; with no title, it reviews the drafts the capture left |

- **The brain's MCP server** for on-demand tools, added as `mimirsynth` with the recall token, so it offers the reading ones (`recall`, `facts_about`, `timeline`, `whats_new`…); proposals go through the plugin's own tool, which redacts them first and uses the write token. The token stays in MimirSynth's own file: it is never written to `opencode.json`.
- **Optional capture of what each session learned**, explained below.

The commands run inside the plugin, so they need neither a shell nor Node.js; only the setup, which asks for tokens, runs in a terminal.

## Install

One command, with [Node.js](https://nodejs.org) 18 or later:
```bash
npx -y @mimirsynth/opencode install
```
It adds the plugin to OpenCode's global configuration (`opencode plugin @mimirsynth/opencode --global`, which OpenCode installs from npm at the next start) and then runs the setup. If you prefer, do the two steps yourself:
```bash
opencode plugin @mimirsynth/opencode --global
npx -y @mimirsynth/opencode setup
```
Or add `"@mimirsynth/opencode"` to `"plugin"` in `~/.config/opencode/opencode.json` (every project) or in a project's `opencode.json`.

The setup asks for:
- the URL and the brain;
- a **reader** token for recall (My account → API tokens, scope Recall);
- optionally a **contributor** token to propose;
- the capture mode.

It writes `~/.config/mimirsynth/config.json`, readable only by you. The same keys can come from `MIMIRSYNTH_*` environment variables (`MIMIRSYNTH_URL`, `MIMIRSYNTH_BRAIN`, `MIMIRSYNTH_TOKEN`…), which take precedence. Restart OpenCode afterwards and check it with `/mimirsynth-status`.

The file is shared with every MimirSynth agent plugin, so one setup serves Claude Code, OpenCode and the rest, and a `projects` entry can give some folders another brain with its own tokens: see [`docs/AGENT_CLIENT.md`](../../docs/AGENT_CLIENT.md).

### Options

In `opencode.json`, the plugin takes options: `["@mimirsynth/opencode", {"mcp": false}]` leaves out the MCP server, `{"commands": false}` the four commands. The plugin never replaces a command or an MCP server of the same name that you already have: to configure the MCP server yourself, add your own `mimirsynth` entry.

## Capturing what a session learned (off by default)

`capture` decides it:
- **`off`** (the default): nothing about the sessions is written or sent.
- **`draft`**: each session is kept on this machine, already redacted, until you review it with `/mimirsynth-remember`.
- **`send`**: at the **next** session start, each finished session becomes a proposal.

What is recorded and sent:
- **Which sessions:** only those that changed files or ended with a substantial answer, as at most **one proposal per session**. What a subagent changes counts in the session that started it.
- **What it holds:** the task (the first prompt), the outcome (the last answer) and the files changed. Never the transcript.
- **How it is sent:** with low confidence (`capture_confidence`, 0.3), so it waits in **quarantine**. It is only sent with a **contributor** token: with a curator's it would be approved at once, so it is refused and said.
- **Secrets:** before anything is written to disk or sent, it is redacted with a port of the server's own detector, kept equal to it by the shared contract tests. It works by patterns and is not infallible: read the drafts if in doubt.
- **When a session is finished:** OpenCode has no «session end», so a session counts as finished when OpenCode closes, when you delete it, or after 30 minutes without a new prompt. It leaves the machine at the next session start.
- **Where:** `~/.config/mimirsynth/state/opencode/sessions/`, one file per session readable only by you; records older than 14 days are deleted.

## Other memory plugins

If another plugin or MCP server in OpenCode's configuration looks like it injects memory too, the session start says so in a notice (it does not block anything) and `/mimirsynth-status` lists them. MimirSynth's blocks are marked so you can tell them apart.

## How it works

The plugin uses OpenCode's [plugin hooks](https://opencode.ai/docs/plugins): `config` (adds the commands and the MCP server), `chat.message` (recall and what changed, as a synthetic part of the message), `command.execute.before` (runs the commands), `tool.execute.after` and the `session.*` / `message.*` events (the capture), and three tools of its own: `mimirsynth_propose_memory`, `mimirsynth_send_draft` and `mimirsynth_drop_draft`. Every hook fails open: whatever goes wrong, OpenCode carries on.

It is built on the shared client library ([`integrations/shared/typescript`](../shared/typescript)), bundled into the package when it is built, and it was written against OpenCode 1.19.

## Development

```bash
npm ci
npm run check   # types
npm test        # the hooks and the command-line tool, against a fake server
npm run build   # dist/index.js (the plugin) and dist/cli.js (the command-line tool)
```
`api/tests/test_opencode_plugin.py` runs the hooks against a test instance of MimirSynth and, with `MIMIRSYNTH_TEST_OPENCODE=<opencode>`, OpenCode itself with the plugin and a local stand-in model (`test/mock-llm.mjs`); the `plugin-opencode` workflow runs both. To try a local copy in OpenCode, put its folder in `"plugin"`: `"file:///path/to/integrations/opencode"` (after `npm run build`).

**Releasing:** any change under this folder raises `version` in `package.json` (the `plugin-version` check fails otherwise, and npm refuses to publish a version twice). Each MimirSynth release publishes to npm the version npm does not have yet, with provenance (the `npm` job of `.github/workflows/release.yml`); nobody runs `npm publish` by hand. `prepack` builds it first.
