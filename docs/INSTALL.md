**English** · [Español](es/INSTALL.md)

# Installation

## Requirements
- Docker with Compose v2 and about 2 GB of free RAM for the application, PostgreSQL and FalkorDB.
- An **OpenAI-compatible** endpoint for **embeddings** (e.g. [Ollama](https://ollama.com) with `nomic-embed-text`) and another for the **LLM** that extracts facts ([which model](CONFIGURATION.md#choosing-the-extraction-model)). They can be local or from a cloud provider, and are configured afterwards in the interface. Without them the instance starts, but there is nothing useful to see: proposals are not ingested and recall returns nothing.

## Before you start
On a bare Linux server (e.g. a minimal Debian or Ubuntu), install `curl` and Docker, and check that Compose v2 is there. On macOS or Windows, install [Docker Desktop](https://docs.docker.com/desktop/) instead.
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh    # Docker Engine with the Compose plugin, under a minute
sudo usermod -aG docker "$USER" && newgrp docker    # run docker without sudo
docker compose version    # must answer v2.x
```

### Preparing Ollama
If the models run on [Ollama](https://ollama.com), download them before you start:
```bash
ollama pull nomic-embed-text        # embeddings (768 dimensions, the default)
ollama pull qwen2.5:14b-instruct    # fact extraction: see "Choosing the extraction model" in CONFIGURATION.md
```
- **Ollama on the same host:** the default address, `http://host.docker.internal:11434/v1`, works without changes; the Compose file maps that name to the host, also on Linux. But on Linux Ollama only listens on `127.0.0.1` by default, and the container cannot reach it there. Make it listen on all interfaces and keep port 11434 closed to the outside with your firewall:
  ```bash
  sudo systemctl edit ollama    # add, under [Service]:  Environment="OLLAMA_HOST=0.0.0.0"
  sudo systemctl restart ollama
  ```
- **Ollama on another machine:** use its address, e.g. `http://192.168.1.20:11434/v1`.

## First installation
Everything comes from the official release: a Compose file and an environment template. You do not need the source code.
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL  https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
```
Edit `.env` and set at least `POSTGRES_PASSWORD` and `MIMIRSYNTH_SESSION_SECRET` (generate both with `openssl rand -hex 32`). Then:
```bash
docker compose --profile bundled up -d
```
This pulls the official image (`ghcr.io/mimirsynth/mimirsynth`, for amd64 and arm64). To pin a version, set `MIMIRSYNTH_VERSION=0.10.0` in `.env` (default: `latest`).
- `--profile bundled` also starts a bundled FalkorDB. If you already have one, omit the profile and put its address in `MIMIRSYNTH_FALKOR_HOST`.
- The application is available at `http://localhost:8000` (change the port with `MIMIRSYNTH_PORT`).

> Do not put comments at the end of a value line in `.env` (`KEY=value # comment`): Docker Compose would read them as part of the value.

### First-start wizard
An instance with no administrators prints an **installation code** in its log:
```bash
docker compose logs mimirsynth | grep -A3 "FIRST START"
```
Open the application, enter the code and create the administrator account. Keep `MIMIRSYNTH_SESSION_SECRET` safe: if you lose or change it, the stored secrets (provider keys, SMTP password, OIDC secret) can no longer be decrypted and must be entered again.

### First steps
1. Under **Administration → LLM model** and **Embeddings**, add an engine (endpoint, key and model) and mark it as default. "Test" checks that it responds.
2. Create a **brain** (Administration → Brain access → Create brain) and, if you like, apply an ontology package under Vocabulary → Ontology.
3. Create an API token for your agents and connect the first one: see [AGENTS.md](AGENTS.md).
4. Optional: SMTP email (invitations and password recovery), OIDC, mandatory two-factor and document folders. See [CONFIGURATION.md](CONFIGURATION.md).

## HTTPS and reverse proxy
Do not expose port 8000 to the Internet without TLS. Put a reverse proxy (Caddy, Traefik, nginx…) in front, set `MIMIRSYNTH_PUBLIC_URL` to the public address and `MIMIRSYNTH_COOKIE_SECURE=true`. If you upload large files, check the proxy's request-size limit: uploads are sent in parts (64 MB by default).

PostgreSQL and FalkorDB do not publish ports outside the Compose network. Do not expose them.

## Upgrading
The release includes an update script that makes the backup, updates and checks in one go:
```bash
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/update.sh && chmod +x update.sh
./update.sh              # latest stable release; ./update.sh --check only reports; --version 0.7.1 picks one
```
It does, in this order:
1. **Downloads** the new image first, so a wrong version or no network stops everything before touching anything.
2. **Backs up** PostgreSQL, the `docstore` volume, the bundled FalkorDB (if you use `--profile bundled`) and your `docker-compose.yml` and `.env` into `./backup`. **Only one backup is kept**: the previous one is replaced once the new one has been written and checked, so backups never pile up.
3. **Updates**: pins `MIMIRSYNTH_VERSION` in `.env` and recreates only the application (migrations run on start). It adopts the release's `docker-compose.yml` only if yours is the unmodified one of the version you were running; otherwise it keeps yours and tells you (`--update-compose` forces it, `--keep-compose` never touches it).
4. **Checks** that it answers with the new version and is healthy, and shows the database revision. If it does not verify, it tells you how to go back.

To go back: `./update.sh --rollback` puts back the previous `docker-compose.yml` and `.env` (and with them the previous image), keeping the failed ones as `*.rolledback`; add `--with-db` to restore the database too (anything written since the backup is lost). The rollback does not restore the documents volume or FalkorDB (they are in the backup, to restore by hand if needed), and an external FalkorDB is not part of the backup at all: save it yourself. Without the script, the manual way is `docker compose pull` and `docker compose --profile bundled up -d`, after a backup.

## Backups
Three things must be saved, and they must be consistent with each other:
- **PostgreSQL** (users, brains, proposals, indexes): `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql`
- **The `docstore` volume** (originals of uploaded documents, wiki page snapshots and the extracted text of every document).
- **FalkorDB** (the knowledge): the `graphdata` volume, or a dump with `redis-cli --rdb`.
Also save your `.env`.

Restoring is the reverse path: start the services, restore the database (`psql`) and put the volumes back. The episode text index can be rebuilt from the graph and the document index from the originals.

This copies the whole instance. A single brain can be exported to a package from Administration → Brain access → Export; see «Export a brain» in the wiki.

## Monitoring the instance
MimirSynth alerts about the graph and the AI models itself ([NOTIFICATIONS.md](NOTIFICATIONS.md)), but **not about its own PostgreSQL**: alerts are stored in that database, so while it is down there is nowhere to keep them. Watch it from outside with any HTTP monitor (Uptime Kuma, Gatus, a `curl` in cron…) pointed at `GET /api/health`. It needs no sign-in and answers in under 3 seconds:

| Answer | Meaning |
|---|---|
| `200` `{"ok": true, "db": true, "graph": true, "graphs": 3}` | Everything is fine |
| `503` with `"db": false` | The application is alive but cannot reach PostgreSQL |
| `503` with `"graph": false` | The application is alive but FalkorDB does not answer |
| No answer or connection error | The application is down |

Alert on any status other than `200`; to tell the cases apart, check `db` and `graph` in the body. Each check waits at most 2 seconds, and the cause of a failure goes to the container log (`docker compose logs mimirsynth`), never to the response. If the monitor runs on another machine, use the public address behind the reverse proxy (`https://memory.example.com/api/health`). The container's Docker health check uses the same endpoint, so `docker ps` shows it as `unhealthy` in both cases.

## Contributing
Building from source is for contributors: see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Common problems
- **"define POSTGRES_PASSWORD" or "define MIMIRSYNTH_SESSION_SECRET" on start:** they are missing from `.env`.
- **Approved proposals stay "approved":** no LLM is configured. Add an engine under Administration → LLM model.
- **Embeddings fail with a connection error, with Ollama on the same Linux host:** Ollama is only listening on `127.0.0.1`; see [Preparing Ollama](#preparing-ollama). If you use your own `docker-compose.yml`, check that the `mimirsynth` service has `extra_hosts: ["host.docker.internal:host-gateway"]`.
- **Recall returns nothing:** check the embeddings (Administration → Embeddings → Test) and that the text index is synchronised (the Ask tab shows its status).
- **No alert arrived when PostgreSQL went down:** it cannot alert about itself. Watch it with an external monitor: see [Monitoring the instance](#monitoring-the-instance).
- **I cannot find the installation code:** it only appears while there is no administrator. Restart the container so it generates a new one.
- **The only administrator lost access:** with access to the server, set `is_admin = false` for that user in the `users` table and restart the container: the first-start wizard will reappear with a new code.
