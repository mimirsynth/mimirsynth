**English** · [Español](API-REST)

# REST API

All of the interface's functionality is available through a JSON REST API under `/api`. With the application running, the **interactive documentation (OpenAPI)** is at `https://your-server/docs`, with all parameters and schemas. This page is the map.

## Authentication
- **Agents and scripts:** header `Authorization: Bearer mst_…` with an [API token](Connect-agents). A token is scoped to **one brain** and a role (maximum curator); it cannot use the instance administration routes. Its scope can limit it further (`recall`, `documents`, `propose`): a route outside it answers `403`. An expired token answers `401` with the date.
- **The web interface:** a signed session cookie after signing in.
- **MCP:** `POST /api/brains/{slug}/mcp` is the brain's [MCP server](Connect-agents) (Streamable HTTP, stateless). It accepts **only API tokens**, never the session cookie, and refuses browser origins other than the instance's.

Common errors: `401` (not authenticated or invalid token), `403` (insufficient role), `404` (does not exist or you have no access), `409` (conflict, e.g. duplicate), `422` (invalid data, or a proposal blocked for carrying a secret), `429` (too many attempts), `503` (from `/health`: the database or the graph is down).

<!-- generated:start (scripts/wiki_reference.py writes this part from the code: do not edit it by hand) -->
## Per-brain routes
All hang off `/api/brains/{slug}/…`. The role is the **minimum** their dependencies require; a few routes check more, see the notes below.

| Area | Routes | Role |
|---|---|---|
| **Recall** | `POST /recall` · `POST /mcp` · `POST /recall/{rid}/ratings` · `POST /answer` | reader |
| | `GET /recall/quality` | curator |
| | `PUT /recall/settings` | administrator |
| **Text index** | `GET /index/status` | reader |
| | `POST /index/sync` | curator |
| **Overview** | `GET /overview` · `GET /overview/activity` | reader |
| **Episodes** | `GET /episodes/sources` · `GET /episodes` · `GET /episodes/{uuid}` | reader |
| **Facts** | `GET /facts/relations` · `GET /facts` · `GET /timeline` · `GET /entities/{uuid}` · `GET /entities` | reader |
| | `PATCH/DELETE /facts/{uuid}` · `POST /facts/{uuid}/invalidate` · `POST /facts/{uuid}/reactivate` · `PUT /entities/{uuid}/type` | curator |
| **Graph and query** | `GET /graph` · `POST /query` | reader |
| **Proposals** | `POST /proposals/corrections` · `GET/POST /proposals` · `GET /proposals/counts` · `GET /proposals/{pid}` | contributor |
| | `POST /proposals/{pid}/reactivate` · `POST /proposals/{pid}/approve` · `POST /proposals/{pid}/ingest` · `POST /proposals/{pid}/reject` | curator |
| **Documents** | `GET /docs/sources` · `GET /docs` · `GET /docs/search` · `GET /docs/{doc_id}` · `GET /docs/{doc_id}/text` · `GET /docs/{doc_id}/file` · `GET /docs/{doc_id}/context` · `GET /docs/{doc_id}/entities` · `GET /docs/mentions` | reader |
| | `DELETE /docs/{doc_id}` · `POST /docs/{doc_id}/reindex` · `POST /docs/uploads` · `PUT /docs/uploads/{uid}/parts/{n}` · `DELETE /docs/uploads/{uid}` · `POST /docs/uploads/{uid}/complete` · `POST /docs/{doc_id}/promote` | contributor |
| | `POST /docs/duplicates` · `GET /docs/roots` · `POST /docs/sources` · `PATCH/DELETE /docs/sources/{sid}` · `POST /docs/sources/{sid}/scan` · `GET /docs/wiki/adapters` · `POST /docs/wiki/collections` · `GET /docs/sources/{sid}/wiki/collections` · `POST /docs/sources/wiki` · `POST /docs/sources/git` | administrator |
| **Vocabulary** | `GET /vocabulary` · `GET /vocab/aliases` · `GET /vocab/types` · `GET /vocab/types/{name}/preview` · `POST /vocab/duplicates/preview` · `GET /ontology` | reader |
| | `POST /vocab/ops/{oid}/revert` · `GET /summaries` · `POST /summaries/entity/{uuid}` · `POST /summaries/{sid}/approve` · `POST /summaries/approve` · `POST /summaries/reject` | curator |
| | `POST /vocab/aliases` · `DELETE /vocab/aliases/{aid}` · `POST /vocab/types` · `PUT/DELETE /vocab/types/{name}` · `POST /vocab/types/{name}/move` · `POST /vocab/relations` · `PUT/DELETE /vocab/relations/{name}` · `PUT /vocab/map` · `PUT /vocab/instructions` · `POST /vocab/duplicates/merge` · `POST/DELETE /vocab/duplicates/ignore` · `GET /retype` · `POST /retype/scan` · `POST /retype/apply` · `POST /retype/reject` · `POST /retype/{sid}/apply-as` · `POST /retype/{sid}/revert` · `GET/POST /vocab/entity-aliases` · `POST /summaries/scan` · `PUT /ontology` · `POST /ontology/preset/{name}` | administrator |
| **Needs your attention** | `GET /attention` | curator |
| **What changed** | `GET /changes` | curator |
| **Facts to review** | `GET /review/stale` · `POST /review/stale/{uuid}/confirm` | curator |
| **Contradictions** | `GET /conflicts` · `POST /conflicts/dismiss` · `DELETE /conflicts/dismiss/{did}` · `POST /conflicts/resolve` | curator |
| **Reference queries** | `GET/POST /refqueries` · `PATCH/DELETE /refqueries/{qid}` · `GET /refqueries/export` · `POST /refqueries/import` · `GET/POST /refqueries/runs` · `GET /refqueries/runs/{rid}` | curator |
| **Federation** | `GET /grants` | reader |
| | `POST /grants` · `PATCH/DELETE /grants/{gid}` | administrator |
| **Jobs** | `GET /jobs` · `GET /jobs/summary` · `GET /jobs/{jid}` | reader |
| | `POST /jobs/{jid}/cancel` · `POST /jobs/{jid}/retry` | curator |
| **Members** | `GET/PUT /members` · `DELETE /members/{user_id}` | administrator |
| **Tokens** | `GET/POST /tokens` · `POST /tokens/{token_id}/rotate` · `DELETE /tokens/{token_id}` | reader |
| **The brain itself** | `PATCH /api/brains/{slug}` · `GET /secrets/scan` | administrator |
| | `POST /delete` | owner |
| **AI consumption** | `GET /ai-usage` · `PUT /ai-budget` | administrator |
| **Incoming webhooks** | `GET/POST /webhooks` · `PUT/DELETE /webhooks/{hid}` · `POST /webhooks/{hid}/rotate` · `GET /webhooks/{hid}/events` · `POST /webhooks/preview` | administrator |
| | `POST /hooks/{key}` | the webhook's secret |
| **Retention** | `GET/PUT /retention` · `POST /retention/run` | owner |
| **Export** | `GET/POST /exports` · `GET /exports/{jid}/download` | administrator |

