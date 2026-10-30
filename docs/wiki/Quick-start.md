**English** · [Español](Gu%C3%ADa-r%C3%A1pida)

# Quick start

From an empty machine to a working memory with an agent connected, in about 15 minutes. The details of each step are in the linked pages.

**You need:**
- **Docker with Compose v2** (and `curl`).
- An **OpenAI-compatible** endpoint for **embeddings** (e.g. [Ollama](https://ollama.com) with `nomic-embed-text`) and another for the **LLM** that extracts the facts. They can be local or from a cloud provider, and they are independent: local embeddings with an API LLM is a valid mix. Without both the instance starts, but there is nothing useful to see: proposals are not ingested and recall returns nothing.

## 1. Prepare the machine
On a bare Linux server (Debian, Ubuntu), install `curl` and Docker; on macOS or Windows, install [Docker Desktop](https://docs.docker.com/desktop/) instead.
```bash
sudo apt-get update && sudo apt-get install -y curl openssl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker    # run docker without sudo
docker compose version                               # must answer v2.x
```
**If the models run on Ollama**, download them first (`ollama pull nomic-embed-text` and an extraction model, see step 4). With Ollama on the **same Linux host**, make it listen on all interfaces so the container can reach it: see [Preparing Ollama](Installation#preparing-ollama).

## 2. Start the application
```bash
mkdir mimirsynth && cd mimirsynth
curl -fsSLO https://github.com/MimirSynth/mimirsynth/releases/latest/download/docker-compose.yml
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/env.example -o .env
# edit .env: set POSTGRES_PASSWORD and MIMIRSYNTH_SESSION_SECRET (openssl rand -hex 32)
docker compose --profile bundled up -d
```
Open `http://localhost:8000`. More detail in [[Installation]].

## 3. Create your administrator account
The first time, the screen asks for an **installation code** that appears in the server log:
```bash
docker compose logs mimirsynth | grep -A3 "FIRST START"
```
Paste it and enter your name, email and a password (at least 12 characters; the form ticks each rule as you type). You are in as instance administrator, and you land on **First steps**: a **Create your first brain** button and a short checklist (AI models, API token, connecting an agent) with a link to each screen.

## 4. Configure the AI models
Under **Administration → LLM model** add an engine: endpoint (base URL), key and model. Press **Test** and mark it as **Default**. Repeat under **Embeddings** (e.g. `nomic-embed-text`, 768 dimensions). See [[AI providers]].

Which extraction model: locally, an *instruct* model of about **14B parameters or more** (e.g. `qwen2.5:14b-instruct`, about 10 GB of memory); through an API, a small, cheap model with structured output. Models of 4B or less are enough to try the installation, not for a memory you want to keep: expect malformed or missing entities. Avoid models that "reason" by default unless you turn that off.

> **Choose the embedding model with care.** It can be changed later (**Reindex** under Administration → Embeddings), but that recomputes every vector of every brain.

## 5. Create a brain
Press **Create your first brain** (or **Administration → Brain access → Create brain**), give it a name and, if you like, a description, and apply an **ontology package** under *Vocabulary → Ontology*. See [[Brains and members]].

## 6. Add your first memory
Go to **Proposals → new proposal**: write a title and a text with a concrete fact, with exact names and dates ("On 12 October we migrated the production database to server db02"). As administrator it is approved on submission and ingestion starts (you will see the progress under **Jobs**). When it finishes, look at **Facts**, **Journal** and **Graph**.

## 7. Ask it something
In **Ask** write "where is the production database?". You will see the facts, the fragments of the original texts, any document passages and the context block an agent would receive. See [[Ask]].

## 8. Connect your first agent
Under **My account → API tokens**, create a token for that brain with the **Contributor** role (it is shown only once). With Claude Code, over MCP:
```bash
claude mcp add --transport http mimirsynth "http://localhost:8000/api/brains/my-brain/mcp" --header "Authorization: Bearer mst_..."
```
The agent can now read the memory (`recall`) and propose new facts (`remember`). What a contributor proposes stays in quarantine under **Proposals** until a curator or the decider approves it. Other agents and the HTTP API: [[Connect agents]]; the Claude Code options: [[Claude Code integration]].

## 9. (Optional) Production, documents, users and email
- Put it behind HTTPS ([[HTTPS and reverse proxy]]) and point an external monitor at `/api/health`: the built-in alerts cannot report PostgreSQL going down ([Monitoring the instance](Installation#monitoring-the-instance)).
- Upload files or connect a folder or wiki under **Knowledge** ([[Knowledge]], [[Document memory]]).
- Invite more people under **Administration → Users** ([[Administer users]]); configure SMTP email so they receive the invitation ([[SMTP email]]).
- Require two-factor, or sign in with passkeys ([[Security and two-factor]]).
