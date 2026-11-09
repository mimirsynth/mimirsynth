**English** · [Español](Soluci%C3%B3n-de-problemas)

# Troubleshooting

First, look at the state: `docker compose ps`, `docker compose logs mimirsynth --tail 100` and `curl http://localhost:8000/api/health` (`200` with `"db": true, "graph": true` means the application reaches PostgreSQL and FalkorDB; `503` says which one fails). The bell in the sidebar also lists the alerts you can see. Then look for your symptom.

## First run
The four problems that most often stop a first installation. If you are following [[Your first 15 minutes]], this is where its table sends you.

### Docker is not running
The installer says «Docker is not installed» or «Docker Desktop is not running», or a `docker` command answers `Cannot connect to the Docker daemon`.
- **Windows:** open Docker Desktop and wait until it says the engine is running. If it does not start, it usually lacks WSL2: run `wsl --install` in a PowerShell opened as administrator and restart the computer.
- **Windows, running `install.sh` inside WSL** («Docker is not available in this WSL distribution»): in Docker Desktop, turn on *Settings → Resources → WSL integration* for that distribution, or run `install.ps1` from PowerShell instead.
- **macOS:** open Docker Desktop and wait for it to start (the installer tries to start it itself).
- **Linux:** start the service with `sudo systemctl start docker` (and `sudo systemctl enable docker` so it starts with the computer). If Docker is missing, the installer offers to install it, or pass `--install-docker`. If it says your user cannot use Docker without `sudo`, it goes on with `sudo` this time; to stop needing it, run `sudo usermod -aG docker "$USER"` and sign out and in again.
- **Linux, just after the machine started** («Waiting for apt», or «apt is still in use after 300s»): the system's own updates (apt-daily, unattended-upgrades) or cloud-init hold apt for a few minutes after the first boot, and the installer waits for them before it installs Docker. If they take longer, it stops having installed nothing and names the program: wait for it to end (`systemctl status unattended-upgrades apt-daily-upgrade`) and run the installer again, or let it wait longer with `curl -fsSL …/install.sh | APT_WAIT_SECONDS=900 bash`.

Then run the installer again: it removes nothing, and picks up the configuration it already wrote.

### Ollama is not reachable from the container
The embeddings or LLM test fails with «connection refused», a timeout or «cannot be reached», and the address points at Ollama.
- **Do not use `localhost` or `127.0.0.1` in the address.** MimirSynth runs in a container, and there `localhost` is the container itself, not your computer. Use:

  | Where Ollama runs | Address |
  |---|---|
  | In the container the installer started | `http://ollama:11434/v1` |
  | On the same computer (the Ollama app or service) | `http://host.docker.internal:11434/v1` |
  | On another machine | its address, e.g. `http://192.168.1.20:11434/v1` |
