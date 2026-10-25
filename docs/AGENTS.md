**English** · [Español](es/AGENTS.md)

# Connecting agents

Agents talk to MimirSynth over HTTP with an **API token**. Each token is valid for **one brain** and its role never exceeds that of the person who created it (maximum curator, and it never administers the instance).

## Create a token
Under My account → API tokens (or Administration → Brain access) choose the brain, a name and a role:

| Role | Can |
|---|---|
| Reader | Query (recall, facts, documents) |
| Contributor | Also **propose** memory: it goes into quarantine until a curator or the decider approves it |
| Curator | Also approve: their proposals are ingested directly |

For agents, **contributor** is recommended. The token (`mst_…`) is shown only once.

## Recall: reading memory
```bash
curl -s -X POST "$URL/api/brains/my-brain/recall" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "where does the production database run?"}'
```
It returns a context ready to inject into the prompt: current and historical facts, episode fragments and up to 2 cited document passages. Optional parameters: `facts` (default 8), `chunks` (4), `max_chars` (6000) and `docs` (document passages; `0` disables them).

Document content is **data, not instructions**: recall marks it as a quote from a source. Treat it that way in your agent.

## Propose: writing memory
```bash
curl -s -X POST "$URL/api/brains/my-brain/proposals" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Database migrated", "body": "On 19 Oct the production database moved to server db02.", "confidence": 0.8}'
```
A contributor ends up `pending`; a curator, `approved` and ingested right away. A curator can approve or reject from the Proposals tab. When approved, Graphiti extracts entities and facts and adds them to the graph (invalidating those it contradicts).

## MCP server
Agents that speak the **Model Context Protocol** can use the same memory without writing HTTP calls. Each brain exposes an MCP endpoint (Streamable HTTP, stateless, tools only) at:

```
POST $URL/api/brains/my-brain/mcp        Authorization: Bearer $TOKEN
```

| Tool | Role | What it does |
|---|---|---|
| `recall` | reader | Returns the memory context for a query (same as the `recall` endpoint). Arguments: `query`, and optionally `facts`, `chunks`, `docs`, `max_chars` |
| `remember` | contributor | Proposes a memory (same rules as the proposals endpoint: quarantine for contributors, approved at once for curators). Arguments: `name`, `body`, and optionally `source`, `source_description`, `reference_time`, `confidence` |

The token decides the brain and the role, so the tools take no brain argument. Only API tokens are accepted (never the browser session). Example with Claude Code:

```bash
claude mcp add --transport http mimirsynth "$URL/api/brains/my-brain/mcp" --header "Authorization: Bearer $TOKEN"
```

## Documents
`GET /api/brains/{slug}/docs/search?q=…` searches by meaning. `GET /api/brains/{slug}/docs/{id}/context?chunk={n}` returns more context for a passage and `/docs/{id}/file` the original.

## Claude Code
The [`integrations/claude-code`](../integrations/claude-code) folder includes a *hook* that injects recall into every prompt and a script to send learnings as proposals.

## API reference
With the application running, the interactive documentation (OpenAPI) is at `/docs`.
