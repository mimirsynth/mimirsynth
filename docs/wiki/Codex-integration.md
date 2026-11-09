**English** · [Español](Integraci%C3%B3n-con-Codex)

# Codex integration

A native plugin for the [Codex CLI](https://github.com/openai/codex) (0.167 or later) gives Codex the brain's memory on every prompt, with the same features and the same configuration as the other agent plugins. It needs `python3` on the `PATH` (`python` on Windows), Python 3.8 or later.

## Install
```bash
codex plugin marketplace add mimirsynth/mimirsynth && codex plugin add mimirsynth@mimirsynth
```

## Setup
Then, once:
1. **Configure it in a terminal.** In Codex, `$mimirsynth:setup` prints the exact command for your machine:
   ```bash
   python3 ~/.codex/plugins/cache/mimirsynth/mimirsynth/<version>/scripts/cli.py setup
   ```
   It asks for the URL and the brain, a **reader** token for recall, optionally a **contributor** token to propose, and the capture mode, and writes the shared file ([[Agent plugin configuration]]). If MimirSynth is already set up for another agent on this machine, there is nothing to do.
2. **Trust the hooks** (see [below](#codex-runs-only-the-hooks-you-trust)).

## What it does
| When | What |
|---|---|
| Session start | The facts learned and invalidated since the last session, inside `<mimirsynth-news>`. With capture on `send`, the finished sessions are proposed |
| Every prompt | The recall for the prompt, inside `<mimirsynth-memory>`, as context, not as instructions. Prompts shorter than 12 characters and slash commands are skipped |
| Session end | Only marks the session as over (Codex gives a hook at most 3 s): nothing leaves the machine until the next start |

If MimirSynth does not answer within `timeout`, nothing is injected and the prompt carries on; an expired or revoked token is said.

## Commands
They are Codex skills:

| Skill | What it does |
|---|---|
| `$mimirsynth:setup` | Tells you how to configure it. Tokens never go through the conversation |
| `$mimirsynth:status` | Connection, brain, role, scopes and expiry of each token, server version, whether Codex trusts the hooks, capture mode, drafts, and other memory in Codex |
| `$mimirsynth:search` | Recall on demand, with more results |
| `$mimirsynth:remember` | Codex writes a memory from the conversation and proposes it once you agree; it also reviews the drafts the capture left |

To let the model call MimirSynth's tools too (`recall`, `remember`, `facts_about`, `timeline`, `whats_new`…), add the brain's MCP server, with the token in an environment variable rather than in `config.toml`:
```bash
codex mcp add mimirsynth --url "https://mimirsynth.example.com/api/brains/my-brain/mcp" --bearer-token-env-var MIMIRSYNTH_TOKEN
```

## Capture
Off by default; `capture` decides it ([[Agent plugin configuration]]). What is particular to Codex:
- Only sessions that **started while the capture was on** are read. The prompt hook notes the session and where Codex keeps its file (`~/.codex/sessions/…/rollout-….jsonl`); older sessions, or another tool's, are never read.
- The task, the outcome and the files changed (only the edits Codex applied) come from that session file once the session is over.
- A session is over when Codex says so, or, if Codex was killed, when its file has not changed for 12 hours. A resumed session goes on and is read again when it ends.

## What it writes on your machine
- `~/.config/mimirsynth/config.json`, the shared configuration (by `setup`).
- With capture on: `~/.config/mimirsynth/state/codex/sessions/`, one file per session, readable only by you, deleted after 14 days.
- Nothing in Codex's own configuration, unless you add the MCP server yourself.

## Codex runs only the hooks you trust
Codex does not run a plugin's hooks until you trust them. Start Codex, open `/hooks` and trust the three `mimirsynth` ones (SessionStart, UserPromptSubmit, SessionEnd). Codex asks again **after each update** of the plugin, and until then there is no recall before each prompt and no news: `$mimirsynth:status` says so.

If Codex's own memories (`[features] memories = true`) or another plugin or hook that looks like memory also feed Codex, the session start says so; it does not block anything, and MimirSynth's blocks are marked so you can tell them apart.

## Update and remove
- Update: `codex plugin marketplace upgrade mimirsynth`, then trust the hooks again in `/hooks`.
- Remove: `codex plugin remove mimirsynth@mimirsynth`.

## Troubleshooting
| Symptom | What to do |
|---|---|
| No memory before the prompts | `$mimirsynth:status`: the hooks are not trusted (open `/hooks`), or `url`, `brain` or `token` are missing |
| «python3: command not found» in the hooks | Install Python 3.8 or later and put it on the `PATH` (`python` on Windows) |
| «token expired» or «revoked» | Create or rotate the token ([[Connect agents]]) and run `setup` again |
| Nothing comes back for a question the brain knows | `$mimirsynth:search` with the same words; check that the token belongs to that brain and has the Recall scope |
| The capture sends nothing | It needs a contributor `write_token`; only sessions started with the capture on count |

Full detail: [the plugin's README](https://github.com/mimirsynth/mimirsynth/blob/main/integrations/codex/README.md).