## Account and instance routes
Under `/api/…`.

| Area | Routes | Access |
|---|---|---|
| **Access** | `GET /auth/options` · `POST /auth/setup` · `GET/POST /auth/login` · `POST /auth/mfa` · `GET /auth/token/{raw}` · `POST /auth/accept` · `POST /auth/forgot` · `GET /auth/login/{slug}` · `GET /auth/callback/{slug}` · `GET /auth/callback` · `POST /auth/logout` · `POST /auth/passkey/options` · `POST /auth/passkey/login` · `POST /auth/passkey/mfa/options` · `POST /auth/passkey/mfa` | public |
| **My account** | `POST /me/password` · `GET /me` · `GET /me/identities` · `DELETE /me/identities/{iid}` · `GET /me/identities/link/{slug}` · `GET/PATCH /me/profile` · `POST/DELETE /me/avatar` · `GET /users/{uid}/avatar` · `GET /me/tokens` · `GET /me/activity` · `POST /me/sessions/revoke-others` · `GET /me/2fa` · `POST /me/2fa/begin` · `POST /me/2fa/enable` · `POST /me/2fa/disable` · `POST /me/2fa/recovery` · `GET /me/passkeys` · `POST /me/passkeys/begin` · `POST /me/passkeys/finish` · `POST /me/passkeys/{pid}/delete` · `PATCH /me/passkeys/{pid}` · `GET/PUT /me/digest` · `GET /me/digest/preview` | signed in |
| **Search all brains** | `POST /search` | signed in |
| **Notifications** | `GET /notifications` · `GET /notifications/summary` · `POST /notifications/read` | signed in |
| | `GET /notifications/catalog` · `GET/POST /notifications/channels` · `PUT/DELETE /notifications/channels/{cid}` · `POST /notifications/channels/{cid}/test` · `GET /notifications/deliveries` · `POST /notifications/deliveries/{did}/retry` | instance administrator |
| **Brains** | `GET /brains` | signed in |
| | `POST /brains` | instance administrator |
| **AI consumption** | `GET /ai-usage` · `PUT/DELETE /ai-usage/prices` | instance administrator |
| **Import a brain** | `POST /brain-imports/uploads` · `PUT /brain-imports/uploads/{uid}/parts/{n}` · `DELETE /brain-imports/uploads/{uid}` · `POST /brain-imports/uploads/{uid}/complete` · `GET/POST /brain-imports` | instance administrator |
| **Administration** | `GET /ai-status` | signed in |
| | `GET /users` · `GET /audit` · `GET/POST /doc-roots` · `DELETE /doc-roots/{rid}` · `POST /llm-engines/models` · `GET/POST /llm-engines` · `PATCH/DELETE /llm-engines/{eid}` · `POST /llm-engines/{eid}/default` · `POST /llm-engines/{eid}/test` · `GET/POST /decision-engines` · `PATCH/DELETE /decision-engines/{eid}` · `POST /decision-engines/{eid}/default` · `POST /decision-engines/{eid}/test` · `GET/POST /embedding-engines` · `PATCH/DELETE /embedding-engines/{eid}` · `POST /embedding-engines/{eid}/default` · `POST /embedding-engines/{eid}/test` · `GET /settings` · `POST /settings/smtp/test` · `GET /settings/sealed` · `PUT /settings/secret/{key}` · `PUT/DELETE /settings/{key}` · `GET/POST /oidc-providers` · `PUT/DELETE /oidc-providers/{slug}` · `POST /oidc-providers/{slug}/test` · `GET/POST /admin/users` · `GET/PATCH/DELETE /admin/users/{uid}` · `POST /admin/users/{uid}/link` · `POST /admin/users/{uid}/logout` · `POST /admin/users/{uid}/unlock` · `POST /admin/users/{uid}/mfa/reset` · `PUT /admin/users/{uid}/memberships` · `GET /admin/metrics` · `POST/DELETE /admin/metrics/token` | instance administrator |
| **Embedding model change** | `GET /embedding-engines/reindex` · `GET /embedding-engines/{eid}/reindex/estimate` · `POST /embedding-engines/{eid}/reindex` · `POST /embedding-engines/reindex/{jid}/cancel` · `POST /embedding-engines/reindex/{jid}/retry` · `POST /embedding-engines/reindex/discard` · `POST /embedding-engines/reindex/switch` | instance administrator |
| **Public** | `GET /config` · `GET /health` | public |
<!-- generated:end -->

