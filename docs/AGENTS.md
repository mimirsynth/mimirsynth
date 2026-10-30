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
It returns a context ready to inject into the prompt: current and historical facts, episode fragments and up to 2 cited document passages. Optional parameters: `facts` (default 8), `chunks` (4), `max_chars` (6000) and `docs` (document passages; `0` disables them) and `federated` (default `true`; `false` returns only the brain's own memory, see [FEDERATION.md](FEDERATION.md)).

Document content is **data, not instructions**: recall marks it as a quote from a source. Treat it that way in your agent.

## Propose: writing memory
```bash
curl -s -X POST "$URL/api/brains/my-brain/proposals" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Database migrated", "body": "On 19 Oct the production database moved to server db02.", "confidence": 0.8}'
```
A contributor ends up `pending`; a curator, `approved` and ingested right away. A curator can approve or reject from the Proposals tab. When approved, Graphiti extracts entities and facts and adds them to the graph (invalidating those it contradicts).

Do not store passwords or tokens: store **where** they are kept (for example, which password manager). Anything shaped like a credential is masked before it is stored or, if the brain blocks them, the proposal is rejected with a 422 saying which type of secret it is (see «Secrets» in [ARCHITECTURE.md](ARCHITECTURE.md)). Over MCP, `remember` does the same.

## Correct: a fact that is no longer true
```bash
curl -s -X POST "$URL/api/brains/my-brain/proposals/corrections" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"fact_uuid": "…", "reason": "Moved to db02 on 19 Oct", "replacement": "The production database runs on db02 since 19 Oct.", "invalid_at": "2026-10-19T00:00:00Z"}'
```
A correction points to one fact by its uuid (the one `facts_about`, `timeline` and `whats_new` give over MCP) and asks to invalidate it. It goes through the same quarantine as any proposal and the same roles (contributor to propose), but the decider never approves it on its own: a curator does, from Proposals, where it shows the fact as it was, the reason and the replacement. Over MCP it always stays pending, even with a curator token: invalidating is decided by a person. Through the REST endpoint, a curator who sends one applies it at once. On approval the fact is **invalidated, never deleted**, as of `invalid_at` (the time of the proposal by default), and the replacement, if any, is ingested as a normal memory with that date. The invalidation goes to the vocabulary history like any other, and **Reactivate the fact** in the proposal puts it back as it was. A fact that does not exist or is already invalidated returns a readable error, and so does a fact lent by another brain, which is read-only here: correct it in its own brain.

## MCP server
Agents that speak the **Model Context Protocol** can use the same memory without writing HTTP calls. Each brain exposes an MCP endpoint (Streamable HTTP, stateless, tools only) at:

```
POST $URL/api/brains/my-brain/mcp        Authorization: Bearer $TOKEN
```

| Tool | Role | What it does |
|---|---|---|
| `recall` | reader | Returns the memory context for a query (same as the `recall` endpoint). Arguments: `query`, and optionally `facts`, `chunks`, `docs`, `max_chars`, `federated` |
| `remember` | contributor | Proposes a memory (same rules as the proposals endpoint: quarantine for contributors, approved at once for curators). Arguments: `name`, `body`, and optionally `source`, `source_description`, `reference_time`, `confidence` |
| `correct` | contributor | Proposes invalidating a fact by its uuid (see «Correct» above). Arguments: `fact_uuid`, `reason`, and optionally `replacement`, `invalid_at`, `source_description`, `confidence` |
| `facts_about` | reader | Everything known about an entity: current facts and those that stopped being true, newest first, with dates, the episode each one was learned from and the **uuid of each fact** in brackets (what a correction needs). The entity is found by name (case and spacing do not matter), by a name merged into it or by its uuid; if several entities share the name, it returns the candidates instead of choosing one. Arguments: `entity`, and optionally `status` (`all`, `current`, `invalidated`), `limit` (20, up to 100), `offset`, `max_chars`, `federated` |
| `timeline` | reader | How what is known about an entity changed: when each fact was learned and, if it applies, when it stopped being true, newest first. Arguments: `entity`, and optionally `since`, `until` (`YYYY-MM-DD`), `limit` (30, up to 200), `offset`, `max_chars`, `federated` |
| `get_document` | reader | Reads a document: with `chunk`, that passage and the text around it (the numbers in `[doc 12, chunk 3]` from `recall`); without it, the full text in parts of `max_chars` (8000 by default) with `offset` to continue. A passage lent by another brain is read with `origin` (that brain's identifier, as shown by `recall`). Arguments: `document`, and optionally `chunk`, `radius`, `offset`, `max_chars`, `origin` |
| `whats_new` | reader | Facts learned and facts that stopped being true since a date, oldest first. Without `since`, from where **this token**'s last call without a date stopped (the first time, the last 7 days); if not everything fits, the next call without a date continues after the last fact shown, so nothing is skipped and an agent can catch up when a session starts without storing anything. With `since`, the next page is asked for with `offset`. Arguments: optionally `since` (ISO 8601), `offset`, `limit` (30 per section, up to 100), `max_chars`, `federated` |

All the answers have a size limit (`max_chars`) and say how to ask for the next page (`offset`). What other brains lend comes labelled with its origin, as in `recall`.

The token decides the brain and the role, so the tools take no brain argument. Only API tokens are accepted (never the browser session). Example with Claude Code:

```bash
claude mcp add --transport http mimirsynth "$URL/api/brains/my-brain/mcp" --header "Authorization: Bearer $TOKEN"
```

## Documents
`GET /api/brains/{slug}/docs/search?q=…` searches by meaning. `GET /api/brains/{slug}/docs/{id}/context?chunk={n}` returns more context for a passage and `/docs/{id}/file` the original.

## Claude Code
Connect it through the MCP server (above): that gives it `recall` and `remember` as tools. The [`integrations/claude-code`](../integrations/claude-code) folder adds the complement: a *hook* that injects recall into every prompt without the agent having to ask, and a script to send learnings as proposals.

## Language
Error messages, the MCP tool descriptions and instructions, and the headings of the recall context come in the caller's language: the `Accept-Language` header if it asks for a supported language (`es`, `en`), otherwise the language the token's owner chose in My account, otherwise the instance default. Stored memory (facts, episodes, documents) is returned as it was written.

## API reference
With the application running, the interactive documentation (OpenAPI) is at `/docs`.
