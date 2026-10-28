**English** · [Español](es/CONFIGURATION.md)

# Configuration

Configuration has two levels:

1. **Environment (`.env`):** only what is needed to start and connect. Read at startup.
2. **Interface (Administration → Settings and the other sections):** everything else. Applied without a restart; every change is recorded in the audit log. If an equivalent environment variable exists, it acts as the default, and "Restore" in the interface goes back to it.

## Environment variables
Commented template: `env.example` in the [latest release](https://github.com/MimirSynth/mimirsynth/releases/latest) (or [`.env.example`](../.env.example) in the repository).

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | – | PostgreSQL password (required) |
| `MIMIRSYNTH_SESSION_SECRET` | – | Signs sessions and encrypts the secrets stored in the database (required) |
| `MIMIRSYNTH_PORT` | `8000` | Port published on the host |
| `MIMIRSYNTH_FALKOR_HOST` / `_PORT` | `falkordb` / `6379` | FalkorDB |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | empty | Existing graphs to adopt as brains on first start (`slug:Name,other:Other`) |
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local` (own accounts, optional OIDC) or `off` (development only, no sign-in) |
| `MIMIRSYNTH_PUBLIC_URL` | empty | Public URL, for OIDC, invitation links and **passkeys** (its domain is the passkeys' relying-party ID: set it, over HTTPS, before anyone registers one) |
| `MIMIRSYNTH_COOKIE_SECURE` | `false` | `true` if you serve over HTTPS |
| `MIMIRSYNTH_EMBEDDING_*`, `MIMIRSYNTH_LLM_*` | empty | Default engines if none is configured in the interface yet |
| `MIMIRSYNTH_SOURCES_DIR` | `./sources` | Host folder mounted read-only at `/sources` |

## AI providers
Under **Administration → LLM model / Embeddings / Decider**. Each engine is an OpenAI-compatible endpoint (base URL, key and model). Keys are stored encrypted.
- **LLM model:** extracts entities and facts when proposals are ingested. For "reasoning" models that return empty JSON, use a proxy that disables *thinking*.
- **Embeddings:** model and dimension **cannot be changed** once the index exists (vectors depend on the model). It must be the same one Graphiti uses on that FalkorDB.
- **Decider:** closed-decision model (with probabilities) for proposal triage and the type corrector. It only approves what is factual with enough confidence; it never rejects on its own. It assumes no domain: it judges each proposal against the brain's scope, built from the brain's **description** (Administration → Brain access → Edit) and the entity and relation types of its ontology. A proposal that does not fit that scope goes to a curator. Without description or ontology, it only checks that the proposal is a factual statement with no instructions for the system.

### Changing the embedding model
**From the interface:** Administration → Embeddings → **Reindex** on an engine with another model shows the estimate and, after confirming, computes the vectors in shadow; a panel on the same screen shows the progress (with Cancel), unfinished shadows (Retry, Discard) and, once they are ready, **Switch to the new model**, which asks you to tick that you have backed up FalkorDB and PostgreSQL. When it finishes, it reminds you to recalibrate the minimum passage similarity and to switch the agents that write directly to Graphiti. The rest of this section describes the API behind it.

Changing to an engine with another model is done in two steps: first every vector is computed with the new engine **in shadow**, without touching the vectors in use (the default engine, the recall, ingestion and the index keep working as before), and then the vectors are **swapped** and the new engine becomes the default.
- `GET /api/embedding-engines/{id}/reindex/estimate`: an upper bound of the items (graph entities and facts, episode and document chunks), approximate calls to the engine and memory needed in FalkorDB. It uses bounded, cheap queries (a count per type and a sample of 1000 items for the text size; table statistics in PostgreSQL), stops after 5 seconds and answers `partial: true`, and the last result is reused for 5 minutes (`?refresh=true` redoes it). In PostgreSQL the space the new column and its HNSW index will take is estimated, but free disk space cannot be queried through SQL: check it yourself.
- `POST /api/embedding-engines/{id}/reindex`: starts the *Embedding model change (shadow fill)* job, resumable, with progress, cancellation and retry (`POST /api/embedding-engines/reindex/{job}/cancel|retry`). The request does not estimate anything (it only refuses if the last estimate already said there is not enough memory): the job makes the full estimate when it starts, leaves it in its log and does not go on if FalkorDB does not have that memory free with a 50 % margin. No LLM is used. In FalkorDB (graphiti-core 0.30.2 format) it fills `name_embedding_reindex` of `Entity` and `Community` nodes and `fact_embedding_reindex` of `RELATES_TO` edges, plus the source text in `*_reindex_src`; in pgvector, an `embedding_reindex vector(<new dimension>)` column with its own HNSW index (built `CONCURRENTLY`, so it does not block index writes) in `episode_chunks` and `doc_chunks`. A retry only computes what is missing or what changed in the meantime. Changes to the structure of those tables use a short `lock_timeout` and are retried, so the job never sits waiting behind the index sync.
- **Rate limits:** batch size and pause between batches in Administration → Ingestion and jobs; on a 429 the job waits for `Retry-After` (up to 5 minutes).
- **Cancel** the job or `POST /api/embedding-engines/reindex/discard` (when it is not running) removes everything auxiliary: the shadow properties in FalkorDB and the shadow column and index in PostgreSQL.
- **Unfinished shadows:** while there are shadows, a marker (`reindex_shadow`) records the engine, the state (`running`, `failed` or `ready`) and the dates, so `GET /api/embedding-engines/reindex` reports them without scanning the graph, with `orphan: true` when there are shadows and no fill is running. If a fill stays failed or stalled for longer than *Alert about a stalled model change* (24 h by default, Administration → Ingestion and jobs), the `reindex.orphan` alert is raised; it is resolved when the shadows are discarded or the fill finishes. A finished fill (`ready`) waits for the swap and does not alert.

**Swap.** `POST /api/embedding-engines/reindex/switch` with `{"backup_confirmed": true}` (a finished fill is required, and you must confirm that you have backed up FalkorDB and PostgreSQL; the confirmation is kept in the job log and the audit) starts the *Embedding model change (swap)* job:
1. It computes what changed since the fill, outside the pause.
2. It pauses vector writes (ingestion, index sync, document indexing, fact edits). New writes wait; the change waits for the ones in progress for at most *Model change wait* seconds (60 by default, Administration → Ingestion and jobs). If they do not finish, it steps back, writes go on and it tries again later (3 attempts): the change is postponed, writes are never cut off. The recall does not go through the pause (it only waits the few milliseconds of the final PostgreSQL transaction).
3. With writes paused, it completes what is left, swaps the vectors of every graph (the previous ones are kept as `*_prev`) and, in **one PostgreSQL transaction**, replaces the `embedding` columns and their HNSW indexes with the new ones (new dimension if it changed), marks the new engine as the default and removes the marker. If anything fails before that transaction commits, the graphs go back to their previous vectors and everything stays on the previous engine, with the fill ready to retry. The job log records how long writes were paused.
4. If the service dies in the middle, on the next start, **before serving**, each graph is made consistent with the default engine: if the change was not committed it goes back to the previous vectors; if it was, only the previous vectors are removed.

The single-process gate assumes the service runs as one process (as the image does). After the change, **recalibrate the minimum passage similarity** (Administration → Recall): similarities from different models are not comparable. Agents that write directly to Graphiti keep writing with the previous model until you change them: switch them to the same model.

**Your `.env` after the change.** Once the engine is switched, the model lives in Administration → Embeddings, not in the variables. `MIMIRSYNTH_EMBEDDING_DIM` (and `MIMIRSYNTH_EMBEDDING_MODEL` / `MIMIRSYNTH_EMBEDDING_BASE_URL`) keep their old values. They only matter in two cases: a fresh installation (which creates the index with that size) and the fallback used when **no** engine is registered in Administration. Keep an engine registered, and if you rely on the variables, update them to the new model and dimension.

## Accounts and security
- **Users:** Administration → Users. Sign-up by invitation (single-use link) or with a temporary password; roles, brains, disable, reset and delete.
- **Passkeys:** each person can add passkeys (WebAuthn) in My account → Security to sign in with their device's fingerprint, face or PIN, or to use as the second step after the password. A passkey requires user verification, so it counts as two-factor, including when the administrator makes two-factor mandatory. A passkey only works on the domain it was created on (the `MIMIRSYNTH_PUBLIC_URL` host); changing the domain invalidates them, so keep the password as a fallback. An administrator's «reset two-factor» on a user also removes their passkeys.
- **Account security:** minimum password length, lockout after failed attempts, link validity and **mandatory two-factor**.
- **Email (SMTP):** needed to send invitations and recover passwords by email. Without it, the administrator copies the links from the user's page.
- **Identity (OIDC):** a list of sign-in providers; you can add several, and each shows its own button on the sign-in screen. Every provider has its own issuer, Client ID, secret, scopes, automatic sign-up policy (by email domain) and group-based roles. Roles granted by a group are revoked when the person leaves the group (never those set by hand, and never the last administrator). People can link several providers to their account from My account → Security. Each one shows the return URL to register at the provider and lets you test the connection. By default only people who already have an account or invitation with the same verified email can sign in. The `MIMIRSYNTH_OIDC_*` variables and the old single-provider settings are imported once, when upgrading to 0.5, as the provider `oidc` (same return URL, `/api/auth/callback`); after that, manage them only here.
  - **Automatic sign-up:** with "Yes" and a list of **allowed domains**, anyone signing in with a *verified* email from those domains is registered automatically, as a user with the provider's **initial access** and whatever their groups grant. It is never applied to unverified emails, even if you enable "Accept unverified emails".
  - **Initial access:** brains that an automatically registered person joins, as `brain:role` separated by commas (e.g. `docs:reader, wiki:contributor`). Only `reader` and `contributor` are allowed: anyone from those domains gets it without anyone reviewing them, and what they propose follows the brain's policy (a curator or the decider). It is applied **once**, when the account is created, as an ordinary membership: an administrator can change or remove it under Users and no later sign-in restores it. If a group grants a higher role on the same brain, the higher one wins. Saving the provider refuses an entry with another role or a brain that does not exist; a brain deleted later is skipped. It does not apply to invitations, which bring their own roles.
  - **Groups:** if your provider sends each person's groups (`groups` claim by default), you can name an **instance administrators group** and **group=brain:role** rules (e.g. `curators=docs:curator`). On sign-in the role is *granted* if the person does not already have an equal or higher one, and a role that a group granted is **removed** when the person is no longer in that group (the previous role is restored, if they had one). Roles set by hand are never touched, the last administrator is never removed, and nothing is removed if the provider does not send the groups claim at all. "Owner" is never granted by group.
  - **Unverified emails:** "Accept unverified emails" exists for providers that do not mark the email as verified (Entra ID, for example), so that invitations can be accepted through them. With it, an unverified email only links to an **invitation** (an account with no credentials yet). An account that is already active is only linked automatically with a verified email; otherwise the sign-in screen asks the person to sign in as usual and link the provider from My account → Security.

## Language
**Administration → General → Default language** sets the interface and email language for people who have not chosen one. Each person picks theirs under My account → Profile. English and Spanish are included.

## Document memory
- **Folders:** Administration → Folders registers the roots under `/sources` that brain administrators can use as sources. Under Knowledge you add sources of type folder, wiki (Outline) or uploads.
- **Limits:** maximum file size, upload part size and extracted text size (Administration → Limits).
- **Recall:** minimum similarity, passages per query and maximum time of the document search (Administration → Recall). Similarity depends on the embedding model: recalibrate it if you change it.

## System
- **Ingestion and jobs:** retries and retention periods (scheduled rescans without issues are purged after 7 days by default; the rest after 60).
- **Audit:** log of administration and access actions.
