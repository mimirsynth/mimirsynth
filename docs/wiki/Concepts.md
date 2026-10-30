**English** · [Español](Conceptos)

# Concepts

A few ideas are worth having clear before using MimirSynth. Everything else builds on them.

## Memory with history
A normal database stores the current value and forgets the previous one. MimirSynth stores **what was known and when**. If one day you say "the database runs on server 1" and weeks later "it now runs on server 2", the first fact is not deleted: it is **invalidated** (it stops being true from a date) and the second becomes the current one. You can ask for the current state or for how it was at any moment in the past.

## The four levels of information
| Level | What it is | Where you see it |
|---|---|---|
| **Episode** | A text exactly as it was told: a note, a message, an approved proposal. It is immutable. | [[Journal]] |
| **Entity** | A "thing" the texts refer to: a person, a server, an application, a project. | [[Graph]], [[Vocabulary]] |
| **Fact** | A statement between two entities, with a start date and, if it stops being true, an end date. ("Service X runs on server Y.") | [[Facts]] |
| **Document** | A file or a wiki page: the original is kept and searched by its content, but it is not turned into facts. | [[Knowledge]] |

Facts and entities are **extracted automatically from episodes** with a language model (LLM). Documents, on the other hand, are indexed and always cited with their provenance.

## Origins
Every entity and fact remembers **where it came from**: the episodes that mention it and, through them, the type of source (text, message, document, folder, wiki…), the person or agent token that proposed it and the document it was promoted from. The [[Graph]] can draw these origins as **halos** around the nodes they back, and what is confirmed by two or more origins stands out as more robust.

## Brain
A **brain** is an isolated knowledge domain: it has its own graph, ontology, documents, members and tokens. It is used to separate, for example, a team's technical memory from each member's personal one. Nothing in one brain is visible from another, unless an administrator of a brain explicitly **lends** read access to another (**federation**): then the receiving brain's recall also searches what it is lent, marked with its origin. Lending is read-only, one way, revocable and audited. You switch brain with the selector in the side bar.

## Proposals and quarantine
What a **contributor** (or an agent with a contributor token) writes **does not go straight into the graph**: it is stored as a pending **proposal**. A **curator** (or a "decider" model, if configured) reviews it and only when approved is it ingested. That way an agent that makes a mistake does not pollute the memory. A curator's proposals are approved on submission. Before being stored, every proposal goes through the brain's **secret detector**, which masks or blocks credentials; one with a possible secret always waits for a person. See [[Proposals]].

## Ontology and vocabulary
The **ontology** is the list of entity types (Service, Person, Server…) and relation types (RunsOn, DependsOn…) the ingestor may use. Without it the model invents types and relations freely, with a lot of noise. A relation can be marked as **single-valued** (one value at a time, like "lives in"): two current facts with different values then show up as a possible **contradiction** for a curator to resolve. The **vocabulary** is the screen where you maintain all this: unify similar relations, merge duplicate entities, fix types, resolve contradictions. See [[Vocabulary]].

## Recall
**Recall** is the search an agent does before answering. It combines, without calling an LLM and in a fraction of a second: current and historical facts, fragments of the original texts and (if any) document passages, plus what other brains lend to this one. The result is a block of context ready to paste into the prompt. You try it by hand in [[Ask]]; agents use it over MCP (the `recall` tool) or the [[REST API]] ([[Connect agents]]). To check that it keeps answering well, a brain can keep **reference queries**: questions with what their recall must and must not bring, run on demand and before and after an embedding model change.

## Roles
Each person has a **role per brain** (reader, contributor, curator, administrator, owner) and may also be an **instance administrator**. See [[Roles and permissions]].

## Jobs
Everything slow (ingesting a proposal, indexing a document, rescanning a folder, finding duplicates, running reference queries) is done in the background and appears in [[Jobs]] with its progress.

## The three AI models
MimirSynth needs, at most, three OpenAI-compatible endpoints (configured in [[AI providers]]):
- **LLM:** extracts entities and facts from approved proposals. Its size decides the quality of the graph.
- **Embeddings:** turns texts into vectors to search by meaning. It can be changed later, but that recomputes every vector.
- **Decider** (optional): a closed-decision model that automatically approves what is clearly factual and within the brain's scope, and suggests type corrections. It never rejects on its own.
