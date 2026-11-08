**English** · [Español](README.es.md)

# MimirSynth for Codex

A native plugin for the [Codex CLI](https://github.com/openai/codex) (0.167 or later), with the same features and the same configuration as the [Claude Code plugin](../claude-code/README.md):
- **What changed at session start.** The facts learned and invalidated since the last session (`POST /news`), inside `<mimirsynth-news>`.
- **Recall before every prompt.** A hook asks the brain before the model reads the prompt and injects the answer inside `<mimirsynth-memory>`, as context, not as instructions. You set the size (`max_chars`, 4000) and the timeout (`timeout`, 4 s). If the server does not answer, nothing is injected and the prompt carries on; an expired or revoked token is said.
- **Four commands**, as Codex skills:

| Skill | What it does |
|---|---|
| `$mimirsynth:setup` | Tells you how to configure it. Tokens never go through the conversation: you run `cli.py setup` in your terminal, which asks for them hidden |
| `$mimirsynth:status` | Connection, brain, role, scopes and expiry of each token, server version, whether Codex trusts the hooks, capture mode, drafts, and other memory in Codex |
| `$mimirsynth:search` | Recall on demand, with more results |
| `$mimirsynth:remember` | Codex writes a memory from the conversation and proposes it once you agree; it also reviews the drafts the capture left |

- **Optional capture of what each session learned** (off by default), read from Codex's own session files.

It is built on the shared client library, which it carries in `plugin/scripts/mimirsynth_agent/` (a copy of `integrations/shared/python/mimirsynth_agent`), and it needs `python3` on the `PATH` (`python` on Windows), Python 3.8 or later.

## Install

One command, from this repository's marketplace:

```bash
codex plugin marketplace add mimirsynth/mimirsynth && codex plugin add mimirsynth@mimirsynth
```

Then, once:
1. **Configure it** in a terminal. In Codex, `$mimirsynth:setup` prints the exact command for your machine; it is
   ```bash
   python3 ~/.codex/plugins/cache/mimirsynth/mimirsynth/<version>/scripts/cli.py setup
   ```
   It asks for the URL and the brain, a **reader** token for recall, optionally a **contributor** token to propose, and the capture mode, and writes `~/.config/mimirsynth/config.json`, readable only by you. If MimirSynth is already set up for another agent on this machine (the Claude Code plugin, for example), there is nothing to do: the file is shared.
2. **Trust the hooks.** Codex does not run a plugin's hooks until you trust them: start Codex, open `/hooks` and trust the three `mimirsynth` ones (SessionStart, UserPromptSubmit, SessionEnd). Codex asks again after each update of the plugin, and until then there is no recall before each prompt and no news: `$mimirsynth:status` says so.

The same keys can come from `MIMIRSYNTH_*` environment variables, which take precedence, and a `projects` entry can give some folders another brain with its own tokens: see [`docs/AGENT_CLIENT.md`](../../docs/AGENT_CLIENT.md).

To update: `codex plugin marketplace upgrade mimirsynth`, then trust the hooks again in `/hooks`. To remove: `codex plugin remove mimirsynth@mimirsynth`.

### The tools too (optional)

The plugin recalls before each prompt by itself. To also let the model call MimirSynth's tools (`recall`, `remember`, `facts_about`, `timeline`, `whats_new`…), add the brain's MCP server, with the token in an environment variable rather than in `config.toml`:

```bash
codex mcp add mimirsynth --url "https://mimirsynth.example.com/api/brains/my-brain/mcp" --bearer-token-env-var MIMIRSYNTH_TOKEN
```

## Capturing what a session learned (off by default)

`capture` decides it:
- **`off`** (the default): nothing about the sessions is written, read or sent.
- **`draft`**: each finished session is kept on this machine, already redacted, until you review it with `$mimirsynth:remember`.
- **`send`**: at the **next** session start, each finished session becomes a proposal.

How it works with Codex:
- **Which sessions:** only those that started while the capture was on. The prompt hook notes the session and where Codex keeps its file (`~/.codex/sessions/…/rollout-….jsonl`); sessions from before, or from another tool, are never read. Of those, only the ones that changed files or ended with a substantial answer are proposed, at most **one proposal per session**.
- **What it holds:** the task (the first prompt), the outcome (the last answer) and the files changed (only the edits Codex applied), read from the session file once the session is over. Never the transcript.
- **When a session is over:** when Codex says so (the SessionEnd hook), or, if Codex was killed, when its file has not changed for 12 hours. A resumed session goes on and is read again when it ends.
- **How it is sent:** with low confidence (`capture_confidence`, 0.3), so it waits in **quarantine**, and only with a **contributor** token: with a curator's it would be approved at once, so it is refused and said.
- **Secrets:** before anything is written to disk or sent, it is redacted with the server's own detector (`scripts/mimirsynth_agent/secretscan.py` is the same file as `api/mimirsynth/secretscan.py`, and a test keeps them equal). It works by patterns and is not infallible: read the drafts if in doubt.
- **Where the records live:** `~/.config/mimirsynth/state/codex/sessions/`, one file per session, readable only by you, deleted after 14 days.

## Other memory

If Codex's own memories (`[features] memories = true`) or another plugin or hook that looks like memory also feed Codex, the session start says so (it does not block anything). MimirSynth's blocks are marked so you can tell them apart.

## Fail open

Every call has the configured timeout and every hook exits cleanly whatever happens: when MimirSynth is down, Codex carries on without memory. SessionEnd only marks the session as over (Codex gives it at most 3 s); nothing leaves the machine until the next start.

## Tests

`api/tests/test_codex_plugin.py` checks the hooks, the session-file reader and the capture with a recorded API, and, with `MIMIRSYNTH_TEST_CODEX` set to a `codex` executable, installs the plugin from this repository into a throwaway `CODEX_HOME` and runs the real Codex against a test instance, with a stand-in for the model so no account is needed. The `plugin-codex` workflow runs it in the CI.
