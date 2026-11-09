**English** · [Español](Variables-de-entorno)

# Environment variables

The environment (`.env`) only carries **what is needed to start and connect**. Everything else is changed in [Administration](Administration-overview) and applies without a restart; if an equivalent variable exists, it only acts as the **default value** (see [[Settings reference]]).

Commented template: `env.example` in the [latest release](https://github.com/MimirSynth/mimirsynth/releases/latest) (or [`.env.example`](https://github.com/MimirSynth/mimirsynth/blob/main/.env.example) in the repository). Copy it to `.env`, which is **not committed to the repository**.

> **No comments at the end of a line.** `KEY=value  # comment` makes Docker Compose read the comment as part of the value. Put comments on their own line.

> **Only what the Compose file passes reaches the application.** The official `docker-compose.yml` lists, under the `mimirsynth` service's `environment:`, the variables it forwards from `.env`: the ones in the tables below, unless a row says otherwise. To use another `MIMIRSYNTH_*` variable (for example `MIMIRSYNTH_INGEST_CONCURRENCY`), add it there as well; writing it only in `.env` has no effect.

## Required
| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL password. Generate it with `openssl rand -hex 32` |
| `MIMIRSYNTH_SESSION_SECRET` | Signs sessions and **encrypts** the secrets stored in the database (provider keys, SMTP password, OIDC and notification channel secrets). **Keep it**; if it changes you must re-enter those secrets. The application **does not start** with the default value when sign-in is on |

## Connection and startup
| Variable | Default | Description |
|---|---|---|
| `MIMIRSYNTH_VERSION` | `latest` | Image version to run (a release tag such as `0.8.0`). Compose only; `update.sh` pins it for you ([[Upgrade and backups]]) |
| `MIMIRSYNTH_PORT` | `8000` | Host port on which the application is published. Compose only |
| `COMPOSE_PROFILES` | empty (the installer sets it) | The [profiles](#compose-profiles) a plain `docker compose up -d` starts, separated by commas, e.g. `bundled,ollama`. Read by Docker Compose, not by the application |
| `MIMIRSYNTH_DATABASE_URL` | local SQLite | Control-plane database. In production, PostgreSQL with pgvector (`postgresql+psycopg://…`). The official compose builds it from `POSTGRES_PASSWORD`: do not set it in `.env` |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | empty | Existing graphs to adopt as brains **only on first start**: `slug:Name,other:Other`. Entries with an invalid format are ignored with a warning |
| `MIMIRSYNTH_DEFAULT_GRAPH` | `default` | Default graph |
| `MIMIRSYNTH_STATIC_DIR` | — | Folder of the built web (set by the Docker image) |
| `MIMIRSYNTH_CORS_ORIGINS` | `*` | Allowed CORS origins. With `*` only `http://localhost:5173` (development) is allowed. Only needed if you serve the web from another domain. Not forwarded by the official compose |

## Graph database
Where the graph connection comes from, in this order:
1. **These variables**, when `MIMIRSYNTH_GRAPH_BACKEND`, `MIMIRSYNTH_FALKOR_HOST` or `MIMIRSYNTH_NEO4J_URI` has a value (the installer writes them when you choose an existing database). They win over the interface, which shows them read-only, and change in `.env`, with a restart.
2. **Administration → Graph database**, where an administrator enters the connection, tests it and saves it without a restart.
3. **The bundled FalkorDB** (the `bundled` profile), when neither says anything.

| Variable | Default | Description |
|---|---|---|
| `MIMIRSYNTH_GRAPH_BACKEND` | empty | `falkordb` or `neo4j` (Neo4j 5.26 or later). Empty: `neo4j` when `MIMIRSYNTH_NEO4J_URI` has a value, otherwise `falkordb` |
| `MIMIRSYNTH_FALKOR_HOST` / `_PORT` | empty / `6379` | An existing FalkorDB. Only with the `falkordb` backend |
| `MIMIRSYNTH_FALKOR_USERNAME` / `_PASSWORD` | empty | Credentials of a FalkorDB with ACL users. Only with the `falkordb` backend |
| `MIMIRSYNTH_NEO4J_URI` | empty | Neo4j address: `neo4j://host:7687`, or `neo4j+s://` with TLS (Neo4j Aura); `bolt://` connects directly to one server only. Only with the `neo4j` backend |
| `MIMIRSYNTH_NEO4J_USER` / `_PASSWORD` | `neo4j` / empty | Neo4j credentials. Only with the `neo4j` backend |
| `MIMIRSYNTH_NEO4J_DATABASE` | empty | The Neo4j database every brain lives in, each one as its own `group_id`; empty: the server's default. Only with the `neo4j` backend |
| `MIMIRSYNTH_FALKOR_BUNDLED_HOST` | `falkordb` (compose) / `localhost` | Where the bundled FalkorDB answers. Fixed by the official compose |

Changing the backend does not move the data: a brain whose graph is not in the new database looks empty until you switch back. Details, and what changes with Neo4j, in [Graph database](https://github.com/MimirSynth/mimirsynth/blob/main/docs/CONFIGURATION.md#graph-database).

## Compose profiles
The official `docker-compose.yml` has three optional services, each behind a profile. Start them with `--profile <name>` on each command, or list them once in `COMPOSE_PROFILES` in `.env` (the installer does), so a plain `docker compose up -d` starts them.

| Profile | Starts | Notes |
|---|---|---|
| `bundled` | FalkorDB | The graph database, unless another one is chosen (above) |
| `ollama` | Ollama, for the embeddings | Runs on the CPU; models live in the `ollamadata` volume. Address from the application: `http://ollama:11434/v1`. Download the model once with `docker compose exec ollama ollama pull nomic-embed-text` |
| `ocr` | The OCR service (Tesseract, Spanish and English) | Needs `MIMIRSYNTH_OCR_URL=http://ocr:8001`. See [[Document memory]] |

Neither Ollama nor the OCR service has authentication: never publish their ports.

## Access, addresses and language
| Variable | Default | Description |
|---|---|---|
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local`: own accounts (and OIDC if configured). `off`: **development only**, no sign-in, everyone is administrator |
| `MIMIRSYNTH_PUBLIC_URL` | empty | Public URL, over HTTPS in production. Used for the OIDC return URL, invitation and recovery links and **passkeys**: its domain is the passkeys' relying-party ID, so set it before anyone registers one (changing the domain later invalidates them). The MCP server also accepts browser requests only from this origin. Also editable under Administration → Identity |
| `MIMIRSYNTH_COOKIE_SECURE` | `false` | `true` if you serve over HTTPS |
| `MIMIRSYNTH_DEFAULT_LANGUAGE` | `en` | Default language (`en` or `es`) of the interface and emails for people who have not chosen one, and the last fallback for the language of API errors, MCP texts and recall headings ([[Connect agents]]). Also under Administration → General |
| `MIMIRSYNTH_ADMIN_EMAILS` | empty | Emails that become instance administrators when they first sign in through OIDC, **only with an email the provider marks as verified** |
| `MIMIRSYNTH_ACCOUNT_URL` | empty | Page of your identity provider where password, passkeys and two-factor are managed; linked from My account |
| `MIMIRSYNTH_OIDC_*` | — | **Only read once**, on the first start after upgrading to 0.5, to import the provider you had as `oidc`. After that, providers are managed in Administration → Identity and these variables can be removed |

## Default engines
Used **only if no engine is configured in the interface** ([[AI providers]]).
| Variable | Default | Description |
|---|---|---|
| `MIMIRSYNTH_EMBEDDING_BASE_URL` | `http://host.docker.internal:11434/v1` (compose) | Embeddings endpoint: by default, Ollama on the same host (the compose maps that name to the host, also on Linux); with the `ollama` profile, `http://ollama:11434/v1`. It must be the same one Graphiti uses on that graph |
| `MIMIRSYNTH_EMBEDDING_MODEL` | `nomic-embed-text` | Model |
| `MIMIRSYNTH_EMBEDDING_API_KEY` | empty | Key |
| `MIMIRSYNTH_EMBEDDING_DIM` | `768` | Model dimension |
| `MIMIRSYNTH_LLM_BASE_URL` | empty | LLM endpoint. **Empty = ingestion disabled** |
| `MIMIRSYNTH_LLM_API_KEY` | empty | Key |
| `MIMIRSYNTH_LLM_MODEL` | empty | Model |
| `MIMIRSYNTH_LLM_SMALL_MODEL` | empty | Optional small model (defaults to the same) |
| `MIMIRSYNTH_INGEST_CONCURRENCY` | `2` | Simultaneous LLM calls per ingestion. **Only read at startup** and not forwarded by the official compose (add it there); lower it if your provider limits requests |

**After changing the embedding model** from the interface (**Reindex** under Administration → Embeddings), the model lives in the interface and `MIMIRSYNTH_EMBEDDING_*` keep their old values. They only matter on a fresh installation (which creates the index with `MIMIRSYNTH_EMBEDDING_DIM`) and as the fallback when **no** engine is registered: keep an engine registered or update them to the new model and dimension.

## Documents
| Variable | Default | Description |
|---|---|---|
| `MIMIRSYNTH_SOURCES_DIR` | `./sources` | **Host** folder mounted read-only at `/sources`. Compose only |
| `MIMIRSYNTH_DOC_STORE` | `/data/documents` | Volume with the uploaded originals. **Include it in backups**. Fixed by the official compose |
| `MIMIRSYNTH_DOC_ROOTS_BASE` | `/sources` | Folder roots can only be under this path. Fixed by the official compose |
| `MIMIRSYNTH_OCR_URL` | empty | The OCR service: `http://ocr:8001` with the `ocr` profile. Empty: scanned PDFs and images are not read. See [[Document memory]] |
| `OCR_WORKERS` | `2` | Documents the OCR service reads at the same time; Tesseract uses one CPU per page. Read by the `ocr` service, not by the application |
| `MIMIRSYNTH_VERIFIERS_DIR` | (empty) | Folder with your own fact verifiers (`*.py`), loaded at start. Empty: only the built-in example. It is external code that runs with the verifiers' credentials: set it only for code you trust. See [[Verifiable facts]] |
| `MIMIRSYNTH_EXPORT_TTL_HOURS` | `24` | Hours an exported brain package waits to be downloaded before it is deleted. See [[Export a brain]] |
| `MIMIRSYNTH_IMPORT_MAX_MB` | `20480` | Largest brain package that can be uploaded to import it. See [[Import a brain]] |

## Defaults of settings (optional)
These variables exist, but are **managed from the interface**; set one only if you want a different starting value (and add it to the compose file): `MIMIRSYNTH_DOC_MAX_MB` (forwarded by the compose), `…_DOC_PART_MB`, `…_DOC_TEXT_MAX_MB`, `…_DOC_MIN_SIMILARITY`, `…_DOC_PASSAGES`, `…_DOC_SEARCH_TIMEOUT`, `…_INDEX_SYNC_MINUTES`, `…_INGEST_RETRIES`, `…_REINDEX_BATCH`, `…_REINDEX_PAUSE`, `…_REINDEX_SWITCH_WAIT`, `…_REINDEX_ORPHAN_HOURS`, `…_JOBS_KEEP_DAYS`, `…_JOBS_KEEP_SCHEDULED_DAYS`, `…_NOTIFY_*` (repeat interval, quiet hours, health checks, version check, private networks, retention), `…_PASSWORD_MIN_LENGTH`, `…_LOGIN_MAX_ATTEMPTS`, `…_LOCKOUT_MINUTES`, `…_INVITE_DAYS`, `…_REQUIRE_2FA` and the SMTP ones (`…_SMTP_*`). Full table in [[Settings reference]].
