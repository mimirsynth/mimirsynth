**English** · [Español](Instalaci%C3%B3n)

# Installation

## Requirements
- **Docker** with Compose v2 and about **2 GB of RAM** free for the application, PostgreSQL and FalkorDB.
- An **OpenAI-compatible** endpoint for **embeddings** and another for the extraction **LLM**. They can be local (Ollama, vLLM…) or from a cloud provider, and they are independent of each other. They are configured afterwards, in the interface. Without them the instance starts, but proposals are not ingested and recall returns nothing.
- A free port (8000 by default).

## Before you start
On a bare Linux server (e.g. a minimal Debian or Ubuntu), install `curl` and Docker and check that Compose v2 is there. On macOS or Windows, install [Docker Desktop](https://docs.docker.com/desktop/) instead.
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine with the Compose plugin
sudo usermod -aG docker "$USER" && newgrp docker      # run docker without sudo
docker compose version                                 # must answer v2.x
```

### Preparing Ollama
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

## What gets installed
The `docker-compose.yml` defines:
- **mimirsynth**: the API and the interface in a single container (unprivileged, read-only file system). It maps `host.docker.internal` to the host, so it can reach services running there (Ollama, for example).
- **postgres**: PostgreSQL with the pgvector extension (users, brains, proposals, alerts, text and document indexes).
- **falkordb** (`bundled` profile, optional): the graph engine. If you already have a FalkorDB, do not enable the profile and point `MIMIRSYNTH_FALKOR_HOST` at it.

PostgreSQL and FalkorDB **do not publish ports** outside the Compose network.

## Steps
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
The first time it downloads the published image (`ghcr.io/mimirsynth/mimirsynth`, for amd64 and arm64). To pin a version, set `MIMIRSYNTH_VERSION=0.10.0` in `.env` (default: `latest`). Check that it is healthy:
```bash
docker compose ps                          # the services "healthy"
curl -s http://localhost:8000/api/health   # {"ok":true,"db":true,"graph":true,...}
```

## First start
An instance with no administrators prints an **installation code** in its log and shows a wizard on the web:
```bash
docker compose logs mimirsynth | grep -A3 "FIRST START"
```
The code only exists while there is no administrator (if you lose it, restart the container to generate another). Open the application, paste it and create the administrator account. The password fields list every rule and tick them as you type.

Then you land on **First steps**: while no brain exists, an administrator sees a **Create your first brain** button and a short checklist (AI models, API token, connecting an agent) with a link to each screen. Anyone else without a brain sees «You do not have access to any brain yet. Ask an administrator to add you.»

## After installing
1. Configure the models: [[AI providers]].
2. Create a brain: [[Brains and members]].
3. Create an API token and connect your first agent: [[Connect agents]].
4. If you are going to expose it, put it behind HTTPS: [[HTTPS and reverse proxy]].
5. Configure email and users: [[SMTP email]], [[Administer users]].
6. Plan backups and upgrades: [[Upgrade and backups]], and monitor the instance (below).

## Monitoring the instance
MimirSynth raises alerts about the graph and the AI models itself (the bell and the notification channels), but **not about its own PostgreSQL**: alerts are stored in that database, so while it is down there is nowhere to keep them. Watch it from outside with any HTTP monitor (Uptime Kuma, Gatus, a `curl` in cron…) pointed at `GET /api/health`. It needs no sign-in and answers in under 3 seconds:

| Answer | Meaning |
|---|---|
| `200` `{"ok": true, "db": true, "graph": true, "graphs": 3}` | Everything is fine |
| `503` with `"db": false` | The application is alive but cannot reach PostgreSQL |
| `503` with `"graph": false` | The application is alive but FalkorDB does not answer |
| No answer or connection error | The application is down |

Alert on any status other than `200`; to tell the cases apart, look at `db` and `graph` in the body. Each check waits at most 2 seconds, and the cause of a failure goes to the container log (`docker compose logs mimirsynth`), never to the response. If the monitor runs on another machine, use the public address behind the reverse proxy (`https://memory.example.com/api/health`). The container's Docker health check uses the same endpoint, so `docker ps` shows it as `unhealthy` in both cases.

To see how it is doing (recall time, jobs waiting, proposals, AI engine errors), turn on the Prometheus metrics at `/metrics` under Administration → Metrics: see [[Metrics]].

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

## Development mode (no sign-in)
`MIMIRSYNTH_AUTH_MODE=off` disables sign-in and makes everyone a local administrator. **Only for development on your own machine**; never use it on a reachable server.
