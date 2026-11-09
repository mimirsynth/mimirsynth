**English** · [Español](Instalaci%C3%B3n)

# Installation

## Requirements
- **Docker** with Compose v2 and about **2 GB of RAM** free for the application, PostgreSQL and FalkorDB (more with the bundled Ollama).
- An **OpenAI-compatible** endpoint for **embeddings** and another for the extraction **LLM**. They can be local (Ollama, vLLM…) or from a cloud provider, and they are independent of each other. They are configured afterwards, in the setup wizard. Without them the instance starts, but proposals are not ingested and recall returns nothing.
- A free port (8000 by default).

## Install with one command
If you are new to all this, [[Your first 15 minutes]] walks you through the same installation with every question explained.

The installer checks Docker, asks two questions, generates the secrets, starts everything and opens the browser on the setup wizard. You never edit `.env`.

On **Linux** or **macOS**:
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
```
On **Windows**, in PowerShell, with [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) installed:
```powershell
irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1 | iex
```
What it does, in order:
1. **Checks Docker and Compose v2.** On Linux, if Docker is missing, it offers to install it with Docker's official script (`get.docker.com`, needs `sudo`). On macOS and Windows it points you to Docker Desktop, and starts it if it is installed but not running; on Windows, Docker Desktop needs WSL2 (`wsl --install` in a PowerShell opened as administrator).
2. **Asks where your knowledge graph lives.** *Local* (the default) starts a bundled FalkorDB next to MimirSynth. *Existing* asks for the type (FalkorDB or Neo4j), host, port, user and password of a server you already run, and checks that it answers before going on. A server on the same computer (`localhost`) is reached from the container as `host.docker.internal`. The full connection test (credentials, version, permissions) happens in the setup wizard.
3. **Offers a bundled Ollama** for embeddings and downloads `nomic-embed-text`. The image is a download of about 3.5 GB and runs on the CPU; if Ollama already runs on the computer, the installer uses it instead. On a Mac with Apple silicon, the native Ollama app is faster: it uses the GPU.
4. **Writes `docker-compose.yml` and `.env`** in `~/mimirsynth` (`%USERPROFILE%\mimirsynth` on Windows), with a random `POSTGRES_PASSWORD` and `MIMIRSYNTH_SESSION_SECRET`, the release version pinned in `MIMIRSYNTH_VERSION`, a free port (8000, or the next one) and the chosen profiles in `COMPOSE_PROFILES`, so a plain `docker compose up -d` in that folder starts the same services later.
5. **Starts the stack**, waits until `/api/health` answers, prints the address and the **first-start code**, and opens the browser.

Running it again is safe: if MimirSynth is already installed in that folder, it changes nothing and offers to upgrade with `update.sh` instead (on Linux; see [[Upgrade and backups]]). If it stops halfway, it says why and removes nothing: fix the cause ([First run](Troubleshooting#first-run)) and run it again.

### Without questions
Every answer has a flag (`--help` lists them). With `--yes` it asks nothing: the bundled FalkorDB, no Ollama unless `--ollama`, and no Docker installation unless `--install-docker`.
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash -s -- --yes --ollama
MIMIRSYNTH_GRAPH_PASSWORD='…' ./install.sh --yes --graph existing --graph-type neo4j --graph-host graph.example.com
```
In PowerShell the parameters have the same names (`-Yes`, `-Ollama`, `-Graph existing`, `-GraphType`, `-GraphHost`…). The password of an existing graph database is read from `MIMIRSYNTH_GRAPH_PASSWORD`, never from the command line. Messages follow the system language (`--lang es`), and so does the instance's default language.

### Checking the download
Each release lists the SHA-256 of its assets in its notes and in `SHA256SUMS`:
```bash
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing && bash install.sh
```

## Manual installation
The installer does nothing you cannot do by hand. These are the same steps, for when you want to control each one.

