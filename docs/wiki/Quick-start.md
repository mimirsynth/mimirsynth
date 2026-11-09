**English** · [Español](Gu%C3%ADa-r%C3%A1pida)

# Quick start

From an empty machine to a working memory with an agent connected, in about 15 minutes, for someone who knows Docker. If agents, Docker or tokens are new to you, follow [[Your first 15 minutes]] instead: the same path, with every step explained.

**You need:**
- **Docker with Compose v2.** On Linux the installer offers to install it; on macOS and Windows, install [Docker Desktop](https://docs.docker.com/desktop/) first.
- An **OpenAI-compatible** endpoint for **embeddings** and another for the **LLM** that extracts the facts. They can be local or from a cloud provider, and they are independent: local embeddings with an API LLM is a valid mix. The installer can start a bundled Ollama for the embeddings. Without an LLM the instance starts, but approved proposals are not ingested.

## 1. Install
On Linux or macOS:
```bash
curl -fsSL https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.sh | bash
```
On Windows, in PowerShell, with Docker Desktop running:
```powershell
irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1 | iex
```
It checks Docker, asks whether to start a bundled FalkorDB or use your own FalkorDB or Neo4j, and whether to start a bundled Ollama for embeddings (with `nomic-embed-text`). It writes `docker-compose.yml` and `.env` with generated secrets in `~/mimirsynth`, starts the stack, prints the address and the **first-start code** and opens the browser. Without questions: `… | bash -s -- --yes --ollama`. Every option, the checksums and the manual installation: [[Installation]].

**If the models run on your own Ollama**, download them first (`ollama pull nomic-embed-text` and an extraction model, see step 2). With Ollama on the **same Linux host**, make it listen on all interfaces so the container can reach it: see [Preparing Ollama](Installation#preparing-ollama).

## 2. Follow the setup wizard
<!-- TODO(#361): written from the scope of the setup wizard v2; confirm the step names when #361 is merged. -->
In the browser, the wizard goes through the whole setup and resumes where you left it:
1. **Administrator account**, with the first-start code.
2. **Graph database:** the connection test must pass; it offers to adopt graphs that are already there.
3. **Embeddings:** an *Ollama (local)* or *OpenAI-compatible / OpenRouter* preset; the test must pass.
4. **LLM:** the same presets. It can be skipped, with a warning on the home screen until it is configured.
5. **Decider** (optional).
6. **First brain:** name and slug.
7. **Token:** a contributor token for your agent, shown once.
8. **Connect your agent** (step 3).

Which extraction model: locally, an *instruct* model of about **14B parameters or more** (e.g. `qwen2.5:14b-instruct`, about 10 GB of memory); through an API, a small, cheap model with structured output. Models of 4B or less are enough to try the installation, not for a memory you want to keep: expect malformed or missing entities. Avoid models that "reason" by default unless you turn that off. See [[AI providers]].

> **Choose the embedding model with care.** It can be changed later (**Reindex** under Administration → Embeddings), but that recomputes every vector of every brain. The text index is created with 768 dimensions unless `MIMIRSYNTH_EMBEDDING_DIM` says otherwise before the first start: see [Embedding dimension mismatch](Troubleshooting#embedding-dimension-mismatch).

With the first brain in place, a **guided tour** of eight steps shows the navigation, the brain switcher, proposals, the graph, Ask and administration. It appears once per person; Escape or **Skip tour** closes it, and the **help menu** (the question mark at the bottom of the sidebar) plays it again.

## 3. Connect your first agent
**Administration → Brain → Connect an agent** (the wizard's last step) gives, for Claude Code, Codex, OpenCode, Hermes Agent, OpenClaw or any MCP client, what to paste, already filled in with the server, the brain and a token, and turns green on the agent's first call. By hand, with Claude Code over MCP and a **Contributor** token from **My account → API tokens**:
```bash
claude mcp add --transport http mimirsynth "http://localhost:8000/api/brains/my-brain/mcp" --header "Authorization: Bearer mst_..."
```
The agent can now read the memory (`recall`) and propose new facts (`remember`). What a contributor proposes stays in quarantine under **Proposals** until a curator or the decider approves it. Other agents and the HTTP API: [[Connect agents]]; the Claude Code options: [[Claude Code integration]].

## 4. First memory and first question
Ask the agent to remember a concrete fact, with exact names and dates ("On 12 October we migrated the production database to server db02"), or write it yourself under **Proposals → new proposal** (as administrator it is approved on submission). Approve the agent's proposal under **Proposals → To review**; ingestion runs under **Jobs**, and then the facts are in **Facts**, **Journal** and **Graph**. In **Ask**, write "where is the production database?" to see the facts, the fragments of the original texts and the context block an agent would receive ([[Ask]]).

The **Getting started** list on the home screen ticks each of these steps as it happens and suggests the next ones.

## 5. (Optional) Production, documents, users and email
- Put it behind HTTPS ([[HTTPS and reverse proxy]]) and point an external monitor at `/api/health`: the built-in alerts cannot report PostgreSQL going down ([Monitoring the instance](Installation#monitoring-the-instance)).
- Upload files or connect a folder or wiki under **Knowledge** ([[Knowledge]], [[Document memory]]).
- Invite more people under **Administration → Users** ([[Administer users]]); configure SMTP email so they receive the invitation ([[SMTP email]]).
- Require two-factor, or sign in with passkeys ([[Security and two-factor]]).

If something fails on the way: [First run](Troubleshooting#first-run).
