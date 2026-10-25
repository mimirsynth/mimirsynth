**English** · [Español](es/INSTALL.md)

# Installation

## Requirements
- Docker with Compose v2 and about 2 GB of free RAM for the application, PostgreSQL and FalkorDB.
- An **OpenAI-compatible** endpoint for **embeddings** (e.g. [Ollama](https://ollama.com) with `nomic-embed-text`) and another for the **LLM** that extracts facts. They can be local or from a cloud provider, and are configured afterwards in the interface.

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
This pulls the official image (`ghcr.io/mimirsynth/mimirsynth`, for amd64 and arm64). To pin a version, set `MIMIRSYNTH_VERSION=0.4.0` in `.env` (default: `latest`).
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
3. Create an API token for your agents: see [AGENTS.md](AGENTS.md).
4. Optional: SMTP email (invitations and password recovery), OIDC, mandatory two-factor and document folders. See [CONFIGURATION.md](CONFIGURATION.md).

## HTTPS and reverse proxy
Do not expose port 8000 to the Internet without TLS. Put a reverse proxy (Caddy, Traefik, nginx…) in front, set `MIMIRSYNTH_PUBLIC_URL` to the public address and `MIMIRSYNTH_COOKIE_SECURE=true`. If you upload large files, check the proxy's request-size limit: uploads are sent in parts (64 MB by default).

PostgreSQL and FalkorDB do not publish ports outside the Compose network. Do not expose them.

## Upgrading
```bash
docker compose pull
docker compose --profile bundled up -d
```
Database migrations are applied automatically on start. Take a backup before upgrading.

## Backups
Three things must be saved, and they must be consistent with each other:
- **PostgreSQL** (users, brains, proposals, indexes): `docker compose exec -T postgres pg_dump -U mimirsynth mimirsynth > mimirsynth.sql`
- **The `docstore` volume** (originals of uploaded documents).
- **FalkorDB** (the knowledge): the `graphdata` volume, or a dump with `redis-cli --rdb`.
Also save your `.env`.

Restoring is the reverse path: start the services, restore the database (`psql`) and put the volumes back. The episode text index can be rebuilt from the graph and the document index from the originals.

## Contributing
Building from source is for contributors: see [CONTRIBUTING.md](../CONTRIBUTING.md).

## Common problems
- **"define POSTGRES_PASSWORD" or "define MIMIRSYNTH_SESSION_SECRET" on start:** they are missing from `.env`.
- **Approved proposals stay "approved":** no LLM is configured. Add an engine under Administration → LLM model.
- **Recall returns nothing:** check the embeddings (Administration → Embeddings → Test) and that the text index is synchronised (the Ask tab shows its status).
- **I cannot find the installation code:** it only appears while there is no administrator. Restart the container so it generates a new one.
- **The only administrator lost access:** with access to the server, set `is_admin = false` for that user in the `users` table and restart the container: the first-start wizard will reappear with a new code.
