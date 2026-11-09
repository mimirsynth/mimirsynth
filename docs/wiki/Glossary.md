**English** · [Español](Glosario)

# Glossary

| Term | Meaning |
|---|---|
| **Agent** | A program that uses an AI model to work for you: Claude Code, Codex, OpenCode, Hermes Agent, OpenClaw, a bot, a script. It connects to a brain with an **API token**, recalls before it answers and proposes what it learns. See [[Connect agents]] |
| **Alias** | A rule saying "this relation reads as that other one". Applies on reading; does not change the graph. See [[Relations and aliases]] |
| **Setup wizard** | The screens that guide the first start: administrator account, graph database, AI models, first brain, token and connecting an agent. It resumes where you stopped. See [[Your first 15 minutes]] |
| **Alert** | A notification of a problem in the instance (AI model or graph not responding, failed ingestion or job…). Shown in the bell and optionally sent through channels (email, Telegram, ntfy, Gotify, webhook). It never includes memory content |
| **Brain** | An isolated knowledge domain: its graph, ontology, documents, members. See [[Concepts]] |
| **Bi-temporal** | Storing two dates per piece of data: when it happened and when it was recorded |
| **Contributor** | A role that can propose memory and upload documents, but whose contributions go through review |
| **CoALA** | A cognitive framework for agents (episodic, semantic, procedural memory…) that inspires the design |
| **Reference query** | A question saved in a brain with what its recall must bring and what it must not; running them measures whether recall gets better or worse. Under Ask → Reference queries |
| **Injected context** | The block of text recall returns, ready to put in an agent's prompt |
| **Contradiction** | Two or more current facts with the same subject and a single-valued relation, but different values. A curator decides which one stays under Content quality → Contradictions |
| **Quarantine** | The state of a proposal awaiting review, before entering the graph |
| **Curator** | A role that approves or rejects proposals and corrects facts: the person who decides what enters a brain's memory. Also the name of the daily review that turns what it finds into proposals, see [[Curator]] |
| **Decider** | A closed-decision model that triages proposals against the brain's scope and suggests types; it never rejects on its own |
| **Secret detector** | A check that looks for credentials in proposals and documents before they are stored and, depending on the brain's policy, masks them, blocks the content or only warns |
| **Docker** | The tool that runs MimirSynth and its databases in **containers**, small isolated machines, so nothing else on your computer changes. *Docker Compose* starts them together from `docker-compose.yml`. On Windows and macOS it comes with Docker Desktop |
| **Duplicate (document)** | A document whose text repeats one already indexed in the brain; it is marked and not indexed twice |
| **Embedding** | A list of numbers that represents the meaning of a text, so that texts that say similar things get similar numbers: it is how the memory is searched by meaning and not only by words. An **embedding model** computes it, and each model gives lists of a fixed length, its **dimension** (768 for `nomic-embed-text`). Changing the model recomputes the whole memory, see [[AI providers]] |
| **Entity** | A "thing" in the graph: person, server, application, project… |
| **Episode** | A text as it was told; immutable, and the source of the facts |
| **FalkorDB** | The graph database where knowledge is stored |
| **Federation** | One brain lending read access to another through a **grant** (scope: graph, documents or both; optional expiry). The receiving brain's recall includes what it is lent, marked with its origin. Read-only, one way and one hop |
| **Graphiti** | The library that extracts entities and facts from texts and maintains the temporal graph |
| **Halo** | In the [[Graph]], a translucent area in an origin's colour that wraps the nodes that origin backs; a node with several origins sits where their halos overlap |
| **Fact** | A statement between two entities, with validity dates |
| **Ingestion** | The process by which an approved proposal becomes entities and facts |
| **Installer** | The script (`install.sh`, or `install.ps1` on Windows) that checks Docker, asks where the graph lives and whether to start Ollama, writes the configuration with generated secrets and starts MimirSynth. Running it again changes nothing. See [[Installation]] |
| **Invalidate** | Mark a fact as no longer true, keeping its history |
| **Instance** | One full installation of MimirSynth, with all its brains |
| **Passkey** | A WebAuthn credential stored on your device: you sign in with fingerprint, face or PIN. It counts as two-factor and only works on the instance's domain, over HTTPS |
| **LLM** | Large language model: an AI model that reads and writes text, like the one behind your agent. Here, the one that reads each approved proposal and extracts its entities and facts; its size decides the quality of the graph. Recall does not use it, see [[AI providers]] |
| **MCP** | Model Context Protocol: the standard way to give an AI agent extra tools. Each brain has its own MCP server, and an agent connected to it gets tools such as `recall` (read the memory) and `remember` (propose something to keep). See [[Connect agents]] |
| **Neo4j** | A graph database that MimirSynth can use instead of FalkorDB, when you already run one (5.26 or later). All brains then share one database. See [[Installation]] |
| **OIDC** | A standard for signing in with an external identity provider |
| **Ollama** | A program that runs AI models on your own computer, free and without an account. The installer can start one for the embeddings (`nomic-embed-text`); from the container it is `http://ollama:11434/v1`, or `http://host.docker.internal:11434/v1` when it runs on your computer |
| **Ontology** | The list of entity and relation types (and rules between them) that guides extraction |
| **Origin** | Where an entity or a fact comes from: the type of source, the document, the person who proposed it or the agent's token. The [[Graph]] can group by any of them |
| **Proposal** | A memory contribution awaiting approval |
| **pgvector** | A PostgreSQL extension to store and search vectors |
| **Promote to memory** | Turn a passage of a document into a proposal |
| **Recall** | The search combining facts, episode texts and documents to give an agent context |
| **Single-valued relation** | A relation type marked in the ontology ("A single value at a time") that can only have one current value per subject; it is what makes contradictions detectable |
| **Shadow fill** | The first step of an embedding model change: every vector is computed with the new model without touching the ones in use; then they are swapped |
| **RRF** | "Reciprocal rank fusion": a way to mix several ranked lists |
| **Slug** | A short identifier of a brain, used in API addresses |
| **SMTP** | The email-sending protocol |
| **TOTP** | A 6-digit code that changes every 30 seconds (two-factor with an app) |
| **API token** | The credential an agent uses to reach one brain: a long secret that starts with `mst_`, shown **only once** when it is created. Its **role** says what the agent may do (a **reader** recalls; a **contributor** also proposes, and what it proposes waits in quarantine) and it can expire. One per agent, so each can be revoked alone. See [[Connect agents]] |
| **Current** | A fact that is still true (not invalidated) |
