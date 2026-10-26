# Changelog

All notable changes to MimirSynth. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/) (0.x: the API and the schema may change between minor versions).

Releases publish a container image to `ghcr.io/mimirsynth/mimirsynth` (tags `X.Y.Z`, `X.Y`, `X` and `latest`; `linux/amd64` and `linux/arm64`).

## [Unreleased]
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
