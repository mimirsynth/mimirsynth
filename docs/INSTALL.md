**English** · [Español](es/INSTALL.md)

# Installation

## Requirements
- Docker with Compose v2 and about 2 GB of free RAM for the application, PostgreSQL and FalkorDB.
- An **OpenAI-compatible** endpoint for **embeddings** (e.g. [Ollama](https://ollama.com) with `nomic-embed-text`) and another for the **LLM** that extracts facts ([which model](CONFIGURATION.md#choosing-the-extraction-model)). They can be local or from a cloud provider, and are configured afterwards in the interface. Without them the instance starts, but there is nothing useful to see: proposals are not ingested and recall returns nothing.

## Install with one command
The installer checks Docker, asks two questions, generates the secrets, starts everything and opens the browser on the first-start wizard. You never edit `.env`.

On **Linux** or **macOS**:
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
```
On **Windows**, in PowerShell, with [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) installed:
```powershell
irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1 | iex
```
What it does, in order:
1. **Checks Docker and Compose v2.** On Linux, if Docker is missing, it offers to install it with Docker's official script (`get.docker.com`, needs `sudo`). On a machine that has just started, it first waits while the system's own updates (apt-daily, unattended-upgrades) or cloud-init are using apt, saying which program holds it, for up to 5 minutes (`APT_WAIT_SECONDS`). On macOS and Windows it points you to Docker Desktop, and starts it if it is installed but not running; on Windows, Docker Desktop needs WSL2 (`wsl --install` in a PowerShell opened as administrator).
2. **Asks where your knowledge graph lives.** *Local* (the default) starts a bundled FalkorDB next to MimirSynth. *Existing* asks for the type (FalkorDB or Neo4j), host, port, user and password of a server you already run, and checks that it answers. Before starting anything it then runs the full connection test, the same one as Administration → Graph database (address, TLS, credentials, version, write permission and the graphs it already holds), from a MimirSynth container, so it reaches the server as MimirSynth will. If the test fails, it says which step and why and asks again; without questions it stops and leaves nothing installed. Neo4j is reached with `neo4j://`, or `neo4j+s://` with `--graph-tls`: the routing scheme, which a cluster such as Neo4j Aura needs and a single server accepts too (`--graph-scheme bolt` asks for a direct `bolt://` connection instead). The test tries the same address that goes into `.env`. With no `--graph-database` it uses the user's default database and names it: on Neo4j Aura that database is named after the instance id, not `neo4j`, and the installer finds it by itself. A server on the same computer (`localhost`) is reached from the container as `host.docker.internal`; on Linux it must listen on an address the containers reach, not only on `127.0.0.1`. The connection goes into `.env`, which wins over the interface: Administration → Graph database shows it read-only, and it changes in `.env` with a restart.
3. **Offers a bundled Ollama** for embeddings (the `ollama` profile) and downloads `nomic-embed-text`. The image is a download of about 3.5 GB and runs on the CPU; if Ollama already runs on the computer, the installer uses it instead. On a Mac with Apple silicon, the native Ollama app is faster: it uses the GPU.
4. **Writes `docker-compose.yml` and `.env`** in `~/mimirsynth` (`%USERPROFILE%\mimirsynth` on Windows), with a random `POSTGRES_PASSWORD` and `MIMIRSYNTH_SESSION_SECRET`, the release version pinned in `MIMIRSYNTH_VERSION`, a free port (8000, or the next one) and the chosen profiles in `COMPOSE_PROFILES`, so a plain `docker compose up -d` in that folder starts the same services later.
5. **Starts the stack**, waits until `/api/health` answers, prints the address and the **first-start code**, and opens the browser. If the started instance cannot use an existing graph database, it ends with an error instead: MimirSynth stays started, and the message says to fix the connection in `.env` and run `docker compose up -d`.

Running it again is safe: if MimirSynth is already installed in that folder, it changes nothing and offers to upgrade with `update.sh` instead (on Linux; see [Upgrading](#upgrading)).

### Without questions
Every answer has a flag, for scripts and automation (`--help` lists them). With `--yes` it asks nothing: the bundled FalkorDB, no Ollama unless `--ollama`, and no Docker installation unless `--install-docker`.
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash -s -- --yes --ollama
MIMIRSYNTH_GRAPH_PASSWORD='…' ./install.sh --yes --graph existing --graph-type neo4j --graph-host graph.example.com
# Neo4j Aura: the host from its connection URI, with TLS, and no database (the installer finds the instance's own)
MIMIRSYNTH_GRAPH_PASSWORD='…' ./install.sh --yes --graph existing --graph-type neo4j --graph-host abcd1234.databases.neo4j.io --graph-tls
```
In PowerShell the parameters have the same names (`-Yes`, `-Ollama`, `-Graph existing`, `-GraphType`, `-GraphHost`, `-GraphPort`, `-GraphUser`, `-GraphDatabase`, `-GraphTls`, `-GraphScheme`, `-SkipGraphCheck`, `-Dir`, `-Port`, `-Version`, `-Lang`, `-NoBrowser`, `-NoStart`):
```powershell
& ([scriptblock]::Create((irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1))) -Yes -Ollama
```
The password of an existing graph database is read from `MIMIRSYNTH_GRAPH_PASSWORD`, never from the command line, so it does not stay in the shell history. Messages are in English or Spanish, following the system language (`--lang es`); the instance's default language follows them.

Neo4j needs a release after 0.14.0. With an older one the installer cannot run the full test before the start (it says so and only checks that the server answers), writes the connection to `.env`, and the instance only talks to FalkorDB.

### Checking the download
Each release lists the SHA-256 of its assets in its notes and in `SHA256SUMS`. To check the installer before running it:
```bash
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing && bash install.sh
```

## Manual installation
The installer does nothing you cannot do by hand. These are the same steps, for when you want to control each one.

### Before you start
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

### Downloading and starting
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
This pulls the official image (`ghcr.io/mimirsynth/mimirsynth`, for amd64 and arm64). To pin a version, set `MIMIRSYNTH_VERSION=0.15.0` in `.env` (default: `latest`).
- `--profile bundled` also starts a bundled FalkorDB, which is the one used unless you choose another. If you already have a FalkorDB or a Neo4j, omit the profile and enter it in **Administration → Graph database** after the first start, or set it in `.env` (see [Graph database](CONFIGURATION.md#graph-database)).
- The application is available at `http://localhost:8000` (change the port with `MIMIRSYNTH_PORT`).

> Do not put comments at the end of a value line in `.env` (`KEY=value # comment`): Docker Compose would read them as part of the value.

## First-start wizard
An instance with no administrators prints a **first-start code** in its log (the installer shows it for you):
```bash
docker compose logs mimirsynth | grep -A3 "FIRST START"
```
Open the application, enter the code and create the administrator account. Keep `MIMIRSYNTH_SESSION_SECRET` safe: it encrypts the stored secrets (provider keys, SMTP password, OIDC secret, two-factor seeds…), so a restore on another host or a copy of the database for a test stack needs the **same** value. With another one the application still starts, but says so: one line in its log, a notice at the top of Administration and `"secrets": "unreadable"` in `/api/health`; whatever needs those secrets answers with a clear error. Put the right value back and restart. If it is lost, enter those secrets again and remove two-factor from the affected accounts (Administration → Users); the notice goes once nothing is left unread.

## First steps: the setup wizard
Once the administrator exists, the **setup wizard** opens by itself and takes you, step by step, to your agent's first recall:
1. **Graph database:** the one in use (the bundled FalkorDB, or the one the installer set), with its test, changing it, and adopting graphs that are already there.
2. **Embeddings:** it looks for a local Ollama (the bundled one, your computer's), can download `nomic-embed-text`, or takes an OpenAI-compatible service.
3. **LLM** (extracts facts from what agents propose) and **decider** (approves clearly factual proposals by itself): both can be skipped. Without an LLM, approved proposals wait and the home screen says so until you add one.
4. **Your first brain**, an **API token** for your agent (Contributor role, shown once), and **connecting your agent**, which turns green when it makes its first recall.

The graph and embedding steps cannot be skipped: «Next» asks the server to check them. Every step is kept as you pass it, so you can leave at any point and the wizard picks up where you left off, on any device; «Set up by hand» leaves it for good. An administrator can open it again from **Administration → Setup wizard**. An instance that already had brains before this version does not open it by itself.

Then, if you like: apply an ontology package under Vocabulary → Ontology, and set up SMTP email (invitations and password recovery), OIDC, mandatory two-factor and document folders. See [CONFIGURATION.md](CONFIGURATION.md) and [AGENTS.md](AGENTS.md).

## OCR for scanned PDFs and images (optional)

A scanned PDF has no text layer, and an image (`.png`, `.jpg`) is only pixels: to index them MimirSynth needs OCR. Tesseract runs in **its own container**, so the main image does not grow.
1. Start it with the `ocr` profile, alongside the others you use: `docker compose --profile ocr up -d` (add `--profile bundled` if you use the bundled FalkorDB).
2. Add `MIMIRSYNTH_OCR_URL=http://ocr:8001` to `.env` and run `docker compose up -d mimirsynth`.

Under **Knowledge**, a brain administrator sees whether OCR answers. The image reads Spanish and English; for more languages, build it with `docker build --build-arg LANGS="spa eng cat" -t mimirsynth-ocr ocr/` and point the service at it. Under Administration → Settings → Documents you choose the languages (`spa+eng`) and the maximum of pages read with OCR per document (50). The service has no authentication: do not publish its port. `update.sh` updates it along with the application.

Instead of Tesseract, a brain can read its scanned pages with the **vision model** of an LLM engine (Knowledge → *Read with the vision model*). Each page is then one call to the engine, so it is off by default. A lone image does not need the OCR service in that case, but a PDF still does, to turn its pages into images.

## HTTPS and reverse proxy
Do not expose port 8000 to the Internet without TLS. Put a reverse proxy (Caddy, Traefik, nginx…) in front, set `MIMIRSYNTH_PUBLIC_URL` to the public address and `MIMIRSYNTH_COOKIE_SECURE=true`. If you upload large files, check the proxy's request-size limit: uploads are sent in parts (64 MB by default).

PostgreSQL and FalkorDB do not publish ports outside the Compose network. Do not expose them.

## Upgrading
The release includes an update script that makes the backup, updates and checks in one go. The installer leaves it in the installation folder; otherwise download it:
```bash
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/update.sh && chmod +x update.sh
./update.sh              # latest stable release; ./update.sh --check only reports; --version 0.7.1 picks one
```
It never goes down on its own: on a version newer than the latest stable release, such as a release candidate, it says so and changes nothing. With `--version` and an older version, it stops before changing anything if that version's application does not know the database's revision (`--force` goes anyway); going back needs the database of that version too, with `./update.sh --rollback --with-db`.

**It updates itself first.** Before deciding anything, it compares itself with the `update.sh` of the release it goes to (for `--check`, the latest one). When they differ it replaces itself with that one, after checking it against the release's `SHA256SUMS`, and runs again with the same options. It never takes an older release's `update.sh` (going down with `--version` keeps the current one), and when the download or the checksum fails it carries on as it is and says so; `--no-self-update` keeps yours. Running the installer again also gives an existing installation the `update.sh` of the installer's release, checked the same way and never an older one.

It does, in this order:
1. **Downloads** the new image first, so a wrong version or no network stops everything before touching anything.
2. **Backs up** PostgreSQL, the `docstore` volume, the bundled FalkorDB (if you use `--profile bundled`) and your `docker-compose.yml` and `.env` into `./backup`. **Only one backup is kept**: the previous one is replaced once the new one has been written and checked, so backups never pile up. If the application is not answering when the update starts (after a failed update, for example), that backup does **not** replace the previous one: it goes beside it as `./backup.failed-DATE` (only the newest of those is kept), and `./backup` stays the backup of the last working instance, the one `--rollback` uses.
3. **Updates**: pins `MIMIRSYNTH_VERSION` in `.env` and recreates only the application (migrations run on start). It adopts the release's `docker-compose.yml` only if yours is the unmodified one of the version you were running; otherwise it keeps yours and tells you (`--update-compose` forces it, `--keep-compose` never touches it).
4. **Checks** that it answers with the new version and is healthy, and shows the database revision. If it does not verify, it tells you how to go back.

To go back: `./update.sh --rollback` puts back the previous `docker-compose.yml` and `.env` (and with them the previous image), keeping the failed ones as `*.rolledback`; add `--with-db` to restore the database too (anything written since the backup is lost). It only goes back to a backup of a working instance: one whose `INFO` has no version (made while the application was not answering, by an older `update.sh`) is refused before anything changes. The rollback does not restore the documents volume or FalkorDB (they are in the backup, to restore by hand if needed), and an external FalkorDB is not part of the backup at all: save it yourself. Without the script, the manual way is `docker compose pull` and `docker compose --profile bundled up -d`, after a backup.

`update.sh` runs on Linux (it needs GNU tools). On Windows, run it from WSL in the installation folder; on macOS, back up and upgrade by hand as above.

## Backups
Three things must be saved, and they must be consistent with each other:
- **PostgreSQL** (users, brains, proposals, indexes): `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql`
- **The `docstore` volume** (originals of uploaded documents, wiki page snapshots and the extracted text of every document).
- **FalkorDB** (the knowledge): the `graphdata` volume, or a dump with `redis-cli --rdb`.
Also save your `.env`.

Restoring is the reverse path: start the services, restore the database (`psql`) and put the volumes back. The episode text index can be rebuilt from the graph and the document index from the originals.

This copies the whole instance. A single brain can be exported to a package from Administration → Brain → Export; see «Export a brain» in the wiki.

## Monitoring the instance
MimirSynth alerts about the graph and the AI models itself ([NOTIFICATIONS.md](NOTIFICATIONS.md)), but **not about its own PostgreSQL**: alerts are stored in that database, so while it is down there is nowhere to keep them. Watch it from outside with any HTTP monitor (Uptime Kuma, Gatus, a `curl` in cron…) pointed at `GET /api/health`. It needs no sign-in and answers in under 3 seconds:

| Answer | Meaning |
|---|---|
| `200` `{"ok": true, "db": true, "graph": true, "graphs": 3}` | Everything is fine |
| `503` with `"db": false` | The application is alive but cannot reach PostgreSQL |
| `503` with `"graph": false` | The application is alive but FalkorDB does not answer |
| No answer or connection error | The application is down |
| `"secrets": "unreadable"` in the body (with any status) | The application works, but `MIMIRSYNTH_SESSION_SECRET` is not the one that sealed the stored secrets: see the first-start wizard above |

Alert on any status other than `200`; to tell the cases apart, check `db` and `graph` in the body. Each check waits at most 2 seconds, and the cause of a failure goes to the container log (`docker compose logs mimirsynth`), never to the response. If the monitor runs on another machine, use the public address behind the reverse proxy (`https://memory.example.com/api/health`). The container's Docker health check uses the same endpoint, so `docker ps` shows it as `unhealthy` in both cases. Being public, it also reports one configuration problem, with no detail (no kinds, no counts): `"secrets": "unreadable"` when `MIMIRSYNTH_SESSION_SECRET` cannot open the stored secrets. That field does not change the status.

To see how it is doing (recall time, jobs waiting, proposals, AI engine errors), turn on the Prometheus metrics at `/metrics` under Administration → Metrics: see «Metrics» in the wiki.

## Contributing
Building from source is for contributors: see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Common problems
- **"define POSTGRES_PASSWORD" or "define MIMIRSYNTH_SESSION_SECRET" on start:** they are missing from `.env`.
- **The installer says Docker needs `sudo`:** your user was just added to the `docker` group, which takes effect at the next login. The installer uses `sudo` meanwhile; log out and in again to run `docker` without it.
- **The installer stops at «nothing answers» or «the connection test failed» for an existing graph database:** the message names the step that failed (address, TLS, credentials, version or write permission). Check the host, the port and the firewall from that computer, and the user and password. To install anyway, answer that you want to continue, or add `--skip-graph-check`: the instance then starts with that connection, and the setup wizard's graph step waits until it passes, after you fix it in `.env` and run `docker compose up -d`.
- **Neo4j Aura: «The server has no database «neo4j»», «The server cannot find this user's default database» or `Database … not found` in the log:** leave the database empty (Aura names it after the instance id, and the test finds it) and connect with `neo4j+s://` (`--graph-tls`), not `bolt+s://`: over `bolt+s://` the driver talks to one member of the cluster, which may not hold the database. An instance installed by 0.15.0-rc.1 has `bolt+s://` in `.env`: change it to `neo4j+s://` and run `docker compose up -d`.
- **Approved proposals stay "approved":** no LLM is configured. Add an engine under Administration → LLM model.
- **Embeddings fail with a connection error, with Ollama on the same Linux host:** Ollama is only listening on `127.0.0.1`; see [Preparing Ollama](#preparing-ollama). If you use your own `docker-compose.yml`, check that the `mimirsynth` service has `extra_hosts: ["host.docker.internal:host-gateway"]`.
- **Recall returns nothing:** check the embeddings (Administration → Embeddings → Test) and that the text index is synchronised (the Ask tab shows its status).
- **No alert arrived when PostgreSQL went down:** it cannot alert about itself. Watch it with an external monitor: see [Monitoring the instance](#monitoring-the-instance).
- **I cannot find the first-start code:** it only appears while there is no administrator. Restart the container so it generates a new one.
- **The only administrator lost access:** with access to the server, set `is_admin = false` for that user in the `users` table and restart the container: the first-start wizard will reappear with a new code.