### Before you start
On a bare Linux server (e.g. a minimal Debian or Ubuntu), install `curl` and Docker and check that Compose v2 is there. On macOS or Windows, install [Docker Desktop](https://docs.docker.com/desktop/) instead.
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine with the Compose plugin
sudo usermod -aG docker "$USER" && newgrp docker      # run docker without sudo
docker compose version                                 # must answer v2.x
```

#### Preparing Ollama
If the models run on [Ollama](https://ollama.com), download them before you start:
```bash
ollama pull nomic-embed-text        # embeddings (768 dimensions, the default)
ollama pull qwen2.5:14b-instruct    # fact extraction (about 14B or more is recommended)
```
- **Ollama on the same host:** the default address, `http://host.docker.internal:11434/v1`, works without changes: the Compose file maps that name to the host, also on Linux. But on Linux Ollama only listens on `127.0.0.1` by default, and the container cannot reach it there. Make it listen on all interfaces and keep port 11434 closed to the outside with your firewall:
  ```bash
  sudo systemctl edit ollama    # add, under [Service]:  Environment="OLLAMA_HOST=0.0.0.0"
  sudo systemctl restart ollama
  ```
- **Ollama on another machine:** use its address, e.g. `http://192.168.1.20:11434/v1`.

For the choice of extraction model (size, what to expect from small models), see [[AI providers]].

### What gets installed
The `docker-compose.yml` defines (the installer writes the same one):
- **mimirsynth**: the API and the interface in a single container (unprivileged, read-only file system). It maps `host.docker.internal` to the host, so it can reach services running there (Ollama, for example).
- **postgres**: PostgreSQL with the pgvector extension (users, brains, proposals, alerts, text and document indexes).
- **falkordb** (`bundled` profile, optional): the graph engine. If you already have a FalkorDB, do not enable the profile and point `MIMIRSYNTH_FALKOR_HOST` at it.

PostgreSQL and FalkorDB **do not publish ports** outside the Compose network.

### Downloading and starting
Everything comes from the official release: a Compose file and an environment template. You do not need the source code.
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
```
Edit `.env`. The essentials:

| Variable | What to put |
|---|---|
| `POSTGRES_PASSWORD` | A password (`openssl rand -hex 32`) |
| `MIMIRSYNTH_SESSION_SECRET` | Another long random secret. **Keep it**: it signs sessions and encrypts the database secrets |

Frequent options: `MIMIRSYNTH_PORT`, `MIMIRSYNTH_PUBLIC_URL`, `MIMIRSYNTH_COOKIE_SECURE`, `MIMIRSYNTH_DEFAULT_LANGUAGE`, `MIMIRSYNTH_EMBEDDING_BASE_URL`, `MIMIRSYNTH_FALKOR_HOST`. Full list in [[Environment variables]].

> **Do not put comments at the end of a value line** in `.env` (`KEY=value  # comment`): Docker Compose would read them as part of the value.

Start it:
```bash
docker compose --profile bundled up -d
```
The first time it downloads the published image (`ghcr.io/mimirsynth/mimirsynth`, for amd64 and arm64). To pin a version, set `MIMIRSYNTH_VERSION=0.15.0` in `.env` (default: `latest`). Check that it is healthy:
```bash
docker compose ps                          # the services "healthy"
curl -s http://localhost:8000/api/health   # {"ok":true,"db":true,"graph":true,...}
```

## First start
An instance with no administrators asks for a **first-start code** on the web and prints it in its log. The installer prints it for you; after a manual installation:
```bash
docker compose logs mimirsynth | grep -A3 "FIRST START"
```
The code only exists while there is no administrator (if you lose it, restart the container to generate another).

Paste it and create the administrator account (the form ticks each password rule as you type). Then **First-run setup** opens at `/configuracion` and goes on to the first recall, one step per screen, resuming where you left it: **your account** → **graph database** (the connection test must pass) → **embeddings** (the engine must answer with the index dimension) → **LLM model** (it can be skipped, with a reminder on the home screen) → **decider** (optional) → **your first brain** → **API token** (Contributor, 90 days) → **connect your agent**. Each step is explained in [[Your first 15 minutes]]. **Set up by hand** closes it; the **Setup wizard** button at the top of Administration opens it again. While there is no brain and the wizard is closed, an administrator lands on **First steps**, with a **Create your first brain** button and links to each screen.

Anyone else without a brain sees «You do not have access to any brain yet. Ask an administrator to add you.»

## After installing
1. The models, the first brain, a token and the first agent come with the wizard; to change them later: [[AI providers]], [[Brains and members]], [[Connect agents]].
2. If you are going to expose it, put it behind HTTPS: [[HTTPS and reverse proxy]].
3. Configure email and users: [[SMTP email]], [[Administer users]].
4. Plan backups and upgrades: [[Upgrade and backups]], and monitor the instance (below).

## Monitoring the instance
MimirSynth raises alerts about the graph and the AI models itself (the bell and the notification channels), but **not about its own PostgreSQL**: alerts are stored in that database, so while it is down there is nowhere to keep them. Watch it from outside with any HTTP monitor (Uptime Kuma, Gatus, a `curl` in cron…) pointed at `GET /api/health`. It needs no sign-in and answers in under 3 seconds:

| Answer | Meaning |
|---|---|
| `200` `{"ok": true, "db": true, "graph": true, "graphs": 3}` | Everything is fine |
| `503` with `"db": false` | The application is alive but cannot reach PostgreSQL |
| `503` with `"graph": false` | The application is alive but FalkorDB does not answer |
| No answer or connection error | The application is down |
| `"secrets": "unreadable"` in the body (with any status) | The application works, but `MIMIRSYNTH_SESSION_SECRET` is not the one that sealed the stored secrets: see [[Upgrade and backups]] |

Alert on any status other than `200`; to tell the cases apart, look at `db` and `graph` in the body. Each check waits at most 2 seconds, and the cause of a failure goes to the container log (`docker compose logs mimirsynth`), never to the response. If the monitor runs on another machine, use the public address behind the reverse proxy (`https://memory.example.com/api/health`). The container's Docker health check uses the same endpoint, so `docker ps` shows it as `unhealthy` in both cases. Being public, it also reports one configuration problem, with no detail (no kinds, no counts): `"secrets": "unreadable"` when `MIMIRSYNTH_SESSION_SECRET` cannot open the stored secrets. That field does not change the status.

To see how it is doing (recall time, jobs waiting, proposals, AI engine errors), turn on the Prometheus metrics at `/metrics` under Administration → Metrics: see [[Metrics]].

## OCR for scanned PDFs and images (optional)

A scanned PDF has no text layer, and an image (`.png`, `.jpg`) is only pixels: to index them MimirSynth needs OCR. Tesseract runs in **its own container**, so the main image does not grow.
1. Start it with the `ocr` profile, alongside the others you use: `docker compose --profile ocr up -d` (add `--profile bundled` if you use the bundled FalkorDB).
2. Add `MIMIRSYNTH_OCR_URL=http://ocr:8001` to `.env` and run `docker compose up -d mimirsynth`.

Under **Knowledge**, a brain administrator sees whether OCR answers. The image reads Spanish and English; for more languages, build it with `docker build --build-arg LANGS="spa eng cat" -t mimirsynth-ocr ocr/` and point the service at it. Under Administration → Settings → Documents you choose the languages (`spa+eng`) and the maximum of pages read with OCR per document (50). The service has no authentication: do not publish its port. `update.sh` updates it along with the application.

Instead of Tesseract, a brain can read its scanned pages with the **vision model** of an LLM engine (Knowledge → *Read with the vision model*). Each page is then one call to the engine, so it is off by default. A lone image does not need the OCR service in that case, but a PDF still does, to turn its pages into images.

## Installing without the bundled FalkorDB
If you already have a FalkorDB (for example, the one of an existing Graphiti), do not use `--profile bundled`:
```bash
# in .env
MIMIRSYNTH_FALKOR_HOST=my-falkordb
MIMIRSYNTH_FALKOR_PORT=6379
# optional: adopt its graphs as brains on first start
MIMIRSYNTH_BOOTSTRAP_GRAPHS=docs:Documentation,team:Team
docker compose up -d
```
The format is `slug:Name`. It only applies on first start (when there are no brains yet). Slugs must be lowercase letters, digits and hyphens. An external FalkorDB is not part of the backups made by `update.sh`: save it yourself ([[Upgrade and backups]]).

## Installing with Neo4j
If your graphs live in Neo4j (5.26 LTS or later, Community or Enterprise), do not use `--profile bundled`:
```bash
# in .env
MIMIRSYNTH_GRAPH_BACKEND=neo4j
MIMIRSYNTH_NEO4J_URI=neo4j://my-neo4j:7687
MIMIRSYNTH_NEO4J_USER=neo4j
MIMIRSYNTH_NEO4J_PASSWORD=…
# optional: a database other than the user's default
MIMIRSYNTH_NEO4J_DATABASE=
docker compose up -d
```
Use `neo4j://`, or `neo4j+s://` with TLS: a cluster needs this routing scheme and a single server accepts it too. **Neo4j Aura** is such a cluster: `MIMIRSYNTH_NEO4J_URI=neo4j+s://<instance id>.databases.neo4j.io:7687` (not `bolt+s://`), and leave `MIMIRSYNTH_NEO4J_DATABASE` empty, since Aura names its database after the instance id and MimirSynth uses the user's default one. The installer does all this by itself with `--graph-tls` and no `--graph-database`.
All brains share that database: a brain is the nodes whose `group_id` is its name, as Graphiti writes them, and `MIMIRSYNTH_BOOTSTRAP_GRAPHS` adopts existing `group_id`s the same way. An export then carries only the graph's JSON copy, and the Cypher console only runs what it can keep inside the brain. Details and supported versions in [the configuration reference](https://github.com/MimirSynth/mimirsynth/blob/main/docs/CONFIGURATION.md#graph-database), and what keeps the brains apart, and its limits, in [Brain isolation on Neo4j](https://github.com/MimirSynth/mimirsynth/blob/main/docs/CONFIGURATION.md#brain-isolation-on-neo4j). Neo4j is not part of the backups made by `update.sh`: save it yourself.

## Development mode (no sign-in)
`MIMIRSYNTH_AUTH_MODE=off` disables sign-in and makes everyone a local administrator. **Only for development on your own machine**; never use it on a reachable server.
