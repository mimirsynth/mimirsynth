**English** · [Español](Conectar-agentes)

# Connect agents

An **agent** (Claude Code, a bot, a script, another service) talks to MimirSynth with an **API token**. There are two operations: **reading** memory (*recall*) and **writing** memory (*proposals*, called `remember` over MCP). An agent that speaks the **Model Context Protocol (MCP)** connects to the brain's built-in MCP server with a single line; any other client uses the HTTP API.

## 1. Create a token
In [[My account]] → **API tokens** (or in [[Brains and members]]):
1. Choose the **brain** it will access.
2. Give it a **name** that identifies the agent ("Claude Code laptop").
3. Choose the **role**:
   | Token role | The agent can |
   |---|---|
   | **Reader** | Query: recall, facts, documents |
   | **Contributor** | Also **propose** memory (it goes into quarantine) and upload documents |
   | **Curator** | Also approve: its proposals are ingested directly |
4. Choose when it **expires**: 30, 90 or 365 days, or never (the instance may set a maximum, and then «never» is not offered).
5. Choose its **scope**, which limits it further than the role:
   | Scope | The agent can |
   |---|---|
   | **Recall** | Recall and read the memory (facts, entities, journal, graph, query); over MCP, `recall`, `facts_about`, `timeline` and `whats_new` |
   | **Documents** | Get document passages in the recall, its own and those lent to the brain, and read documents (`/docs`; `get_document` over MCP) |
   | **Propose** | Send proposals and corrections (`remember` and `correct` over MCP) |

   All three are ticked by default. A token without **Documents** gets no passages at all, over HTTP, MCP or federation. Curating depends only on the role.
6. Copy the token (`mst_…`): **it is shown only once**.

**Expiry and rotation.** An expired token answers `401` with the date it expired, and the recall hook shows that message instead of failing silently. A few days before, the `token.expiring` notification announces it (see [[Notifications]]). **Rotate** gives a new token with the same name, role, scope and lifetime, shown once; the old one keeps working for the grace period you choose (none, 1 hour, or 1, 3 or 7 days), so there is time to update the agent. Only the token's owner can rotate it. Tokens made before expiry existed never expire: the list marks them **never expires** and suggests rotating them. The list also says how long a token has gone unused, to clean up forgotten ones. API tokens are managed from a session, never with another token.

**Recommendation:** give agents the **contributor** role. That way what they write goes through a curator's (or the decider's) review and an agent that makes a mistake does not pollute the graph. A token **cannot have more role than your user** and **never administers the instance**.

