<p><img src="web/public/mimirsynth-mark.svg" alt="MimirSynth" width="64" height="64" /></p>

# MimirSynth

**English** · [Español](README.es.md)

Memory for AI agents, based on the CoALA cognitive framework and built on a temporal knowledge graph ([Graphiti](https://github.com/getzep/graphiti)), with its own web UI. Facts are never overwritten: they are invalidated and their history is kept.

Status: **under active development** (0.x). It works end to end, but the API and the schema may change between versions.

## What it offers
**Memory that keeps its history**
- **Temporal facts:** every fact has validity dates; when it stops being true it is invalidated, never overwritten, so you can ask what was known at any moment.
- **Brains:** isolated knowledge domains, each with its own graph, ontology, members and tokens. A brain can **lend read access** to another (federation), with an expiry and revocable at any time.
- **Ontology packages** (general, infrastructure, team projects, personal and family, software knowledge), versioned and updatable without losing your own changes.

**What goes in is reviewed**
- **Proposal quarantine:** what agents write waits for a curator, or for an automatic decider that judges it against the brain's scope.
- **Secret detector:** credentials in proposals and documents are masked, blocked or flagged, as each brain chooses.
- **Upkeep tools:** type corrector, duplicate merging, relation aliases and **contradictions** between current facts in single-valued relations.

**Recall for agents**
- **Hybrid recall** of facts, episode text and document passages, ready to be injected into an agent's prompt, in the caller's language.
- **Built-in MCP server** (`recall` and `remember`), REST API and a [Claude Code integration](integrations/claude-code).
- **Reference queries** per brain to measure recall quality and catch regressions, for instance when changing the embedding model, which can be done from the interface.

**Documents**
- Upload files, or connect folders and wikis (Outline, Confluence, Notion) as sources; duplicates are detected and indexed only once.

**Web interface and administration**
- Explore the graph (2D, radial, tree and 3D, with halos showing where each piece of knowledge came from), ask questions, review proposals and curate the vocabulary. In **English and Spanish**.
- Own accounts with two-factor and **passkeys**, several OIDC providers with group-based roles, per-brain roles and an audit log.
- **Notifications** in the app and through Telegram, ntfy, Gotify, webhook or email; `update.sh` to back up, update and roll back in one step.

**Full user guide in the [wiki](https://github.com/MimirSynth/mimirsynth/wiki)** (also [in Spanish](https://github.com/MimirSynth/mimirsynth/wiki/Inicio)). Technical documentation: [installation](docs/INSTALL.md), [configuration](docs/CONFIGURATION.md), [connecting agents](docs/AGENTS.md), [architecture](docs/ARCHITECTURE.md), [ontology](docs/ONTOLOGY.md), [document memory](docs/DOCUMENTS.md), [federation](docs/FEDERATION.md) and [notifications](docs/NOTIFICATIONS.md).

## Quick start
You need Docker with Compose v2, an OpenAI-compatible endpoint for embeddings (e.g. Ollama with `nomic-embed-text`) and another for the extraction LLM ([which model](docs/CONFIGURATION.md#choosing-the-extraction-model)). Without both endpoints the instance starts, but there is nothing useful to see.

On a bare Linux server (Debian, Ubuntu), first install `curl` and Docker; on macOS or Windows, install Docker Desktop instead. If you run Ollama on the same Linux host, [prepare it](docs/INSTALL.md#preparing-ollama) so the container can reach it.
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker    # run docker without sudo
docker compose version    # must answer v2.x
```
Then:
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
# edit .env: set POSTGRES_PASSWORD and MIMIRSYNTH_SESSION_SECRET (openssl rand -hex 32)
docker compose --profile bundled up -d    # pulls the published image; includes FalkorDB (without the profile, point MIMIRSYNTH_FALKOR_HOST at your own)
docker compose logs mimirsynth | grep -A3 "FIRST START"    # installation wizard code
```
Open `http://localhost:8000`, enter the code and create the administrator account. Then, under **Administration**, add the AI engines (**LLM model** and **Embeddings**, with "Test" to check them) and create a brain (**Brain access → Create brain**).

### Connect your first agent
Under **My account → API tokens**, create a token for that brain with the **Contributor** role (it is shown only once). With Claude Code, over MCP:
```bash
claude mcp add --transport http mimirsynth "http://localhost:8000/api/brains/my-brain/mcp" --header "Authorization: Bearer mst_..."
```
The agent can now read the memory (`recall`) and propose new facts (`remember`). What a contributor proposes stays in quarantine, under **Proposals**, until a curator or the decider approves it. Other agents, the HTTP API and the Claude Code recall hook: [docs/AGENTS.md](docs/AGENTS.md).

In production, point an external monitor at `/api/health`: the built-in alerts cannot report PostgreSQL going down ([monitoring](docs/INSTALL.md#monitoring-the-instance)).

## Configuration
The environment only carries what is needed to start and connect (table below). Everything else — document limits, recall, job retention, AI providers, folders — is changed under **Administration** and applies without a restart; if one of those variables exists, it only acts as the default value.

### Environment variables
| Variable | Default | Description |
|---|---|---|
| `MIMIRSYNTH_FALKOR_HOST` | `localhost` | FalkorDB host |
| `MIMIRSYNTH_FALKOR_PORT` | `6379` | Port |
| `MIMIRSYNTH_DATABASE_URL` | local SQLite | Control plane (PostgreSQL in production) |
| `MIMIRSYNTH_BOOTSTRAP_GRAPHS` | _(empty)_ | Existing graphs to adopt as brains |
| `MIMIRSYNTH_AUTH_MODE` | `local` | `local` (own accounts, plus OIDC if configured). `off` for development only: no sign-in |
| `MIMIRSYNTH_STATIC_DIR` | _(empty)_ | Directory with the web build (set by the Docker image) |

## The name
Mímir is the guardian of the well of knowledge (Mímisbrunnr) in Norse mythology. According to the Ynglinga saga, Odin keeps his head and consults it for advice: an external memory that is queried. "Synth" alludes to synthetic memory and to synthesis: the system consolidates episodes into knowledge. It has no relation to Grafana Mimir or to other projects called Mimir.

## License
Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Dependencies have their own licenses; FalkorDB, for example, is *source-available* (SSPL): see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#dependencies-and-licenses).

## Contributing
Read [CONTRIBUTING.md](CONTRIBUTING.md). The project works in English, and Spanish is welcome in issues and discussions. For vulnerabilities, see [SECURITY.md](SECURITY.md).
