**English** · [Español](Glosario)

# Glossary

| Term | Meaning |
|---|---|
| **Alias** | A rule saying "this relation reads as that other one". Applies on reading; does not change the graph. See [[Relations and aliases]] |
| **Alert** | A notification of a problem in the instance (AI model or graph not responding, failed ingestion or job…). Shown in the bell and optionally sent through channels (email, Telegram, ntfy, Gotify, webhook). It never includes memory content |
| **Brain** | An isolated knowledge domain: its graph, ontology, documents, members. See [[Concepts]] |
| **Bi-temporal** | Storing two dates per piece of data: when it happened and when it was recorded |
| **Contributor** | A role that can propose memory and upload documents, but whose contributions go through review |
| **CoALA** | A cognitive framework for agents (episodic, semantic, procedural memory…) that inspires the design |
| **Reference query** | A question saved in a brain with what its recall must bring and what it must not; running them measures whether recall gets better or worse. Under Ask → Reference queries |
| **Injected context** | The block of text recall returns, ready to put in an agent's prompt |
| **Contradiction** | Two or more current facts with the same subject and a single-valued relation, but different values. A curator decides which one stays under Content quality → Contradictions |
| **Quarantine** | The state of a proposal awaiting review, before entering the graph |
| **Curator** | A role that approves or rejects proposals and corrects facts |
| **Decider** | A closed-decision model that triages proposals against the brain's scope and suggests types; it never rejects on its own |
| **Secret detector** | A check that looks for credentials in proposals and documents before they are stored and, depending on the brain's policy, masks them, blocks the content or only warns |
| **Duplicate (document)** | A document whose text repeats one already indexed in the brain; it is marked and not indexed twice |
| **Embedding** | A numeric representation of a text, used to search by meaning |
| **Entity** | A "thing" in the graph: person, server, application, project… |
| **Episode** | A text as it was told; immutable, and the source of the facts |
| **FalkorDB** | The graph database where knowledge is stored |
| **Federation** | One brain lending read access to another through a **grant** (scope: graph, documents or both; optional expiry). The receiving brain's recall includes what it is lent, marked with its origin. Read-only, one way and one hop |
| **Graphiti** | The library that extracts entities and facts from texts and maintains the temporal graph |
| **Halo** | In the [[Graph]], a translucent area in an origin's colour that wraps the nodes that origin backs; a node with several origins sits where their halos overlap |
| **Fact** | A statement between two entities, with validity dates |
| **Ingestion** | The process by which an approved proposal becomes entities and facts |
| **Invalidate** | Mark a fact as no longer true, keeping its history |
| **Instance** | One full installation of MimirSynth, with all its brains |
| **Passkey** | A WebAuthn credential stored on your device: you sign in with fingerprint, face or PIN. It counts as two-factor and only works on the instance's domain, over HTTPS |
| **LLM** | Large language model; here, the one that extracts the facts |
| **MCP** | Model Context Protocol: a protocol for connecting tools to AI agents. Each brain has its own MCP server, with the tools `recall` and `remember`. See [[Connect agents]] |
| **OIDC** | A standard for signing in with an external identity provider |
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
| **API token** | A credential for an agent to access a brain |
| **Current** | A fact that is still true (not invalidated) |
