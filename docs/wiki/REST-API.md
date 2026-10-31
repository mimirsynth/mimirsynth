**English** · [Español](API-REST)

# REST API

All of the interface's functionality is available through a JSON REST API under `/api`. With the application running, the **interactive documentation (OpenAPI)** is at `https://your-server/docs`, with all parameters and schemas. This page is the map.

## Authentication
- **Agents and scripts:** header `Authorization: Bearer mst_…` with an [API token](Connect-agents). A token is scoped to **one brain** and a role (maximum curator); it cannot use the instance administration routes.
- **The web interface:** a signed session cookie after signing in.
- **MCP:** `POST /api/brains/{slug}/mcp` is the brain's [MCP server](Connect-agents) (Streamable HTTP, stateless). It accepts **only API tokens**, never the session cookie, and refuses browser origins other than the instance's.

Common errors: `401` (not authenticated or invalid token), `403` (insufficient role), `404` (does not exist or you have no access), `409` (conflict, e.g. duplicate), `422` (invalid data, or a proposal blocked for carrying a secret), `429` (too many attempts), `503` (from `/health`: the database or the graph is down).

## Per-brain routes
All hang off `/api/brains/{slug}/…`. The role is the **minimum** needed.

| Area | Routes | Role |
|---|---|---|
| **Recall** | `POST /recall` (optional `federated`) · `POST /mcp` | reader |
| **Text index** | `GET /index/status` · `POST /index/sync` | reader · curator |
| **Overview** | `GET /overview` · `GET /overview/activity` | reader |
| **Episodes** | `GET /episodes` · `GET /episodes/sources` · `GET /episodes/{uuid}` | reader |
| **Facts** | `GET /facts` · `GET /facts/relations` · `GET /timeline` | reader |
| | `PATCH /facts/{uuid}` · `POST …/invalidate` · `POST …/reactivate` · `DELETE …` | curator |
| **Graph and query** | `GET /graph` (optional `group_by`) · `POST /query` (read-only Cypher) | reader |
| **Proposals** | `GET /proposals` (paginated) · `GET /proposals/counts` · `GET /proposals/{id}` · `POST /proposals` · `POST /proposals/corrections` | contributor |
| | `POST /proposals/{id}/approve` · `…/reject` · `…/ingest` · `…/reactivate` | curator |
| **Documents** | `GET /docs` · `GET /docs/search` · `GET /docs/{id}` · `…/text` · `…/file` · `…/context` · `…/entities` · `GET /docs/mentions` · `GET /docs/sources` | reader |
| | `POST /docs/uploads` (+ parts and `complete`) · `POST /docs/{id}/promote` | contributor |
| | `DELETE /docs/{id}` · `POST /docs/{id}/reindex` · `POST /docs/duplicates` · sources (`/docs/sources`, scan, wikis) | administrator |
| **Vocabulary** | `GET /vocabulary` · `GET /vocab/aliases` · `GET /vocab/types` · `GET /ontology` | reader |
| | aliases, types, relations, move/merge, duplicates, ontology, corrector (`/retype`) | administrator |
| | `POST /vocab/ops/{id}/revert` | curator |
| **Contradictions** | `GET /conflicts` (`?all=true` measures every relation) · `POST /conflicts/resolve` · `POST /conflicts/dismiss` · `DELETE /conflicts/dismiss/{id}` | curator |
| **Reference queries** | `GET/POST /refqueries` · `PATCH/DELETE /refqueries/{id}` · `GET /refqueries/export` · `POST /refqueries/import` · `GET/POST /refqueries/runs` · `GET /refqueries/runs/{id}` | curator |
| **Federation** | `GET /grants` | reader |
| | `POST /grants` · `PATCH /grants/{id}` · `DELETE /grants/{id}` | administrator |
| **Jobs** | `GET /jobs` · `GET /jobs/summary` · `GET /jobs/{id}` | reader |
| | `POST /jobs/{id}/cancel` · `…/retry` | curator |
| **Members** | `GET/PUT /members` · `DELETE /members/{user_id}` | administrator |
| **Tokens** | `GET/POST /tokens` · `DELETE /tokens/{id}` | reader (from your own role down) |
| **The brain itself** | `PATCH /api/brains/{slug}` (name, description, slug, secrets policy) · `GET /api/brains/{slug}/secrets/scan` | administrator |
| | `POST /api/brains/{slug}/delete` | owner |