## Notes on some routes
- **Routes that check more than their role:** `POST /tokens/{id}/rotate` is only for the token's owner, and `/tokens` and `POST /api/search` only work from a session, never with an API token (`403`); a token's role never exceeds yours. A contributor only sees their own proposals. Connecting a wiki and changing its collections or key need the instance administrator. `PATCH /api/brains/{slug}` can only change the graph for the instance administrator.
- **`POST /recall`** returns a `recall_id`; `POST /recall/{recall_id}/ratings` rates what came back: `kind` (`fact`, `chunk` or `doc`), `id`, `rating` (`useful`, `irrelevant` or `incorrect`) and an optional `note`. `GET /recall/quality?days=30` sums the ratings, and `PUT /recall/settings` (`keep_query_text`) decides whether the text of the queries is kept.
- **`PUT /entities/{uuid}/type`** takes `{"type": …}`, a type of the brain's ontology; it is undone from the vocabulary history. `GET /entities?q=` finds entities by name.
- **`POST /query`** runs read-only Cypher.
- **Uploads:** `POST /docs/uploads`, then each part with `PUT /docs/uploads/{uid}/parts/{n}` and `POST …/complete`. The wiki sources are under `/docs/sources` and `/docs/wiki`.
- **The collections of a wiki source** (instance administrator): `GET /docs/sources/{id}/wiki/collections` returns those available, the `selected` ones and the indexed `documents` per collection. `PATCH /docs/sources/{id}` with `collection_ids` changes them: adding starts a scan and returns its `job`; removing answers `409` with the number of documents until `confirm_removed` repeats it, and then takes only those out of the index. Only pages whose collection is known are removed; the pages in the wiki are never touched. See [[Knowledge]].
- **`GET /attention`** says what waits for a decision: `proposals`, `corrections`, `duplicates`, `conflicts`, `stale`, `refqueries`, and `retype` for administrators; `null` when a counter could not be computed. It is cached for a minute and dropped by any successful write on the brain; `?fresh=true` recalculates.
- **`GET /changes?days=7`** (1–31): `facts_new`, `facts_gone`, `docs_new`, `proposals_new` and `proposals_decided` over the period; `null` when the graph could not be counted.
- **`GET /review/stale`** lists the current facts past their relation's shelf life, oldest first; `…/confirm` confirms one.
- **`/tokens`:** `scopes` (`recall`, `documents`, `propose`) and `days` until it expires (empty for never). `POST /tokens/{id}/rotate` takes `grace_hours` (0–168, default 24).
- **`PATCH /api/brains/{slug}`** changes the name, description, slug and secrets policy. `POST /api/brains/{slug}/delete` deletes the brain.
- **AI consumption:** `GET /ai-usage?days=30` and `PUT /ai-budget` (`limit`, `unit`: `tokens` or `cost`, `pause`) for a brain; for the instance, `GET /api/ai-usage?days=30` (per brain and engine, with requests per minute now) and `PUT/DELETE /api/ai-usage/prices` (price per million tokens of a model). See [[AI consumption]].
- **Incoming webhooks:** `POST /hooks/{key}` has no session: the webhook's secret is the credential, as an HMAC signature or a token header, and it answers `202` with what happened to each event. `POST /webhooks/{id}/rotate` gives a new secret, shown once; `POST /webhooks/preview` takes `template`, `config`, `body` and `event`. See [[Incoming webhooks]].
- **`/retention`:** `rejected_days` and `jobs_days`, in days (empty for the instance's, 0 for forever); `POST /retention/run` purges now.
- **`POST /exports`** takes `vectors` and an optional `password`; `GET /exports/{id}/download` works once (`410` once downloaded or expired). See [[Export a brain]].
- **`POST /api/search`** `{query, facts, chunks}`: the recall in every brain the person can read, grouped by brain with `state` `ok`, `timeout` or `error`.
- **Import a brain:** `POST /api/brain-imports/uploads`, its parts and `…/complete` (which returns the manifest's summary), then `POST /api/brain-imports` (`upload_id`, `slug`, `name`, `mode`, optional `password`, `dump` for fast restore). See [[Import a brain]].
- **Sign-in:** `GET /api/auth/login/{provider}` and `/api/auth/callback/{provider}` are the OIDC sign-in.
- **`GET /api/ai-status`** (`?check=true` tests every engine and returns `model` and `ms`).
- **Embedding model change:** `GET /api/embedding-engines/reindex` is the state of the shadow fill (`orphan: true` only for a failed or abandoned one), and `POST /api/embedding-engines/reindex/switch` needs `{"backup_confirmed": true}`.
- **`POST /mcp`**: the MCP server, with the tools `recall`, `facts_about`, `timeline`, `get_document` and `whats_new` (reader) and `remember` and `correct` (contributor).
- **`POST /answer`** runs the recall like `POST /recall` and streams NDJSON, one object per line: `{"type": "sources", "recall_id", "sources": [{"ref": "F1", "kind": "fact" | "episode" | "document", "id", "text", …}]}`, then `{"type": "delta", "text"}` as the answer is written, and `{"type": "done", "citations": ["F1", "D1"], "unknown": [], "called": true}` (or `{"type": "error", "detail"}`). `unknown` lists labels the model cited that were not in the evidence. With no evidence it answers that there is no information and `called` is `false`. It needs the `recall` scope, brings document passages only with `documents`, answers `429` past *Answers per person and hour* or while the brain's AI budget is used up with pause, and `503` without an LLM engine.
- **`POST /recall`** takes `federated` (default `true`): it also searches what other brains lend to this one, marks lent items with `origin` and adds a `federated` list with the state of each source. **`/grants`** manages what this brain lends (`scope`: `graph`, `docs` or `both`; optional expiry in `days`); the receiving brain can decline with `DELETE`.
- **`GET /entities/{uuid}`** is the [[Entity page]] in one call: the entity, its facts grouped by direction and relation (`current` and `previous`, oldest first, with a `conflict` flag for single-valued relations and `generic` for catch-all ones such as `RELATES_TO`, which go last), its neighbours and the episodes that mention it; the documents that mention it come from `GET /docs/mentions?entity=`. `as_of` (a date) gives what was current that day; `origin` reads an entity lent by another brain. `GET /entities?q=` finds entities by name or merged name. `entity.summary_repeats` is `true` when at least half of the summary's lines are the entity's own facts (the page then hides it), and `entity.aliases` never holds the entity's own name.
- **`GET /proposals`** is paginated: it takes `status`, `kind` (`memory` or `correction`), `q` (title), `author` (user id), `sort` (`id`, `name`, `author`, `conf`, `at`), `order` (`asc`/`desc`), `limit` (default 50, maximum 500) and `offset`, and returns `{total, limit, offset, authors, items}` instead of a bare list. A contributor only sees their own.
- **`GET /proposals/counts`** counts per state (only of one `kind` when given), plus `kinds` (each kind across every state) and `corrections_pending`.
- **`POST /proposals`** returns the proposal plus `secrets_notice`: which types of secret were masked or flagged, in the caller's language, never the value (empty when nothing was found).
- **`POST /proposals/corrections`** proposes invalidating a fact: `{fact_uuid, reason, replacement?, invalid_at?}`. A curator applies it at once; `POST /proposals/{id}/reactivate` undoes an applied one. See [[Proposals]].
- **`GET /graph?group_by=`** (`label`, `source`, `document`, `author`, `token`) adds the provenance: each node and fact carries `sources`, `source_count` and `provenance` (the keys for every grouping), and the response adds `groups` with each origin's name and counts. Without `group_by` nothing is computed: in a large brain it can cost more than the subgraph itself.
- **`GET /docs/{id}/entities`** returns, besides the mentioned `entities`, the `relations` between them (current only, unless `expired=true`), `total` and `expired_count`.
- **`POST /docs/duplicates`** starts the *Find duplicate documents* job and returns its id; documents whose text repeats another's are marked `duplicate` and taken out of the index.
- **`GET /secrets/scan`** runs the secret detector read-only over the brain's proposals and documents and returns counts per rule, never values. The policy (`secret_mode`: `mask`, `block`, `warn`; `secret_allow`: exceptions) is changed with `PATCH /api/brains/{slug}`.
- **`/conflicts`**: possible contradictions in single-valued relations; `/resolve` invalidates the facts in `invalidate`, keeping `keep` when given (without it, only the listed facts are invalidated); at least one fact of the group must stay current, or it returns 400. Undoable from the vocabulary history. Each group carries `targets` and `likely_multi` (the relation probably holds several values, so there is no suggestion), and with `all=true` each relation in `by_relation` carries `max_targets` and `likely_multi`. `/dismiss` marks a group as not a contradiction (`{source_uuid, source, relation, target_type, facts}`); it stays hidden while no other fact joins it, and the `GET` lists it under `dismissed`.
- **`/refqueries`**: reference queries and their runs; `POST /refqueries/runs` with `sweep` (a list of similarity thresholds) simulates without changing the setting.

`GET /health` answers `200` with `{"ok", "db", "graph", "graphs"}` when PostgreSQL and FalkorDB respond, and `503` with the same body when either is down; it is the endpoint for an external monitor ([Monitoring the instance](Installation#monitoring-the-instance)).

## Conventions
- Dates in ISO 8601 with time zone.
- Paginated lists: `limit` and `offset`, and they return `total`.
- **Language:** error messages (`detail`), the MCP texts and the headings of the recall context follow the `Accept-Language` header (`en`, `es`), then the language the session's or token's owner chose, then the instance default. Stored memory is never translated. If your client compares error texts, send `Accept-Language` or compare the status code.
- The API **may change between 0.x versions**: pin the MimirSynth version you use.

## Examples
See [[Connect agents]] (recall, proposals and MCP) and [[Document memory]] (document search).
