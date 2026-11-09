**English** · [Español](Integraci%C3%B3n-con-OpenCode)

# OpenCode integration

A native [OpenCode](https://opencode.ai) plugin gives the agent the brain's memory on every prompt, adds four commands and the brain's MCP server, with the same configuration as the other agent plugins. It was written against OpenCode 1.19.

## Install
One command, with [Node.js](https://nodejs.org) 18 or later:
```bash
npx -y @mimirsynth/opencode install
```
It adds the plugin to OpenCode's global configuration (`opencode plugin @mimirsynth/opencode --global`, which OpenCode installs from npm at the next start) and then runs the setup. The two steps can also be done apart:
```bash
opencode plugin @mimirsynth/opencode --global
npx -y @mimirsynth/opencode setup
```
Or add `"@mimirsynth/opencode"` to `"plugin"` in `~/.config/opencode/opencode.json` (every project) or in a project's `opencode.json`.

## Setup
`npx -y @mimirsynth/opencode setup` asks, in your terminal and hidden, for the URL and the brain, a **reader** token for recall, optionally a **contributor** token to propose, and the capture mode, and writes the shared file ([[Agent plugin configuration]]). Restart OpenCode afterwards and check it with `/mimirsynth-status`. The commands run inside the plugin and need neither a shell nor Node.js; only the setup, which asks for tokens, runs in a terminal.

## What it does
| When | What |
|---|---|
| First message of a session | The facts learned and invalidated since the last session, inside `<mimirsynth-news>`. With capture on `send`, the finished sessions are proposed |
| Every prompt | The recall for the prompt, inside `<mimirsynth-memory>`, added to the message before the model reads it. The prompt is redacted before it leaves the machine. Prompts shorter than 12 characters and slash commands are skipped |
| OpenCode starts | Adds the four commands and the `mimirsynth` MCP server to OpenCode's configuration, in memory |

If MimirSynth does not answer within `timeout`, nothing is injected and the prompt carries on; an expired or revoked token is said in a notice.

## Commands and tools
| Command | What it does |
|---|---|
| `/mimirsynth-setup` | Tells you how to configure it. Tokens never go through the conversation |
| `/mimirsynth-status` | Connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts, and other memory plugins here |
| `/mimirsynth-search <query>` | Recall on demand, with more results |
| `/mimirsynth-remember [title]` | The agent writes a memory from the conversation and proposes it once you agree; with no title, it reviews the drafts the capture left |

The model also gets the brain's MCP tools that read (`recall`, `facts_about`, `timeline`, `whats_new`…). It proposes through the plugin's own tools, `mimirsynth_propose_memory`, `mimirsynth_send_draft` and `mimirsynth_drop_draft`, which redact first and use the write token.

The same commands exist in a terminal: `npx -y @mimirsynth/opencode status`, `search`, `remember`, `drafts`, `send-draft` and `drop-draft`.

## Capture
Off by default; `capture` decides it ([[Agent plugin configuration]]). What is particular to OpenCode:
- OpenCode has no «session end», so a session counts as finished when OpenCode closes, when you delete it, or after 30 minutes without a new prompt. It leaves the machine at the next session start.
- What a subagent changes counts in the session that started it.

## What it writes on your machine
- `~/.config/mimirsynth/config.json`, the shared configuration (by `setup`).
- The plugin's entry in OpenCode's `opencode.json` (by `install`, or by you).
- With capture on: `~/.config/mimirsynth/state/opencode/sessions/`, one file per session, readable only by you, deleted after 14 days.

## The MCP server, without the token in `opencode.json`
The plugin adds the brain's MCP server as `mimirsynth` when OpenCode loads its configuration, with the recall token taken from MimirSynth's own file. That entry lives only in memory: the token is **never written to `opencode.json`**, so a project's configuration can be committed safely.

In `opencode.json` the plugin takes options: `["@mimirsynth/opencode", {"mcp": false}]` leaves out the MCP server, `{"commands": false}` the four commands. The plugin never replaces a command or an MCP server of the same name that you already have: to configure the MCP server yourself, add your own `mimirsynth` entry.

If another plugin or MCP server looks like it injects memory too, the session start says so in a notice and `/mimirsynth-status` lists them; nothing is blocked.

## Update and remove
- Update: OpenCode checks plugins listed without a version when it starts; `opencode plugin update @mimirsynth/opencode` installs the new one. An entry with an exact version (`@mimirsynth/opencode@0.1.1`) stays on it.
- Remove: take `@mimirsynth/opencode` out of `"plugin"` in `opencode.json`.

## Troubleshooting
| Symptom | What to do |
|---|---|
| The `/mimirsynth-…` commands do not appear | Restart OpenCode after the install; check that `@mimirsynth/opencode` is in `"plugin"` of the `opencode.json` it reads |
| No memory before the prompts | `/mimirsynth-status`: `url`, `brain` or `token` are missing, or `recall` is off |
| «token expired» or «revoked» | Create or rotate the token ([[Connect agents]]) and run `npx -y @mimirsynth/opencode setup` again |
| The MCP tools are missing | The `mcp` option is `false`, or you already have a `mimirsynth` MCP entry of your own, which wins |
| The capture sends nothing | It needs a contributor `write_token`; a session is sent at the next session start |

Full detail: [the plugin's README](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/opencode/README.md).
