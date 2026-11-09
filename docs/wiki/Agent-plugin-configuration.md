**English** · [Español](Configuraci%C3%B3n-de-los-plugins-de-agente)

# Agent plugin configuration

Every native agent plugin ([[Claude Code integration]], [[Codex integration]], [[OpenCode integration]], [[Hermes Agent integration]], [[OpenClaw integration]]) reads **one configuration file** and behaves the same way: recall before each prompt, what changed at session start, `setup` / `status` / `search` / `remember`, and a session capture that is off by default. One `setup`, in any of them, serves every agent on the machine. This page is that file; each plugin page only says what is particular to its agent.

The full contract, for whoever writes a plugin, is [`docs/AGENT_CLIENT.md`](https://github.com/mimirsynth/mimirsynth/blob/main/docs/AGENT_CLIENT.md).

## The file
`~/.config/mimirsynth/config.json`, on every system (Windows included), or the file named by **`MIMIRSYNTH_CONFIG`**. Each plugin's `setup` writes it, asking for the tokens hidden, in a terminal and never through the conversation, and makes it readable only by its owner (`0600`). Running `setup` again keeps what you do not change.

```json
{
  "url": "https://mimirsynth.example.com",
  "brain": "team",
  "token": "mst_…",
  "write_token": "mst_…",
  "capture": "off",
  "projects": {
    "/home/me/work/infra": {"brain": "infra", "token": "mst_…", "write_token": "mst_…"}
  }
}
```

| Key | Default | Meaning |
|---|---|---|
| `url` | — | The server, `https://…` (a trailing `/` does not matter) |
| `brain` | — | The brain's slug |
| `token` | — | An API token for that brain, used to recall. **Reader** with the Recall scope is enough |
| `write_token` | `token` | A **contributor** token, used to propose |
| `timeout` | `4` | Seconds a call may take before the plugin gives up |
| `max_chars` | `4000` | Most characters the recall before each prompt injects |
| `recall` | `true` | Recall before each prompt |
| `news` | `true` | What changed in the brain, at session start |
| `capture` | `off` | What happens to what a session learned: `off`, `draft` or `send` ([below](#capture-of-what-a-session-learned)) |
| `capture_confidence` | `0.3` | The confidence a captured proposal declares (0 to 1) |
| `projects` | — | Other values for some folders ([below](#another-brain-per-folder-projects)) |

`url`, `brain` and `token` are what a plugin needs to work at all; without them it does nothing and says so in `status`.

## Where a value comes from
The first one that gives it wins:
1. the environment variable **`MIMIRSYNTH_<KEY>`**: `MIMIRSYNTH_URL`, `MIMIRSYNTH_BRAIN`, `MIMIRSYNTH_TOKEN`, `MIMIRSYNTH_WRITE_TOKEN`, `MIMIRSYNTH_CAPTURE`…;
2. the entry of `projects` for the working directory;
3. the top level of the file;
4. the default.

An empty value (a variable that is unset or blank, `""` or `null` in the file) counts as not given, so the next one applies. A file that is missing or is not valid JSON counts as empty. A value that cannot be read as its type (`"timeout": "soon"`) falls back to the default: a typo never stops an agent. Booleans take `false`, `off`, `no` and `0` as false.

Environment variables are how one agent uses another brain without touching the shared file, for example a Hermes Agent profile through its own `.env`.

## Another brain per folder: `projects`
`projects` maps a folder to an object with any of the keys above. When the agent works in that folder or below it, its values replace the top-level ones; when several folders hold the working directory, the deepest one wins. Folders are absolute (a leading `~` is the home folder), compared without following links and, on Windows, without case. A folder whose name only starts the same does not count: `/work` does not hold `/workshop`. Environment variables still win over it.

Each token is valid for one brain, so an entry that changes `brain` brings that brain's `token` and `write_token`: otherwise the top-level token is used and the server answers 403. Tokens stay in this one file, never in the repository.

## Reader and contributor tokens
A plugin uses up to two tokens of the same brain, created in [[My account]] → **API tokens** ([[Connect agents]]):

| Key | Role | Used for |
|---|---|---|
| `token` | **Reader** (Recall scope; add Documents to get passages) | The recall before each prompt, what changed, `search`, `status` |
| `write_token` | **Contributor** (Propose scope) | `remember` and the capture's proposals, which wait in quarantine for a curator |

Without `write_token`, proposals go with `token`, and a reader token cannot propose. One contributor token in `token` works for both. Do not give a plugin a **curator** token: its proposals would skip quarantine, so the capture refuses to send with one and says so. `status` shows each token's role, scopes and expiry, and an expired or revoked token is said in the agent, so the memory never stops without anyone noticing.

## Capture of what a session learned
| `capture` | What happens |
|---|---|
| `off` | The default. Nothing about the sessions is written or sent |
| `draft` | Each session is kept on this machine, already redacted, until you review it (`remember` with no title, or the plugin's `drafts` command) |
| `send` | At the **next** session start, each finished session worth it becomes one proposal, in quarantine |

`drafts` is read as `draft` and `auto` as `send`; any other value is `off`. The rules are the same in every plugin:
- **Which sessions:** only those that changed files, or ended with an answer of at least 400 characters; at most **one proposal per session**.
- **What it holds:** the task (the first prompt, up to 500 characters), the outcome (the last answer, up to 3000) and the files changed (the first 20). Never the transcript.
- **The proposal:** named «`<Agent>: <project> — <first line of the task>`», with `capture_confidence` (0.3), so a curator or the decider looks at it.
- **Only with a contributor token**, as above.
- **Secrets:** everything is redacted before it is written to disk or sent, with the server's own secret detector. It works by patterns and is not infallible: read the drafts if in doubt.
- **Where the records live:** one file per session, readable only by you, in `~/.config/mimirsynth/state/<agent>/sessions/` unless the agent gives the plugin a folder of its own (each plugin page says where). Records older than 14 days are deleted.

## Plugin versions and updates
Each plugin has its own version, raised whenever anything in its folder changes; an agent only updates an installed plugin when that version goes up. Each agent keeps its own copy, so each one is updated on its own:

| Agent | Update |
|---|---|
| Claude Code | `claude plugin marketplace update mimirsynth`, then `claude plugin update mimirsynth@mimirsynth` (or **Update now** under `/plugin` → Installed), then `/reload-plugins` |
| Codex | `codex plugin marketplace upgrade mimirsynth`, then trust the hooks again in `/hooks` |
| OpenCode | OpenCode checks plugins listed without a version when it starts; `opencode plugin update @mimirsynth/opencode` installs the new one |
| Hermes Agent | `hermes plugins update mimirsynth` |
| OpenClaw | With the Gateway stopped, `openclaw plugins update mimirsynth` |

The configuration file does not change with an update: a newer plugin reads the same keys.

## See also
- [[Connect agents]]: tokens, roles, scopes, the MCP server and the HTTP API.
- [[Writing good memory]]: what is worth proposing.
