**English** · [Español](es/ONTOLOGY.md)

# Ontology packages

The ontology of a brain tells the ingestor which **entity types** and **relation types** to extract, and which relations are allowed between which types. Without it, the model invents types freely. MimirSynth ships **standard packages** you can apply under Vocabulary → Ontology.

| Package | For | Entity types | Relation types |
|---|---|---|---|
| `general` | A mixed or personal notebook: people, organizations, places, events, documents, projects, decisions, topics | 8 | 10 |
| `infrastructure` | Infrastructure and IT operations: hosts, guests, services, networks, storage, incidents, changes, runbooks | 16 | 15 |
| `team-projects` | Team and project work: people, teams, projects, tasks, milestones, meetings, decisions, risks | 11 | 14 |
| `personal-family` | Family life: people, household, pets, places, trips, appointments, belongings, subscriptions, documents | 12 | 11 |
| `software-knowledge` | Software engineering: repositories, applications, components, libraries, APIs, environments, releases, bugs, decisions | 14 | 15 |

> The former `generic` package was replaced by `general` (the old name still works as an alias). Brains that already applied it keep their ontology.

## Design criteria
- **Few, clear types.** A type exists only if it answers a question people will ask. Everything else falls to the *last resort* (`Topic`, `RelatesTo`), which every package marks as such.
- **Aligned with existing vocabularies** so names and meaning are familiar: schema.org (Person, Organization, Place, Event, Project, SoftwareApplication), FOAF, Dublin Core, DOAP, ITIL/CMDB configuration items and Architecture Decision Records. Each package lists the standards it follows.
- **Every type says what it is, when to use it and when not to**, with examples. The model classifies using only that description.
- **Descriptions and type names are in English**, which models read best; the interface and your notes can be in any language.
- **A consistent map.** Every entity type and every relation type appears in at least one rule, and rules never reference types that do not exist (checked by the tests).

## Versions and updates
Each package has a **version**. The brain remembers which package and version it applied. When a newer version ships, Vocabulary → Ontology offers **Update**, which **adds what is missing** (types, relations, rules) and never touches what you already have or changed by hand. **Replace ontology** discards everything and applies the package as is. Entities already in the graph never change.

## Single-valued relations and contradictions
A relation type can be marked as **single-valued** (`"functional": true`; in Vocabulary → Ontology, «A single value at a time»): a subject cannot have two current targets, such as where a device is installed or whom a person reports to. If it does, Vocabulary → **Contradictions** shows them so that a curator chooses which one stays current; the others are invalidated with the date of the one kept, and this can be undone from the vocabulary history. No AI model is used: the fact with the newest validity date is suggested. If two have the same date, or any of them only has the date it was learned (which does not tell which one is more current), there is no suggestion and the person decides. Generic relations such as `RELATES_TO` are never compared and cannot be marked. A group that is not a contradiction can be hidden until a new fact joins it. Once a day every brain with a marked relation is checked and, if there are cases, an alert is raised (`conflicts.found`, information).

- **No relation is single-valued by default, not even in the packages.** Many look single-valued and are not: measured on a real graph, «located at» mixed hosts, URLs, VLANs and services. Each brain marks its own after measuring.
- **Measure before marking:** «Measure across all relations» counts, without changing anything, what share of subjects has more than one current target in each relation, from lowest to highest. The candidates are those with a low share and some cases, not those with a high share. Also from the command line, read-only: `python -m mimirsynth.conflicts <graph> [--brain-id N]`.
- Relations are compared after normalising format and aliases, and **only targets of the same entity type are compared**: «X located at a host» and «X located at a VLAN» do not contradict each other. Two targets with the same name except for case and spacing count as the same (that is a vocabulary duplicate, not a contradiction).

## Type corrector
The type corrector (Vocabulary → Type corrector) does not assume any domain: each package says, in its `retype` block, what to review and what to set aside before asking the decider.

```json
"retype": {"review_first": ["Topic", "Item"], "doubtful_rules": []}
```

- **What gets reviewed**, in this order: entities without a type, entities whose type is **not in the brain's ontology** (for example the defaults of an agent that writes to Graphiti directly), and entities of the types in `review_first` (the package's catch-all or easily confused types). Other entities are left alone. Ties are broken by id, so two scans in a row keep the same order.
- **What is set aside as doubtful** without asking the decider: a name of five words or more (in every brain) and, only if the package enables them, the technical rules `file` (path or file name), `option` (command-line option), `code` (code expression), `version` (version at the end of the name) and `problem` (words such as *bug*, *error*, *fix*). `infrastructure` enables all five; `software-knowledge` only `option`, because the others would discard its own repositories, documents, APIs and releases; the other packages none.
- **The decider's question** does not rule out errors or procedures when the ontology has a type for them (`Bug`, `Incident`, `Runbook`…).
- A brain whose ontology was written by hand, or whose package no longer exists, uses the minimum: it reviews `Object`, `Thing` and `Topic` and applies no technical rule.

The block is read from the package when the corrector runs, so changing it needs no new package version. The tests check that each block only uses types of its package and known rules, and that a package's rules do not discard the examples of its own types.

## Writing your own
Start from the package that is closest, then edit types, relations, map and instructions in the interface. Keep descriptions short and explicit about when **not** to use a type.