Tokens are **per brain**: an agent using two brains needs two tokens (or one brain that others lend to, see [Federated recall](#federated-recall)). If you disable or delete the account that created a token, the token stops working. Revoke the ones you no longer use.

## 2. Connect over MCP
Each brain exposes an MCP server at:
```
https://your-server/api/brains/<slug>/mcp        Authorization: Bearer mst_…
```
It uses the Streamable HTTP transport, stateless and tools only: any MCP client that can send a header works. With Claude Code:
```bash
claude mcp add --transport http mimirsynth "https://your-server/api/brains/my-brain/mcp" --header "Authorization: Bearer mst_..."
```
The server offers these tools:

| Tool | Minimum token role | What it does |
|---|---|---|
| `recall` | Reader | Returns the memory context for a question, the same as the HTTP recall. Arguments: `query` and, optionally, `facts`, `chunks`, `docs`, `max_chars` and `federated` |
| `remember` | Contributor | Proposes a memory, with the same rules as the HTTP proposals (quarantine for a contributor, approved at once for a curator). Arguments: `name`, `body` and, optionally, `source`, `source_description`, `reference_time` and `confidence` |
| `facts_about` | Reader | Everything known about an entity: current facts and those that stopped being true, newest first, with dates, the episode each one was learned from and the **uuid of each fact** in brackets. The entity is found by name (case and spacing do not matter), by a name merged into it or by its uuid; an ambiguous name returns the candidates. Arguments: `entity` and, optionally, `status`, `limit`, `offset`, `max_chars` and `federated` |
| `timeline` | Reader | How what is known about an entity changed: when each fact was learned and when it stopped being true. Arguments: `entity` and, optionally, `since`, `until`, `limit`, `offset`, `max_chars` and `federated` |
| `get_document` | Reader | Reads a passage with the text around it (the `[doc N, chunk M]` numbers that `recall` gives) or a whole document in parts. A passage lent by another brain is read with `origin`. Arguments: `document` and, optionally, `chunk`, `radius`, `offset`, `max_chars` and `origin` |
| `whats_new` | Reader | Facts learned and facts that stopped being true since a date, oldest first. Without `since`, from where this token's last call without a date stopped, so an agent catches up at the start of a session without storing anything. Arguments: optionally `since`, `offset`, `limit`, `max_chars` and `federated` |
| `correct` | Contributor | Proposes invalidating a fact that is no longer true, by its uuid, with the reason and optionally the text that replaces it. It **always waits for a person**, even with a curator token (see [[Proposals]]). Arguments: `fact_uuid`, `reason` and, optionally, `replacement`, `invalid_at`, `source_description` and `confidence` |

- The token decides the brain and the role, so the tools take no brain argument. To use two brains, add two servers with different names.
- With a **reader** token, `remember` and `correct` answer with an error the model can read ("this token can only read").
- Every answer has a size limit (`max_chars`) and says how to ask for the next page, and what other brains lend comes labelled with its origin.
- Only **API tokens** are accepted, never a browser session; a request from a web page of another origin is refused.
- When a tool fails (invalid arguments, a blocked secret…), the error comes back to the model as a tool result, so it can correct itself.

For Claude Code there is also a recall hook that injects memory into every prompt without the model asking: see [[Claude Code integration]].

## 3. Use the HTTP API
All requests carry the header `Authorization: Bearer mst_…`. The base address is `https://your-server/api/brains/<slug>/…`.

### Reading: recall
```bash
curl -s -X POST "$URL/api/brains/my-brain/recall" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"query": "where does the production database run now?"}'
```
The response includes:
- `facts`: the most similar facts (current and invalidated, with dates).
- `chunks`: fragments of the episodes' original text.
- `documents`: the cited document passages, if any.
- `context`: **the block of text ready to inject into the prompt**.
- `federated`: only when other brains lend to this one, the state of each of them (`ok`, `error`, `off`).
- `ms`: timings.

Optional parameters:
| Parameter | Default | Range | What it is |
|---|---|---|---|
| `facts` | 8 | 0–30 | Maximum number of facts |
| `chunks` | 4 | 0–15 | Maximum number of episode fragments |
| `max_chars` | 6000 | 500–30000 | Maximum size of the context |
| `docs` | the instance's (2) | 0–6 | Document passages. **0 = no documents** |
| `federated` | `true` | | Include what other brains lend to this one. `false` = only this brain's own memory |

> Recall takes on the order of **100–300 ms** and **uses no LLM**, so it is safe to call on every turn. If the server does not respond, your agent should carry on without memory (the Claude Code hook does).

### Writing: proposals
```bash
curl -s -X POST "$URL/api/brains/my-brain/proposals" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Database migrated", "body": "On 19 Oct the production database moved to server db02.", "confidence": 0.8}'
```
| Field | Required | What it is |
|---|---|---|
| `name` | yes | Short title (up to 255 characters) |
| `body` | yes | The content (up to 50,000 characters) |
| `source` | no | `text` (default), `message` or `json` |
| `source_description` | no | Where it comes from (up to 255 characters) |
| `reference_time` | no | ISO date of **when** what you describe happened, if not now |
| `confidence` | no | 0–1: your confidence in the data |

With a **contributor** token the proposal stays **pending**; with **curator**, **approved** and ingested right away. For writing tips, [[Writing good memory]].

### Documents
`GET /api/brains/<slug>/docs/search?q=…` searches by meaning. `GET …/docs/<id>/context?chunk=<n>` returns more context for a passage and `…/docs/<id>/file` the original. See [[Document memory]].

## Federated recall
An administrator of a brain can **lend read access** to another brain (Administration → Brain access → **Federation**). The receiving brain's recall, over HTTP and over MCP, then also searches what it is lent, merges it with its own memory and marks each lent item with its origin (`· from «slug»` in the context, an `origin` field in the JSON). The agent needs no extra token: it keeps using the receiving brain's token. Lending is read-only, one way and one hop; `remember` always writes to the token's own brain. Pass `federated: false` to get only the brain's own memory. Details in [Federation between brains](https://github.com/MimirSynth/mimirsynth/blob/main/docs/FEDERATION.md).

## Language of the answers
Error messages, the MCP tool descriptions and instructions, and the headings of the recall context (`## Current facts`…) come in the caller's language, chosen in this order:
1. The `Accept-Language` header, if it asks for a supported language (`en`, `es`).
2. The language the token's owner chose in [[My account]].
3. The instance default (`MIMIRSYNTH_DEFAULT_LANGUAGE`, or Administration → General).

Stored memory (facts, episodes, documents) is returned as it was written; it is not translated. If your client compares error texts, send `Accept-Language` or, better, compare the status code.

## Secrets
**Do not send passwords, keys or tokens:** write **where** they are kept (for example, which password manager). Before a proposal is stored, over HTTP or through `remember`, it goes through the brain's secret detector, and what happens depends on the brain's policy (Administration → Brain access → **Secrets**):
- **Mask** (the default): a certain secret is replaced by `[secret removed: type]` and the rest is stored.
- **Block**: the proposal is rejected with a `422` that says which type of secret it contains.
- **Only warn**: it is stored as is and flagged.

A value that only *might* be a secret is always flagged, and a flagged proposal **always waits for a curator's review**, even when a curator token sends it. The value never reaches the audit log, the logs or the API responses.

The answer says what happened: the `remember` result adds, for example, «Secrets masked before saving: GitHub token», and the HTTP response carries the same text in `secrets_notice` (empty when nothing was found). The value is never in it.

## 4. Integrate recall in your agent
The typical integration:
1. **Before** the agent answers, call `recall` with the user's message (or let an MCP agent call the tool itself).
2. Inject `context` into the prompt (as context, **not as instructions**).
3. **Afterwards**, if the agent learned something worth remembering, send a proposal (`remember`).

Recovered content — above all from documents — is **data, not instructions**: it may contain text that looks like an order. Your agent must treat it as a quote from a source and not execute it.

The full endpoint reference is in [[REST API]].

## Security
- Keep the token as a secret (password manager, environment variable), not in code.
- Use HTTPS ([[HTTPS and reverse proxy]]).
- One token per agent and per brain: that way you can revoke one without affecting the rest, and in the [[Audit log]] you know who wrote what.
