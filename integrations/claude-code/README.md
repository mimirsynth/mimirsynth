**English** · [Español](README.es.md)

# MimirSynth for Claude Code

Claude Code connects to MimirSynth through the **MCP server** that every brain exposes: that gives the agent `recall` and `remember` as tools. This folder adds the complement, a **recall hook** that injects memory into every prompt without the agent having to ask for it, and a script to send learnings as proposals from the command line. See [`docs/AGENTS.md`](../../docs/AGENTS.md) for tokens, roles and the API.

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

Over MCP, recall only happens when the agent decides to call the tool. `mimirsynth_recall.py` is a `UserPromptSubmit` hook that queries MimirSynth **before every prompt** and injects the relevant context (inside `<mimirsynth-memory>` tags), so the agent always starts with it. It is read-only: a *Reader* token is enough, and the MCP token also works.

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
