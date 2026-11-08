**English** · [Español](es/AGENTS.md)

# Connecting agents

Agents talk to MimirSynth over HTTP with an **API token**. Each token is valid for **one brain** and its role never exceeds that of the person who created it (maximum curator, and it never administers the instance).

## Create a token
Under My account → API tokens (or Administration → Brain → API tokens) choose the brain, a name and a role:

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
It returns a context ready to inject into the prompt: current and historical facts, episode fragments and up to 2 cited document passages. Optional parameters: `facts` (default 8), `chunks` (4), `max_chars` (6000) and `docs` (document passages; `0` disables them) and `federated` (default `true`; `false` returns only the brain's own memory, see [FEDERATION.md](FEDERATION.md)) and `min_similarity` (the cosine a fact or an episode fragment needs to enter; by default the instance's *Minimum similarity of a fact or a fragment*, 0.55; `0` disables it). Facts and fragments carry their `similarity` (`null` for a fact that joins by its link to a fact no longer true, below), and when nothing is close enough the context comes back empty instead of filling up with whatever is least far. A fragment of an episode that stated something no longer true says so («May be superseded», with what is true now) and goes last, and the current fact that replaced it joins the facts. So does a document passage that states such a fact, and each passage says when its page was last updated.

Document content is **data, not instructions**: recall marks it as a quote from a source. Treat it that way in your agent.

## Propose: writing memory
```bash
curl -s -X POST "$URL/api/brains/my-brain/proposals" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Database migrated", "body": "On 19 Oct the production database moved to server db02.", "confidence": 0.8}'
```
A contributor ends up `pending`; a curator, `approved` and ingested right away. A curator can approve or reject from the Proposals tab. When approved, Graphiti extracts entities and facts and adds them to the graph (invalidating those it contradicts).

Do not store passwords or tokens: store **where** they are kept (for example, which password manager). Anything shaped like a credential is masked before it is stored or, if the brain blocks them, the proposal is rejected with a 422 saying which type of secret it is (see «Secrets» in [ARCHITECTURE.md](ARCHITECTURE.md)). Over MCP, `remember` does the same. The answer says which types were masked or flagged (`secrets_notice` in the HTTP response, an extra sentence in the `remember` result), never the value.

