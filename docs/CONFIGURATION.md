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
- **Embeddings:** stored vectors depend on the model and its dimension. Moving to another engine with the same model (another host) is immediate with "Default". To move to another model, use **Reindex** on the new engine (see below). Agents that write directly to Graphiti on that FalkorDB must use the same model.
- **Decider:** closed-decision model (with probabilities) for proposal triage and the type corrector. It only approves what is factual with enough confidence; it never rejects on its own.

### Changing the embedding model
**Administration → Embeddings → Reindex** (on an engine with another model, after confirming) starts the *Embedding model change* job. It needs no LLM: it only computes embeddings, with the new engine, for every brain:
- in FalkorDB, in the format of graphiti-core 0.30.2: `name_embedding` of the `Entity` nodes (and of `Community` nodes, if any) and `fact_embedding` of the `RELATES_TO` edges;
- in pgvector, the episode fragments (`episode_chunks`) and document chunks (`doc_chunks`). If the dimension changes, the `embedding` columns and their HNSW indexes are recreated with the new one.

While it runs, everything keeps working with the current engine: the new vectors are written aside (shadow properties and a shadow column with its own HNSW index). Only at the end, with vector writes paused for a moment, are the new vectors swapped in and the new engine marked as the default, in a single PostgreSQL transaction. If anything fails, the graphs go back to their previous vectors and the default engine does not change. Progress, cancellation and retry are shown on the same screen; the job is resumable (after a restart or a retry it only computes what is missing or what changed in the meantime). Cancelling discards what was computed.

When it finishes, **recalibrate the minimum passage similarity** (Administration → Recall): similarities from different models are not comparable. Graphs without a brain are not reindexed.

## Accounts and security
- **Users:** Administration → Users. Sign-up by invitation (single-use link) or with a temporary password; roles, brains, disable, reset and delete.
- **Passkeys:** each person can add passkeys (WebAuthn) in My account → Security to sign in with their device's fingerprint, face or PIN, or to use as the second step after the password. A passkey requires user verification, so it counts as two-factor, including when the administrator makes two-factor mandatory. A passkey only works on the domain it was created on (the `MIMIRSYNTH_PUBLIC_URL` host); changing the domain invalidates them, so keep the password as a fallback. An administrator's «reset two-factor» on a user also removes their passkeys.
- **Account security:** minimum password length, lockout after failed attempts, link validity and **mandatory two-factor**.
- **Email (SMTP):** needed to send invitations and recover passwords by email. Without it, the administrator copies the links from the user's page.
- **Identity (OIDC):** a list of sign-in providers; you can add several, and each shows its own button on the sign-in screen. Every provider has its own issuer, Client ID, secret, scopes, automatic sign-up policy (by email domain) and group-based roles. Roles granted by a group are revoked when the person leaves the group (never those set by hand, and never the last administrator). People can link several providers to their account from My account → Security. Each one shows the return URL to register at the provider and lets you test the connection. By default only people who already have an account or invitation with the same verified email can sign in. The `MIMIRSYNTH_OIDC_*` variables and the old single-provider settings are imported once, when upgrading to 0.5, as the provider `oidc` (same return URL, `/api/auth/callback`); after that, manage them only here.
  - **Automatic sign-up:** with "Yes" and a list of **allowed domains**, anyone signing in with a *verified* email from those domains is registered automatically, as a user with no access to any brain. It is never applied to unverified emails, even if you enable "Accept unverified emails".
  - **Groups:** if your provider sends each person's groups (`groups` claim by default), you can name an **instance administrators group** and **group=brain:role** rules (e.g. `curators=docs:curator`). On sign-in the role is *granted* if the person does not already have an equal or higher one; it is never lowered or removed (removing someone from a group does not take their access away: do that under Users), and "owner" is never granted by group.

## Language
**Administration → General → Default language** sets the interface and email language for people who have not chosen one. Each person picks theirs under My account → Profile. English and Spanish are included.

## Document memory
- **Folders:** Administration → Folders registers the roots under `/sources` that brain administrators can use as sources. Under Knowledge you add sources of type folder, wiki (Outline) or uploads.
- **Limits:** maximum file size, upload part size and extracted text size (Administration → Limits).
- **Recall:** minimum similarity, passages per query and maximum time of the document search (Administration → Recall). Similarity depends on the embedding model: recalibrate it if you change it.

## System
- **Ingestion and jobs:** retries and retention periods (scheduled rescans without issues are purged after 7 days by default; the rest after 60).
- **Audit:** log of administration and access actions.