- **Linux, Ollama on the same computer:** Ollama listens only on `127.0.0.1` by default, and the container cannot reach it there. Make it listen on all interfaces and keep port 11434 closed to the outside with your firewall: `sudo systemctl edit ollama`, add `Environment="OLLAMA_HOST=0.0.0.0"` under `[Service]`, then `sudo systemctl restart ollama` ([Preparing Ollama](Installation#preparing-ollama)).
- **The model is not downloaded** (the test reaches Ollama, but it answers that the model is not found): `ollama pull nomic-embed-text`, or, with the bundled Ollama, `docker compose exec ollama ollama pull nomic-embed-text` in the installation folder. The same for the LLM model.
- **The bundled Ollama is not running:** `docker compose ps` in the installation folder must list `ollama`. If it is missing, the installation was made without it: install Ollama on the computer, or add `ollama` to `COMPOSE_PROFILES` in `.env` and run `docker compose up -d`.
- **With your own `docker-compose.yml`:** on Linux the `mimirsynth` service needs `extra_hosts: ["host.docker.internal:host-gateway"]`.

### Graph connection errors
The graph database test fails, the installer warns that the server does not answer, or `/api/health` answers `"graph": false`. The test says what failed:

| Message | What to do |
|---|---|
| «… refuses the connection: check that the server is running and listens on that port» | The server is down or listens elsewhere. With the bundled FalkorDB, `docker compose ps` must show `falkordb` healthy and `.env` must include `bundled` in `COMPOSE_PROFILES`; `docker compose logs falkordb` says why it stopped. With your own server, check the port: 6379 for FalkorDB, 7687 (Bolt) for Neo4j |
| «… does not answer in time: check the address, the port and the firewall» | A firewall drops the connection, or the address is wrong. A server on the same computer is `host.docker.internal`, never `localhost`; on Linux it must listen on an address the containers reach, not only on `127.0.0.1` |
| «The server «…» cannot be found: check the name» | The name does not resolve from the container. Use an IP address or `host.docker.internal` |
| «The server rejects the user or the password» | Wrong credentials. Neo4j's user is usually `neo4j` |
| «The user cannot write: MimirSynth needs read and write permission» | Give that user write access, or use another one |
| «The server has no database «…»» | Neo4j: leave the database empty to use the user's default, or create it. On Neo4j Aura the database is named after the instance id, not `neo4j`. With `bolt://` or `bolt+s://` a cluster such as Aura answers this for every database: use `neo4j+s://` |
| «The server cannot find this user's default database» | The address uses `bolt://` or `bolt+s://` and the server is a cluster, such as Neo4j Aura: use `neo4j+s://` (`neo4j://` without TLS). An instance installed by 0.15.0-rc.1 has `bolt+s://` in `.env`: change it and run `docker compose up -d` |
| «… answers, but the servers it gives for routing cannot be reached» | A Neo4j cluster gives addresses (its advertised address, `server.default_advertised_address`) that the container does not reach. Fix them on the server or, with a single server, connect with `bolt://` |
| «… is not supported: … or later is needed» | MimirSynth needs FalkorDB 4.0 or later, or Neo4j 5.26 or later |
| «… is a Redis server without the graph module: FalkorDB is needed» | The port belongs to a plain Redis. Point at a FalkorDB |
| «… accepts the connection but does not answer as …» | It is another service's port, or the server expects TLS: tick **Encrypted connection (TLS)** |

After the installation, the connection is changed under **Administration → Graph database**, which tests it before saving. If that page says the connection comes from the environment variables, change it in `.env` and run `docker compose up -d`.

### Embedding dimension mismatch
The setup wizard says «text-embedding-3-small gives 1536 dimensions and the index has 768», saving the first embedding engine fails with «the text index has 768 dimensions and this model gives 1536», an engine's **Test** answers «dimension 1024, expected 768», or editing one answers «the endpoint returns a different dimension for that model».

Each embedding model gives vectors of a fixed size, its **dimension**, and the index where MimirSynth searches texts is created on the first start with the size in `MIMIRSYNTH_EMBEDDING_DIM`: 768 by default, the size of `nomic-embed-text`. A model of another size does not fit in it.
- **The simplest fix:** use a 768-dimension model, such as `nomic-embed-text`.
- **In the setup wizard, with the memory still empty:** add the engine with the model you want under Administration → Embeddings and switch to it with **Reindex**, as the wizard says; with nothing stored it takes seconds. Then go back to the wizard (the **Setup wizard** button at the top of Administration) and press **Next**.
- **A new installation, before the first start or without the wizard**, and you want another model: set `MIMIRSYNTH_EMBEDDING_MODEL` and `MIMIRSYNTH_EMBEDDING_DIM` (for example `1536` for `text-embedding-3-small`) in `.env`, then run `docker compose down -v` and `docker compose up -d` in the installation folder. **`down -v` deletes all the data**, the administrator account included: do it only on an installation you have just made. A new first-start code appears in the log.
- **An instance that already has memory:** never change the model by hand. Add an engine with the new model and move everything to it with **Reindex** under Administration → Embeddings, which recomputes every vector before switching ([Changing the embedding model](AI-providers#changing-the-embedding-model)).
- **«the endpoint returns a different dimension»:** the model behind that name changed at the provider (for example, another tag pulled in Ollama). Go back to the model you had, or reindex to a new engine.

## Startup and installation
| Symptom | Cause and solution |
|---|---|
| `define POSTGRES_PASSWORD` / `define MIMIRSYNTH_SESSION_SECRET` | They are missing from `.env`. Set them |
| The application stops on start with an error about `MIMIRSYNTH_SESSION_SECRET` | With sign-in on, the default secret is not accepted: set a random one |
| «The instance's secret key does not open the stored secrets» in Administration, or «A stored secret cannot be read» on an action | `MIMIRSYNTH_SESSION_SECRET` is not the one the database was sealed with (a restore on another host, a copy for a test stack, an edited `.env`). Put the right one back and restart; if it is lost, see [[Upgrade and backups]] |
| Brains with odd names appear on first start | A trailing comment on the `MIMIRSYNTH_BOOTSTRAP_GRAPHS` line in `.env`. Remove line-end comments ([[Environment variables]]) |
| A variable in `.env` has no effect | The official compose only forwards the variables it lists under `environment:`. Add it there ([[Environment variables]]) |
| `bind: address already in use` | Port 8000 is taken: change `MIMIRSYNTH_PORT` |
| A service "unhealthy" | `docker compose logs <service>`. PostgreSQL/FalkorDB take a few seconds; if it persists, check memory and disk space. The application is also marked unhealthy while it cannot reach PostgreSQL or FalkorDB |
| Embeddings or the LLM fail with a connection error, with Ollama | See [Ollama is not reachable from the container](#ollama-is-not-reachable-from-the-container) |
| I cannot find the first-start code | It only appears while there are no administrators; restart the container to generate a new one |
| The only administrator lost access | In the database, set `is_admin = false` for that user and restart: the first-start wizard returns |
| An update did not verify | `update.sh` tells you how to go back: `./update.sh --rollback` (add `--with-db` to restore the database too). See [[Upgrade and backups]] |

## Signing in
| Symptom | Cause and solution |
|---|---|
| "Incorrect email or password, or account temporarily locked" | Wrong password, disabled account or locked after several attempts. Wait out the lockout time or ask an administrator to unlock it |
| "Too many attempts" | IP/account limit; wait a few minutes |
| The password is not accepted when creating or changing it | The form lists every rule (minimum length, not your email or name, not common or a sequence, at least 5 different characters) and ticks the ones you meet; the disabled button says what is missing |
| The session is lost on reload (with HTTPS) | Use `MIMIRSYNTH_COOKIE_SECURE=true` only if you serve over HTTPS; and a correct `MIMIRSYNTH_PUBLIC_URL` |
| Passkeys are not offered or fail | They need HTTPS and the domain of `MIMIRSYNTH_PUBLIC_URL`; a passkey created on another domain does not work. Sign in with your password and register a new one ([[Security and two-factor]]) |
| The recovery email does not arrive | SMTP not configured, or request limit. See [[SMTP email]] |
| The invitation link "is not valid or has expired" | Used, expired (7 days) or replaced by a newer one: generate another ([[Administer users]]) |
| It asks for a 6-digit code and I cannot | Use a recovery code or a passkey, or have an administrator reset your two-factor |
| OIDC says you already have an account and must link the provider | The provider did not mark your email as verified, so it is not linked to an active account automatically. Sign in as usual and link the provider from My account → Security |
| The OIDC button fails | See the table in [[OIDC identity]] |

## Memory
| Symptom | Cause and solution |
|---|---|
| Approved proposals not ingested ("Approved") | No LLM configured: [[AI providers]] |
| **Failed** ingestions with "rate limit" | Your provider limits requests. Raise the retries ([[Recall and ingestion]]) and, if needed, lower `MIMIRSYNTH_INGEST_CONCURRENCY` (add it to the compose file); retry from [[Proposals]] |
| Failed ingestions with invalid JSON or empty answers | A "reasoning" model that does not return JSON. Use another model or a proxy that disables *thinking* |
| Malformed entities, entities missing, facts in English for a text in another language | The extraction model is too small (4B or less). Use one of about 14B or more, or a small API model with structured output ([[AI providers]]) |
| The proposal is ingested but produces 0 facts | Text with no concrete information, or failed extraction: check the [[Journal]] and [[Writing good memory]] |
| A proposal is rejected with `422` and a secret type | The brain **blocks** secrets. Remove the credential and write where it is kept instead |
| A curator's proposal stays pending | It contains a possible secret: a flagged proposal always waits for a person's review ([[Proposals]]) |
| Recall returns nothing | Empty brain, embeddings down or index not synchronised. [[Ask]]: look at the index status and "Reindex now" |
| Recall brings no document passages after changing the embedding model | Similarities of different models are not comparable: recalibrate "Minimum similarity of a passage" (Administration → Recall). Reference queries can simulate other thresholds |
| Embedding dimension errors | See [Embedding dimension mismatch](#embedding-dimension-mismatch) |
| A model change is left half-way (`reindex.orphan` alert) | A shadow fill failed or stalled. In Administration → Embeddings, **Retry** or **Discard** it; discarding frees the memory it uses |
| An "AI model not responding" alert that solves itself | The health check alerts after 2 consecutive failures by default ("Consecutive failures before alerting", Administration → Notifications). Raise it if your provider has frequent one-off errors |
| "text index disabled" | The instance has no PostgreSQL with pgvector (e.g. development SQLite) |

## Documents
| Symptom | Cause and solution |
|---|---|
| A document stays "with error" | Hover the state or open the detail to see the reason. Causes: excessive size, PDF without text, embeddings down, or a secret when the brain blocks them |
| A document appears as **duplicate** | Its text repeats one already indexed in the brain, so it is not indexed twice; the detail links to the original. If the original goes away, the oldest duplicate is indexed in its place ([[Knowledge]]) |
| Upload fails with large files | Your proxy limits request size: lower "Size of each part" ([[Folders and limits]]) |
| "No authorised folders" | The instance administrator must register roots in [[Folders and limits]] |
| A scheduled scan fails with an empty folder | Protection: the volume was probably unmounted. Check the mount. A manual scan does empty the index |
| A wiki "cuts" the scan halfway | Expired key, outage or the wiki's rate limit. Nothing is deleted; check the key and rescan |

## Agents
| Symptom | Cause and solution |
|---|---|
| The MCP server answers `401` | The `Authorization: Bearer mst_…` header is missing or the token is not valid. MCP accepts only API tokens, never the browser session |
| The MCP server answers `403` "origin not allowed" | The request came from a web page of another origin. Agent clients do not send one; if you proxy it, do not add an `Origin` header |
| `remember` says the token can only read | The token has the reader role: create a contributor one ([[Connect agents]]) |
| Error messages come in another language | They follow `Accept-Language`, then the token owner's language, then the instance's. Send `Accept-Language` or compare status codes |

## Monitoring
| Symptom | Cause and solution |
|---|---|
| No alert arrived when PostgreSQL went down | It cannot alert about itself: alerts are stored there. Watch `/api/health` with an external monitor ([Monitoring the instance](Installation#monitoring-the-instance)) |

## Performance
- **Slow ingestion:** depends on the LLM. A faster model or more concurrency (if your provider allows it) speeds it up.
- **Slow interface with lots of data:** use filters and dates in [[Facts]] and reduce the "seeds" of the [[Graph]].
- **Slow graph (3D, no GPU):** set **Graphic effects** to **Reduced** on the [[Graph]] screen (it is stored per device), or go back to 2D.
- **Growing disk:** check the documents volume and the [[Jobs]] retention.

## How to ask for help
Open an [issue](https://github.com/MimirSynth/mimirsynth/issues) with: MimirSynth version, what you expected and what happened, and the steps to reproduce. **Check that logs contain no secrets** before pasting them. For vulnerabilities, use the [private security advisory](https://github.com/MimirSynth/mimirsynth/security/advisories/new), not a public issue.
