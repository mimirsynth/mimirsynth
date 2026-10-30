**English** · [Español](es/ARCHITECTURE.md)

# Architecture

MimirSynth is a memory layer for AI agents. It relies on [Graphiti](https://github.com/getzep/graphiti) (a temporal knowledge graph) on FalkorDB and adds what a graph alone does not give: users and permissions, quarantine for what agents write, hybrid recall, document memory and a web interface.

## Core idea

Facts are not overwritten: they are **invalidated** and their history is kept (bi-temporal model: when it happened and when it became known). Each memory type of the [CoALA](https://arxiv.org/abs/2309.02427) cognitive framework has its place:

| Memory | What it stores | Where |
|---|---|---|
| Episodic | What happened, immutable | Graphiti episodes, plus an index of their text in PostgreSQL (pgvector + full-text search) |
| Semantic | Entities and facts with validity dates | Graphiti on FalkorDB |
| Documents | What documents say | Chunks with vectors and full text in PostgreSQL; originals on a volume. See [DOCUMENTS.md](DOCUMENTS.md) |

## Components

```
agents / plugins ──API token──┐
browser ──────account or OIDC─┤
                              ▼
                    ┌──────────────────┐        ┌────────────────┐
                    │ MimirSynth       │───────▶│ FalkorDB       │ one graph per brain
                    │ API (FastAPI)    │        └────────────────┘
                    │ + UI (React)     │        ┌────────────────┐
                    │                  │───────▶│ PostgreSQL     │ control plane,
                    └──────────────────┘        │ + pgvector     │ text indexes
                       │        │               └────────────────┘
                       ▼        ▼
              LLM (extraction)  Embeddings   (any OpenAI-compatible endpoint)
```

- **A single container** serves the API and the interface; PostgreSQL and FalkorDB are separate services (the `docker-compose.yml` includes both).
- **Ingestion:** `graphiti-core` is used as a library inside the application, on the same FalkorDB.
- **AI providers** (LLM, embeddings and deciders) are configured in the interface, with keys encrypted in the database. Any OpenAI-compatible endpoint works (cloud, Ollama, a proxy…).

## Brains

A **brain** is an isolated knowledge domain: its graph, its ontology (entity and relation types), its text index, its members and its tokens. Everything the API does is scoped to a brain and to the authenticated user.

## Users and roles

- **Own accounts** (email and password with argon2id, lockout after failed attempts, single-use invitation and recovery links, optional email through SMTP) **TOTP two-factor** with recovery codes, which the administrator can require, and **passkeys** (WebAuthn) for passwordless sign-in or as a second step.
- **Optional OIDC, one or several providers** (Keycloak, Authentik, Entra ID, PocketID…): by default only people who already have an account or invitation can sign in; each provider can optionally allow automatic sign-up by domain and grant roles from its groups.
- **Per-brain role:** reader < contributor < curator < administrator < owner. The instance administrator sees everything.
- **API tokens** scoped to a brain, for agents and plugins; they never exceed the creator's role and do not administer the instance.
- Administration and access actions are recorded in an **audit log**.
- **Language:** the interface and emails are available in English and Spanish, chosen per person.

## Writing: proposal quarantine

What a contributor or an agent adds does not go straight into the graph. It creates a **proposal** with its author and confidence:

1. A **decider** (closed-decision model with a threshold) can automatically approve what is clearly factual. It never rejects on its own.
2. Anything doubtful waits for a **curator**, who approves or rejects. If a curator proposes, it is approved.
3. Once approved, it is **ingested** with Graphiti (extraction of entities and facts with the brain's LLM) through a queued job, with retries and progress.

### Secrets

Before a proposal is stored (from the interface, the API or `remember` over MCP) or a document is indexed, a **secret detector** looks for credentials in the text:

- **Certain:** unmistakable formats (AWS access keys, GitHub, GitLab, Slack, npm or Hugging Face tokens, Google, Stripe, SendGrid or AI provider API keys, Telegram bot tokens, PEM private keys, JWTs, `Authorization` headers and passwords inside a URL).
- **Possible:** a random-looking value assigned to a word such as `password`, `secret` or `token`. These are only flagged: entropy alone would mistake checksums, UUIDs and container IDs, which are normal content in technical documentation.

Each brain chooses what to do under Administration → Brain access → Secrets:

| Mode | Certain secrets | Possible secrets |
|---|---|---|
| **Mask** (default) | Replaced with `[secret removed: type]` before storing | Flagged |
| **Block** | The proposal is rejected (422) saying which type it is; the document is not indexed and leaves the index | Flagged |
| **Only warn** | Flagged, left untouched | Flagged |

A proposal with something flagged is neither approved by the decider nor approved on submission, even when a curator sends it: it waits for a curator's review, with the notice in its detail. In the audit log and in jobs, whatever is flagged in its title is hidden. The marker is written in the instance language, because it stays in memory. The brain's **exceptions** (one per line) turn a rule off (`rule:jwt`) or accept values matching a regular expression; an expression that would accept everything (`.*`) is rejected when saved. **Scan what is already stored** runs the detector read-only over the brain's proposals and indexed documents and shows, for each hit, the rule and the text before it, never the value: use it to measure hits and false positives before changing the policy. What is already in the graph is not scanned, and changing the policy does not reprocess what is already stored: to apply it to a document, reindex it.

Neither the audit log, the logs nor the API store or return the detected value: only the rule and its position. In documents the indexed text is masked (chunks, vectors and normalised text); **the downloadable original is not modified**. The detector (`api/mimirsynth/secretscan.py`) does not depend on the rest of the package, so a client can take it along and redact before sending.

## Reading: hybrid recall

A query combines, without calling an LLM:

1. **Facts** (current and historical) from the graph, by embedding similarity.
2. **Fragments of the original episode text**, by vectors and full text.
3. **Document passages**, with a budget and a maximum time.
4. Reciprocal rank fusion (RRF) with a recency weight, and a block with the evolution of the facts of the queried entities.

## Vocabulary

The ontology is defined per brain (standard packages in `api/mimirsynth/presets/`, see [ONTOLOGY.md](ONTOLOGY.md)). The interface lets you normalise aliases, merge duplicates, retype entities and edit relation types; every change is reversible and audited.

## Jobs

Ingestion, folder scanning and reindexing go through a general queue with progress, cancellation and retry. Scheduled rescans without issues purge themselves; the periods are changed under Administration → Settings.

## Configuration

The environment only carries what is needed to start and connect (see `.env.example`). Everything else is changed in the interface (Administration) and applies without a restart; the equivalent environment variables act as defaults. Secrets stored in the database are encrypted with a key derived from `MIMIRSYNTH_SESSION_SECRET`: if it changes, they must be entered again.

## Dependencies and licenses

MimirSynth is published under Apache-2.0. Graphiti is Apache-2.0. **FalkorDB is *source-available* (SSPL)**, not a permissive open-source license: review its terms before offering MimirSynth as a service. Graph access goes through our own layer so the engine can be replaced in the future.
