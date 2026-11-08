**English** · [Español](README.es.md)

# MimirSynth for Claude Code

Claude Code connects to MimirSynth through the **MCP server** that every brain exposes: that gives the agent `recall` and `remember` as tools. This folder adds the complement, a **recall hook** that injects memory into every prompt without the agent having to ask for it, and a script to send learnings as proposals from the command line. See [`docs/AGENTS.md`](../../docs/AGENTS.md) for tokens, roles and the API.

## The plugin (recommended)

The `plugin/` folder is a Claude Code plugin that packs the recall hook and more:
- **What changed at session start.** It brings the facts learned and invalidated since the last session (`POST /news`, the REST face of the MCP's `whats_new`), inside `<mimirsynth-news>`.
- **Recall before every prompt.** As the loose hook does, inside `<mimirsynth-memory>`. You set the size (`max_chars`, 4000) and the timeout (`timeout`, 4 s). If the server does not answer, nothing is injected and the prompt carries on. An expired or revoked token is said.
- **Four commands:**

| Command | What it does |
|---|---|
| `/mimirsynth:setup` | Tells you how to configure it. Tokens never go through the conversation: you run `cli.py setup` in your terminal, which asks for them hidden |
| `/mimirsynth:status` | Connection, brain, role, scopes and expiry of each token, server version, capture mode, drafts, and other memory hooks on this machine |
| `/mimirsynth:search <query>` | Recall on demand, with more results |
| `/mimirsynth:remember [title]` | Claude writes a memory from the conversation and sends it once you agree; with no title, it reviews the drafts the capture left |

- **Optional capture of what each session learned**, explained below.

### Install

In Claude Code:
```
/plugin marketplace add mimirsynth/mimirsynth
/plugin install mimirsynth@mimirsynth
```
Then configure it in a terminal; `/mimirsynth:setup` shows the exact path:
```bash
python3 ~/.claude/plugins/…/mimirsynth/scripts/cli.py setup
```
It asks for:
- the URL and the brain;
- a **reader** token for recall;
- optionally a **contributor** token to propose;
- the capture mode.

It writes `~/.config/mimirsynth/config.json`, readable only by you. The same keys can come from `MIMIRSYNTH_*` environment variables, which take precedence. The hooks need `python3` on the `PATH`.

The file is shared with every MimirSynth agent plugin, and a `projects` entry can give some folders another brain with its own tokens: see [`docs/AGENT_CLIENT.md`](../../docs/AGENT_CLIENT.md). The plugin is built on the shared client library, which it carries in `scripts/mimirsynth_agent/` (a copy of `integrations/shared/python/mimirsynth_agent`).

### Capturing what a session learned (off by default)

`capture` decides it:
- **`off`** (the default): nothing about the sessions is written or sent.
- **`draft`**: each session is kept on this machine, already redacted, until you review it with `/mimirsynth:remember`.
- **`send`**: at the **next** session start, each finished session becomes a proposal.

What is recorded and sent:
- **Which sessions:** only those that changed files or ended with a substantial answer, as at most **one proposal per session**.
- **What it holds:** the task (the first prompt), the outcome (the last answer) and the files changed. Never the transcript.
- **How it is sent:** with low confidence (`capture_confidence`, 0.3), so it waits in **quarantine**. It is only sent with a **contributor** token: with a curator's it would be approved at once, so it is refused and said.
- **Secrets:** before anything is written to disk or sent, it is redacted with the server's own detector (`scripts/mimirsynth_agent/secretscan.py` is the same file as `api/mimirsynth/secretscan.py`, and a test keeps them equal). It works by patterns and is not infallible: read the drafts if in doubt.
- **When it leaves the machine:** at the next start, not at the end of the session, because Claude Code gives a plugin only 1.5 s when a session ends.

### Other memory plugins

If another plugin or hook also injects memory, the session start says so (it does not block anything). MimirSynth's blocks are marked so you can tell them apart. If `mimirsynth_recall.py` is still in `settings.json`, it says that too.

### Moving from the loose scripts

1. Install the plugin. Your `~/.config/mimirsynth/config.json` keeps working, with the same keys.
2. Remove the `mimirsynth_recall.py` hook from `~/.claude/settings.json`, or the context is injected twice. `/mimirsynth:status` warns while it is there.
3. `mimirsynth_remember.py` can stay for scripts. Inside Claude Code, `/mimirsynth:remember` does the same.

The loose scripts below keep working as they were.

## 1. Connect over MCP

1. In MimirSynth: My account → API tokens → create a token for your brain. **Contributor** is recommended: it can read and propose, and what it proposes goes into quarantine until a curator or the decider approves it. A *Reader* token is enough if the agent should only query.
2. Add the server to Claude Code:
   ```bash
   claude mcp add --transport http mimirsynth "https://mimirsynth.example.com/api/brains/my-brain/mcp" --header "Authorization: Bearer mst_..."
   ```
   Add `--scope user` to make it available in every project.
3. In Claude Code, `/mcp` lists the server and its tools:

| Tool | Role | What it does |
|---|---|---|
| `recall` | reader | Returns the memory context for a query: current and historical facts, episode fragments and cited document passages |
| `remember` | contributor | Proposes a memory (quarantine for contributors, approved at once for curators) |

The token decides the brain and the role, so the tools take no brain argument. Only API tokens are accepted, never the browser session.

## 2. Recall hook (optional complement)

Over MCP, recall only happens when the agent decides to call the tool. `mimirsynth_recall.py` is a `UserPromptSubmit` hook that queries MimirSynth **before every prompt** and injects the relevant context (inside `<mimirsynth-memory>` tags), so the agent always starts with it. It is read-only: a *Reader* token is enough (with the **Recall** scope), and the MCP token also works. It fails open: if MimirSynth does not answer, it injects nothing. If the token **expired or was revoked**, it says so instead, with MimirSynth's message (for example «token expired on …»), so the agent does not stop remembering without anyone noticing.

1. Save the configuration in `~/.config/mimirsynth/config.json`:
   ```json
   {"url": "https://mimirsynth.example.com", "token": "mst_...", "brain": "my-brain"}
   ```
   The environment variables `MIMIRSYNTH_URL`, `MIMIRSYNTH_TOKEN` and `MIMIRSYNTH_BRAIN` take precedence over the file.
2. Add the hook in `~/.claude/settings.json`:
   ```json
   {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": "python3 /path/to/mimirsynth_recall.py"}]}]}}
   ```

Prompts shorter than 12 characters and slash commands are skipped. If the server does not respond within 4 s (`MIMIRSYNTH_TIMEOUT`), nothing is injected and the prompt carries on.

With both in place, the hook brings the context to every prompt and the MCP tools let the agent query again with other words or propose what it learns.

## 3. Writing memory from the command line

Over MCP, the agent proposes with `remember`. For scripts or other hooks, `mimirsynth_remember.py` sends a learning as a proposal:

```bash
python3 mimirsynth_remember.py --title "Database moved to db02" --content "On 19 Oct the production database moved to server db02" --confidence 0.8
```

- It uses `write_token` from `~/.config/mimirsynth/config.json` (an API token with the **contributor** role: it goes into quarantine and a curator or the decider approves it). Without it, it uses `token`, which returns 403 if it is a reader token.
- With a curator token it is approved and ingested right away. Contributor is recommended for agents.
- `--dry-run` shows the request without sending it.

Do not store passwords or tokens, only **where** they are kept: anything shaped like a credential is masked before it is stored or, if the brain blocks them, the proposal is rejected with a 422. `remember` over MCP applies the same rules.

## Documents in recall

With document memory, the context returned by `recall` (tool, hook or `/recall` endpoint) can include a `## Documents` section with up to 2 cited passages (title, section, `[doc N, chunk M]`). It only appears if there is a really relevant passage, it does not exceed ~600 tokens and it is omitted if the search takes longer than 0.6 s. The agent can ask for more context with `GET /api/brains/{slug}/docs/{N}/context?chunk={M}` or the original with `/docs/{N}/file`. To disable it for one request, use `"docs": 0`; the threshold (Administration → Recall → "Minimum similarity of a passage") must be recalibrated if the embedding model changes.
