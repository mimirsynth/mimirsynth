**English** · [Español](Ontolog%C3%ADa)

# Ontology

A brain's **ontology** defines which **entity types** and **relation types** the ingestor may extract when writing, and between which types each relation is allowed. **Without an ontology, the model invents types and relations freely**, and the graph fills with variants and noise. With it, extraction is much more consistent. It also tells the [[Type corrector]] what to review, the decider what the brain is about (see [[Proposals]]) and [[Contradictions]] which relations are single-valued.

> Ontology changes **guide future ingestions** and do not modify what is already in the graph. To fix what is stored, use [[Entity types]], [[Relations and aliases]] and the [[Type corrector]].

The **Ontology** tab of [[Vocabulary]]. Everyone can read it; only brain administrators edit it.

## What it contains
1. **Entity types** (edited in their own tab, [[Entity types]]).
2. **Relation types:** *PascalCase* name without spaces (`RunsOn`), a **description** of when it is used and, optionally, the **A single value at a time** mark (see below).
3. **Map rules:** which relations are allowed between which pairs of types. For example, between *Service* and *Host*, `RunsOn` is allowed. A rule has a **Source**, a **Target** and the list of **allowed relations** between them.
4. **Extraction instructions:** free text (up to 4,000 characters) given to the LLM: what is important, how to classify, what to avoid.

## Standard packages
A **package** is a ready-made starting ontology. Every type says what it is, when to use it and when not to, with examples; every package has extraction instructions and is aligned with known vocabularies (schema.org, FOAF, Dublin Core, DOAP, ITIL/CMDB…). Type names and descriptions are in English, which models read best; your notes can be in any language.

| Package | For | Entity types | Relation types |
|---|---|---|---|
| `general` | A mixed or personal notebook: people, organizations, places, events, documents, projects, decisions, topics | 8 | 10 |
| `infrastructure` | Infrastructure and IT operations: hosts, guests, services, networks, storage, incidents, changes, runbooks | 16 | 15 |
| `team-projects` | Team and project work: people, teams, projects, tasks, milestones, meetings, decisions, risks | 11 | 14 |
| `personal-family` | Family life: people, household, pets, places, trips, appointments, belongings, subscriptions, documents | 12 | 11 |
| `software-knowledge` | Software engineering: repositories, applications, components, libraries, APIs, environments, releases, bugs, decisions | 14 | 15 |

The former `generic` package is now `general` (the old name still works). Brains that applied it keep their ontology. When you choose a package under **Apply package**, its description, size, version and the standards it follows (**Based on:**) are shown. Details: [`docs/ONTOLOGY.md`](https://github.com/MimirSynth/mimirsynth/blob/main/docs/ONTOLOGY.md).

## Applying a package
- **Brain without an ontology:** choose a package and press **Apply**.
- **Brain with an ontology:** you get two options:
  - **Add what is missing:** adds the package's types, relations and rules that you do not have, and touches nothing you already have.
  - **Replace ontology:** asks for confirmation and then **overwrites** the current types, relations, map and instructions with the package's, **including changes made by hand**. Use it at the start, not over an ontology you have worked on.

Entities already in the graph never change.

### Package updates
Packages have a **version**, and the brain remembers which package and version it applied. When a newer version ships, the tab says there is a new version of the package, with the installed and available versions and an **Update** button, which **adds what is missing** (types, relations, rules) without touching anything you have or changed by hand.

## Editing by hand
- **Relations:** add, edit the description or the single-value mark, or remove. Removing a relation also removes it from the map rules that use it (the notice tells you how many).
- **Map rules:** add or edit (choose source, target and tick the allowed relations) or remove.
- **Instructions:** edit the guidance text.

After each change a notice offers **Undo**.

## Single-valued relations
Tick **A single value at a time** on a relation type only if a subject **cannot have two current targets at once**: where a physical device is installed, whom a person reports to. Marked relations carry the **single value** tag, and two current targets of the same type become a possible contradiction in [[Contradictions]].

**No relation is marked by default, not even in the packages**, because many relations look single-valued and are not. Measure first with **Measure across all relations** in [[Contradictions]] and mark only the relations with a low share of subjects with several targets.

## Shelf life and facts to review
Some data goes stale without anyone contradicting it: an IP, a version, who runs a service. A relation type can have a **shelf life** in days (in the relation's edit dialog, **Shelf life (days)**); none has one by default, not even in the packages, so nothing changes until a brain sets one.

A current fact of that relation whose last date (its last confirmation or, failing that, its validity date) is older than its shelf life is **to review**:
- In the recall it weighs less (`recall_stale_weight`, 0.6 by default) and is marked «not confirmed since …», also in the context the agent reads.
- It is listed in Vocabulary → **To review**, for curators: **Confirm** renews its date (stored in PostgreSQL; the graph is not touched) and **Invalidate** works as from Facts. Confirmations are audited (`fact.confirm`).
- Once a day, the `facts.stale` notification counts them per brain, without any text.

A fact without a validity date (imported from another system, for example) never goes stale by date: there is nothing to measure from. Lent facts are not marked here: the shelf life is the lending brain's. A generic relation such as `RELATES_TO` cannot have a shelf life.

## Writing good descriptions
The LLM decides by looking at the descriptions. Good ones:
- Say **when yes** and **when no**, with real examples.
- Resolve your domain's typical confusions ("physical servers are *Host*, never *Location*").
- Are specific and short.

## What happens if an extraction goes outside the ontology
Ingestion does not block it: the **proposal report** ([[Proposals]]) says how many entities ended up *untyped* and which types fell outside. That is how you see what the ontology is missing. The [[Type corrector]] reviews those entities later.
