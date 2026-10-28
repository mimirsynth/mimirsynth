# Changelog

All notable changes to MimirSynth. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/) (0.x: the API and the schema may change between minor versions).

Releases publish a container image to `ghcr.io/mimirsynth/mimirsynth` (tags `X.Y.Z`, `X.Y`, `X` and `latest`; `linux/amd64` and `linux/arm64`).

## [Unreleased]
### Added
- **`update.sh`**, attached to every release: backs up, updates and checks in one step (`./update.sh`, `--check`, `--version X`, `--rollback [--with-db]`). It downloads the new image first (a wrong version stops everything before touching anything), keeps **a single backup** (PostgreSQL, documents volume, bundled FalkorDB, `docker-compose.yml` and `.env`) that is replaced only after the new one is complete, adopts the release's compose file only if yours is the unmodified one, and verifies the new version and its health afterwards. See `docs/INSTALL.md`.

- OIDC providers: **initial access** for automatic sign-up (#66). A list of `brain:role` (only `reader` and `contributor`) that a person registered automatically through that provider receives once, when the account is created, as ordinary memberships recorded in the audit log (`member.set`, `via=oidc-default:<provider>`). An administrator can change or remove them and no later sign-in restores them; a group that grants a higher role on the same brain wins. Saving the provider refuses other roles and brains that do not exist. Migration `0022`. See `docs/CONFIGURATION.md`.
- Documentation: how to watch PostgreSQL with an external monitor, since the built-in alerts are stored in it and cannot report its outage (#68). See «Monitoring the instance» in `docs/INSTALL.md`.

### Changed
- **OIDC with «Accept unverified emails»** (#66): an unverified email now links only to an invitation, never to an account that is already active. That person sees a message asking them to sign in as usual and link the provider from My account → Security (`auth_error=link_required`). Before, an unverified email matching an active account, including an administrator's, was enough to sign in as that account. With a verified email nothing changes.
- `GET /api/health` now also checks PostgreSQL (#68). It returns `db` and `graph` (`true`/`false`) and answers `503` with the same body when either is down, so an external monitor can tell «application down» (no answer) from «application alive, database down». Each check waits at most 2 seconds. The error detail is no longer part of the response (the endpoint is public): it goes to the log.
- The health check of the graph and the AI models now alerts only after **2 consecutive failures** (new setting «Consecutive failures before alerting» under Administration → Notifications; 1 restores the old behaviour). A one-off 500 or timeout from a provider no longer raises an alert and its recovery message.
- The type corrector no longer assumes an infrastructure domain (#56). What it reviews comes from the brain's ontology: entities without a type, entities whose type is not in the ontology, and the types the package lists in its new `retype` block. It used to review only a fixed list (`Person`, `Location`, `Organization`, `Event`…), so in a family brain it checked correct people and places and never looked at pets or belongings. The technical rules that set names aside as doubtful before asking the decider (file, option, code, version, problem) now apply only when the package enables them: all of them in `infrastructure`, which behaves as before; only `option` in `software-knowledge`; none in the other packages or in hand-written ontologies. The decider's question no longer rules out errors or procedures when the ontology has types for them. See `docs/ONTOLOGY.md`.
- **Effect on existing suggestions:** in brains whose package no longer enables a rule, suggestions that the corrector showed as doubtful for that rule (for example «Receta 1.5» for the version rule) are shown as pending again and can be applied. Nothing changes in `infrastructure` brains.

### Fixed
- `GET /api/embedding-engines/reindex` no longer reports `orphan: true` when the shadow fill has finished and is waiting for the switch (#69). `orphan` is now `true` only for a failed or abandoned fill. The `reindex.orphan` alert and the panel already looked at the state, so nothing else changes.
- Documentation: after changing the embedding model, what to do with `MIMIRSYNTH_EMBEDDING_DIM` and the other `MIMIRSYNTH_EMBEDDING_*` variables in `.env`.

## [0.7.1] - 2026-10-27
### Added
- Administration → Embeddings: change the embedding model from the interface (#48). **Reindex** on an engine with another model shows the estimate (items, engine calls, memory) and computes the vectors in shadow; a panel shows the progress with Cancel, unfinished shadows with Retry and Discard and, when ready, **Switch to the new model**, which requires ticking that FalkorDB and PostgreSQL have been backed up. When it finishes it reminds you to recalibrate the recall's minimum passage similarity and to switch agents that write directly to Graphiti.
- Second step of the embedding model change (#48): swapping to the new engine. `POST /api/embedding-engines/reindex/switch` (needs a finished shadow fill and an explicit backup confirmation, kept in the log and the audit) catches up with what changed, pauses vector writes for at most a configurable wait (if writes in progress do not finish, the change is postponed, never the writes), swaps the vectors of every graph and, in one PostgreSQL transaction, replaces the columns and HNSW indexes and makes the new engine the default. On failure the graphs roll back and everything stays on the previous engine; after a crash in the middle, the service makes every graph consistent with the default engine on start, before serving. The pause duration is logged. Interface in a later step.
- First step towards changing the embedding model (#48): a resumable background job computes, with the new engine and without touching the vectors in use, every vector of every brain in shadow (entity and fact embeddings in FalkorDB, `episode_chunks` and `doc_chunks` in pgvector with their own HNSW index). API only for now: a bounded estimate (cheap counts and a sample, with a time limit and a short cache), start (the job estimates and refuses to go on without enough free memory in FalkorDB), progress, cancel, retry and discard. Unfinished shadows leave a marker reported by the API and raise the new `reindex.orphan` alert if they stay failed or stalled. The shadow HNSW index is built concurrently and table changes use a short `lock_timeout` with retries. Batch size and pause between batches are configurable and `Retry-After` is honoured on 429. Cancelling or discarding removes every shadow property, column and index. Swapping the vectors and the interface will come in later steps. See `docs/CONFIGURATION.md`.
- Knowledge → document viewer: under «Mentioned entities», a new **Relations** section shows how those entities relate in the graph («A —relation→ B», with the fact and the date it holds from). Only current facts by default, with a switch to include the ones that are no longer true, and «Show more». One graph query, no LLM or embeddings; `GET /docs/{id}/entities` now also returns `relations`, `total` and `expired_count`.

### Changed
- The decider no longer assumes an infrastructure domain. Triage used to ask whether a proposal was "a factual statement about the infrastructure"; it now judges it against the brain's scope (its description and the entity and relation types of its ontology), and without either only checks that it is factual. The type corrector's questions are generic too. It still never rejects on its own: what does not fit goes to a curator. The brain description can now be edited when creating or editing a brain.

### Fixed
- Knowledge → document viewer: the status tags (indexed, size, chunks) no longer sit flush against the panel header.

## [0.7.0] - 2026-10-26
### Added
- **Notifications**: a bell in the sidebar with the alerts you can see (instance administrators see all; curators see their brains') and, for administrators, channels to send them to: **Telegram**, **ntfy**, **Gotify**, **webhook** (optionally signed with HMAC-SHA256) and **email**. Events: AI model or graph not responding, failed ingestion after its retries, failed job, document source error, account lockout, and new versions (opt-in). Repeated problems are grouped, recoveries are announced, channels filter by severity and event, quiet hours hold non-critical alerts, and failed deliveries retry with growing waits and can be retried by hand. Alerts never include memory content. Channel secrets are stored encrypted; links to the cloud metadata address are always refused. Migration `0021`. See `docs/NOTIFICATIONS.md`.
- **Passkeys (WebAuthn)**: add them in My account → Security and sign in with your device's fingerprint, face or PIN, or use them as the second step after the password. They require user verification, so a passkey counts as two-factor, also when the administrator makes two-factor mandatory. Only the public key is stored; the sign counter detects cloned keys; challenges are single-use. Removing one asks for the password and never leaves an account without a way in; an administrator's two-factor reset also removes the person's passkeys. New dependency `webauthn` and migration `0020`. Needs `MIMIRSYNTH_PUBLIC_URL` over HTTPS. See `docs/CONFIGURATION.md`.
- **Federation between brains**: an administrator of a brain can lend read access to another brain (scope: graph, documents or both; optional expiry; revocable at any time; audited). The receiving brain's `recall` (REST and MCP) merges what it is lent with its own using weighted RRF and marks each lent item with its origin. One way and one hop; no embeddings or summaries are shared. New Administration → Brains → Federation panel, `/api/brains/{slug}/grants`, `federated` option on `recall`, and migration `0019`. See `docs/FEDERATION.md`.
- Wiki adapters for **Confluence** (Cloud and Data Center) and **Notion**, read-only. Written against each API's documented format and covered by tests with simulated responses; not yet validated against a live instance. Docmost is left out for now (no documented public API).
- Knowledge → Sources → Edit: change which collections (spaces, databases) of a connected wiki are indexed, using the stored credentials.

### Changed
- Sign out is now one click away: the sidebar shows the person's avatar and name (linking to My account) with a sign-out button next to it, and My account has a highlighted «Sign out» button under its section menu. It used to be a small button in My account → Security → Sessions.
- A wiki page's content can now be fetched lazily: a rescan only downloads the pages that are new or whose modification date changed.
- Accessibility pass (see `docs/ACCESSIBILITY.md`): every screen has a level-one heading and the sign-in and setup screens a `main` landmark; action columns in tables have a visually hidden header instead of an empty one; the pager no longer overflows at 320 px; a skipped heading level fixed.

## [0.6.0] - 2026-10-26
### Added
- Own MCP server: `POST /api/brains/{slug}/mcp` (Streamable HTTP, stateless) exposes the tools `recall` (reader) and `remember` (contributor) with the same API tokens and roles as the REST API. Only API tokens are accepted, browser origins other than the instance's are rejected, and tool failures are returned to the model as tool errors. See `docs/AGENTS.md`.
- Standard ontology packages replace the old starter ones: `general`, `infrastructure` (rewritten), `team-projects`, `personal-family` and `software-knowledge`. Aligned with schema.org, FOAF, Dublin Core, DOAP and ITIL/CMDB; every type says what it is, when to use it and when not to, with examples; every package has extraction instructions. See `docs/ONTOLOGY.md`.
- Ontology packages are versioned. A brain remembers the package and version it applied; when a newer version ships, **Update** adds what is missing (types, relations, rules) without touching anything you changed by hand. «Replace ontology» now asks for confirmation.
- Tests check each package: valid map, no unused types or relations, descriptions with guidance and examples, no personal data.

### Changed
- The `generic` package is now `general` (the old name still works as an alias).
- Type corrector: applying or rejecting in bulk now asks for confirmation with a summary by proposed type, there is a «Reject all visible» action, the result of each action is reported (including how many did not fit the ontology), the confidence is shown as a percentage and a filter can no longer apply rows it has hidden.
- The request limiter (sign-in, two-factor, password recovery and setup) now keeps its attempts in the database (migration `0018`): it is shared between processes and survives restarts, so restarting the service no longer resets the counters. If the database fails it falls back to an in-memory counter, so access is never left unprotected.

## [0.5.0] - 2026-10-25
### Added
- Roles granted by a provider group are now revoked when the person leaves that group (instance administrator and brain roles). Every grant is recorded with its origin: roles set by hand by an administrator, and roles that existed before, are never touched; a role raised by a group goes back to the previous one. The last active administrator is never revoked, and nothing is revoked if the provider does not send the groups claim.
- My account → Security → Linked identities: link and unlink external providers (several per person). Unlinking is refused if it would leave no way to sign in.
- Several OIDC providers at once. Administration → Identity is now a list (add, edit, test, delete); each provider has its own issuer, credentials, scopes, automatic sign-up policy and group-based roles, and its own button on the sign-in screen. New routes `/api/auth/login/{slug}` and `/api/auth/callback/{slug}`.
- The CI now runs the test suite against a real FalkorDB and a real PostgreSQL with pgvector, so those tests are no longer skipped.

### Changed
- Administration → LLM model, Embeddings and Decider: the «Add engine» button moves to the card header and the AI status is shown once (only the one for that section) instead of three times.
- Migration `0016` imports the previous single OIDC configuration (settings and `MIMIRSYNTH_OIDC_*`) as the provider `oidc`, which keeps its return URL (`/api/auth/callback`): nothing to change at your identity provider. The old settings are removed afterwards.
- Deleting a provider is refused if someone would be left with no way to sign in.

## [0.4.0] - 2026-10-25
### Changed
- Web toolchain moved to current majors: Vite 8, React 19, Mantine 9 and TypeScript 7. Node 26 for the web build stage.
- The i18n guard (`npm run i18n`) parses the sources with `oxc-parser` instead of the TypeScript compiler API.
- Release workflow actions updated (Docker buildx/QEMU/metadata/build-push v4–v7, build-provenance v4).
- Dependabot now proposes major updates, one pull request each; `graphiti-core` stays pinned.

## [0.3.1] - 2026-10-25
### Changed
- Installation uses only the official artefacts: each release attaches `docker-compose.yml` and `env.example`, and the Compose file no longer builds (`docker-compose.build.yml` is the contributor override). Documentation is written for users; building from source lives in `CONTRIBUTING.md`.

## [0.3.0] - 2026-10-25
First public release.

### Added
- Own user accounts (argon2id passwords, invitations and recovery by single-use link, lockout, first-start wizard), TOTP two-factor with recovery codes (optionally mandatory), optional SMTP email.
- OIDC sign-in as an optional, linked identity, with automatic sign-up by allowed domain and roles granted from provider groups.
- Administration reorganised into sectioned cards with side navigation; settings stored in the database and editable without a restart (secrets encrypted).
- Interface and server messages in English and Spanish, per-person and per-instance language, translated emails.
- Document memory: uploads, read-only folders and Outline wikis, hybrid search, recall integration and "promote to memory".
- Job queue with progress, cancel and retry; grouped scheduled rescans and automatic retention.
- Brains with per-brain roles, proposal quarantine with an optional decider, ontology packages, vocabulary tools (aliases, duplicates, type corrector).
- Hybrid recall (facts, episode text, documents) and API tokens for agents; Claude Code integration.
- Container image published to GHCR; Docker Compose uses it by default.

### Changed
- Documentation rewritten for users: README, `docs/` and a bilingual wiki.

### Security
- Sessions, secrets and credentials hardened (see `SECURITY.md`); the application refuses to start with the default session secret when sign-in is enabled.
