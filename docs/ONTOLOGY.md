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

## Writing your own
Start from the package that is closest, then edit types, relations, map and instructions in the interface. Keep descriptions short and explicit about when **not** to use a type.