### What changed since 0.6
- **`POST /mcp`**: the MCP server, with the tools `recall`, `facts_about`, `timeline`, `get_document` and `whats_new` (reader) and `remember` and `correct` (contributor).
- **`POST /recall`** takes `federated` (default `true`): it also searches what other brains lend to this one, marks lent items with `origin` and adds a `federated` list with the state of each source. **`/grants`** manages what this brain lends (`scope`: `graph`, `docs` or `both`; optional expiry in `days`); the receiving brain can decline with `DELETE`.
- **`GET /proposals`** is paginated: it takes `status`, `q` (title), `author` (user id), `sort` (`name`, `author`, `conf`, `at`), `order` (`asc`/`desc`), `limit` (default 50, maximum 500) and `offset`, and returns `{total, limit, offset, authors, items}` instead of a bare list. A contributor only sees their own.
- **`POST /proposals`** returns the proposal plus `secrets_notice`: which types of secret were masked or flagged, in the caller's language, never the value (empty when nothing was found).
- **`POST /proposals/corrections`** proposes invalidating a fact: `{fact_uuid, reason, replacement?, invalid_at?}`. A curator applies it at once; `POST /proposals/{id}/reactivate` undoes an applied one. See [[Proposals]].
- **`GET /graph?group_by=`** (`label`, `source`, `document`, `author`, `token`) adds the provenance: each node and fact carries `sources`, `source_count` and `provenance` (the keys for every grouping), and the response adds `groups` with each origin's name and counts. Without `group_by` nothing is computed: in a large brain it can cost more than the subgraph itself.
- **`GET /docs/{id}/entities`** returns, besides the mentioned `entities`, the `relations` between them (current only, unless `expired=true`), `total` and `expired_count`.
- **`POST /docs/duplicates`** starts the *Find duplicate documents* job and returns its id; documents whose text repeats another's are marked `duplicate` and taken out of the index.
- **`GET /secrets/scan`** runs the secret detector read-only over the brain's proposals and documents and returns counts per rule, never values. The policy (`secret_mode`: `mask`, `block`, `warn`; `secret_allow`: exceptions) is changed with `PATCH /api/brains/{slug}`.
- **`/conflicts`**: possible contradictions in single-valued relations; `/resolve` keeps one fact (`keep`) and invalidates the rest (`invalidate`), undoable from the vocabulary history. `/dismiss` marks a group as not a contradiction (`{source_uuid, source, relation, target_type, facts}`); it stays hidden while no other fact joins it, and the `GET` lists it under `dismissed`.
- **`/refqueries`**: reference queries and their runs; `POST /refqueries/runs` with `sweep` (a list of similarity thresholds) simulates without changing the setting.

## Account and instance routes
| Area | Routes |
|---|---|
| **Access** | `GET /auth/options` · `POST /auth/login` · `POST /auth/mfa` · `POST /auth/logout` · `POST /auth/forgot` · `GET /auth/token/{code}` · `POST /auth/accept` · `POST /auth/setup` · `GET /auth/login/{provider}` and `/auth/callback/{provider}` (OIDC) · `POST /auth/passkey/options`, `/auth/passkey/login`, `/auth/passkey/mfa/options`, `/auth/passkey/mfa` |
| **My account** | `GET /me` · `GET/PATCH /me/profile` · `POST/DELETE /me/avatar` · `POST /me/password` · `GET /me/tokens` · `GET /me/activity` · `POST /me/sessions/revoke-others` · `GET /me/2fa` and the two-factor ones · `GET /me/passkeys`, `POST /me/passkeys/begin`, `…/finish`, `PATCH /me/passkeys/{id}`, `POST /me/passkeys/{id}/delete` · `GET /me/identities`, `DELETE /me/identities/{id}`, `GET /me/identities/link/{provider}` |
| **Notifications** | `GET /notifications` · `GET /notifications/summary` · `POST /notifications/read` (the alerts you can see) |
| **Brains** | `GET /brains` · `POST /brains` (instance administrator) |
| **Administration** (instance administrator) | `GET/POST /admin/users` and the per-user actions · `GET /settings` · `PUT/DELETE /settings/{key}` · `POST /settings/smtp/test` · `/oidc-providers` (list, add, edit, delete, `…/{provider}/test`) · `GET/POST /llm-engines`, `/embedding-engines`, `/decision-engines` (+ test, default) · `/notifications/channels` (+ test), `/notifications/deliveries` (+ retry), `/notifications/catalog` · `GET/POST /doc-roots` · `GET /audit` · `GET /ai-status` (`?check=true` tests every engine and returns `model` and `ms`) |
| **Embedding model change** (instance administrator) | `GET /embedding-engines/reindex` (state of the shadow fill; `orphan: true` only for a failed or abandoned one) · `GET /embedding-engines/{id}/reindex/estimate` · `POST /embedding-engines/{id}/reindex` · `POST /embedding-engines/reindex/{job}/cancel` · `…/retry` · `POST /embedding-engines/reindex/discard` · `POST /embedding-engines/reindex/switch` (with `{"backup_confirmed": true}`) |
| **Public** | `GET /health` · `GET /config` |

`GET /health` answers `200` with `{"ok", "db", "graph", "graphs"}` when PostgreSQL and FalkorDB respond, and `503` with the same body when either is down; it is the endpoint for an external monitor ([Monitoring the instance](Installation#monitoring-the-instance)).

## Conventions
- Dates in ISO 8601 with time zone.
- Paginated lists: `limit` and `offset`, and they return `total`.
- **Language:** error messages (`detail`), the MCP texts and the headings of the recall context follow the `Accept-Language` header (`en`, `es`), then the language the session's or token's owner chose, then the instance default. Stored memory is never translated. If your client compares error texts, send `Accept-Language` or compare the status code.
- The API **may change between 0.x versions**: pin the MimirSynth version you use.

## Examples
See [[Connect agents]] (recall, proposals and MCP) and [[Document memory]] (document search).