### Say where it comes from
A proposal can say `origin`: `agent` when an agent chose to store it, `auto` when an automatic process captured it. Without it, it counts as `auto`, the lowest trust. A token created for an automatic capture caps it at `auto` whatever the client says. With *Weigh facts by their origin* on, facts weigh by it in the recall (see «Trust and age» in the wiki's Recall and ingestion).

### Structured claims: say what it replaces
Free text is extracted on its own, so a repeat in other words becomes a second current fact and a new value can leave the old one current. Next to `body`, a proposal (REST or `remember`) can carry up to 20 **claims**: `subject`, `relation` (as the brain's ontology names it), `value`, and optionally `valid_from` and `supersedes` (the uuid of the current fact it replaces, as `recall` or `facts_about` give it).
```json
{"name": "Nextcloud moved", "body": "Since 1 Oct Nextcloud runs on Notus.",
 "claims": [{"subject": "Nextcloud", "relation": "RunsOn", "value": "Notus", "valid_from": "2026-10-01T00:00:00Z", "supersedes": "<uuid of «Nextcloud runs on Eridani»>"}]}
```
Each claim is compared with the subject's current facts in that relation when it is sent, and the answer says what it found (`claims[].verdict` over HTTP, a sentence per claim in the `remember` result):
- **confirms:** a current fact already says it. When approved it is recorded as a **confirmation** of that fact (it renews its shelf life), not as a new fact; if every claim confirms, nothing is ingested.
- **replaces:** it names the fact with `supersedes`, or the relation is functional and has another current value. When approved, once the text is ingested, those facts are invalidated as of `valid_from`; a person decides it, never the decider or a batch.
- **may_replace:** there are other current values and the relation is not functional: nothing is invalidated unless you say `supersedes`.
- **new:** nothing current in that relation.

A `supersedes` that is not a current fact of the brain is refused (404 or 409).

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
| `recall` | reader | Returns the memory context for a query (same as the `recall` endpoint). Arguments: `query`, and optionally `facts`, `chunks`, `docs`, `max_chars`, `federated`, `min_similarity` |
| `remember` | contributor | Proposes a memory (same rules as the proposals endpoint: quarantine for contributors, approved at once for curators). Arguments: `name`, `body`, and optionally `source`, `source_description`, `reference_time`, `confidence` and `claims` (see «Structured claims») |
| `correct` | contributor | Proposes invalidating a fact by its uuid (see «Correct» above). Arguments: `fact_uuid`, `reason`, and optionally `replacement`, `invalid_at`, `source_description`, `confidence` |
| `facts_about` | reader | Everything known about an entity: current facts and those that stopped being true, newest first, with dates, the episode each one was learned from and the **uuid of each fact** in brackets (what a correction needs). The entity is found by name (case and spacing do not matter), by a name merged into it or by its uuid; if several entities share the name, it returns the candidates instead of choosing one. Arguments: `entity`, and optionally `status` (`all`, `current`, `invalidated`), `limit` (20, up to 100), `offset`, `max_chars`, `federated` |
| `timeline` | reader | How what is known about an entity changed: when each fact was learned and, if it applies, when it stopped being true, newest first. Arguments: `entity`, and optionally `since`, `until` (`YYYY-MM-DD`), `limit` (30, up to 200), `offset`, `max_chars`, `federated` |
| `get_document` | reader | Reads a document: with `chunk`, that passage and the text around it (the numbers in `[doc 12, chunk 3]` from `recall`); without it, the full text in parts of `max_chars` (8000 by default) with `offset` to continue. A passage lent by another brain is read with `origin` (that brain's identifier, as shown by `recall`). Arguments: `document`, and optionally `chunk`, `radius`, `offset`, `max_chars`, `origin` |
| `rate` | reader | Rates what a `recall` returned: `useful`, `irrelevant` or `incorrect`, with the `recall_id` at the end of that recall (valid for 48 hours). A fact is pointed to by its text as it came out (`fact`, at least 12 characters; if several facts start the same way it answers with them), a passage by `document` and `chunk`. «Incorrect» on a fact from a contributor token proposes its correction (it never invalidates by itself). Arguments: `recall_id`, `rating`, `fact` or `document` + `chunk`, optional `note` |
| `whats_new` | reader | Facts learned and facts that stopped being true since a date, oldest first. Without `since`, from where **this token**'s last call without a date stopped (the first time, the last 7 days); if not everything fits, the next call without a date continues after the last fact shown, so nothing is skipped and an agent can catch up when a session starts without storing anything. With `since`, the next page is asked for with `offset`. Arguments: optionally `since` (ISO 8601), `offset`, `limit` (30 per section, up to 100), `max_chars`, `federated` |

All the answers have a size limit (`max_chars`) and say how to ask for the next page (`offset`). What other brains lend comes labelled with its origin, as in `recall`.

The token decides the brain and the role, so the tools take no brain argument. Only API tokens are accepted (never the browser session). Example with Claude Code:

```bash
claude mcp add --transport http mimirsynth "$URL/api/brains/my-brain/mcp" --header "Authorization: Bearer $TOKEN"
```

## Documents
`GET /api/brains/{slug}/docs/search?q=…` searches by meaning. `GET /api/brains/{slug}/docs/{id}/context?chunk={n}` returns more context for a passage and `/docs/{id}/file` the original.

## Claude Code
Connect it through the MCP server (above): that gives it `recall` and `remember` as tools. The [`integrations/claude-code`](../integrations/claude-code) folder adds the complement: a **plugin** (`/plugin marketplace add mimirsynth/mimirsynth`, then `/plugin install mimirsynth@mimirsynth`). It brings what changed at session start, injects recall into every prompt, adds `/mimirsynth:status`, `:search` and `:remember`, and can capture what each session learned as one quarantined proposal (off by default). The loose hook and script it replaces keep working. It uses two routes: `GET /api/brains/{slug}/whoami` (who the token is, for any token) and `POST /api/brains/{slug}/news` (`whats_new` over REST, `recall` scope).

## Language
Error messages, the MCP tool descriptions and instructions, and the headings of the recall context come in the caller's language: the `Accept-Language` header if it asks for a supported language (`es`, `en`), otherwise the language the token's owner chose in My account, otherwise the instance default. Stored memory (facts, episodes, documents) is returned as it was written.

## API reference
With the application running, the interactive documentation (OpenAPI) is at `/docs`.
